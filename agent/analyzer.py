import json
import os
from pathlib import Path

from json_repair import repair_json
import requests
from dotenv import load_dotenv

from agent.topic_observer import classify_topic_family, resolve_topic_family
from settings import (
    DEEPSEEK_API_URL,
    DEEPSEEK_MODEL,
    FINAL_ANALYZER_MAX_TOKENS,
    FINAL_SECTION_LIMITS,
    FINAL_SUBTOPIC_LIMIT,
    FINAL_TOPIC_FAMILY_LIMIT,
    TREND_MAX_TOKENS,
)


load_dotenv()


PREFERENCES_PATH = Path(__file__).resolve().parent.parent / "preferences.json"

# Final selection pipeline:
# DeepSeek component scores -> score normalization -> quality gate ->
# Python rating/sort -> section and topic caps -> public output fields -> Top 3.
# Preferences are only the last sort tie-breaker; they never bypass quality.

SYSTEM_PROMPT = (
    "你是一名服务于中高水平本科生、研究生和早期研究者的 AI 技术情报分析师。"
)

GENERIC_CAUTIONS = {
    "需进一步验证",
    "需要进一步验证",
    "需阅读全文确认",
    "需要阅读全文确认",
    "需读全文确认",
    "需要读全文确认",
    "需自行确认",
    "需要自行确认",
    "需确认兼容性",
    "需要确认兼容性",
    "兼容性待确认",
    "实际效果有待观察",
    "稳定性未知",
    "生态不成熟",
}
UNSUPPORTED_ABSENCE_CLAIMS = (
    "未经独立复现",
    "尚无独立复现",
    "缺少独立复现",
    "缺少第三方",
    "未提供独立",
    "没有独立",
    "未见第三方",
    "输入未提供",
    "兼容性未知",
    "稳定性未知",
    "生态不成熟",
)

session = requests.Session()


def load_preferences(path=PREFERENCES_PATH):
    if not path.exists():
        return {"preferred_tracks": [], "current_focus": []}

    with path.open("r", encoding="utf-8") as file:
        raw_preferences = json.load(file)

    return {
        "preferred_tracks": clean_string_list(
            raw_preferences.get("preferred_tracks", [])
        ),
        "current_focus": clean_string_list(
            raw_preferences.get("current_focus", [])
        ),
    }


def clean_string_list(values):
    if not isinstance(values, list):
        return []

    return [
        value.strip()
        for value in values
        if isinstance(value, str) and value.strip()
    ]


