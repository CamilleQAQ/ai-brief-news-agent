import calendar
from datetime import datetime, timedelta, timezone
from html import unescape
import re
from urllib.parse import urljoin
from xml.etree import ElementTree

import feedparser
import requests

from settings import EDITORIAL_ITEMS_PER_SOURCE, EDITORIAL_LOOKBACK_DAYS


RSS_SOURCES = [
    ("OpenAI", 1, "https://openai.com/news/rss.xml"),
    ("Google DeepMind", 1, "https://deepmind.google/blog/rss.xml"),
    ("Google AI Blog", 1, "https://blog.google/technology/ai/rss/"),
    ("Mistral", 1, "https://mistral.ai/news/rss"),
    ("NVIDIA Developer", 1, "https://developer.nvidia.com/blog/feed/"),
    ("Microsoft Research", 1, "https://www.microsoft.com/en-us/research/feed/"),
    ("Hugging Face Blog", 1, "https://huggingface.co/blog/feed.xml"),
    ("Berkeley BAIR Blog", 1, "https://bairblog.github.io/feed.xml"),
    (
        "MIT Technology Review AI",
        2,
        "https://www.technologyreview.com/topic/artificial-intelligence/feed/",
    ),
    (
        "TechCrunch AI",
        3,
        "https://techcrunch.com/category/artificial-intelligence/feed/",
    ),
]

SITEMAP_SOURCES = [
    (
        "Anthropic",
        1,
        "https://www.anthropic.com/sitemap.xml",
        "/news/",
    ),
    (
        "DeepSeek News",
        1,
        "https://api-docs.deepseek.com/sitemap.xml",
        "/news/",
    ),
]

META_BLOG_URL = "https://ai.meta.com/blog/"
DEFAULT_HEADERS = {"User-Agent": "ai-brie-news-agent/0.1"}

session = requests.Session()
session.headers.update(DEFAULT_HEADERS)


def get_editorial_news(
    days=EDITORIAL_LOOKBACK_DAYS,
    limit_per_source=EDITORIAL_ITEMS_PER_SOURCE,
):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    all_items = []

    for source, tier, url in RSS_SOURCES:
        items = collect_source_safely(
            source,
            get_feed_items,
            url,
            source,
            tier,
            cutoff,
            limit_per_source,
        )
        all_items.extend(items)

    for source, tier, sitemap_url, path_filter in SITEMAP_SOURCES:
        items = collect_source_safely(
            source,
            get_sitemap_items,
            sitemap_url,
            path_filter,
            source,
            tier,
            cutoff,
            limit_per_source,
        )
        all_items.extend(items)

    meta_items = collect_source_safely(
        "Meta AI",
        get_listing_page_items,
        META_BLOG_URL,
        "/blog/",
        "Meta AI",
        1,
        cutoff,
        limit_per_source,
    )
    all_items.extend(meta_items)

    return deduplicate_items(all_items)


def collect_source_safely(source, collector, *args):
    try:
        return collector(*args)
    except (requests.RequestException, ElementTree.ParseError, ValueError) as error:
        print(f"  警告：跳过 {source}（{error.__class__.__name__}）")
        return []


def get_feed_items(url, source, tier, cutoff, limit):
    response = session.get(url, timeout=20)
    response.raise_for_status()

    feed = feedparser.parse(response.content)
    items = []

    for entry in feed.entries:
        published_at = get_feed_datetime(entry)

        if published_at and published_at < cutoff:
            continue

        link = entry.get("link", "")
        title = clean_text(entry.get("title", ""))

        if not link or not title:
            continue

        items.append(build_item(
            title=title,
            link=link,
            summary=clean_text(entry.get("summary", "")),
            source=source,
            tier=tier,
            published_at=published_at,
        ))

        if len(items) == limit:
            break

    return items


def get_sitemap_items(
    sitemap_url,
    path_filter,
    source,
    tier,
    cutoff,
    limit,
):
    response = session.get(sitemap_url, timeout=20)
    response.raise_for_status()

    root = ElementTree.fromstring(response.content)
    sitemap_rows = []

    for element in root:
        values = {
            child.tag.rsplit("}", 1)[-1]: child.text or ""
            for child in element
        }
        link = values.get("loc", "")

        if path_filter in link:
            sitemap_rows.append((link, parse_datetime(values.get("lastmod"))))

    sitemap_rows.reverse()
    sitemap_rows.sort(
        key=lambda row: row[1] or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )

    items = []

    for link, sitemap_date in sitemap_rows[:20]:
        item = get_page_item(link, source, tier, sitemap_date)
        published_at = parse_datetime(item.get("published_at"))

        if not published_at or published_at < cutoff:
            continue

        items.append(item)

        if len(items) == limit:
            break

    return items


