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


def parse_md(path) -> dict:
    text = path.read_text(encoding="utf-8")
    m = FM_RE.match(text)
    if m:
        meta = yaml.safe_load(m.group(1)) or {}
        body = m.group(2)
    else:
        meta, body = {}, text
    date = dt.date.fromisoformat(meta.get("date") or path.stem)
    return {
        "date": date,
        "slug": path.stem,
        "title": meta.get("title") or f"{date.isoformat()} 브리핑",
        "summary": meta.get("summary", ""),
        "body_md": body,
        "body_html": md.markdown(body, extensions=["extra", "sane_lists", "nl2br"]),
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