def build_prompt(candidates, preferences=None):
    candidates_text = ""

    for index, item in enumerate(candidates):
        arxiv_evidence = ""

        if item.get("source") == "arXiv":
            arxiv_evidence = f"""
arXiv ID：{item.get("arxiv_id", "")}
作者：{", ".join(item.get("authors") or [])}
全部分类：{", ".join(item.get("categories") or [])}
发布类型：{item.get("announce_type", "")}
证据等级：{item.get("evidence_level", "abstract_only")}
正文证据章节：{", ".join(item.get("evidence_sections") or [])}
候选 artifact 链接（需核验）：{", ".join(item.get("artifact_links") or [])}
正文证据：{item.get("evidence_text", "")}
"""

        candidates_text += f"""
{index}.
标题：{item.get("title", "")}
链接：{item.get("link", "")}
摘要：{item.get("summary", "")[:900]}
来源：{item.get("source", "")}
候选分类：{item.get("category", "")}
观测主题家族：{classify_topic_family(item)}
来源等级：{item.get("source_tier", "")}
GitHub Stars：{item.get("stars", "")}
GitHub 语言：{item.get("language", "")}
GitHub Topics：{", ".join(item.get("topics") or [])}
GitHub 创建时间：{item.get("created_at", "")}
GitHub 更新时间：{item.get("updated_at", "")}
GitHub 最近 Push：{item.get("pushed_at", "")}
发布时间：{item.get("published_at", "")}
{arxiv_evidence}
"""

    return f"""
你是个人 AI Daily Brief 的最终分析器。

你的核心目标不是覆盖尽可能多的 AI 新闻，而是：

从候选内容中筛选出，对想提升科研能力、工程能力、项目质量和求职竞争力的本科生、硕士生和早期研究者，学习收益 / 时间投入比最高的内容。

Daily Brief 的目标是“今天最值得用户知道和投入时间的内容”，不是只筛选“今天刚发布的内容”。发布时间是背景信息，不能覆盖 student_value、novelty、evidence_quality、reproducibility 和 actionability。

始终遵守：
- 宁缺毋滥，不为了填满栏目凑数量
- 学习价值 > 热度
- 方法论 > 新闻感
- 可复现性 > 营销宣传
- 技术深度 > Star 数
- 前沿不等于值得投入时间

## 重点方向

- Agent & LLM Systems
- Reasoning & Model Architecture
- Training & Post-training
- Efficient AI & AI Infrastructure
- Multimodal
- Evaluation
- 极少数真正重要的 AI for Science

## 学生价值判断

对每条候选先问：一个想提升竞争力的本科生或研究生，看完到底能获得什么？

优先保留：
- 新 problem formulation、evaluation methodology 或实验设计
- 新训练策略、系统架构或建模方式
- 有代码、checkpoint、数据、完整配置、benchmark 或 reproducible harness
- 能衍生 course project、research project、复现、benchmark、作品集或实习项目
- 能帮助理解 runtime、inference、training infrastructure、evaluation、code intelligence 或 developer tooling

不要仅因为内容“很前沿”就提高优先级。

## arXiv 证据判断

title 和 abstract 只用于候选召回，不能单独证明论文贡献或实验质量。
对于 evidence_level=html_sections 的论文，必须结合正文证据判断：
- 方法相对已有工作具体改变了什么
- 实验覆盖哪些任务、数据集和 baseline
- 核心 claim 是否有对应实验证据
- 是否提供代码、数据或 checkpoint
- 正文是否明确写出适用范围或 limitation

正文证据仍然属于作者自述，不等于 peer review 或独立复现。
如果 evidence_level=abstract_only，应降低对强 claim 的确信，不得自行补全正文实验、baseline、代码或 limitation。

## 防止主题坍缩

Python 会在最终选择时执行两层限制：同一个细分主题最多保留 3 条，同一个主题家族最多保留 4 条。
你仍应先按质量和边际信息价值筛选，不要依赖 Python 截断。

每条内容必须输出一个 topic_family，只能是：
Agent、Training、Reasoning、Evaluation、Multimodal、Systems-Inference、Other。

Agent Memory、MCP、Coding Agent、Multi-Agent、Agent Harness/Runtime、RAG/Context Engineering 和 Agent Evaluation 虽然是不同 subtopic，但全部属于 Agent 主题家族。

如果候选大量集中在 Agent、MCP、Memory 或 Coding Agent：
- 比较边际信息价值，只保留最有代表性的方法、系统或工具
- 主动检查 Model Architecture、Reasoning、Training/Post-training、Multimodal、Efficient Inference/Systems 和 Evaluation 是否有更值得保留的内容
- 不要为了多样性选低质量内容；没有好内容的方向可以为空

每条入选内容必须输出一个 subtopic，优先使用以下规范名称：
Agent Memory、MCP、Coding Agent、Multi-Agent、Agent Harness/Runtime、RAG/Context Engineering、Agent Evaluation、Model Architecture、Reasoning、Training/Post-training、Multimodal、Efficient Inference/Systems、Evaluation、AI for Science、Industry/Product Event、Other。

## GitHub 判断

Stars 只允许作为辅助背景，不能主导选择。
主要判断技术新意、真实问题、架构学习价值、可复现性、工程价值，以及是否只是已有工具的重新包装。
低 Star 的新方法可以高于高 Star 的普通 wrapper。
Awesome List、普通教程、boilerplate、泛 AI Demo 和缺少技术内容的包装项目必须排除。

## 事实与作者宣称

README、Blog 或项目介绍中的 SOTA、10x faster、99% reduction、millisecond indexing、better than、significantly cheaper 等说法，如果主要来自作者自己的 benchmark，必须写成：
- “作者报告……”
- “项目宣称……”
- “根据项目提供的 benchmark……”

不能写成已经独立验证的事实。

caution 默认必须返回空字符串。只有输入中的标题、摘要或元数据明确提供了具体限制证据时才能输出 caution，同时必须提供 caution_basis：
- caution_basis 必须是从候选输入中逐字复制的一小段证据，不得改写或概括
- 例如输入明确写了只在两个任务上实验，才可以说明实验范围有限
- 不得因为输入没有提到某件事，就推断“缺少第三方 benchmark”“尚无独立复现”“稳定性未知”或“生态不成熟”
- 不得生成“需进一步验证”“需阅读全文确认”“需确认兼容性”等没有具体信息的万能免责声明
- 如果找不到可以逐字引用的 limitation 依据，caution 和 caution_basis 都返回空字符串

GitHub 创建时间只说明仓库创建日期，不能据此推断项目刚发布、生态不成熟或稳定性未知。更新时间和 Push 时间也不能证明生产采用或成熟度。

## 栏目规则

### AI News：0–5 条
只收录真正影响学习、研究或工程判断的模型发布、重大能力/API/价格变化、重要开源、benchmark 或行业级技术事件。
普通论文和普通仓库不能进入 News。

### Papers & Blogs：0–5 条
只收录值得认真投入阅读时间的论文、研究博客、技术报告、系统文章和评测文章。
why_read 必须回答为什么学生值得投入时间。
what_you_get 必须具体说明可以学到的方法、建模方式、实验设计或系统知识。

### GitHub / Open Source：0–5 条
只收录值得阅读源码、运行、复现或用于项目的工程内容。
why_it_matters 要明确偏学习价值、工具价值、项目价值还是研究价值。
what_to_do 应根据真实价值选择：阅读 README、阅读核心源码、clone 并运行、做最小实验、收藏即可、暂时不用投入时间。不要全部写成 clone。

### Skills & Workflows：0–3 条
只保留能立即提升科研、开发或求职效率的 Skill、MCP Server、工作流或小型工具。
普通 GitHub 项目不能为了填栏目塞进来；没有足够好的内容就返回空数组。

## 来源约束

- arXiv 只能进入 Papers & Blogs
- GitHub 只能进入 GitHub / Open Source 或 Skills & Workflows
- 官方博客和媒体可以进入 AI News、Papers & Blogs；明确可直接使用的工作流也可以进入 Skills & Workflows
- 每个候选最多进入一个栏目
- Tier 不代表内容自动重要
- 只能使用输入信息，不得编造安装命令、官方身份、采用情况或独立验证结果

## 内部评分

每条入选内容输出以下 1–5 JSON 整数。评分用于辅助判断，不能简单机械求和排序：

- student_value：对科研、项目、工程或求职是否有明显帮助
- novelty：是否有真正的新方法、新架构或新问题定义
- reproducibility：是否有代码、数据、配置、checkpoint 或清晰可复现实验
- evidence_quality：claim 的证据质量和可信度
- actionability：用户能否马上阅读、clone、实验或加入项目
- redundancy_penalty：与当天其他内容的重复程度；1 表示几乎不重复，5 表示高度重复

## 输出要求

- title 使用简洁中文标题
- candidate_index 必须对应输入索引
- direction 使用上述重点方向之一
- subtopic 使用上述规范细分主题之一
- topic_family 使用上述七个主题家族之一；Agent Evaluation 等 Agent 相关评测必须归入 Agent
- 内容简洁，不写长篇评价
- daily_trends 本轮固定返回空数组，最终可见内容确定后再生成
- 严格输出合法 JSON，不要输出 Markdown 或额外解释

JSON 格式：

{{
  "news": [
    {{
      "candidate_index": 0,
      "title": "中文标题",
      "summary": "发生了什么",
      "why_it_matters": "对学生或早期研究者的实际价值",
      "caution": "有输入证据时才输出具体限制，否则为空字符串",
      "caution_basis": "从候选输入逐字复制的依据，否则为空字符串",
      "direction": "Reasoning & Model Architecture",
      "subtopic": "Reasoning",
      "topic_family": "Reasoning",
      "student_value": 4,
      "novelty": 4,
      "reproducibility": 3,
      "evidence_quality": 4,
      "actionability": 3,
      "redundancy_penalty": 1
    }}
  ],
  "papers_blogs": [
    {{
      "candidate_index": 1,
      "title": "中文标题",
      "summary": "内容概要",
      "why_read": "为什么学生值得投入阅读时间",
      "what_you_get": "可以具体学到什么",
      "caution": "有输入证据时才输出具体限制，否则为空字符串",
      "caution_basis": "从候选输入逐字复制的依据，否则为空字符串",
      "direction": "Evaluation",
      "subtopic": "Evaluation",
      "topic_family": "Evaluation",
      "student_value": 5,
      "novelty": 4,
      "reproducibility": 3,
      "evidence_quality": 3,
      "actionability": 4,
      "redundancy_penalty": 1
    }}
  ],
  "open_source": [
    {{
      "candidate_index": 2,
      "title": "中文标题",
      "summary": "项目概要",
      "why_it_matters": "说明学习、工具、项目或研究价值",
      "what_to_do": "一个与投入价值匹配的具体行动",
      "caution": "有输入证据时才输出具体限制，否则为空字符串",
      "caution_basis": "从候选输入逐字复制的依据，否则为空字符串",
      "direction": "Efficient AI & AI Infrastructure",
      "subtopic": "Efficient Inference/Systems",
      "topic_family": "Systems-Inference",
      "student_value": 4,
      "novelty": 3,
      "reproducibility": 4,
      "evidence_quality": 3,
      "actionability": 5,
      "redundancy_penalty": 1
    }}
  ],
  "skills": [
    {{
      "candidate_index": 3,
      "title": "中文标题",
      "what_it_does": "它能做什么",
      "why_useful": "为什么能提升效率",
      "use_case": "具体适用场景",
      "how_to_try": "基于输入信息的简短尝试方式",
      "caution": "有输入证据时才输出具体限制，否则为空字符串",
      "caution_basis": "从候选输入逐字复制的依据，否则为空字符串",
      "direction": "Agent & LLM Systems",
      "subtopic": "MCP",
      "topic_family": "Agent",
      "student_value": 4,
      "novelty": 3,
      "reproducibility": 4,
      "evidence_quality": 3,
      "actionability": 5,
      "redundancy_penalty": 2
    }}
  ],
  "daily_trends": []
}}

## 最终质量检查

生成前逐项检查并在发现问题时重新调整：
1. Agent 内容比例是否过高，是否把 Agent Evaluation 错算成独立的 Evaluation 家族
2. 某一细分主题是否超过 3 条，某一主题家族是否超过 4 条
3. 是否存在高度重复条目
4. 是否因为 Stars 高保留了普通项目
5. 是否把作者 claim 写成确定事实，是否生成了输入没有支持的项目年龄、成熟度、稳定性或验证状态
6. 是否存在看起来高级、但学生读完没有明显收获的内容
7. 是否遗漏更有价值的 Training、Architecture、Reasoning、Multimodal、Inference 或 Evaluation 内容
8. 每条是否真的值得用户花时间
9. 每条非空 caution 是否都有输入中逐字可查的 caution_basis
10. 是否出现“需进一步验证”“需阅读全文确认”等万能免责声明

候选内容：
{candidates_text}
"""


