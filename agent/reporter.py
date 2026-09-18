REPORT_WIDTH = 72

SECTION_LABELS = {
    "news": "AI News",
    "papers_blogs": "Papers & Blogs",
    "open_source": "GitHub / Open Source",
    "skills": "Skills & Workflows",
}


def render_report(result):
    sections = [
        ("AI NEWS", "news", render_news_item),
        ("PAPERS & BLOGS", "papers_blogs", render_paper_item),
        ("GITHUB / OPEN SOURCE", "open_source", render_open_source_item),
        ("SKILLS & WORKFLOWS", "skills", render_skill_item),
    ]
    total = sum(len(result.get(key, [])) for _, key, _ in sections)
    lines = [
        "=" * REPORT_WIDTH,
        "AI BRIE NEWS AGENT · DAILY BRIEF",
        f"本期共 {total} 条高价值内容",
        "=" * REPORT_WIDTH,
    ]
    lines.extend(render_top_items(result.get("top_items", [])))

    for title, key, renderer in sections:
        lines.extend(render_section(title, result.get(key, []), renderer))

    lines.extend(render_trends(result.get("daily_trends", [])))
    lines.append("=" * REPORT_WIDTH)
    return "\n".join(lines)


def render_top_items(items):
    lines = [
        "",
        "TODAY'S TOP 3",
        "今天最值得投入时间的内容，不代表今天刚发布",
        "-" * REPORT_WIDTH,
    ]

    if not items:
        lines.append("今日暂无")
        return lines

    for index, item in enumerate(items[:3], start=1):
        section = SECTION_LABELS.get(item.get("section"), "其他")
        lines.extend([
            "",
            f"{index}. {item.get('title', '无标题')}",
            f"栏目：{section}",
        ])
        lines.extend(compact_lines([
            ("价值", shorten_text(item.get("why"))),
            ("建议", shorten_text(item.get("action"))),
            ("链接", item.get("url")),
        ]))

    return lines


def shorten_text(value, max_chars=120):
    text = " ".join(str(value or "").split())

    if len(text) <= max_chars:
        return text

    for punctuation in ("。", "！", "？", ". ", "! ", "? "):
        position = text.find(punctuation)
        if 0 < position < max_chars:
            return text[:position + len(punctuation)].strip()

    return text[:max_chars - 1].rstrip() + "…"


def render_section(title, items, renderer):
    lines = ["", title, "-" * REPORT_WIDTH]

    if not items:
        lines.append("今日暂无")
        return lines

    for index, item in enumerate(items, start=1):
        lines.extend(["", f"{index}. {item.get('title', '无标题')}"])
        lines.extend(renderer(item))

    return lines


def render_news_item(item):
    return compact_lines([
        ("摘要", item.get("summary")),
        ("价值", item.get("why_it_matters")),
        ("注意", item.get("caution")),
        ("来源", item.get("source")),
        ("链接", item.get("url")),
    ])


def render_paper_item(item):
    return compact_lines([
        ("方向", item.get("direction")),
        ("摘要", item.get("summary")),
        ("为什么读", item.get("why_read")),
        ("你会获得", item.get("what_you_get")),
        ("注意", item.get("caution")),
        ("来源", item.get("source")),
        ("链接", item.get("url")),
    ])


def render_open_source_item(item):
    stars = item.get("stars")
    star_text = str(stars) if isinstance(stars, int) else ""

    return compact_lines([
        ("方向", item.get("direction")),
        ("摘要", item.get("summary")),
        ("价值", item.get("why_it_matters")),
        ("建议行动", item.get("what_to_do")),
        ("注意", item.get("caution")),
        ("Stars", star_text),
        ("链接", item.get("url")),
    ])


def render_skill_item(item):
    return compact_lines([
        ("它能做什么", item.get("what_it_does")),
        ("为什么实用", item.get("why_useful")),
        ("适用场景", item.get("use_case")),
        ("如何尝试", item.get("how_to_try")),
        ("注意", item.get("caution")),
        ("链接", item.get("url")),
    ])


def compact_lines(fields):
    return [
        f"{label}：{value}"
        for label, value in fields
        if value not in (None, "")
    ]


def render_trends(trends):
    lines = ["", "TREND SUMMARY", "-" * REPORT_WIDTH]

    if not trends:
        lines.append("今日暂无明显趋势变化")
        return lines

    for index, trend in enumerate(trends, start=1):
        lines.append(f"{index}. {trend}")

    return lines
