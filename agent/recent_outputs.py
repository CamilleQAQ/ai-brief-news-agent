import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from settings import (
    COOLDOWN_DAYS,
    DEFAULT_COOLDOWN_DAYS,
    HISTORY_RETENTION_DAYS,
    MAX_HISTORY_ITEMS,
)


STATE_PATH = (
    Path(__file__).resolve().parent.parent
    / ".state"
    / "recent_outputs.json"
)
TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
}


def load_recent_outputs(path=STATE_PATH, now=None):
    if not path.exists():
        return empty_history()

    try:
        with path.open("r", encoding="utf-8") as file:
            history = json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        print(f"  警告：无法读取 recent-output history（{error.__class__.__name__}）")
        return empty_history()

    if not isinstance(history, dict) or not isinstance(
        history.get("items"), dict
    ):
        print("  警告：recent-output history 格式无效，按空历史继续")
        return empty_history()

    return prune_history(history, now=now)


def empty_history():
    return {"version": 1, "items": {}}


def filter_recent_outputs(items, history, now=None):
    current_time = now or datetime.now(timezone.utc)
    history_items = history.get("items", {})
    filtered = []
    seen_keys = set()

    for item in items:
        key = canonical_item_key(item)

        if key in seen_keys:
            continue

        seen_keys.add(key)
        record = history_items.get(key)

        if record and is_on_cooldown(item, record, current_time):
            continue

        filtered.append(item)

    return filtered


def is_on_cooldown(item, record, now):
    last_output_at = parse_timestamp(record.get("last_output_at"))

    if last_output_at is None:
        return False

    cooldown_days = get_cooldown_days(item.get("source"))
    return now - last_output_at < timedelta(days=cooldown_days)


def get_cooldown_days(source):
    return COOLDOWN_DAYS.get(
        str(source or "").casefold(),
        DEFAULT_COOLDOWN_DAYS,
    )


def record_final_outputs(history, result, candidates, now=None):
    current_time = now or datetime.now(timezone.utc)
    updated = {
        "version": 1,
        "items": dict(history.get("items", {})),
    }
    candidates_by_url = {
        normalize_url(candidate.get("link", "")): candidate
        for candidate in candidates
        if candidate.get("link")
    }

    for section in ("news", "papers_blogs", "open_source", "skills"):
        for output_item in result.get(section, []):
            normalized_url = normalize_url(output_item.get("url", ""))
            candidate = candidates_by_url.get(normalized_url, output_item)
            key = canonical_item_key(candidate)

            updated["items"][key] = {
                "source": candidate.get("source", ""),
                "url": candidate.get("link") or output_item.get("url", ""),
                "title": str(
                    candidate.get("title") or output_item.get("title", "")
                )[:120],
                "last_output_at": current_time.isoformat(),
            }

    return prune_history(updated, now=current_time)


def save_recent_outputs(history, path=STATE_PATH):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")

    try:
        with temporary_path.open("w", encoding="utf-8") as file:
            json.dump(history, file, ensure_ascii=False, indent=2)
            file.write("\n")

        os.replace(temporary_path, path)
    except OSError as error:
        temporary_path.unlink(missing_ok=True)
        print(f"  警告：无法保存 recent-output history（{error.__class__.__name__}）")
        return False

    return True


def prune_history(history, now=None):
    current_time = now or datetime.now(timezone.utc)
    cutoff = current_time - timedelta(days=HISTORY_RETENTION_DAYS)
    retained = []

    for key, record in history.get("items", {}).items():
        if not isinstance(record, dict):
            continue

        timestamp = parse_timestamp(record.get("last_output_at"))

        if timestamp is not None and timestamp >= cutoff:
            retained.append((key, record, timestamp))

    retained.sort(key=lambda entry: entry[2], reverse=True)
    retained = retained[:MAX_HISTORY_ITEMS]

    return {
        "version": 1,
        "items": {key: record for key, record, _ in retained},
    }


def canonical_item_key(item):
    source = str(item.get("source", "")).casefold()
    url = item.get("link") or item.get("url") or ""
    normalized_url = normalize_url(url)

    arxiv_id = extract_arxiv_id(normalized_url)
    if source == "arxiv" or arxiv_id:
        if arxiv_id:
            return f"arxiv:{arxiv_id}"

    github_repo = extract_github_repo(normalized_url)
    if source == "github" or github_repo:
        if github_repo:
            return f"github:{github_repo}"

    if normalized_url:
        return f"url:{normalized_url}"

    title = normalize_title(item.get("title", ""))
    digest = hashlib.sha256(
        f"{source}:{title}".encode("utf-8")
    ).hexdigest()[:20]
    return f"title:{digest}"


def normalize_url(url):
    if not isinstance(url, str) or not url.strip():
        return ""

    parsed = urlsplit(url.strip())
    scheme = parsed.scheme.casefold() or "https"
    hostname = (parsed.hostname or "").casefold()
    port = f":{parsed.port}" if parsed.port else ""
    path = re.sub(r"/{2,}", "/", parsed.path).rstrip("/")
    query = urlencode(sorted(
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.casefold().startswith("utm_")
        and key.casefold() not in TRACKING_QUERY_KEYS
    ))

    return urlunsplit((scheme, hostname + port, path, query, ""))


def extract_arxiv_id(url):
    match = re.search(
        r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})(?:v\d+)?(?:\.pdf)?$",
        url,
        flags=re.IGNORECASE,
    )
    return match.group(1) if match else ""


def extract_github_repo(url):
    parsed = urlsplit(url)

    if parsed.hostname != "github.com":
        return ""

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        return ""

    return f"{parts[0]}/{parts[1]}".casefold()


def normalize_title(title):
    return " ".join(str(title or "").casefold().split())


def parse_timestamp(value):
    if not isinstance(value, str) or not value:
        return None

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)