def analyze_news(candidates):
    if not candidates:
        raise ValueError("candidates 为空，没有内容可以分析")

    return request_deepseek_json(
        build_prompt(candidates),
        max_tokens=FINAL_ANALYZER_MAX_TOKENS,
    )


def request_deepseek_json(prompt, max_tokens):
    api_key = os.getenv("DEEPSEEK_API_KEY")

    if not api_key:
        raise RuntimeError(
            "没有找到 DEEPSEEK_API_KEY，请检查 .env 文件"
        )

    response = session.post(
        DEEPSEEK_API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": DEEPSEEK_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "thinking": {"type": "disabled"},
            "response_format": {"type": "json_object"},
            "max_tokens": max_tokens,
        },
        timeout=90,
    )

    if not response.ok:
        print("DeepSeek API 请求失败")
        print("状态码：", response.status_code)
        print("错误信息：", response.text)

    response.raise_for_status()

    content = response.json()["choices"][0]["message"]["content"]
    return parse_json_response(content)


def parse_json_response(content):
    text = content.strip()

    if text.startswith("```json"):
        text = text[7:]

    if text.startswith("```"):
        text = text[3:]

    if text.endswith("```"):
        text = text[:-3]

    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        print("JSON 格式异常，尝试自动修复...")
        return repair_json(text, return_objects=True)


