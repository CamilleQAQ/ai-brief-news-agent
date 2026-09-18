import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agent.recent_outputs import (
    canonical_item_key,
    empty_history,
    filter_recent_outputs,
    load_recent_outputs,
    MAX_HISTORY_ITEMS,
    prune_history,
    record_final_outputs,
    save_recent_outputs,
)


NOW = datetime(2026, 9, 16, 8, 0, tzinfo=timezone.utc)


class RecentOutputTests(unittest.TestCase):
    def test_github_url_variants_have_same_key(self):
        first = {
            "source": "GitHub",
            "link": "https://github.com/Deer-Flow/llm-space/",
        }
        second = {
            "source": "GitHub",
            "link": "https://github.com/deer-flow/llm-space?utm_source=test",
        }

        self.assertEqual(
            canonical_item_key(first),
            canonical_item_key(second),
        )

    def test_arxiv_versions_and_pdf_have_same_key(self):
        urls = (
            "https://arxiv.org/abs/2609.13463v1",
            "https://arxiv.org/abs/2609.13463v2",
            "https://arxiv.org/pdf/2609.13463.pdf",
        )
        keys = {
            canonical_item_key({"source": "arXiv", "link": url})
            for url in urls
        }

        self.assertEqual(keys, {"arxiv:2609.13463"})

    def test_recent_output_is_filtered_and_old_output_is_allowed(self):
        item = {
            "source": "GitHub",
            "link": "https://github.com/example/repo",
        }
        key = canonical_item_key(item)
        recent_history = {
            "version": 1,
            "items": {
                key: {
                    "last_output_at": (NOW - timedelta(days=2)).isoformat(),
                }
            },
        }
        old_history = {
            "version": 1,
            "items": {
                key: {
                    "last_output_at": (NOW - timedelta(days=8)).isoformat(),
                }
            },
        }

        self.assertEqual(
            filter_recent_outputs([item], recent_history, now=NOW),
            [],
        )
        self.assertEqual(
            filter_recent_outputs([item], old_history, now=NOW),
            [item],
        )

    def test_same_run_arxiv_duplicates_are_removed(self):
        items = [
            {
                "source": "arXiv",
                "link": "https://arxiv.org/abs/2609.13463v1",
            },
            {
                "source": "arXiv",
                "link": "https://arxiv.org/pdf/2609.13463.pdf",
            },
        ]

        filtered = filter_recent_outputs(items, empty_history(), now=NOW)

        self.assertEqual(len(filtered), 1)

    def test_only_final_visible_items_are_recorded(self):
        candidates = [
            {
                "title": "Selected",
                "source": "GitHub",
                "link": "https://github.com/example/selected",
            },
            {
                "title": "Not selected",
                "source": "GitHub",
                "link": "https://github.com/example/not-selected",
            },
        ]
        result = {
            "news": [],
            "papers_blogs": [],
            "open_source": [{
                "title": "Selected",
                "url": "https://github.com/example/selected",
            }],
            "skills": [],
        }

        history = record_final_outputs(
            empty_history(),
            result,
            candidates,
            now=NOW,
        )

        self.assertIn("github:example/selected", history["items"])
        self.assertNotIn("github:example/not-selected", history["items"])

    def test_history_round_trip_and_invalid_json_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "recent_outputs.json"
            history = {
                "version": 1,
                "items": {
                    "github:example/repo": {
                        "source": "GitHub",
                        "last_output_at": NOW.isoformat(),
                    }
                },
            }

            save_recent_outputs(history, path=path)
            loaded = load_recent_outputs(path=path, now=NOW)
            self.assertIn("github:example/repo", loaded["items"])

            path.write_text("{invalid", encoding="utf-8")
            loaded = load_recent_outputs(path=path, now=NOW)
            self.assertEqual(loaded, empty_history())

    def test_history_is_bounded(self):
        items = {
            f"url:https://example.com/{index}": {
                "last_output_at": (
                    NOW - timedelta(seconds=index)
                ).isoformat(),
            }
            for index in range(MAX_HISTORY_ITEMS + 5)
        }

        history = prune_history(
            {"version": 1, "items": items},
            now=NOW,
        )

        self.assertEqual(len(history["items"]), MAX_HISTORY_ITEMS)
        self.assertIn("url:https://example.com/0", history["items"])
        self.assertNotIn(
            f"url:https://example.com/{MAX_HISTORY_ITEMS + 4}",
            history["items"],
        )


if __name__ == "__main__":
    unittest.main()
