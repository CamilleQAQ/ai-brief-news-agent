import os

import requests
from dotenv import load_dotenv

from agent.analyzer import parse_json_response
from agent.topic_observer import classify_topic_family
from settings import (
    DEEPSEEK_API_URL,
    DEEPSEEK_MODEL,
    PREFILTER_MAX_TOKENS,
    PREFILTER_TOPIC_FAMILY_LIMIT,
)


load_dotenv()


session = requests.Session()


def build_arxiv_prefilter_prompt(news, max_candidates):
    items_text = ""

    for index, item in enumerate(news):
        items_text += f"""
{index}.
标题：{item.get("title", "")}
摘要：{item.get("summary", "")[:600]}
arXiv 分类：{item.get("category", "")}
观测主题家族：{classify_topic_family(item)}
"""

    return f"""
你是 AI 技术情报系统的 arXiv 候选筛选器。

请从下面的论文中选出最多 {max_candidates} 条，供下一阶段进行深度分析。
可以少选，也可以一条都不选。不要为了达到数量上限而降低标准。

重点判断：
- 方法、机制或架构是否有明显新意
- 是否涉及 Agent、LLM Systems、Reasoning、Model Architecture、Inference、AI Infra 或 Multimodal 等重要方向
- 是否可能成为更大技术趋势的一部分
- 对学习、项目、研究或求职是否可能有实际价值

应降低优先级或排除：
- 只做非常小的 incremental improvement
- 与 AI 技术主线关系较弱
- 摘要无法支持其新意或价值
- 只靠夸张措辞宣称重要性

约束：
- 比较同一主题家族内候选的边际信息价值，避免多个条目重复表达同一件事
- 同一主题家族通常最多选择 {PREFILTER_TOPIC_FAMILY_LIMIT} 条；没有合格的其他方向时允许少选，不得用低质量内容补位
- 只能使用输入中的标题、摘要和 arXiv 分类
- 不得脑补作者机构、实验结果、官方身份、采用情况或行业影响
- 不写摘要，不做最终 S/A/B/C 评级
- 只返回入选条目的索引

严格输出合法 JSON，不要输出 Markdown 或额外解释：

{{
    "selected_indices": [0, 3, 7]
}}

候选论文：
{items_text}
"""


def build_github_prefilter_prompt(news, max_candidates):
    items_text = ""

    for index, item in enumerate(news):
        topics = ", ".join(item.get("topics", []))
        items_text += f"""
{index}.
仓库：{item.get("title", "")}
描述：{item.get("summary", "")[:600]}
搜索分类：{item.get("category", "")}
观测主题家族：{classify_topic_family(item)}
候选信号：{item.get("signal", "")}
Stars：{item.get("stars", 0)}
语言：{item.get("language") or ""}
Topics：{topics}
创建时间：{item.get("created_at", "")}
更新时间：{item.get("updated_at", "")}
最近 Push：{item.get("pushed_at", "")}
"""

    return f"""
你是 AI 技术情报系统的 GitHub 候选筛选器。

请从下面的仓库中选出最多 {max_candidates} 条，供下一阶段进行深度分析。
可以少选，也可以一条都不选。不要为了达到数量上限而降低标准。

重点判断：
- 是否真正属于 Agent、LLM Systems、Reasoning、Inference、AI Infra、Evaluation、RAG 或 Multimodal 等 AI 主线
- 是否是有明确用途的新工具、框架、模型、基础设施或评测系统
- 描述中是否体现出实际工程价值或技术新意
- 是否值得学生学习、实践、研究或在求职时了解

必须过滤：
- Awesome List 或资源导航
- 教程、课程配套仓库和学习示例
- boilerplate、模板、starter 和普通应用 Demo
- 简单聊天壳或缺少技术内容的 API 包装
- 与 AI 前沿关系较弱的通用项目
- 仅仅因为 Stars 很高而入选的项目

约束：
- Agent、MCP、Coding Agent、Agent Evaluation、Agent Memory、RAG 和 Agent Harness 都计入 Agent 家族
- 比较同一家族内项目的边际信息价值；Agent 家族最多选择 {PREFILTER_TOPIC_FAMILY_LIMIT} 条
- 主动检查 Training、Reasoning、Evaluation、Multimodal、Systems-Inference 中是否有同等或更高价值项目
- 不得为了满足多样性选择低质量项目；不足 {max_candidates} 条时允许少选
- Stars 只能作为辅助信息，不能作为入选的主要理由
- 只能使用输入提供的仓库信息
- 不得根据仓库名脑补官方身份、公司采用情况、benchmark 或行业影响
- 描述缺少足够证据时应谨慎筛选
- 不写摘要，不做最终 S/A/B/C 评级
- 只返回入选条目的索引

严格输出合法 JSON，不要输出 Markdown 或额外解释：

{{
    "selected_indices": [0, 3, 7]
}}

候选仓库：
{items_text}
"""


