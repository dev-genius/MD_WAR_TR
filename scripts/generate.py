"""생성 단계.

data/raw/YYYY-MM-DD.json 을 읽어 content/YYYY-MM-DD.md 를 만든다.

ANTHROPIC_API_KEY 가 있으면 Claude 로 편집·요약한다.
없으면 "초안 모드": 수집 원자료를 그대로 구조화해 파일을 만든다(파이프라인 검증용).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys

import common

SYSTEM = """당신은 국제 안보·군사 분야 한국어 브리핑을 만드는 애널리스트다.
독자는 정세를 빠르게 파악하려는 전문 독자다. 문장은 간결하고 건조하게,
분석적 어조로 쓴다. 감탄사·과장·수사는 배제한다.

원칙:
- 사실 기반. 검증되지 않은 전과(戰果)·피해 주장은 "~측 주장" 또는 "미확인"으로 명시한다.
- 상충하는 보도는 함께 제시하고 판단 근거를 밝힌다.
- 역사 서술은 확실한 사실만 쓰고, 불확실한 부분은 그렇다고 밝힌다.
- 저작권: 기사 원문을 재게시하지 않는다. 15단어 이내의 짧은 직접 인용만 허용하고
  항상 출처 매체명과 링크를 붙인다.
- 고유명사·전문용어는 한국어(원어) 형태로 병기한다.
- 내부 데이터 필드명이나 JSON 키를 본문에 노출하지 않는다."""

PROMPT = """오늘 날짜: {date}

아래 수집 데이터로 브리핑 한 호를 작성한다. 지정된 마크다운 구조를 정확히 따르고,
그 외 서두·맺음말·메타설명은 넣지 않는다. 섹션 제목은 아래 표기를 그대로 쓴다.

## 최신 기사

- news 에서 중요도 높은 기사 8~12건을 골라 시간순으로 정렬한다. 중복 기사는 하나로 합친다.
- 각 항목은 한 줄: 한국어로 압축한 헤드라인 + 끝에 `— [매체명](링크)`.
- 분석·해설 없이 헤드라인만. 지역이 다양하게 섞이도록 한다.

## 현대전 추적

- news 를 전선·지역별로 묶어 3~6개 `###` 소제목 아래 정리한다.
  예: `### 우크라이나`, `### 가자·레바논`, `### 수단`, `### 미얀마`, `### 사헬`.
- 각 소제목 아래 1~3개 불릿. 불릿은 한국어 2~3문장 분석 + 필요 시 `"원문 핵심 문구"`(영어, 15단어 이내) + 끝에 `([매체명](링크))`.
- ISW·Bellingcat 등 분석기관 평가는 별도로 요약해 붙인다.

## 일일 전쟁사

- history_candidates 중 중요도가 높고 서사가 있는 사건 **1개**를 고른다.
- 3~5문단으로 배경 → 전개 → 의의를 서술한다.
- 마지막 줄에 `출처: [제목](링크)`.

## 6·25 전쟁사

- 오늘 날짜(월/일)에 해당하는 1950~1953년 6·25 전쟁의 사건을 다룬다.
- 제공된 6·25 관련 항목이 있으면 우선 근거로 삼는다. 없으면 그 월·일 전후의
  잘 기록된 사건을 서술하되 확실한 것만 쓰고, 날짜를 특정하기 애매하면 "이 무렵"으로 표현한다.
- 2~3문단. 지명·부대명은 (원어/한자) 병기. 근거가 부족하면 짧게 쓰고 그 사실을 밝힌다.

## 북한 관련

- north_korea 항목을 요약한다. 미사일·핵·열병식·위성·대남/대미 메시지·제재·북러 협력·경제 등.
- 3~5개 불릿. 각 불릿 한국어 1~2문장 + `([매체명](링크))`.
- 특이 동향이 없으면 "이번 수집 기간 중 주목할 만한 북한 동향은 확인되지 않았다."로 한 줄 처리한다.

수집 데이터(JSON):
```json
{data}
```

출력 형식 (이 구조 그대로, 닫는 --- 포함):
---
title: <이 호의 한 줄 제목>
summary: <3~4문장 요약>
---

## 최신 기사

<본문>

## 현대전 추적

<본문>

## 일일 전쟁사

<본문>

## 6·25 전쟁사

<본문>

## 북한 관련

