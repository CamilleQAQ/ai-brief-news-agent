"""Central behavior knobs for the collection and ranking pipeline.

Secrets stay in ``.env`` and personal interests stay in
``preferences.json``. This module only contains shared, non-secret defaults
that change how much data each stage processes or retains.
"""


# DeepSeek API settings shared by prefilter and final analysis.
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-flash"
PREFILTER_MAX_TOKENS = 1000
FINAL_ANALYZER_MAX_TOKENS = 8000
TREND_MAX_TOKENS = 1000

# Raw collection windows and pool sizes. These values control recall before
# any LLM filtering; they do not guarantee that an item reaches the brief.
ARXIV_ITEMS_PER_CATEGORY = 10
GITHUB_RECENT_DAYS = 90
GITHUB_ACTIVE_DAYS = 14
GITHUB_ITEMS_PER_FAMILY = 10
GITHUB_RECENT_MIN_STARS = 20
GITHUB_ACTIVE_MIN_STARS = 100
EDITORIAL_LOOKBACK_DAYS = 7
EDITORIAL_ITEMS_PER_SOURCE = 5

# Each source-specific prefilter may return fewer items than this ceiling.
PREFILTER_CANDIDATE_LIMIT = 10
PREFILTER_TOPIC_FAMILY_LIMIT = 4

# Final output ceilings. Quality gates may produce fewer or zero items.
FINAL_SECTION_LIMITS = {
    "news": 5,
    "papers_blogs": 5,
    "open_source": 5,
    "skills": 3,
}
FINAL_SUBTOPIC_LIMIT = 3
FINAL_TOPIC_FAMILY_LIMIT = 4

# arXiv HTML evidence is bounded so one paper cannot dominate the prompt.
ARXIV_EVIDENCE_MAX_CHARS = 4500
ARXIV_SECTION_MAX_CHARS = 1200
ARXIV_EVIDENCE_WORKERS = 4

# Cooldown history stays small and source-specific. Papers change slowly;
# active repositories change faster; editorial sources use the default.
HISTORY_RETENTION_DAYS = 60
MAX_HISTORY_ITEMS = 2000
COOLDOWN_DAYS = {
    "arxiv": 30,
    "github": 7,
}
DEFAULT_COOLDOWN_DAYS = 14
