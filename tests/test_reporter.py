import unittest

from agent.reporter import render_report, shorten_text


class ReporterTests(unittest.TestCase):
    def test_top_three_is_rendered_before_sections(self):
        result = {
            "top_items": [{
                "title": "Top paper",
                "section": "papers_blogs",
                "why": "学习新的实验设计",
                "action": "阅读方法章节",
                "url": "https://example.com/paper",
            }],
            "news": [],
            "papers_blogs": [],
            "open_source": [],
            "skills": [],
            "daily_trends": [],
        }

        report = render_report(result)

        self.assertIn("TODAY'S TOP 3", report)
        self.assertIn("栏目：Papers & Blogs", report)
        self.assertLess(
            report.index("TODAY'S TOP 3"),
            report.index("AI NEWS"),
        )
        self.assertIn("不代表今天刚发布", report)

    def test_top_item_text_is_shortened(self):
        long_text = "这是一个很长的价值说明" * 20

        shortened = shorten_text(long_text)

        self.assertLessEqual(len(shortened), 120)
        self.assertTrue(shortened.endswith("…"))


if __name__ == "__main__":
    unittest.main()
