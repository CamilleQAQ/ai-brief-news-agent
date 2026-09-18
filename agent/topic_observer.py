from collections import Counter
import re


TOPIC_FAMILIES = (
    "Agent",
    "Training",
    "Reasoning",
    "Evaluation",
    "Multimodal",
    "Systems-Inference",
    "Other",
)

FAMILY_ALIASES = {
    "agent & llm systems": "Agent",
    "agent": "Agent",
    "mcp": "Agent",
    "llm": "Agent",
    "rag": "Agent",
    "training & post-training": "Training",
    "training/post-training": "Training",
    "reasoning & model architecture": "Reasoning",
    "reasoning & architecture": "Reasoning",
    "evaluation": "Evaluation",
    "multimodal": "Multimodal",
    "efficient ai & ai infrastructure": "Systems-Inference",
    "systems & inference": "Systems-Inference",
    "inference": "Systems-Inference",
    "systems-inference": "Systems-Inference",
}

FAMILY_KEYWORDS = {
    "Agent": (
        "agent", "agentic", "multi-agent", "coding agent", "mcp",
        "model context protocol", "rag", "retrieval augmented",
        "context engineering", "tool use", "智能体", "检索增强",
    ),
    "Training": (
        "training", "post-training", "pretraining", "pre-training",
        "fine-tuning", "finetuning", "rlhf", "rlvr", "grpo", "dpo",
        "distillation", "训练", "微调", "蒸馏", "强化学习",
    ),
    "Reasoning": (
        "reasoning", "reasoner", "chain-of-thought", "test-time compute",
        "inference-time compute", "model architecture", "mixture of experts",
        "transformer architecture", "attention", "推理模型", "模型架构",
        "思维链", "测试时计算", "注意力机制",
    ),
    "Evaluation": (
        "evaluation", "benchmark", "evals", "evaluator", "red teaming",
        "评测", "评估", "基准测试",
    ),
    "Multimodal": (
        "multimodal", "vision-language", "vision language", "vlm",
        "text-to-video", "video model", "world model", "vla", "robotics",
        "多模态", "视觉语言", "视频模型", "世界模型", "机器人",
    ),
    "Systems-Inference": (
        "inference", "serving", "quantization", "kv cache",
        "speculative decoding", "distributed inference", "cuda", "triton",
        "gpu kernel", "throughput", "latency", "推理优化", "模型服务",
        "量化", "分布式推理", "吞吐", "延迟",
    ),
}


def classify_topic_family(item):
    content_text = _item_text(
        item,
        fields=(
            "title", "summary", "subtopic", "topics", "what_it_does",
            "why_it_matters", "why_read", "what_you_get", "why_useful",
            "use_case",
        ),
    )

    # Agent evaluation、Agent benchmark 等仍属于 Agent 语义家族。
    if _keyword_score(content_text, FAMILY_KEYWORDS["Agent"]):
        return "Agent"

    scores = {
        family: _keyword_score(content_text, keywords)
        for family, keywords in FAMILY_KEYWORDS.items()
        if family != "Agent"
    }

    metadata_family = _metadata_family(item)
    if metadata_family:
        scores[metadata_family] = scores.get(metadata_family, 0) + 2

    best_family = max(scores, key=scores.get, default="Other")
    return best_family if scores.get(best_family, 0) else "Other"


def resolve_topic_family(item, candidate=None):
    combined = dict(candidate or {})

    for key, value in item.items():
        if value not in (None, "", []):
            combined[key] = value

    return classify_topic_family(combined)


def topic_family_distribution(items):
    counts = Counter(classify_topic_family(item) for item in items)
    return {family: counts.get(family, 0) for family in TOPIC_FAMILIES}


def print_topic_family_distribution(label, items):
    distribution = topic_family_distribution(items)
    details = " | ".join(
        f"{family}: {distribution[family]}"
        for family in TOPIC_FAMILIES
    )
    print(f"  {label}（{len(items)} 条）：{details}")


def flatten_final_output(result):
    items = []

    for section in ("news", "papers_blogs", "open_source", "skills"):
        items.extend(result.get(section, []))

    return items


def _metadata_family(item):
    for field in ("subtopic", "topic_family", "direction", "category"):
        value = str(item.get(field, "")).strip().casefold()
        if value in FAMILY_ALIASES:
            return FAMILY_ALIASES[value]

    return None


def _item_text(item, fields):
    values = []

    for field in fields:
        value = item.get(field, "")
        if isinstance(value, list):
            values.extend(str(part) for part in value)
        else:
            values.append(str(value))

    return " ".join(values).casefold()


def _keyword_score(text, keywords):
    return sum(_contains_keyword(text, keyword) for keyword in keywords)


def _contains_keyword(text, keyword):
    normalized = keyword.casefold()

    if normalized.isascii() and normalized.replace("-", "").isalnum():
        return bool(re.search(rf"\b{re.escape(normalized)}\b", text))

    return normalized in text
