from concurrent.futures import ThreadPoolExecutor, as_completed
from html import unescape
from html.parser import HTMLParser
import re
from urllib.parse import urljoin

import requests
import feedparser

from settings import (
    ARXIV_EVIDENCE_MAX_CHARS,
    ARXIV_EVIDENCE_WORKERS,
    ARXIV_ITEMS_PER_CATEGORY,
    ARXIV_SECTION_MAX_CHARS,
)


session = requests.Session()

session.headers.update({
    "User-Agent": "ai-brie-news-agent/0.1"
})

ARXIV_HTML_URL = "https://arxiv.org/html/{arxiv_id}"
RELEVANT_SECTION_TERMS = (
    "limitation",
    "experiment",
    "evaluation",
    "verification",
    "protocol",
    "performance",
    "result",
    "ablation",
    "method",
    "approach",
    "deriv",
    "implementation",
    "introduction",
    "contribution",
    "benchmark",
    "dataset",
    "data availability",
    "computational cost",
    "discussion",
    "conclusion",
    "summary",
)


def get_single_rss_news(url, source, limit=10):
    response = session.get(
        url,
        timeout=20
    )

    response.raise_for_status()

    feed = feedparser.parse(response.content)

    news = []

    for entry in feed.entries[:limit]:
        link = entry.get("link", "")
        news.append({
            "title": entry.get("title", ""),
            "link": link,
            "summary": clean_arxiv_summary(entry.get("summary", "")),
            "source": "arXiv",
            "category": source,
            "arxiv_id": extract_arxiv_id(link),
            "authors": [
                author.get("name", "")
                for author in entry.get("authors", [])
                if author.get("name")
            ],
            "categories": [
                tag.get("term", "")
                for tag in entry.get("tags", [])
                if tag.get("term")
            ],
            "published_at": entry.get("published", ""),
            "announce_type": entry.get("arxiv_announce_type", ""),
        })

    return news

def get_rss_news():
    sources = [
        ("https://rss.arxiv.org/rss/cs.AI", "cs.AI"),
        ("https://rss.arxiv.org/rss/cs.LG", "cs.LG"),
        ("https://rss.arxiv.org/rss/cs.CL", "cs.CL"),
    ]

    all_news = []

    for url, source in sources:
        try:
            news = get_single_rss_news(
                url=url,
                source=source,
            limit=ARXIV_ITEMS_PER_CATEGORY
            )
        except requests.RequestException as error:
            print(f"  警告：跳过 arXiv {source}（{error.__class__.__name__}）")
            continue

        all_news.extend(news)

    return all_news


def enrich_arxiv_candidates(
    candidates,
    max_workers=ARXIV_EVIDENCE_WORKERS,
):
    if not candidates:
        return []

    enriched = [None] * len(candidates)

    with ThreadPoolExecutor(
        max_workers=min(max_workers, len(candidates))
    ) as executor:
        futures = {
            executor.submit(enrich_arxiv_candidate, item): index
            for index, item in enumerate(candidates)
        }

        for future in as_completed(futures):
            index = futures[future]

            try:
                enriched[index] = future.result()
            except requests.RequestException:
                enriched[index] = with_abstract_only_evidence(
                    candidates[index]
                )

    return enriched


def enrich_arxiv_candidate(item):
    enriched = dict(item)
    arxiv_id = item.get("arxiv_id") or extract_arxiv_id(
        item.get("link", "")
    )

    if not arxiv_id:
        return with_abstract_only_evidence(enriched)

    response = session.get(
        ARXIV_HTML_URL.format(arxiv_id=arxiv_id),
        timeout=20,
    )

    if response.status_code == 404:
        return with_abstract_only_evidence(enriched)

    response.raise_for_status()
    evidence = extract_arxiv_evidence(
        response.text,
        base_url=response.url,
    )

    if not evidence["text"]:
        return with_abstract_only_evidence(enriched)

    enriched.update({
        "arxiv_id": arxiv_id,
        "evidence_level": "html_sections",
        "evidence_text": evidence["text"],
        "evidence_sections": evidence["sections"],
        "artifact_links": evidence["artifact_links"],
    })
    return enriched


