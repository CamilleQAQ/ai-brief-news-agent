import unittest

from agent.topic_observer import (
    classify_topic_family,
    flatten_final_output,
    resolve_topic_family,
    topic_family_distribution,
)
from collectors.github import SEARCH_FAMILIES


class TopicObserverTests(unittest.TestCase):
    def test_agent_evaluation_counts_as_agent_family(self):
        item = {
            "title": "A benchmark for coding agents",
            "category": "Evaluation",
        }

        self.assertEqual(classify_topic_family(item), "Agent")

    def test_candidate_semantics_override_model_family_label(self):
        item = {
            "topic_family": "Evaluation",
            "subtopic": "Agent Evaluation",
        }
        candidate = {"title": "Long-horizon agent benchmark"}

        self.assertEqual(resolve_topic_family(item, candidate), "Agent")

    def test_balanced_families_are_classified(self):
        items = [
            {"category": "Training & Post-training"},
            {"category": "Reasoning & Model Architecture"},
            {"category": "Efficient AI & AI Infrastructure"},
            {"category": "Multimodal"},
        ]

        distribution = topic_family_distribution(items)

        self.assertEqual(distribution["Training"], 1)
        self.assertEqual(distribution["Reasoning"], 1)
        self.assertEqual(distribution["Systems-Inference"], 1)
        self.assertEqual(distribution["Multimodal"], 1)

    def test_final_output_sections_are_flattened(self):
        result = {
            "news": [{"title": "News"}],
            "papers_blogs": [{"title": "Paper"}],
            "open_source": [{"title": "Repo"}],
            "skills": [{"title": "Skill"}],
            "daily_trends": ["Trend"],
        }

        self.assertEqual(len(flatten_final_output(result)), 4)

    def test_github_search_uses_balanced_families(self):
        self.assertEqual(
            set(SEARCH_FAMILIES),
            {
                "Agent & LLM Systems",
                "Training & Post-training",
                "Reasoning & Model Architecture",
                "Efficient AI & AI Infrastructure",
                "Evaluation",
                "Multimodal",
            },
        )


if __name__ == "__main__":
    unittest.main()
