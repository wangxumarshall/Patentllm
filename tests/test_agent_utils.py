import unittest
import sys
import os

# Add the parent directory to the Python path to allow importing agent modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock MODEL_CONFIG before importing SummaryAgent
# This is to prevent issues if SummaryAgent's __init__ tries to access it
# and it's not set up in the test environment.
from config import settings as config_settings
config_settings.MODEL_CONFIG = {
    "type": "openai", # or "ollama", doesn't matter much for these tests
    "api_key": "test_key",
    "base_url": "http://localhost:1234",
    "model_name": "test_model",
    "request_timeout": 30
}

from agents.summary_agent import SummaryAgent

class TestSummaryAgentSummarization(unittest.TestCase):
    def setUp(self):
        self.agent = SummaryAgent()

    def test_empty_search_results(self):
        results = []
        summary = self.agent._summarize_search_results(results)
        self.assertEqual(summary, "")

    def test_single_result_no_snippets(self):
        results = [{"query": "test query 1", "result": ""}]
        summary = self.agent._summarize_search_results(results)
        expected = "### 搜索查询 1: test query 1\n- 无有效片段" # No trailing \n
        self.assertEqual(summary, expected)

    def test_single_result_one_snippet(self):
        results = [{"query": "query 2", "result": "Snippet 1 for query 2"}]
        summary = self.agent._summarize_search_results(results)
        expected = "### 搜索查询 1: query 2\n- 片段 1: Snippet 1 for query 2" # No trailing \n
        self.assertEqual(summary, expected)

    def test_single_result_multiple_snippets_limit(self):
        results = [{
            "query": "query 3",
            "result": "Snippet 1\nSnippet 2\nSnippet 3\nSnippet 4\nSnippet 5"
        }]
        summary = self.agent._summarize_search_results(results)
        expected = (
            "### 搜索查询 1: query 3\n"
            "- 片段 1: Snippet 1\n"
            "- 片段 2: Snippet 2\n"
            "- 片段 3: Snippet 3" # No trailing \n
        )
        self.assertEqual(summary, expected)

    def test_multiple_results_varying_snippets(self):
        results = [
            {"query": "query A", "result": "A1\nA2\nA3\nA4"},
            {"query": "query B", "result": "B1"},
            {"query": "query C", "result": ""},
            {"query": "query D", "result": "D1\nD2"} # Last one
        ]
        summary = self.agent._summarize_search_results(results)
        expected = (
            "### 搜索查询 1: query A\n"
            "- 片段 1: A1\n"
            "- 片段 2: A2\n"
            "- 片段 3: A3\n\n"  # This one has \n\n because another follows
            "### 搜索查询 2: query B\n"
            "- 片段 1: B1\n\n"  # This one has \n\n
            "### 搜索查询 3: query C\n"
            "- 无有效片段\n\n" # This one has \n\n
            "### 搜索查询 4: query D\n" # Last one
            "- 片段 1: D1\n"
            "- 片段 2: D2" # No trailing \n
        )
        self.assertEqual(summary, expected)

    def test_result_with_empty_lines_in_snippets(self):
        results = [{
            "query": "query E",
            "result": "E1\n\nE2\n  \nE3\nE4" # Includes empty or whitespace-only lines
        }]
        summary = self.agent._summarize_search_results(results)
        expected = (
            "### 搜索查询 1: query E\n"
            "- 片段 1: E1\n"
            "- 片段 2: E2\n"
            "- 片段 3: E3" # No trailing \n, snippet indices corrected
        )
        self.assertEqual(summary, expected)


class TestTextTruncation(unittest.TestCase):
    def _truncate_text(self, text, max_len):
        if len(text) > max_len:
            return text[:max_len] + "\n... (truncated due to length)"
        return text

    def test_no_truncation_needed(self):
        text = "This is a short text."
        max_len = 100
        self.assertEqual(self._truncate_text(text, max_len), text)

    def test_truncation_applied(self):
        text = "This is a very long text that definitely needs to be truncated."
        max_len = 20
        expected = "This is a very long \n... (truncated due to length)"
        self.assertEqual(self._truncate_text(text, max_len), expected)

    def test_text_length_equals_max_len(self):
        text_equal = "abc"
        max_len_equal = 3
        self.assertEqual(self._truncate_text(text_equal, max_len_equal), text_equal)

        text_longer = "abcd"
        max_len_longer = 3
        expected_longer = "abc\n... (truncated due to length)"
        self.assertEqual(self._truncate_text(text_longer, max_len_longer), expected_longer)

        # Test with a common length used in agents
        text_15k = "a" * 15000
        self.assertEqual(self._truncate_text(text_15k, 15000), text_15k)

    def test_truncation_with_summary_max_len(self):
        text = "a" * 20001
        max_len = 20000
        expected = ("a" * 20000) + "\n... (truncated due to length)"
        self.assertEqual(self._truncate_text(text, max_len), expected)

        text_short = "b" * 19999
        self.assertEqual(self._truncate_text(text_short, max_len), text_short)

    def test_truncation_with_research_max_len(self):
        text = "c" * 15001
        max_len = 15000
        expected = ("c" * 15000) + "\n... (truncated due to length)"
        self.assertEqual(self._truncate_text(text, max_len), expected)

        text_short = "d" * 14999
        self.assertEqual(self._truncate_text(text_short, max_len), text_short)


if __name__ == '__main__':
    unittest.main()