def finalize_analysis(result, candidates):
    finalized = empty_result()

    if not isinstance(result, dict):
        return finalized

    preferences = load_preferences()
    prepared_items = []

    for section in FINAL_SECTION_LIMITS:
        prepared_items.extend(
            prepare_section_items(
                result.get(section, []),
                section,
                candidates,
            )
        )

    prepared_items.sort(
        key=lambda item: selection_key(item, preferences),
        reverse=True,
    )

    selected_items = apply_selection_constraints(prepared_items)

    for item in selected_items:
        candidate = candidates[item["candidate_index"]]
        public_item = build_public_item(
            item["section"],
            item,
            candidate,
        )
        finalized[item["section"]].append(public_item)

        if len(finalized["top_items"]) < 3:
            finalized["top_items"].append(
                build_top_item(item["section"], public_item)
            )

    return finalized


def empty_result():
    return {
        "news": [],
        "papers_blogs": [],
        "open_source": [],
        "skills": [],
        "top_items": [],
        "daily_trends": [],
    }


def prepare_section_items(raw_items, section, candidates):
    prepared = []

    if not isinstance(raw_items, list):
        return prepared

    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue

        candidate_index = normalize_nonnegative_int(
            raw_item.get("candidate_index")
        )

        if candidate_index is None or candidate_index >= len(candidates):
            continue

        candidate = candidates[candidate_index]

        if not section_accepts_source(section, candidate.get("source")):
            continue

        item = dict(raw_item)
        item["candidate_index"] = candidate_index
        item["section"] = section
        item["topic_family"] = resolve_topic_family(item, candidate)
        normalize_internal_scores(item)
        item["rating"] = calculate_rating(item)

        if meets_quality_bar(item, section):
            prepared.append(item)

    return prepared


