"""공용 유틸: 경로, 날짜, 설정 로딩, HTTP 세션."""
from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

import requests
import yaml
from dateutil import tz

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
CONTENT_DIR = ROOT / "content"
RAW_DIR = ROOT / "data" / "raw"
SITE_DIR = ROOT / "site"
TEMPLATES_DIR = ROOT / "templates"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 MD_WAR_TR-bot/1.0"
)


def load_yaml(name: str) -> dict:
    with open(CONFIG_DIR / name, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def site_config() -> dict:
    return load_yaml("site.yaml")


def local_tz():
    return tz.gettz(site_config().get("timezone", "Asia/Seoul"))


def today(date_str: str | None = None) -> dt.date:
    """date_str='YYYY-MM-DD' 이면 그 날짜, 아니면 로컬 타임존 오늘."""
    if date_str:
        return dt.date.fromisoformat(date_str)
    return dt.datetime.now(local_tz()).date()


def now_local() -> dt.datetime:
    return dt.datetime.now(local_tz())


def http() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en,ko;q=0.8"})
    return s


def ensure_dirs() -> None:
    for d in (CONTENT_DIR, RAW_DIR, SITE_DIR):
        d.mkdir(parents=True, exist_ok=True)


def raw_path(date: dt.date) -> Path:
    return RAW_DIR / f"{date.isoformat()}.json"


def content_path(date: dt.date) -> Path:
    return CONTENT_DIR / f"{date.isoformat()}.md"


def load_dotenv() -> None:
    """의존성 없는 최소 .env 로더. 이미 설정된 환경변수는 덮어쓰지 않음."""
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


def env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()
