#!/usr/bin/env python3
"""서울시 청년안심주택 사업추진현황 PDF를 내려받아 data/projects.json 으로 변환한다.

동작
  1. 서울시 주택분야 누리집 게시글에서 '사업추진현황' PDF 링크를 찾는다.
  2. PDF를 받아 머리글 위치로 열 경계를 잡고, 행을 열에 배정한다.
  3. 검산(합계 = 공공 + 민간 + 분양, 연번 연속, 최소 행 수)을 통과할 때만 저장한다.
  4. 같은 PDF(sha256 동일)면 아무것도 바꾸지 않는다.

종료 코드: 0 = 갱신 또는 변경 없음, 1 = 실패(기존 데이터는 그대로 유지)
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin

import pdfplumber
import requests

PAGE_URL = "https://news.seoul.go.kr/citybuild/archives/502414"
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
KST = timezone(timedelta(hours=9))
UA = {"User-Agent": "Mozilla/5.0 (youth-housing-dashboard; public data collector)"}

# 머리글 글자 → 열 이름 (왼쪽부터)
HEADERS = [
    ("연번", "no"), ("자치구", "gu"), ("위치", "addr"), ("지하철역", "stn"),
    ("면적", "area"), ("층수", "fl"), ("주차", "park"), ("합계", "tot"),
    ("공공", "pub"), ("민간", "pri"), ("분양", "sale"), ("추진단계", "stage"),
    ("인허가일", "permit"), ("착공신고일", "start"), ("사용승인일", "apr"), ("입주일", "move"),
]
INT_COLS = ["no", "park", "tot", "pub", "pri", "sale"]
DATE_COLS = ["permit", "start", "apr", "move"]
STAGES = {"입주", "준공", "착공신고", "인가완료"}
MIN_ROWS = 100


def log(msg: str) -> None:
    print(f"[scrape] {msg}", flush=True)


def find_pdf() -> tuple[str, str]:
    html = requests.get(PAGE_URL, headers=UA, timeout=30).text
    links = re.findall(r'<a[^>]+href="([^"]+\.pdf)"[^>]*>(.*?)</a>', html, flags=re.S | re.I)
    for href, text in links:
        title = re.sub(r"<[^>]+>", "", text).strip()
        if "사업추진현황" in title:
            return urljoin(PAGE_URL, href), title
    raise RuntimeError("게시글에서 '사업추진현황' PDF 링크를 찾지 못했습니다")


def column_bounds(words: list[dict]) -> list[tuple[str, float, float]]:
    centers = {}
    for label, key in HEADERS:
        hits = [w for w in words if w["text"].startswith(label)]
        if label == "위치":
            hits = [w for w in hits if w["text"] == "위치"]
        if not hits:
            raise RuntimeError(f"머리글 '{label}'을 찾지 못했습니다")
        w = min(hits, key=lambda w: w["top"])
        centers[key] = w["x0"]
    keys = [k for _, k in HEADERS]
    xs = [centers[k] for k in keys]
    if xs != sorted(xs):
        raise RuntimeError("머리글 순서가 예상과 다릅니다")
    # 경계 = 다음 열 머리글의 왼쪽 끝 바로 앞. 셀 단어는 가운데 좌표로 배정한다.
    # (중간값 경계를 쓰면 긴 주소의 끝 단어가 다음 열로 넘어간다)
    bounds = []
    for i, k in enumerate(keys):
        lo = -1e9 if i == 0 else xs[i] - 2
        hi = 1e9 if i == len(keys) - 1 else xs[i + 1] - 2
        bounds.append((k, lo, hi))
    return bounds


def norm_date(s: str) -> str:
    s = s.strip()
    if not s:
        return ""
    m = re.fullmatch(r"(\d{4})[-.](\d{1,2})[-.](\d{1,2})", s)
    if not m:
        raise RuntimeError(f"날짜 형식을 읽지 못했습니다: {s!r}")
    return f"{m[1]}-{int(m[2]):02d}-{int(m[3]):02d}"


def parse(pdf_bytes: bytes) -> list[dict]:
    rows: list[dict] = []
    bounds = None
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            words = page.extract_words(keep_blank_chars=False, use_text_flow=False, x_tolerance=1.5)
            try:
                bounds = column_bounds(words)
            except RuntimeError:
                if bounds is None:
                    raise
            lines: dict[float, list[dict]] = {}
            for w in words:
                key = next((t for t in lines if abs(t - w["top"]) <= 3), w["top"])
                lines.setdefault(key, []).append(w)
            for top in sorted(lines):
                cells: dict[str, list[str]] = {}
                for w in sorted(lines[top], key=lambda w: w["x0"]):
                    cx = (w["x0"] + w["x1"]) / 2
                    col = next(k for k, lo, hi in bounds if lo <= cx < hi)
                    cells.setdefault(col, []).append(w["text"])
                no = " ".join(cells.get("no", []))
                if not re.fullmatch(r"\d+", no):
                    continue
                r = {k: " ".join(cells.get(k, [])).strip() for _, k in HEADERS}
                rows.append(r)
    out = []
    for r in rows:
        rec = {}
        for k, v in r.items():
            if k in INT_COLS:
                v = v.replace(",", "")
                rec[k] = int(v) if v else 0
            elif k == "area":
                rec[k] = float(v.replace(",", "")) if v else None
            elif k in DATE_COLS:
                rec[k] = norm_date(v)
            else:
                rec[k] = v
        out.append(rec)
    return out


def validate(rows: list[dict]) -> None:
    if len(rows) < MIN_ROWS:
        raise RuntimeError(f"행 수가 너무 적습니다: {len(rows)}")
    nos = [r["no"] for r in rows]
    if nos != list(range(1, len(rows) + 1)):
        raise RuntimeError("연번이 1부터 연속되지 않습니다")
    for r in rows:
        if r["tot"] != r["pub"] + r["pri"] + r["sale"]:
            raise RuntimeError(f"연번 {r['no']}: 합계 ≠ 공공+민간+분양")
        if r["stage"] not in STAGES:
            raise RuntimeError(f"연번 {r['no']}: 알 수 없는 단계 {r['stage']!r}")
        if not r["gu"].endswith("구"):
            raise RuntimeError(f"연번 {r['no']}: 자치구 열을 읽지 못했습니다 {r['gu']!r}")


def main() -> int:
    meta_path = DATA / "meta.json"
    meta = json.loads(meta_path.read_text("utf-8")) if meta_path.exists() else {}
    now = datetime.now(KST).isoformat(timespec="seconds")
    try:
        url, title = find_pdf()
        log(f"PDF: {title} — {url}")
        pdf = requests.get(url, headers=UA, timeout=60)
        pdf.raise_for_status()
        sha = hashlib.sha256(pdf.content).hexdigest()
        meta["checked_at"] = now
        if sha == meta.get("pdf_sha256") and (DATA / "projects.json").exists():
            log("변경 없음 (같은 PDF)")
            meta["last_result"] = "unchanged"
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", "utf-8")
            return 0
        rows = parse(pdf.content)
        validate(rows)
        m = re.search(r"(\d{4})\.\s*(\d{1,2})월말", title)
        as_of = f"{m[1]}-{int(m[2]):02d}" if m else ""
        (DATA / "projects.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n", "utf-8")
        meta.update({
            "source_page": PAGE_URL, "pdf_url": url, "pdf_title": title, "pdf_sha256": sha,
            "as_of_month": as_of, "updated_at": now, "rows": len(rows),
            "units": sum(r["tot"] for r in rows), "last_result": "updated",
        })
        meta.pop("last_error", None)
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", "utf-8")
        log(f"갱신: {len(rows)}개 사업장, {meta['units']:,}세대, 기준 {as_of}")
        return 0
    except Exception as e:  # 실패해도 기존 데이터는 건드리지 않는다
        meta.update({"checked_at": now, "last_result": "failed", "last_error": str(e)})
        DATA.mkdir(exist_ok=True)
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", "utf-8")
        log(f"실패: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
