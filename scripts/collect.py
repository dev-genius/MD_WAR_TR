"""수집 단계.

- 일일 전쟁사 후보: Wikipedia 'On this day' 군사 관련 사건
- 현대전 추적 원자료: 구글뉴스 검색 RSS + 일반 RSS + ISW
- 북한 관련: 전용 구글뉴스 + RSS

결과를 data/raw/YYYY-MM-DD.json 으로 저장한다. 네트워크 실패는 소스 단위로
격리하여 나머지 수집은 계속 진행한다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import urllib.parse
from typing import Any

import feedparser
from bs4 import BeautifulSoup

import common

MIL_KEYWORDS = re.compile(
    r"\b(war|battle|siege|invasion|offensive|army|navy|air force|troops|"
    r"military|treaty|armistice|surrender|bombing|campaign|revolt|coup|"
    r"ceasefire|front|regiment|fleet|artillery|nuclear)\b",
    re.I,
)

# 광역 뉴스피드(BBC, 알자지라 등)에서 분쟁 무관 기사를 거르는 필터
CONFLICT_KEYWORDS = re.compile(
    r"\b(war|strike|air ?strike|shelling|missile|drone|troops|military|"
    r"offensive|frontline|front line|ceasefire|truce|army|militia|rebel|"
    r"insurgent|jihadist|coup|junta|clashes?|killed|casualties|siege|"
    r"occupation|artillery|bombard|combat|conflict|Gaza|Ukraine|Sudan|"
    r"Myanmar|Sahel|Hezbollah|Hamas)\b",
    re.I,
)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _within(entry: Any, hours: int) -> bool:
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            published = dt.datetime(*t[:6], tzinfo=dt.timezone.utc)
            return published >= dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)
    return True  # 날짜 없으면 통과


# --------------------------------------------------------------------------- #
# 일일 전쟁사 후보
# --------------------------------------------------------------------------- #
def collect_history(date: dt.date) -> list[dict]:
    url = (
        "https://api.wikimedia.org/feed/v1/wikipedia/en/onthisday/events/"
        f"{date.month:02d}/{date.day:02d}"
    )
    out: list[dict] = []
    try:
        r = common.http().get(url, timeout=20)
        r.raise_for_status()
        for ev in r.json().get("events", []):
            text = _clean(ev.get("text", ""))
            if not MIL_KEYWORDS.search(text):
                continue
            pages = ev.get("pages", []) or []
            link = ""
            if pages:
                link = pages[0].get("content_urls", {}).get("desktop", {}).get("page", "")
            out.append({"year": ev.get("year"), "text": text, "link": link})
    except Exception as e:  # noqa: BLE001
        print(f"[history] 실패: {e}", file=sys.stderr)
    out.sort(key=lambda x: x.get("year") or 0)
    return out


KOREA_WAR_RE = re.compile(
    r"korea|korean war|inchon|incheon|pusan|busan|38th parallel|panmunjom", re.I
)


def split_korea(events: list[dict]) -> tuple[list[dict], list[dict]]:
    """일일 전쟁사 후보에서 6·25 전쟁(1950-1953) 관련 항목을 분리."""
    korea, rest = [], []
    for e in events:
        yr = e.get("year") or 0
        if KOREA_WAR_RE.search(e.get("text", "")) and (1950 <= yr <= 1953 or yr == 0):
            korea.append(e)
        else:
            rest.append(e)
    return korea, rest


# --------------------------------------------------------------------------- #
# 뉴스: RSS / 구글뉴스
# --------------------------------------------------------------------------- #
def _google_news_url(query: str, lang: str) -> str:
    q = urllib.parse.quote(query)
    if lang == "ko":
        return f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"
    return f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


def _parse_feed(url: str, label: str, limit: int, hours: int, conflict_only: bool = False) -> list[dict]:
    items: list[dict] = []
    try:
        feed = feedparser.parse(url, agent=common.USER_AGENT)
        for e in feed.entries:
            if not _within(e, hours):
                continue
            title = _clean(e.get("title", ""))
            summary = _clean(BeautifulSoup(e.get("summary", ""), "html.parser").get_text(" "))
            if conflict_only and not CONFLICT_KEYWORDS.search(f"{title} {summary}"):
                continue
            items.append(
                {
                    "source": label,
                    "title": title,
                    "summary": summary[:500],
                    "link": e.get("link", ""),
                    "published": e.get("published", e.get("updated", "")),
                }
            )
            if len(items) >= limit:
                break
    except Exception as ex:  # noqa: BLE001
        print(f"[feed] {label} 실패: {ex}", file=sys.stderr)
    return items


def collect_group(cfg: dict, limit: int, hours: int) -> list[dict]:
    """{google_news: [...], rss: [...]} 형태의 그룹을 수집."""
    out: list[dict] = []
    for g in cfg.get("google_news", []) or []:
        out += _parse_feed(
            _google_news_url(g["query"], g.get("lang", "en")), g["label"], limit, hours
        )
    for rss in cfg.get("rss", []) or []:
        out += _parse_feed(
            rss["url"], rss["label"], limit, hours, conflict_only=(rss.get("filter") == "conflict")
        )
    return out


def collect_isw_fallback(cfg: dict) -> list[dict]:
    """RSS가 비었을 때 ISW 목록 페이지에서 최신 평가 링크만 긁는다."""
    url = cfg.get("isw_listing_url")
    if not url:
        return []
    out: list[dict] = []
    try:
        r = common.http().get(url, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.select("a[href]"):
            title = _clean(a.get_text())
            href = a["href"]
            if re.search(r"(campaign assessment|offensive campaign)", title, re.I):
                if href.startswith("/"):
                    href = "https://www.understandingwar.org" + href
                out.append({"source": "ISW", "title": title, "summary": "", "link": href, "published": ""})
            if len(out) >= 4:
                break
    except Exception as e:  # noqa: BLE001
        print(f"[isw] 실패: {e}", file=sys.stderr)
    return out


def _dedupe(items: list[dict]) -> list[dict]:
    seen, out = set(), []
    for it in items:
        key = re.sub(r"\W+", "", (it.get("title") or it.get("summary", "")).lower())[:80]
        if key and key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYYY-MM-DD (기본: 오늘)")
    args = ap.parse_args()

    common.load_dotenv()
    common.ensure_dirs()
    date = common.today(args.date)

    cfg = common.load_yaml("feeds.yaml")
    limit = int(cfg.get("max_items_per_source", 6))
    hours = int(cfg.get("lookback_hours", 36))

    history_all = collect_history(date)
    korea, history = split_korea(history_all)

    news = collect_group(cfg, limit, hours)
    if not any(i["source"] == "ISW" for i in news):
        news += collect_isw_fallback(cfg)
    news = _dedupe(news)

    nk = _dedupe(collect_group(cfg.get("north_korea", {}) or {}, limit, hours))

    payload = {
        "date": date.isoformat(),
        "generated_at": common.now_local().isoformat(),
        "history_candidates": history,
        "korean_war_hits": korea,
        "korean_war_date": {"month": date.month, "day": date.day},
        "news": news,
        "north_korea": nk,
    }
    path = common.raw_path(date)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"[collect] {path.name}: 전쟁사 후보 {len(history)} · 6·25 히트 {len(korea)} · "
        f"뉴스 {len(news)} · 북한 {len(nk)}"
    )


if __name__ == "__main__":
    main()
