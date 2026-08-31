# MD_WAR_TR — 일일 안보 브리핑 봇

매일 아침(KST 07:00) GitHub Actions가 자동 실행되어 브리핑 한 호를 생성하고
Firebase Hosting 웹사이트 + RSS 피드로 발행한다.

5부 구성:

1. **최신 기사** — 수집된 기사 중 중요도순 헤드라인
2. **현대전 추적** — 전선·지역별 분석 (우크라이나 / 가자·레바논 / 수단 / 미얀마 / 사헬 …)
3. **일일 전쟁사** — 오늘 날짜의 세계 군사사 사건 1건
4. **6·25 전쟁사** — 오늘 월·일에 해당하는 1950~1953년 6·25 전쟁 사건
5. **북한 관련** — 미사일·핵·북러 협력·제재 등 북한 동향

한국어 서술 + 영어 원문 핵심 인용 병기.

## 파이프라인

```
collect.py    수집  → data/raw/YYYY-MM-DD.json   (위키 On-this-day + 뉴스 RSS + ISW)
generate.py   생성  → content/YYYY-MM-DD.md      (Claude API, 없으면 초안 모드)
build_site.py 빌드  → site/                       (정적 HTML + rss.xml + /latest)
```

`content/`, `data/raw/` 는 Actions 가 매일 레포에 커밋백한다.
`site/` 는 빌드 산출물이며 Firebase 로 배포된다(레포에 커밋 안 함).

- 레포: https://github.com/dev-genius/MD_WAR_TR
- 사이트: https://mh-track-843d0.web.app
- 항상 최신 호: https://mh-track-843d0.web.app/latest  ← 공유용 고정 링크

## 로컬 실행

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # ANTHROPIC_API_KEY (없으면 초안 모드)

python scripts/collect.py && python scripts/generate.py && python scripts/build_site.py
python -m http.server -d site 8000
```

## 배포 구성 (하이브리드)

실행은 GitHub Actions(무료), 웹 호스팅은 Firebase Hosting(Spark 무료 요금제).

등록된 GitHub Secret:
- `ANTHROPIC_API_KEY` — Claude API 키
- `FIREBASE_SERVICE_ACCOUNT` — Firebase 서비스 계정 JSON 전체

`.firebaserc` = `mh-track-843d0` · cron: `.github/workflows/daily.yml` (UTC 22:00 = KST 07:00)
수동 실행: 레포 Actions 탭 → daily-briefing → Run workflow

## 설정 파일

- `config/feeds.yaml` — 현대전/북한 뉴스 소스 (구글뉴스 검색어 + RSS)
- `config/site.yaml` — 사이트 제목/설명/타임존

## 저작권 원칙

뉴스 원문은 재게시하지 않는다. 코드와 프롬프트가 인용을 15단어 이내로 제한하고
항상 출처 매체명·링크를 함께 표기한다. 수집 대상은 공개 RSS 로 한정한다.
