import unittest

from collectors.rss import (
    clean_arxiv_summary,
    extract_arxiv_evidence,
    extract_arxiv_id,
)


class ArxivEnrichmentTests(unittest.TestCase):
    def test_summary_prefix_is_removed(self):
        summary = (
            "arXiv:2609.16129v1 Announce Type: new \n"
            "Abstract: A concrete pruning method."
        )

        self.assertEqual(
            clean_arxiv_summary(summary),
            "A concrete pruning method.",
        )

    def test_arxiv_id_ignores_version(self):
        self.assertEqual(
            extract_arxiv_id("https://arxiv.org/abs/2609.16129v2"),
            "2609.16129",
        )

    def test_relevant_sections_and_artifacts_are_extracted(self):
        html = """
        <html><body>
          <h2>Introduction</h2>
          <p>We formulate pruning as a geometric distance problem.</p>
          <h2>Related Work</h2>
          <p>This paragraph should not be included.</p>
          <h2>Experimental Evaluation</h2>
          <p>We compare against three baselines on two datasets.</p>
          <p><a href="https://github.com/example/project">Code</a></p>
          <h2>Limitations</h2>
          <p>The experiments only cover image classification.</p>
        </body></html>
        """

        evidence = extract_arxiv_evidence(
            html,
            base_url="https://arxiv.org/html/2609.16129",
        )

        self.assertIn("geometric distance", evidence["text"])
        self.assertIn("three baselines", evidence["text"])
        self.assertIn("only cover image classification", evidence["text"])
        self.assertNotIn("should not be included", evidence["text"])
        self.assertEqual(
            evidence["artifact_links"],
            ["https://github.com/example/project"],
        )


if __name__ == "__main__":
    unittest.main()