<본문>
"""


def _frontmatter(title: str, date: dt.date, summary: str) -> str:
    title = title.replace('"', "'")
    summary = summary.replace('"', "'").replace("\n", " ")
    return (
        f'---\ntitle: "{title}"\ndate: "{date.isoformat()}"\n'
        f'summary: "{summary}"\n---\n\n'
    )


def _bullets(items: list[dict], n: int) -> list[str]:
    out = []
    for it in items[:n]:
        title = it.get("title") or it.get("summary", "")[:90]
        src, link = it.get("source", ""), it.get("link", "")
        out.append(f"- {title} — _{src}_" + (f" ([링크]({link}))" if link else ""))
    return out


def draft_mode(raw: dict, date: dt.date) -> str:
    lines = [_frontmatter(f"{date.isoformat()} 브리핑 (초안)", date,
                          "API 키 미설정 상태의 자동 초안. 수집 원자료만 정리했습니다.")]
    lines.append(
        "> **초안 모드** — `ANTHROPIC_API_KEY` 설정 시 편집·요약본으로 자동 전환됩니다.\n"
    )
    news = raw.get("news", [])
    nk = raw.get("north_korea", [])

    lines.append("## 최신 기사\n")
    lines += _bullets(news, 12) or ["- (수집된 기사 없음)"]

    lines.append("\n## 현대전 추적\n")
    lines += _bullets(news[12:], 10) or ["- (추가 항목 없음)"]

    lines.append("\n## 일일 전쟁사\n")
    cands = raw.get("history_candidates", [])
    if cands:
        for c in cands[:6]:
            lines.append(f"- **{c.get('year','?')}** — {c['text']}"
                         + (f" ([wiki]({c['link']}))" if c.get("link") else ""))
    else:
        lines.append("- 오늘 날짜의 군사사 후보를 찾지 못했습니다.")

    lines.append("\n## 6·25 전쟁사\n")
    korea = raw.get("korean_war_hits", [])
    if korea:
        for c in korea:
            lines.append(f"- **{c.get('year','?')}** — {c['text']}"
                         + (f" ([wiki]({c['link']}))" if c.get("link") else ""))
    else:
        lines.append("- 이 날짜에 자동 매칭된 6·25 전쟁 기록 없음. API 키 설정 시 Claude가 서술합니다.")

    lines.append("\n## 북한 관련\n")
    lines += _bullets(nk, 8) or ["- 이번 수집 기간 중 북한 관련 기사 없음."]
    lines.append("")
    return "\n".join(lines)


def claude_mode(raw: dict, date: dt.date) -> str:
    import anthropic

    model = common.env("ANTHROPIC_MODEL", "claude-sonnet-5")
    client = anthropic.Anthropic(api_key=common.env("ANTHROPIC_API_KEY"))
    data = json.dumps(raw, ensure_ascii=False)[:90000]
    msg = client.messages.create(
        model=model,
        max_tokens=6000,
        system=SYSTEM,
        messages=[{"role": "user", "content": PROMPT.format(date=date.isoformat(), data=data)}],
    )
    text = "".join(block.text for block in msg.content if block.type == "text").strip()
    return normalize_output(text, date)


def normalize_output(text: str, date: dt.date) -> str:
    """Claude 출력에서 title/summary 를 뽑아 항상 올바른 frontmatter 로 재조립한다.
    닫는 --- 를 빠뜨리거나 따옴표가 깨져도 안전하게 처리한다."""
    text = text.strip()
    title, summary, body = "", "", text

    if text.startswith("---"):
        rest = text[3:].lstrip("\n")
        m = re.match(r"(.*?)\n---\s*\n(.*)$", rest, re.S)
        if m:
            fm, body = m.group(1), m.group(2)
        else:  # 닫는 --- 누락: '##' 또는 첫 빈 줄까지를 frontmatter 로 간주
            lines = rest.split("\n")
            cut = len(lines)
            fm_lines: list[str] = []
            for i, ln in enumerate(lines):
                if ln.strip().startswith("#") or (not ln.strip() and fm_lines):
                    cut = i
                    break
                fm_lines.append(ln)
            fm, body = "\n".join(fm_lines), "\n".join(lines[cut:])
        for ln in fm.splitlines():
            low = ln.lower()
            if low.startswith("title:"):
                title = ln.split(":", 1)[1].strip().strip('"').strip("'")
            elif low.startswith("summary:"):
                summary = ln.split(":", 1)[1].strip().strip('"').strip("'")

    return _frontmatter(title or f"{date.isoformat()} 전쟁 브리핑", date, summary) + body.strip() + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYYY-MM-DD (기본: 오늘)")
    ap.add_argument("--force", action="store_true", help="이미 있어도 다시 생성")
    args = ap.parse_args()

    common.load_dotenv()
    common.ensure_dirs()
    date = common.today(args.date)

    raw_path = common.raw_path(date)
    if not raw_path.exists():
        sys.exit(f"수집 파일 없음: {raw_path} — 먼저 collect.py 실행")
    raw = json.loads(raw_path.read_text(encoding="utf-8"))

    out_path = common.content_path(date)
    if out_path.exists() and not args.force:
        existing = out_path.read_text(encoding="utf-8")
        is_draft = "(초안)" in existing.split("\n---", 1)[0]
        # 초안 파일인데 이제 키가 생겼으면 편집본으로 자동 승급
        if not (is_draft and common.env("ANTHROPIC_API_KEY")):
            print(f"[generate] 이미 존재: {out_path.name} (--force 로 덮어쓰기)")
            return
        print(f"[generate] 초안 → 편집본 승급: {out_path.name}")

    if common.env("ANTHROPIC_API_KEY"):
        try:
            body = claude_mode(raw, date)
            mode = "claude"
        except Exception as e:  # noqa: BLE001
            print(f"[generate] Claude 실패 → 초안 모드: {e}", file=sys.stderr)
            body = draft_mode(raw, date)
            mode = "draft(fallback)"
    else:
        body = draft_mode(raw, date)
        mode = "draft"

    out_path.write_text(body, encoding="utf-8")
    print(f"[generate] {out_path.name} 작성 ({mode})")


if __name__ == "__main__":
    main()
