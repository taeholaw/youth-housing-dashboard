#!/usr/bin/env python3
"""site/ 와 data/ 를 합쳐 배포용 _site/ 폴더를 만든다."""
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "_site"


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "data").mkdir(parents=True)
    page = (ROOT / "site" / "page.html").read_text("utf-8")
    shim = (ROOT / "site" / "dash-shim.js").read_text("utf-8")
    build = hashlib.sha1((page + shim).encode()).hexdigest()[:8]
    html = (ROOT / "site" / "template.html").read_text("utf-8")
    html = html.replace("{{PAGE}}", page).replace("{{BUILD}}", build)
    (OUT / "index.html").write_text(html, "utf-8")
    shutil.copy(ROOT / "site" / "dash-shim.js", OUT / "dash-shim.js")
    for f in (ROOT / "data").glob("*.json"):
        json.loads(f.read_text("utf-8"))  # 깨진 JSON이면 배포 중단
        shutil.copy(f, OUT / "data" / f.name)
    (OUT / ".nojekyll").write_text("")
    print(f"built _site/ (build {build})")


if __name__ == "__main__":
    main()