def normalize_internal_scores(item):
    for field in (
        "student_value",
        "novelty",
        "reproducibility",
        "evidence_quality",
        "actionability",
        "redundancy_penalty",
    ):
        item[field] = normalize_score(item.get(field), 1, 5)


def meets_quality_bar(item, section):
    if item["student_value"] < 3 or item["evidence_quality"] < 2:
        return False

    if item["redundancy_penalty"] >= 5:
        return False

    if section == "news":
        return item["evidence_quality"] >= 3

    if section == "papers_blogs":
        return max(item["novelty"], item["reproducibility"]) >= 3

    if section == "open_source":
        return (
            item["actionability"] >= 3
            and max(item["novelty"], item["reproducibility"]) >= 3
        )

    return (
        item["student_value"] >= 4
        and item["actionability"] >= 4
        and item["evidence_quality"] >= 3
    )


def selection_key(item, preferences):
    preference_match = matches_preferences(item, preferences)
    rating_rank = {"S": 3, "A": 2, "B": 1, "C": 0}[item["rating"]]

    return (
        rating_rank,
        item["student_value"],
        item["evidence_quality"],
        item["reproducibility"],
        item["actionability"],
        item["novelty"],
        -item["redundancy_penalty"],
        preference_match,
    )


def matches_preferences(item, preferences):
    direction = normalize_text(item.get("direction"))
    searchable_text = normalize_text(" ".join([
        item.get("title", ""),
        item.get("direction", ""),
        item.get("subtopic", ""),
        item.get("topic_family", ""),
    ]))

    preferred_tracks = {
        normalize_text(track)
        for track in preferences.get("preferred_tracks", [])
    }

    if direction and direction in preferred_tracks:
        return 1

    return int(any(
        normalize_text(focus) in searchable_text
        for focus in preferences.get("current_focus", [])
        if normalize_text(focus)
    ))