def build_editorial_prefilter_prompt(news, max_candidates):
    items_text = ""

    for index, item in enumerate(news):
        items_text += f"""
{index}.
标题：{item.get("title", "")}
摘要：{item.get("summary", "")[:700]}
来源：{item.get("source", "")}
来源等级：Tier {item.get("source_tier", "")}
发布时间：{item.get("published_at", "")}
观测主题家族：{classify_topic_family(item)}
"""

    return f"""
你是 AI 技术情报系统的官方博客与行业新闻预筛选器。

请从下面内容中选出最多 {max_candidates} 条，供下一阶段进行深度分析。
可以少选，也可以一条都不选。不要为了达到数量上限而降低标准。

优先选择：
- 新模型发布或重要模型更新
- API、价格、上下文窗口、工具能力或开源策略的重大变化
- Agent、Coding Agent、Reasoning、Inference、AI Infra、Evaluation、Multimodal 等主线的重要技术发布
- 值得认真阅读的研究报告、系统文章、架构解析或高质量技术博客
- 重要合作、收购、开源或战略变化，但必须与 AI 技术主线直接相关

降低优先级或排除：
- 普通公司宣传、品牌活动、招聘和泛政策评论
- 缺少技术内容的产品营销
- 重复报道、轻微功能更新或一般行业评论
- 与项目关注方向关系较弱的内容

来源规则：
- 比较同一主题家族内内容的边际信息价值，同一家族通常最多选择 {PREFILTER_TOPIC_FAMILY_LIMIT} 条
- 没有合格的其他方向时允许少选，不得为了多样性降低质量标准
- Tier 1 是一手或研究型来源，但不能因此自动入选
- Tier 2 可用于高质量行业解释和趋势判断
- Tier 3 只用于快速事件信号，不能把推测或传闻当成事实
- 只能根据输入的标题、摘要、来源和时间判断
- 不得脑补未提供的 benchmark、采用情况或行业影响
- 不写长摘要，不做最终 S/A/B/C 评级
- 只返回入选条目的索引

严格输出合法 JSON，不要输出 Markdown 或额外解释：

{{
    "selected_indices": [0, 3, 7]
}}

候选内容：
{items_text}
"""


def request_selected_indices(prompt):
    api_key = os.getenv("DEEPSEEK_API_KEY")

    if not api_key:
        raise RuntimeError(
            "没有找到 DEEPSEEK_API_KEY，请检查 .env 文件"
        )

    data = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
        "reasoning_effort": "none",
        "response_format": {
            "type": "json_object"
        },
        "max_tokens": PREFILTER_MAX_TOKENS,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    response = session.post(
        DEEPSEEK_API_URL,
        headers=headers,
        json=data,
        timeout=60,
    )

    response.raise_for_status()

    content = response.json()["choices"][0]["message"]["content"]
    result = parse_json_response(content)

    if not isinstance(result, dict):
        return []

    return result.get("selected_indices", [])


def select_items_by_indices(
    news,
    indices,
    max_candidates,
    max_per_family=PREFILTER_TOPIC_FAMILY_LIMIT,
):
    selected = []
    seen_indices = set()
    family_counts = {}

    if not isinstance(indices, list):
        return selected

    for index in indices:
        if isinstance(index, bool) or not isinstance(index, int):
            continue

        if index < 0 or index >= len(news) or index in seen_indices:
            continue

        item = news[index]
        family = classify_topic_family(item)

        if (
            family != "Other"
            and family_counts.get(family, 0) >= max_per_family
        ):
            continue

        selected.append(item)
        seen_indices.add(index)
        family_counts[family] = family_counts.get(family, 0) + 1

        if len(selected) == max_candidates:
            break

    return selected


def prefilter_arxiv_news(news, max_candidates=10):
    if not news:
        return []

    prompt = build_arxiv_prefilter_prompt(news, max_candidates)
    indices = request_selected_indices(prompt)
    return select_items_by_indices(news, indices, max_candidates)


def prefilter_github_news(news, max_candidates=10):
    if not news:
        return []

    prompt = build_github_prefilter_prompt(news, max_candidates)
    indices = request_selected_indices(prompt)
    return select_items_by_indices(news, indices, max_candidates)


def prefilter_editorial_news(news, max_candidates=10):
    if not news:
        return []

    prompt = build_editorial_prefilter_prompt(news, max_candidates)
    indices = request_selected_indices(prompt)
    return select_items_by_indices(news, indices, max_candidates)
