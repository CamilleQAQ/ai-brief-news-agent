import unittest
from unittest.mock import patch

import requests

from collectors.github import get_github_news
from collectors.rss import get_rss_news


class CollectorResilienceTests(unittest.TestCase):
    @patch("collectors.rss.get_single_rss_news")
    def test_arxiv_source_failure_does_not_stop_other_sources(self, get_source):
        get_source.side_effect = [
            requests.ConnectionError("offline"),
            [{"link": "https://arxiv.org/abs/1"}],
            [{"link": "https://arxiv.org/abs/2"}],
        ]

        items = get_rss_news()

        self.assertEqual(len(items), 2)
        self.assertEqual(get_source.call_count, 3)

    @patch.dict(
        "collectors.github.SEARCH_FAMILIES",
        {"Evaluation": "llm evaluation"},
        clear=True,
    )
    @patch("collectors.github.get_active_repositories")
    @patch("collectors.github.get_recent_repositories")
    def test_github_search_failure_keeps_other_signal(
        self,
        get_recent,
        get_active,
    ):
        get_recent.side_effect = requests.HTTPError("rate limited")
        get_active.return_value = [{
            "link": "https://github.com/example/project",
        }]

        items = get_github_news()

        self.assertEqual(items, [{
            "link": "https://github.com/example/project",
        }])
        get_active.assert_called_once()


if __name__ == "__main__":
    unittest.main()
