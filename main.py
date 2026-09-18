import sys

from agent.analyzer import (
    analyze_news,
    finalize_analysis,
    generate_daily_trends,
)
from agent.prefilter import (
    prefilter_arxiv_news,
    prefilter_editorial_news,
    prefilter_github_news,
)
from agent.reporter import render_report
from agent.recent_outputs import (
    filter_recent_outputs,
    load_recent_outputs,
    record_final_outputs,
    save_recent_outputs,
)
from agent.topic_observer import (
    flatten_final_output,
    print_topic_family_distribution,
)
from collectors.github import get_github_news
from collectors.news import get_editorial_news
from collectors.rss import enrich_arxiv_candidates, get_rss_news
from settings import PREFILTER_CANDIDATE_LIMIT


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("=" * 72)
    print("AI BRIEF NEWS AGENT")
    print("=" * 72)

    print("\n[1/5] 正在采集候选内容...")
    arxiv_news = get_rss_news()
    github_news = get_github_news()
    editorial_news = get_editorial_news()
    print(f"  arXiv：{len(arxiv_news)} 条")
    print(f"  GitHub：{len(github_news)} 条")
    print(f"  官方博客与媒体：{len(editorial_news)} 条")
    print("\n  Topic family 观测（启发式分类，不参与筛选）：")
    print_topic_family_distribution("GitHub raw", github_news)

    history = load_recent_outputs()
    raw_counts = {
        "arXiv": len(arxiv_news),
        "GitHub": len(github_news),
        "官方博客与媒体": len(editorial_news),
    }
    arxiv_news = filter_recent_outputs(arxiv_news, history)
    github_news = filter_recent_outputs(github_news, history)
    editorial_news = filter_recent_outputs(editorial_news, history)
    print("\n  Recent-output cooldown：")
    print(f"  arXiv：{raw_counts['arXiv']} → {len(arxiv_news)} 条")
    print(f"  GitHub：{raw_counts['GitHub']} → {len(github_news)} 条")
    print(
        "  官方博客与媒体："
        f"{raw_counts['官方博客与媒体']} → {len(editorial_news)} 条"
    )

    print("\n[2/5] 正在进行来源专项预筛选...")
    arxiv_candidates = prefilter_arxiv_news(
        arxiv_news,
        max_candidates=PREFILTER_CANDIDATE_LIMIT,
    )
    github_candidates = prefilter_github_news(
        github_news,
        max_candidates=PREFILTER_CANDIDATE_LIMIT,
    )
    editorial_candidates = prefilter_editorial_news(
        editorial_news,
        max_candidates=PREFILTER_CANDIDATE_LIMIT,
    )
    arxiv_candidates = enrich_arxiv_candidates(arxiv_candidates)
    print(f"  arXiv：{len(arxiv_news)} → {len(arxiv_candidates)} 条")
    print(f"  GitHub：{len(github_news)} → {len(github_candidates)} 条")
    print(
        "  官方博客与媒体："
        f"{len(editorial_news)} → {len(editorial_candidates)} 条"
    )
    html_evidence_count = sum(
        item.get("evidence_level") == "html_sections"
        for item in arxiv_candidates
    )
    print(
        "  arXiv 正文证据："
        f"{html_evidence_count}/{len(arxiv_candidates)} 篇"
    )
    print("\n  Topic family 观测（启发式分类，不参与筛选）：")
    print_topic_family_distribution(
        "GitHub prefilter",
        github_candidates,
    )

    final_candidates = (
        arxiv_candidates
        + github_candidates
        + editorial_candidates
    )
    print(f"\n[3/5] Final Analyzer 候选：{len(final_candidates)} 条")
    print_topic_family_distribution(
        "Final Analyzer candidates",
        final_candidates,
    )

    if not final_candidates:
        result = finalize_analysis({}, [])
        print("\n[4/5] 四栏目筛选完成：0 条")
        print_topic_family_distribution("Final output", [])
        print("[5/5] Trend Summary：0 条\n")
        print(render_report(result))
        return

    raw_result = analyze_news(final_candidates)
    result = finalize_analysis(raw_result, final_candidates)

    print("\n[4/5] 四栏目筛选完成")
    print(f"  AI News：{len(result['news'])} 条")
    print(f"  Papers & Blogs：{len(result['papers_blogs'])} 条")
    print(f"  GitHub / Open Source：{len(result['open_source'])} 条")
    print(f"  Skills & Workflows：{len(result['skills'])} 条")
    print(f"  Today's Top 3：{len(result['top_items'])} 条")
    print_topic_family_distribution(
        "Final output",
        flatten_final_output(result),
    )

    result["daily_trends"] = generate_daily_trends(result)
    print(f"\n[5/5] Trend Summary：{len(result['daily_trends'])} 条\n")
    report = render_report(result)
    updated_history = record_final_outputs(
        history,
        result,
        final_candidates,
    )
    save_recent_outputs(updated_history)
    print(report)


if __name__ == "__main__":
    main()
