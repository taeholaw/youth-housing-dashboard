#!/usr/bin/env python3
"""사업장 위치(위도·경도)를 만든다 → data/locations.json

원자료에는 좌표가 없다. 무료 지오코더(OpenStreetMap Nominatim)는 지번 단위까지 잡지 못하므로
  1순위: 사업장이 속한 지하철역 좌표 (청년안심주택은 역세권 사업이라 오차가 작다)
  2순위: 역 이름이 없거나 찾지 못하면 법정동 중심점
을 쓴다. 역 좌표가 법정동 중심점에서 3km 넘게 떨어져 있으면 동명이역을 잘못 잡은 것으로 보고 법정동 중심점을 쓴다.
같은 역을 쓰는 사업장은 겹치지 않도록 역 둘레 약 130m 원 위에 나눠 놓는다.

조회 결과는 data/geo_cache.json 에 쌓아 두므로, 다음 실행부터는 새 역·새 동만 조회한다.
Nominatim 이용 정책(초당 1회, 식별 가능한 User-Agent)을 지킨다.
"""
from __future__ import annotations

import json
import math
import re
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CACHE = DATA / "geo_cache.json"
UA = {"User-Agent": "youth-housing-dashboard/1.0 (https://github.com/taeholaw/youth-housing-dashboard)"}
SEOUL_BOX = "126.76,37.71,127.19,37.42"  # lon1,lat1,lon2,lat2
MAX_GAP_KM = 3.0
_last = 0.0


def nominatim(q: str) -> list[dict]:
    global _last
    wait = 1.1 - (time.time() - _last)
    if wait > 0:
        time.sleep(wait)
    r = requests.get("https://nominatim.openstreetmap.org/search", headers=UA, timeout=30,
                     params={"q": q, "format": "jsonv2", "limit": 8, "countrycodes": "kr",
                             "viewbox": SEOUL_BOX, "bounded": 1, "accept-language": "ko"})
    _last = time.time()
    r.raise_for_status()
    return r.json()


def save(cache: dict) -> None:
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True) + "\n", "utf-8")


def km(a, b) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def station(name: str, cache: dict):
    key = "stn:" + name
    if key in cache:
        return cache[key]
    base = re.sub(r"역$", "", name)
    hit = None
    for q in (name, base + "역", base):
        for r in nominatim(q):
            cls, typ = r.get("category") or r.get("class"), r.get("type")
            nm = (r.get("name") or "")
            if (cls in ("railway", "public_transport") or typ in ("station", "subway_entrance")) and base in nm:
                hit = {"lat": float(r["lat"]), "lon": float(r["lon"]), "name": nm, "osm": f"{r['osm_type']}/{r['osm_id']}"}
                break
        if hit:
            break
    cache[key] = hit
    save(cache)
    return hit


def dong(gu: str, dong_name: str, cache: dict):
    key = f"dong:{gu} {dong_name}"
    if key in cache:
        return cache[key]
    hit = None
    for r in nominatim(f"서울특별시 {gu} {dong_name}"):
        if (r.get("category") or r.get("class")) in ("place", "boundary"):
            hit = {"lat": float(r["lat"]), "lon": float(r["lon"]), "name": r.get("name"), "osm": f"{r['osm_type']}/{r['osm_id']}"}
            break
    cache[key] = hit
    save(cache)
    return hit


def main() -> int:
    projects = json.loads((DATA / "projects.json").read_text("utf-8"))
    cache = json.loads(CACHE.read_text("utf-8")) if CACHE.exists() else {}
    out, misses = [], []
    try:
        for p in projects:
            parts = p["addr"].split()
            dong_name = re.sub(r"\d.*$", "", parts[1]) if len(parts) > 1 and not parts[1][0].isdigit() else ""
            dong_name = parts[1] if re.fullmatch(r".+\d가", parts[1] if len(parts) > 1 else "") else dong_name
            d = dong(p["gu"], dong_name, cache) if dong_name else None
            stn = p["stn"] if p["stn"].endswith("역") and "(" not in p["stn"] else ""
            s = station(stn, cache) if stn else None
            if s and d and km((s["lat"], s["lon"]), (d["lat"], d["lon"])) > MAX_GAP_KM:
                s = None
            if s:
                out.append({"no": p["no"], "lat": s["lat"], "lon": s["lon"], "basis": "역", "ref": s["name"]})
            elif d:
                out.append({"no": p["no"], "lat": d["lat"], "lon": d["lon"], "basis": "법정동", "ref": f"{p['gu']} {dong_name}"})
            else:
                misses.append(p["no"])
    finally:
        save(cache)

    # 같은 좌표를 쓰는 사업장은 둘레에 나눠 놓는다(약 130m)
    groups: dict[tuple, list] = {}
    for o in out:
        groups.setdefault((round(o["lat"], 5), round(o["lon"], 5)), []).append(o)
    for g in groups.values():
        if len(g) < 2:
            continue
        g.sort(key=lambda o: o["no"])
        for i, o in enumerate(g):
            a = 2 * math.pi * i / len(g)
            o["lat"] += 0.00117 * math.sin(a)
            o["lon"] += 0.00147 * math.cos(a)
    for o in out:
        o["lat"], o["lon"] = round(o["lat"], 6), round(o["lon"], 6)
    out.sort(key=lambda o: o["no"])
    (DATA / "locations.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", "utf-8")
    by = {}
    for o in out:
        by[o["basis"]] = by.get(o["basis"], 0) + 1
    print(f"[geocode] {len(out)}/{len(projects)}곳 위치 확정 {by}" + (f", 미확정 연번 {misses}" if misses else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