def apply_selection_constraints(items):
    selected = []
    used_indices = set()
    section_counts = {section: 0 for section in FINAL_SECTION_LIMITS}
    subtopic_counts = {}
    family_counts = {}

    for item in items:
        section = item["section"]
        candidate_index = item["candidate_index"]

        if candidate_index in used_indices:
            continue

        if section_counts[section] >= FINAL_SECTION_LIMITS[section]:
            continue

        subtopic = normalize_text(item.get("subtopic"))
        topic_family = item.get("topic_family", "Other")

        if (
            topic_family != "Other"
            and family_counts.get(topic_family, 0)
            >= FINAL_TOPIC_FAMILY_LIMIT
        ):
            continue

        if is_counted_subtopic(subtopic):
            if subtopic_counts.get(subtopic, 0) >= FINAL_SUBTOPIC_LIMIT:
                continue

            subtopic_counts[subtopic] = subtopic_counts.get(subtopic, 0) + 1

        selected.append(item)
        used_indices.add(candidate_index)
        section_counts[section] += 1
        family_counts[topic_family] = family_counts.get(topic_family, 0) + 1

    return selected


def is_counted_subtopic(subtopic):
    return subtopic not in ("", "other", "其他", "industry/product event")


def section_accepts_source(section, source):
    if source == "arXiv":
        return section == "papers_blogs"

    if source == "GitHub":
        return section in ("open_source", "skills")

    return section in ("news", "papers_blogs", "skills")


def build_public_item(section, item, candidate):
    title = item.get("title") or candidate.get("title", "无标题")
    url = candidate.get("link", "")
    source = candidate.get("source", "")
    caution = get_grounded_caution(item, candidate)

    if section == "news":
        public_item = {
            "title": title,
            "summary": item.get("summary", ""),
            "why_it_matters": item.get("why_it_matters", ""),
            "source": source,
            "url": url,
        }
    elif section == "papers_blogs":
        public_item = {
            "title": title,
            "summary": item.get("summary", ""),
            "why_read": item.get("why_read", ""),
            "what_you_get": item.get("what_you_get", ""),
            "direction": item.get("direction", "其他"),
            "source": source,
            "url": url,
        }
    elif section == "open_source":
        public_item = {
            "title": title,
            "summary": item.get("summary", ""),
            "why_it_matters": item.get("why_it_matters", ""),
            "direction": item.get("direction", "其他"),
            "stars": candidate.get("stars", 0),
            "what_to_do": item.get("what_to_do", ""),
            "url": url,
        }
    else:
        public_item = {
            "title": title,
            "what_it_does": item.get("what_it_does", ""),
            "why_useful": item.get("why_useful", ""),
            "use_case": item.get("use_case", ""),
            "how_to_try": item.get("how_to_try", ""),
            "url": url,
        }

    if caution:
        public_item["caution"] = caution

    return public_item


def build_top_item(section, public_item):
    return {
        "title": public_item.get("title", "无标题"),
        "section": section,
        "why": (
            public_item.get("why_it_matters")
            or public_item.get("why_read")
            or public_item.get("why_useful")
            or ""
        ),
        "action": (
            public_item.get("what_to_do")
            or public_item.get("how_to_try")
            or public_item.get("what_you_get")
            or ""
        ),
        "url": public_item.get("url", ""),
    }


