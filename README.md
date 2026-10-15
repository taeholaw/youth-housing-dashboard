# 서울 청년안심주택 사업 현황 대시보드

서울시 「청년안심주택(구 역세권 청년주택) 사업추진현황」 원자료를 매일 자동으로 확인해, 사업장별 공급 파이프라인 · 장기 미준공 리스크 · 청약 경쟁률 · 정책 이슈를 보여 주는 정적 웹사이트입니다.

## 구성

| 경로 | 내용 |
|---|---|
| `scripts/scrape_projects.py` | 서울시 게시글에서 최신 PDF를 찾아 파싱 → `data/projects.json`, `data/meta.json` |
| `scripts/build_site.py` | `site/` + `data/` → 배포용 `_site/` |
| `site/page.html` | 화면 코드 (claude.ai 대시보드와 공용) |
| `site/dash-shim.js` | 웹사이트용 경량 런타임 |
| `data/timeline.json` · `competition.json` · `permits_reported.json` | 직접 관리하는 정책 · 경쟁률 · 보도 수치 (출처 URL 포함) |
| `.github/workflows/update.yml` | 매일 08:00 KST 수집 → 변경 시 커밋 → GitHub Pages 배포 |

## 자동 갱신 방식

1. 매일 08:00(KST) GitHub Actions가 서울시 게시글의 PDF를 확인합니다.
2. PDF가 바뀌었으면(sha256 비교) 표를 다시 읽고 검산합니다: 연번 연속, 합계 = 공공 + 민간 + 분양, 단계 값, 최소 100행.
3. 검산을 통과하고 사업장 데이터가 실제로 바뀐 날에만 `data/`를 커밋합니다. 사이트는 매일 다시 배포되어 '원자료 최종 확인' 시각이 갱신됩니다. 실패하면 기존 데이터를 그대로 두고 Actions에 오류를 남깁니다(`data/meta.json`의 `last_error`).

## 처음 배포

1. 이 폴더를 GitHub 저장소로 올립니다.
2. 저장소 **Settings → Pages → Build and deployment → Source: GitHub Actions**를 선택합니다.
3. **Actions → 원자료 갱신 및 배포 → Run workflow**로 첫 배포를 실행합니다.
4. 주소: `https://<계정>.github.io/<저장소>/` (Settings → Pages에서 사용자 도메인 연결 가능)

## 수동 항목 갱신

정책 이슈나 경쟁률이 새로 나오면 `data/timeline.json`, `data/competition.json`에 행을 추가하고 커밋하면 됩니다. 각 행에는 `source`와 `url`을 꼭 적습니다.

## 로컬 실행

```bash
pip install -r requirements.txt
python scripts/scrape_projects.py
python scripts/build_site.py
python -m http.server -d _site 8000
```

공개 자료를 자동으로 모아 정리한 참고용 자료이며, 투자 · 여신 판단의 근거가 아닙니다. 정확한 내용은 서울시 원문에서 확인하십시오.
