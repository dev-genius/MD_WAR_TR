"""빌드 단계: content/*.md → site/ (정적 HTML + rss.xml)."""
from __future__ import annotations

import datetime as dt
import html
import re
import shutil
from email.utils import format_datetime

import markdown as md
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

import common

FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.S)

# 섹션 제목 → 앵커 id (제목이 조금 달라도 startswith 로 매칭)
SECTION_IDS = [
    ("최신", "latest"),
    ("현대전", "modern"),
    ("일일 전쟁사", "history"),
    ("6", "korea"),
    ("북한", "nk"),
]
SECTION_LABELS = {
    "latest": "최신 기사",
    "modern": "현대전 추적",
    "history": "일일 전쟁사",
    "korea": "6·25 전쟁사",
    "nk": "북한 관련",
}


def _section_id(title: str) -> str:
    t = title.strip()
    for prefix, sid in SECTION_IDS:
        if t.startswith(prefix):
            return sid
    return ""


def process_sections(body_html: str) -> tuple[str, list[dict]]:
    """<h2> 에 번호·앵커를 붙이고 목차 데이터를 만든다."""
    toc: list[dict] = []
    counter = {"n": 0}

    def repl(m: "re.Match") -> str:
        counter["n"] += 1
        num = f"{counter['n']:02d}"
        title = re.sub(r"<.*?>", "", m.group(1)).strip()
        sid = _section_id(title) or f"sec-{counter['n']}"
        toc.append({"id": sid, "num": num, "title": SECTION_LABELS.get(sid, title)})
        return (
            f'<h2 id="{sid}" class="section-head">'
            f'<span class="section-num">{num}</span>'
            f'<span class="section-title">{title}</span></h2>'
        )

    return re.sub(r"<h2>(.*?)</h2>", repl, body_html, flags=re.S), toc


def reading_minutes(text: str) -> int:
    return max(1, round(len(re.sub(r"\s+", "", text)) / 480))


def parse_md(path) -> dict:
    text = path.read_text(encoding="utf-8")
    m = FM_RE.match(text)
    if m:
        meta = yaml.safe_load(m.group(1)) or {}
        body = m.group(2)
    else:
        meta, body = {}, text
    date = dt.date.fromisoformat(meta.get("date") or path.stem)
    raw_html = md.markdown(body, extensions=["extra", "sane_lists", "nl2br"])
    body_html, toc = process_sections(raw_html)
    return {
        "date": date,
        "slug": path.stem,
        "title": meta.get("title") or f"{date.isoformat()} 브리핑",
        "summary": meta.get("summary", ""),
        "body_html": body_html,
        "toc": toc,
        "minutes": reading_minutes(body),
    }


def main() -> None:
    common.ensure_dirs()
    cfg = common.site_config()
    base_url = cfg.get("base_url", "").rstrip("/")

    env = Environment(
        loader=FileSystemLoader(str(common.TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )

    issues = sorted(
        (parse_md(p) for p in common.CONTENT_DIR.glob("*.md")),
        key=lambda x: x["date"],
        reverse=True,
    )
    total = len(issues)
    for idx, issue in enumerate(issues):
        issue["number"] = total - idx  # 가장 오래된 호 = 제1호

    if common.SITE_DIR.exists():
        shutil.rmtree(common.SITE_DIR)
    common.SITE_DIR.mkdir(parents=True)

    # 개별 호 페이지
    issue_tpl = env.get_template("issue.html")
    for i, issue in enumerate(issues):
        prev_issue = issues[i + 1] if i + 1 < len(issues) else None
        next_issue = issues[i - 1] if i > 0 else None
        (common.SITE_DIR / f"{issue['slug']}.html").write_text(
            issue_tpl.render(site=cfg, issue=issue, prev=prev_issue, next=next_issue),
            encoding="utf-8",
        )

    # 인덱스
    (common.SITE_DIR / "index.html").write_text(
        env.get_template("index.html").render(site=cfg, issues=issues),
        encoding="utf-8",
    )

    # 항상 최신 호로: /latest (단톡방에 매일 같은 링크 붙여넣기용)
    if issues:
        latest = issues[0]
        nxt = issues[1] if len(issues) > 1 else None
        (common.SITE_DIR / "latest.html").write_text(
            issue_tpl.render(site=cfg, issue=latest, prev=nxt, next=None),
            encoding="utf-8",
        )

    # RSS
    (common.SITE_DIR / "rss.xml").write_text(build_rss(cfg, base_url, issues), encoding="utf-8")

    # .nojekyll (GitHub Pages 가 _ 파일 무시하지 않도록)
    (common.SITE_DIR / ".nojekyll").write_text("", encoding="utf-8")

    print(f"[build] {len(issues)}개 호 → {common.SITE_DIR}")


def build_rss(cfg: dict, base_url: str, issues: list[dict]) -> str:
    tzinfo = common.local_tz()
    items = []
    for issue in issues[:30]:
        link = f"{base_url}/{issue['slug']}.html"
        pub = dt.datetime.combine(issue["date"], dt.time(7, 0), tzinfo)
        items.append(
            "<item>"
            f"<title>{html.escape(issue['title'])}</title>"
            f"<link>{html.escape(link)}</link>"
            f"<guid isPermaLink=\"true\">{html.escape(link)}</guid>"
            f"<pubDate>{format_datetime(pub)}</pubDate>"
            f"<description>{html.escape(issue['summary'] or issue['title'])}</description>"
            "</item>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0"><channel>'
        f"<title>{html.escape(cfg.get('title', ''))}</title>"
        f"<link>{html.escape(base_url)}</link>"
        f"<description>{html.escape(cfg.get('description', ''))}</description>"
        f"<language>{html.escape(cfg.get('locale', 'ko-KR'))}</language>"
        + "".join(items)
        + "</channel></rss>"
    )


if __name__ == "__main__":
    main()