def with_abstract_only_evidence(item):
    enriched = dict(item)
    enriched.update({
        "evidence_level": "abstract_only",
        "evidence_text": "",
        "evidence_sections": [],
        "artifact_links": [],
    })
    return enriched


def extract_arxiv_evidence(html, base_url=""):
    parser = ArxivEvidenceParser(base_url)
    parser.feed(html)
    return parser.result()


def clean_arxiv_summary(summary):
    text = re.sub(r"<[^>]+>", " ", summary or "")
    text = unescape(text)
    text = re.sub(
        r"^\s*arXiv:\S+\s+Announce Type:\s*\S+\s+Abstract:\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return " ".join(text.split())


def extract_arxiv_id(url):
    match = re.search(
        r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})(?:v\d+)?",
        url or "",
        flags=re.IGNORECASE,
    )
    return match.group(1) if match else ""


class ArxivEvidenceParser(HTMLParser):
    BLOCK_TAGS = {"p", "li", "figcaption"}
    HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
    SKIP_TAGS = {"script", "style", "nav", "header", "footer"}
    VOID_TAGS = {
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "source", "track", "wbr",
    }

    def __init__(self, base_url):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.current_heading = ""
        self.capture_tag = None
        self.capture_depth = 0
        self.capture_text = []
        self.skip_depth = 0
        self.sections = {}
        self.artifact_links = []

    def handle_starttag(self, tag, attrs):
        tag = tag.casefold()

        if tag in self.SKIP_TAGS:
            self.skip_depth += 1
            return

        if self.skip_depth:
            return

        href = dict(attrs).get("href", "")
        if href:
            self._remember_artifact(href)

        if self.capture_tag:
            if tag not in self.VOID_TAGS:
                self.capture_depth += 1
            return

        if tag in self.HEADING_TAGS or tag in self.BLOCK_TAGS:
            self.capture_tag = tag
            self.capture_depth = 1
            self.capture_text = []

    def handle_endtag(self, tag):
        tag = tag.casefold()

        if tag in self.SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1
            return

        if self.skip_depth or not self.capture_tag:
            return

        self.capture_depth -= 1
        if self.capture_depth:
            return

        text = " ".join(" ".join(self.capture_text).split())
        capture_tag = self.capture_tag
        self.capture_tag = None
        self.capture_text = []

        if capture_tag in self.HEADING_TAGS:
            self.current_heading = text
        elif text and self._is_relevant_heading(self.current_heading):
            self.sections.setdefault(self.current_heading, []).append(text)

    def handle_data(self, data):
        if self.capture_tag and not self.skip_depth:
            self.capture_text.append(data)

    def result(self):
        chunks = []
        included_sections = []

        ordered_sections = sorted(
            self.sections.items(),
            key=lambda entry: self._section_priority(entry[0]),
        )

        for heading, paragraphs in ordered_sections:
            section_text = " ".join(paragraphs)[:ARXIV_SECTION_MAX_CHARS]
            if not section_text:
                continue

            remaining = ARXIV_EVIDENCE_MAX_CHARS - sum(
                len(chunk) for chunk in chunks
            )
            if remaining <= 0:
                break

            chunk = f"[{heading}] {section_text}"[:remaining]
            chunks.append(chunk)
            included_sections.append(heading)

        return {
            "text": "\n".join(chunks)[:ARXIV_EVIDENCE_MAX_CHARS],
            "sections": included_sections,
            "artifact_links": self.artifact_links[:5],
        }

    def _is_relevant_heading(self, heading):
        normalized = heading.casefold()
        return any(term in normalized for term in RELEVANT_SECTION_TERMS)

    def _section_priority(self, heading):
        normalized = heading.casefold()

        for index, term in enumerate(RELEVANT_SECTION_TERMS):
            if term in normalized:
                return index

        return len(RELEVANT_SECTION_TERMS)

    def _remember_artifact(self, href):
        absolute_url = urljoin(self.base_url, href)
        if not any(
            domain in absolute_url.casefold()
            for domain in ("github.com", "huggingface.co")
        ):
            return

        if absolute_url not in self.artifact_links:
            self.artifact_links.append(absolute_url)