def get_listing_page_items(
    listing_url,
    path_filter,
    source,
    tier,
    cutoff,
    limit,
):
    response = session.get(listing_url, timeout=20)
    response.raise_for_status()

    links = []

    for href in re.findall(r'href=["\']([^"\']+)', response.text):
        link = urljoin(listing_url, unescape(href))

        if path_filter not in link or link.rstrip("/") == listing_url.rstrip("/"):
            continue

        if link not in links:
            links.append(link)

    items = []

    for link in links[:20]:
        item = get_page_item(link, source, tier)
        published_at = parse_datetime(item.get("published_at"))

        if not published_at or published_at < cutoff:
            continue

        items.append(item)

        if len(items) == limit:
            break

    return items


def get_page_item(link, source, tier, fallback_date=None):
    response = session.get(link, timeout=20)
    response.raise_for_status()

    metadata = extract_metadata(response.text)
    title = metadata.get("og:title") or metadata.get("twitter:title")
    summary = (
        metadata.get("og:description")
        or metadata.get("description")
        or metadata.get("twitter:description")
        or ""
    )
    published_at = extract_page_datetime(response.text, link) or fallback_date

    return build_item(
        title=clean_text(title or link.rstrip("/").rsplit("/", 1)[-1]),
        link=link,
        summary=clean_text(summary),
        source=source,
        tier=tier,
        published_at=published_at,
    )


def extract_metadata(page_html):
    metadata = {}

    for tag in re.findall(r"<meta\s+[^>]*>", page_html, re.IGNORECASE):
        attributes = dict(
            (name.lower(), unescape(value))
            for name, _, value in re.findall(
                r"([\w:-]+)\s*=\s*([\"'])(.*?)\2",
                tag,
                re.IGNORECASE | re.DOTALL,
            )
        )
        key = attributes.get("property") or attributes.get("name")

        if key and attributes.get("content"):
            metadata[key.lower()] = attributes["content"]

    return metadata


def extract_page_datetime(page_html, link):
    metadata = extract_metadata(page_html)

    for key in ("article:published_time", "date", "datepublished"):
        published_at = parse_datetime(metadata.get(key))

        if published_at:
            return published_at

    patterns = [
        r'<time[^>]+datetime=["\']([^"\']+)',
        r'"datePublished"\s*:\s*"([^"]+)"',
    ]

    for pattern in patterns:
        match = re.search(pattern, page_html, re.IGNORECASE)

        if match:
            published_at = parse_datetime(match.group(1))

            if published_at:
                return published_at

    human_date = re.search(
        r"\b(?:January|February|March|April|May|June|July|August|"
        r"September|October|November|December)\s+\d{1,2},\s+\d{4}\b",
        page_html,
        re.IGNORECASE,
    )

    if human_date:
        parsed = datetime.strptime(human_date.group(0), "%B %d, %Y")
        return parsed.replace(tzinfo=timezone.utc)

    url_date = re.search(r"/news/news(\d{2})(\d{2})(\d{2})(?:/|$)", link)

    if url_date:
        year, month, day = (int(part) for part in url_date.groups())
        return datetime(2000 + year, month, day, tzinfo=timezone.utc)

    return None


def build_item(title, link, summary, source, tier, published_at):
    return {
        "title": title,
        "link": link,
        "summary": summary,
        "source": source,
        "category": "Official" if tier == 1 else "Media",
        "source_tier": tier,
        "content_type": "official_blog" if tier == 1 else "media",
        "published_at": published_at.isoformat() if published_at else "",
    }


def get_feed_datetime(entry):
    time_struct = entry.get("published_parsed") or entry.get("updated_parsed")

    if time_struct:
        timestamp = calendar.timegm(time_struct)
        return datetime.fromtimestamp(timestamp, timezone.utc)

    return parse_datetime(entry.get("published") or entry.get("updated"))


def parse_datetime(value):
    if not value:
        return None

    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def clean_text(value):
    text = re.sub(r"<[^>]+>", " ", value or "")
    return " ".join(unescape(text).split())


def deduplicate_items(items):
    unique_items = {}

    for item in items:
        if item.get("link"):
            unique_items[item["link"]] = item

    return list(unique_items.values())
