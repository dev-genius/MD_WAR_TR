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

SYSTEM = """당신은 군사사·안보 분야 한국어 뉴스레터 편집자입니다.
[일일전쟁사] · [6·25 전쟁 그날] · [현대전쟁 추적] 3부 구성의 한 호를 만듭니다.
사실에 근거하고, 검증되지 않은 전과(戰果) 주장은 "~측 주장"으로 명시하며,
선정적 표현을 피합니다. 역사 파트는 확실한 사실만 서술하고 불확실하면 그렇다고 밝힙니다.
저작권 보호를 위해 기사 원문을 재게시하지 않고 문장 단위의 짧은 인용만 사용하며
항상 출처를 링크합니다."""

PROMPT = """오늘 날짜: {date}

아래 수집 데이터로 뉴스레터 한 호를 작성하세요. 반드시 지정한 마크다운 구조를
그대로 따르고, 그 외 서두/맺음말은 넣지 마세요.

## [일일전쟁사]

- history_candidates 중 역사적 중요도가 높고 이야기로 풀 만한 사건 **1개**를 고른다.
- 3~5문단으로 배경 → 전개 → 의의를 서술한다.
- 핵심 고유명사·용어는 한국어(English 원문) 형태로 병기한다.
- 마지막 줄에 `출처: [제목](링크)` 형식으로 위키피디아 링크를 단다.

## [6·25 전쟁 그날]

- 오늘 날짜(korean_war_date의 월/일)에 해당하는 1950~1953년 6·25 전쟁의 사건을 다룬다.
- korean_war_hits 가 있으면 그것을 우선 근거로 삼는다. 없으면 그 월·일 전후의
  잘 기록된 사건(전투, 작전, 회담, 결의)을 서술하되 **확실한 것만** 쓰고,
  특정 날짜에 묶기 애매하면 "이 무렵" 이라고 표현한다.
- 2~3문단. 한국어 서술 + 지명·부대명은 (English/한자) 병기.
- 근거가 부족하면 한 문단으로 짧게 쓰고 그 사실을 밝힌다.

## [현대전쟁 추적]

- news 와 telegram 항목을 전선/지역별로 3~6개 불릿으로 정리한다.
- 각 불릿: 한국어 요약 1~2문장 + 필요 시 `"원문 핵심 문구"` (영어, 15단어 이내) + 끝에 `([출처명](링크))`.
- 상충하는 주장은 병기하고 확인되지 않았음을 밝힌다.
- 텔레그램·OSINT 출처는 "비공식/미확인"으로 표기한다.

수집 데이터(JSON):
```json
{data}
```

출력 형식 (이 구조만):
---
title: <이 호의 한 줄 제목>
summary: <2~3문장 요약>
---

## [일일전쟁사]

<본문>

## [6·25 전쟁 그날]

<본문>

## [현대전쟁 추적]

<본문>
"""


def _frontmatter(title: str, date: dt.date, summary: str) -> str:
    title = title.replace('"', "'")
    summary = summary.replace('"', "'").replace("\n", " ")
    return (
        f'---\ntitle: "{title}"\ndate: "{date.isoformat()}"\n'
        f'summary: "{summary}"\n---\n\n'
    )


def draft_mode(raw: dict, date: dt.date) -> str:
    lines = [_frontmatter(f"{date.isoformat()} 전쟁 브리핑 (초안)", date,
                          "API 키 미설정 상태의 자동 초안입니다. 수집 원자료만 정리했습니다.")]
    lines.append(
        "> 이 호는 **초안 모드**입니다. `ANTHROPIC_API_KEY` 를 설정하면 아래 후보에서 "
        "사건을 골라 이야기로 편집하고, 뉴스는 전선별 요약으로 압축됩니다.\n"
    )

    lines.append("## [일일전쟁사]\n")
    cands = raw.get("history_candidates", [])
    if cands:
        lines.append("_후보 사건:_\n")
        for c in cands[:6]:
            yr = c.get("year", "?")
            lines.append(f"- **{yr}** — {c['text']} " + (f"([wiki]({c['link']}))" if c.get("link") else ""))
    else:
        lines.append("_오늘 날짜의 군사사 후보를 찾지 못했습니다._")

    lines.append("\n## [6·25 전쟁 그날]\n")
    korea = raw.get("korean_war_hits", [])
    if korea:
        for c in korea:
            yr = c.get("year", "?")
            lines.append(f"- **{yr}** — {c['text']} " + (f"([wiki]({c['link']}))" if c.get("link") else ""))
    else:
        lines.append("_이 날짜에 자동 매칭된 6·25 전쟁 기록이 없습니다. "
                     "API 키 설정 시 Claude가 이 무렵의 사건을 서술합니다._")

    lines.append("\n## [현대전쟁 추적]\n")
    news = raw.get("news", [])
    tg = raw.get("telegram", [])
    lines.append("_주요 기사 (상위 6건):_\n")
    for item in news[:6]:
        title = item.get("title") or item.get("summary", "")[:80]
        src = item.get("source", "")
        link = item.get("link", "")
        lines.append(f"- {title} — _{src}_ " + (f"([링크]({link}))" if link else ""))
    if tg:
        lines.append(f"\n_텔레그램/OSINT: {len(tg)}건 수집 (편집 대기)_")
    lines.append("")
    return "\n".join(lines)


def claude_mode(raw: dict, date: dt.date) -> str:
    import anthropic

    model = common.env("ANTHROPIC_MODEL", "claude-sonnet-5")
    client = anthropic.Anthropic(api_key=common.env("ANTHROPIC_API_KEY"))
    data = json.dumps(raw, ensure_ascii=False)[:60000]
    msg = client.messages.create(
        model=model,
        max_tokens=4000,
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
