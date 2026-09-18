import unittest

from agent.analyzer import (
    build_prompt,
    finalize_analysis,
    matches_preferences,
    normalize_internal_scores,
    selection_key,
)


def scored_item(candidate_index, **overrides):
    item = {
        "candidate_index": candidate_index,
        "title": f"Item {candidate_index}",
        "summary": "summary",
        "why_it_matters": "value",
        "what_to_do": "阅读核心源码",
        "direction": "Agent & LLM Systems",
        "subtopic": "MCP",
        "student_value": 4,
        "novelty": 4,
        "reproducibility": 4,
        "evidence_quality": 4,
        "actionability": 4,
        "redundancy_penalty": 1,
    }
    item.update(overrides)
    return item


class FinalSelectionTests(unittest.TestCase):
    def test_top_three_reuses_global_selection_order(self):
        candidates = [
            {
                "title": f"Repo {index}",
                "link": f"https://example.com/{index}",
                "source": "GitHub",
            }
            for index in range(3)
        ]
        raw_result = {
            "open_source": [
                scored_item(
                    0,
                    title="Third",
                    student_value=3,
                    subtopic="MCP",
                ),
                scored_item(
                    1,
                    title="First",
                    student_value=5,
                    subtopic="Coding Agent",
                ),
                scored_item(
                    2,
                    title="Second",
                    student_value=4,
                    subtopic="Agent Memory",
                ),
            ]
        }

        result = finalize_analysis(raw_result, candidates)

        self.assertEqual(
            [item["title"] for item in result["top_items"]],
            ["First", "Second", "Third"],
        )

    def test_same_subtopic_is_limited_to_three_items(self):
        candidates = [
            {
                "title": f"Repo {index}",
                "link": f"https://example.com/{index}",
                "source": "GitHub",
                "stars": 10000 - index,
            }
            for index in range(4)
        ]
        raw_result = {
            "open_source": [scored_item(index) for index in range(4)]
        }

        result = finalize_analysis(raw_result, candidates)

        self.assertEqual(len(result["open_source"]), 3)

    def test_skills_require_high_immediate_value(self):
        candidates = [{
            "title": "Ordinary tool",
            "link": "https://example.com/tool",
            "source": "GitHub",
        }]
        raw_result = {
            "skills": [scored_item(
                0,
                what_it_does="does something",
                why_useful="maybe useful",
                use_case="generic",
                how_to_try="read README",
                student_value=3,
                actionability=5,
            )]
        }

        result = finalize_analysis(raw_result, candidates)

        self.assertEqual(result["skills"], [])

    def test_source_metadata_and_optional_caution_are_preserved(self):
        candidates = [{
            "title": "Original paper",
            "link": "https://example.com/paper",
            "source": "arXiv",
            "summary": "Experiments cover two classification tasks.",
        }]
        raw_result = {
            "papers_blogs": [scored_item(
                0,
                title="中文论文标题",
                why_read="学习新方法",
                what_you_get="学到具体建模方式",
                caution="实验只覆盖两个分类任务。",
                caution_basis="Experiments cover two classification tasks.",
                direction="Multimodal",
                subtopic="Multimodal",
            )]
        }

        result = finalize_analysis(raw_result, candidates)
        paper = result["papers_blogs"][0]

        self.assertEqual(paper["url"], "https://example.com/paper")
        self.assertEqual(paper["source"], "arXiv")
        self.assertIn("两个分类任务", paper["caution"])

    def test_agent_family_is_limited_across_different_subtopics(self):
        subtopics = [
            "MCP",
            "Coding Agent",
            "Agent Memory",
            "Agent Evaluation",
            "Agent Harness/Runtime",
        ]
        candidates = [
            {
                "title": f"Repo {index}",
                "link": f"https://example.com/{index}",
                "source": "GitHub",
            }
            for index in range(len(subtopics))
        ]
        raw_result = {
            "open_source": [
                scored_item(index, subtopic=subtopic)
                for index, subtopic in enumerate(subtopics)
            ]
        }

        result = finalize_analysis(raw_result, candidates)

        self.assertEqual(len(result["open_source"]), 4)

    def test_unsupported_caution_is_removed(self):
        candidates = [{
            "title": "Repository",
            "summary": "A tool for model serving.",
            "link": "https://example.com/repo",
            "source": "GitHub",
        }]
        raw_result = {
            "open_source": [scored_item(
                0,
                caution="生态不成熟，稳定性未知。",
                caution_basis="No production adoption is known.",
                direction="Efficient AI & AI Infrastructure",
                subtopic="Efficient Inference/Systems",
            )]
        }

        result = finalize_analysis(raw_result, candidates)

        self.assertNotIn("caution", result["open_source"][0])

    def test_grounded_claim_cannot_hide_unsupported_absence_claim(self):
        candidates = [{
            "title": "Inference project",
            "summary": "The project reports 0.56 tok/s on its benchmark.",
            "link": "https://example.com/repo",
            "source": "GitHub",
        }]
        raw_result = {
            "open_source": [scored_item(
                0,
                caution="项目报告 0.56 tok/s，但未经独立复现。",
                caution_basis="0.56 tok/s",
                direction="Efficient AI & AI Infrastructure",
                subtopic="Efficient Inference/Systems",
            )]
        }

        result = finalize_analysis(raw_result, candidates)

        self.assertNotIn("caution", result["open_source"][0])

    def test_generic_caution_is_removed_even_with_matching_basis(self):
        candidates = [{
            "title": "Paper",
            "summary": "需进一步验证",
            "link": "https://example.com/paper",
            "source": "arXiv",
        }]
        raw_result = {
            "papers_blogs": [scored_item(
                0,
                why_read="学习实验设计",
                what_you_get="控制变量方法",
                caution="需进一步验证",
                caution_basis="需进一步验证",
                direction="Evaluation",
                subtopic="Evaluation",
            )]
        }

        result = finalize_analysis(raw_result, candidates)

        self.assertNotIn("caution", result["papers_blogs"][0])

    def test_prompt_uses_exact_github_dates_not_retrieval_signal(self):
        candidates = [{
            "title": "Example repository",
            "summary": "A model serving runtime.",
            "source": "GitHub",
            "signal": "new_repository",
            "created_at": "2026-08-01T00:00:00Z",
            "updated_at": "2026-09-01T00:00:00Z",
            "pushed_at": "2026-09-02T00:00:00Z",
            "topics": ["inference"],
        }]

        prompt = build_prompt(candidates, {
            "preferred_tracks": ["Agent & LLM Systems"],
            "current_focus": ["coding agents"],
        })

        self.assertIn("2026-08-01T00:00:00Z", prompt)
        self.assertNotIn("new_repository", prompt)
        self.assertNotIn("coding agents", prompt)

    def test_preferences_are_only_the_last_tiebreaker(self):
        preferences = {
            "preferred_tracks": ["Agent & LLM Systems"],
            "current_focus": ["coding agents"],
        }
        preferred = scored_item(0, title="Coding Agents")
        exploratory = scored_item(
            1,
            title="New Architecture",
            direction="Reasoning & Model Architecture",
            subtopic="Model Architecture",
            student_value=5,
        )
        preferred["rating"] = "A"
        exploratory["rating"] = "S"
        normalize_internal_scores(preferred)
        normalize_internal_scores(exploratory)

        self.assertTrue(matches_preferences(preferred, preferences))
        self.assertFalse(matches_preferences(exploratory, preferences))
        self.assertGreater(
            selection_key(exploratory, preferences),
            selection_key(preferred, preferences),
        )


if __name__ == "__main__":
    unittest.main()
