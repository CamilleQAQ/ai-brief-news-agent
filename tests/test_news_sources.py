import unittest

from collectors.news import RSS_SOURCES


class NewsSourceTests(unittest.TestCase):
    def test_bair_uses_reachable_official_mirror(self):
        source_urls = {
            source: url
            for source, _, url in RSS_SOURCES
        }

        self.assertEqual(
            source_urls["Berkeley BAIR Blog"],
            "https://bairblog.github.io/feed.xml",
        )


if __name__ == "__main__":
    unittest.main()