def get_grounded_caution(item, candidate):
    caution = clean_text_value(item.get("caution"))
    basis = clean_text_value(item.get("caution_basis"))

    if not caution or not basis or is_generic_caution(caution):
        return ""

    source_text = " ".join(
        clean_text_value(value)
        for value in (
            candidate.get("title"),
            candidate.get("summary"),
            candidate.get("category"),
            candidate.get("language"),
            " ".join(candidate.get("topics") or []),
            candidate.get("created_at"),
            candidate.get("updated_at"),
            candidate.get("pushed_at"),
            candidate.get("published_at"),
            candidate.get("evidence_text"),
        )
    )

    normalized_source = normalize_evidence(source_text)

    if normalize_evidence(basis) not in normalized_source:
        return ""

    if any(
        claim in caution and claim not in source_text
        for claim in UNSUPPORTED_ABSENCE_CLAIMS
    ):
        return ""

    return caution


def clean_text_value(value):
    return value.strip() if isinstance(value, str) else ""


def normalize_evidence(value):
    normalized = normalize_text(value)

    for prefix in ("标题:", "标题：", "摘要:", "摘要：", "描述:", "描述："):
        if normalized.startswith(prefix.casefold()):
            normalized = normalized[len(prefix):].strip()

    return normalized


def is_generic_caution(caution):
    normalized = caution.strip().rstrip("。.!！")
    return normalized in GENERIC_CAUTIONS


def generate_daily_trends(result):
    visible_items = []

    for section in FINAL_SECTION_LIMITS:
        for item in result.get(section, []):
            visible_items.append({
                "section": section,
                "title": item.get("title", ""),
                "summary": (
                    item.get("summary")
                    or item.get("what_it_does")
                    or ""
                ),
            })

    if not visible_items:
        return []

    prompt = f"""
根据下面这些最终可见的 Daily Brief 条目，生成 0–4 条简短、具体、客观的中文趋势总结。

规则：
- 只能综合下面最终输出中已经出现的内容
- 每条趋势必须由至少两个相互独立的可见条目共同支持
- 明确指出多个条目分别从哪些层面体现了什么共同变化
- 不得引用隐藏候选、外部知识或用户偏好
- 禁止“AI 正在快速发展”“Agent 越来越重要”“多模态值得关注”等空泛结论
- 不要为了凑数量强行关联；没有明显趋势时返回空数组
- 严格输出合法 JSON，不要输出额外解释

格式：
{{
  "daily_trends": ["趋势 1", "趋势 2"]
}}

最终可见条目：
{json.dumps(visible_items, ensure_ascii=False)}
"""

    trend_result = request_deepseek_json(
        prompt,
        max_tokens=TREND_MAX_TOKENS,
    )

    if not isinstance(trend_result, dict):
        return []

    trends = trend_result.get("daily_trends", [])

    if not isinstance(trends, list):
        return []

    return [
        trend.strip()
        for trend in trends[:4]
        if isinstance(trend, str) and trend.strip()
    ]


def calculate_rating(item):
    student_value = item.get("student_value", 1)
    evidence = item.get("evidence_quality", 1)
    reproducibility = item.get("reproducibility", 1)
    actionability = item.get("actionability", 1)
    novelty = item.get("novelty", 1)
    redundancy = item.get("redundancy_penalty", 5)

    if (
        student_value == 5
        and evidence >= 4
        and max(novelty, reproducibility, actionability) >= 4
        and redundancy <= 2
    ):
        return "S"

    if (
        student_value >= 4
        and evidence >= 3
        and max(novelty, reproducibility, actionability) >= 4
        and redundancy <= 3
    ):
        return "A"

    if student_value >= 3 and evidence >= 2 and redundancy <= 4:
        return "B"

    return "C"


def normalize_score(value, minimum, maximum):
    number = normalize_nonnegative_int(value)

    if number is None or not minimum <= number <= maximum:
        return minimum

    return number


def normalize_nonnegative_int(value):
    if isinstance(value, bool):
        return None

    if isinstance(value, int):
        number = value
    elif isinstance(value, float) and value.is_integer():
        number = int(value)
    elif isinstance(value, str):
        try:
            number = int(value.strip())
        except ValueError:
            return None
    else:
        return None

    return number if number >= 0 else None


def normalize_text(value):
    return " ".join(str(value or "").casefold().split())

