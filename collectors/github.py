import os
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv

from settings import (
    GITHUB_ACTIVE_DAYS,
    GITHUB_ACTIVE_MIN_STARS,
    GITHUB_ITEMS_PER_FAMILY,
    GITHUB_RECENT_DAYS,
    GITHUB_RECENT_MIN_STARS,
)


load_dotenv()


SEARCH_URL = "https://api.github.com/search/repositories"

SEARCH_FAMILIES = {
    "Agent & LLM Systems": "llm agent",
    "Training & Post-training": "llm training",
    "Reasoning & Model Architecture": "reasoning model",
    "Efficient AI & AI Infrastructure": "llm inference",
    "Evaluation": "llm evaluation",
    "Multimodal": "multimodal model",
}


session = requests.Session()

session.headers.update({
    "Accept": "application/vnd.github+json",
    "User-Agent": "ai-brief-news-agent/0.1",
})


github_token = os.getenv("GITHUB_TOKEN")

if github_token:
    session.headers.update({
        "Authorization": f"Bearer {github_token}"
    })


def get_date_days_ago(days):
    return (
        datetime.now(timezone.utc) - timedelta(days=days)
    ).date().isoformat()


def search_repositories(
    keyword,
    category,
    time_filter,
    signal,
    min_stars=20,
    sort="stars",
    limit=10
):
    query = (
        f"{keyword} "
        f"in:name,description "
        f"{time_filter} "
        f"stars:>={min_stars}"
    )

    params = {
        "q": query,
        "sort": sort,
        "order": "desc",
        "per_page": limit,
    }

    response = session.get(
        SEARCH_URL,
        params=params,
        timeout=20
    )

    response.raise_for_status()

    repositories = response.json()["items"]

    news = []

    for repo in repositories:
        news.append({
            "title": repo["full_name"],
            "link": repo["html_url"],
            "summary": repo.get("description") or "",
            "source": "GitHub",
            "category": category,
            "signal": signal,
            "stars": repo["stargazers_count"],
            "language": repo.get("language"),
            "topics": repo.get("topics", []),
            "created_at": repo["created_at"],
            "updated_at": repo["updated_at"],
            "pushed_at": repo["pushed_at"],
        })

    return news

def get_recent_repositories(
    keyword,
    category,
    days=GITHUB_RECENT_DAYS,
    limit=10
):
    since = get_date_days_ago(days)

    return search_repositories(
        keyword=keyword,
        category=category,
        time_filter=f"created:>={since}",
        signal="new_repository",
        min_stars=GITHUB_RECENT_MIN_STARS,
        sort="stars",
        limit=limit
    )


def get_active_repositories(
    keyword,
    category,
    days=GITHUB_ACTIVE_DAYS,
    limit=10
):
    since = get_date_days_ago(days)

    return search_repositories(
        keyword=keyword,
        category=category,
        time_filter=f"pushed:>={since}",
        signal="recently_active",
        min_stars=GITHUB_ACTIVE_MIN_STARS,
        sort="updated",
        limit=limit
    )

def get_github_news(
    recent_days=GITHUB_RECENT_DAYS,
    active_days=GITHUB_ACTIVE_DAYS,
    limit_per_topic=GITHUB_ITEMS_PER_FAMILY,
):
    all_news = []

    for category, keyword in SEARCH_FAMILIES.items():
        recent_news = collect_github_search_safely(
            get_recent_repositories,
            keyword=keyword,
            category=category,
            days=recent_days,
            limit=limit_per_topic,
            signal="recent repositories",
        )

        active_news = collect_github_search_safely(
            get_active_repositories,
            keyword=keyword,
            category=category,
            days=active_days,
            limit=limit_per_topic,
            signal="recently active repositories",
        )

        all_news.extend(recent_news)
        all_news.extend(active_news)

    return deduplicate_repositories(all_news)


def collect_github_search_safely(collector, signal, **kwargs):
    try:
        return collector(**kwargs)
    except requests.RequestException as error:
        category = kwargs.get("category", "unknown")
        print(
            f"  警告：跳过 GitHub {category} / {signal}"
            f"（{error.__class__.__name__}）"
        )
        return []


def deduplicate_repositories(news_items):
    unique_news = {}

    for item in news_items:
        unique_news[item["link"]] = item

    return list(unique_news.values())


if __name__ == "__main__":
    github_news = get_github_news(
        recent_days=90,
        active_days=14,
        limit_per_topic=5
    )

    print(f"\nGitHub 去重后共获取 {len(github_news)} 条内容\n")

    for item in github_news[:20]:
        print(
            item["category"],
            "|",
            item["signal"],
            "|",
            item["stars"],
            "|",
            item["title"]
        )

