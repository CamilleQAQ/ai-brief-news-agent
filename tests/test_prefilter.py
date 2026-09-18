import unittest

from agent.prefilter import select_items_by_indices


class PrefilterSelectionTests(unittest.TestCase):
    def test_agent_family_cap_spans_different_subtopics(self):
        items = [
            {"title": "MCP server", "category": "Agent & LLM Systems"},
            {"title": "Coding agent", "category": "Agent & LLM Systems"},
            {"title": "Agent memory", "category": "Evaluation"},
            {"title": "Agent benchmark", "category": "Evaluation"},
            {"title": "Agent runtime", "category": "Systems & Inference"},
            {"title": "Multimodal model", "category": "Multimodal"},
        ]

        selected = select_items_by_indices(
            items,
            list(range(len(items))),
            max_candidates=6,
        )

        self.assertEqual(len(selected), 5)
        self.assertEqual(selected[-1]["category"], "Multimodal")

    def test_family_cap_does_not_backfill_unselected_items(self):
        items = [
            {"title": f"Agent tool {index}"}
            for index in range(5)
        ] + [{"title": "Multimodal model"}]

        selected = select_items_by_indices(
            items,
            [0, 1, 2, 3, 4],
            max_candidates=6,
        )

        self.assertEqual(len(selected), 4)
        self.assertNotIn(items[5], selected)


if __name__ == "__main__":
    unittest.main()
