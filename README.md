# MD_WAR_TR — 일일 전쟁 브리핑 봇

매일 아침 GitHub Actions가 자동으로 실행되어 두 파트의 브리핑을 생성하고,
GitHub Pages 웹사이트 + RSS 피드로 발행합니다.

1. **[일일전쟁사]** — 오늘 날짜에 있었던 군사사(史) 사건을 AI가 1개 선정해 해설
2. **[6·25 전쟁 그날]** — 오늘 날짜(월·일)에 해당하는 1950~1953년 6·25 전쟁 사건
3. **[현대전쟁 추적]** — 뉴스 RSS · ISW 일일 리포트 · 공개 텔레그램 채널을 수집해 요약

한국어 요약 + 영어 원문(핵심 인용·용어) 병기.

## 파이프라인

```
collect.py   수집   → data/raw/YYYY-MM-DD.json
generate.py  생성   → content/YYYY-MM-DD.md   (Claude API, 없으면 초안 모드)
build_site.py 빌드  → site/  (HTML + rss.xml)
```

`content/`와 `data/raw/`는 Actions가 매일 레포에 커밋백합니다.
`site/`는 빌드 산출물이며 Pages로 배포됩니다(레포에 커밋 안 함).

## 로컬 실행

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # ANTHROPIC_API_KEY 채우기 (없어도 초안 모드로 동작)

python scripts/collect.py
python scripts/generate.py
python scripts/build_site.py
python -m http.server -d site 8000   # http://localhost:8000
```

## 배포 (요약)

1. 이 폴더를 새 **public** GitHub 레포로 push
2. 레포 Settings → Secrets → Actions 에 `ANTHROPIC_API_KEY` 추가
3. 레포 Settings → Pages → Source: **GitHub Actions**
4. `.github/workflows/daily.yml` 의 cron 시간 확인 (기본 UTC 22:00 = KST 07:00)

레포: https://github.com/dev-genius/MD_WAR_TR
사이트: https://dev-genius.github.io/MD_WAR_TR

## 설정 파일

- `config/feeds.yaml` — 뉴스 RSS 피드 / 구글뉴스 검색어
- `config/telegram_channels.yaml` — 수집할 공개 텔레그램 채널
- `config/site.yaml` — 사이트 제목/설명/도메인

## 저작권 원칙

뉴스 원문은 재게시하지 않습니다. 코드가 인용을 문장 단위로 짧게 제한하고
항상 출처 링크를 함께 표기합니다. 수집 대상은 공개 RSS와 공개 채널로 한정합니다.
