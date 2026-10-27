import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from challenge_b import compact_history, analyze_logs, run_log_agent


def response(content=None, tool_calls=None, tokens=10):
    msg = SimpleNamespace(content=content, tool_calls=tool_calls or [])
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=SimpleNamespace(prompt_tokens=tokens))


class Client:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = []
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return next(self.replies)


class ChallengeBTests(unittest.TestCase):
    def test_compaction_preserves_system_and_recent_messages(self):
        messages = [
            {"role": "system", "content": "Keep this constraint"},
            {"role": "user", "content": "error: HTTP 500" * 100},
            {"role": "assistant", "content": "Restart failed" * 100},
            {"role": "user", "content": "What next?"},
        ]
        client = Client([response("Issue: HTTP 500. Tried: restart failed. Next: check database.")])
        result, stats = compact_history(client, "test", messages, threshold_chars=100, keep_recent=1)
        self.assertEqual(result[0], messages[0])
        self.assertIn("restart failed", result[1]["content"])
        self.assertEqual(result[-1], messages[-1])
        self.assertLess(stats["after_chars"], stats["before_chars"])
        self.assertEqual(stats["summary_prompt_tokens"], 10)

    def test_compaction_below_threshold_makes_no_request(self):
        messages = [{"role": "system", "content": "rule"}, {"role": "user", "content": "hello"}]
        client = Client([])
        result, stats = compact_history(client, "test", messages, threshold_chars=1000)
        self.assertEqual(result, messages)
        self.assertFalse(stats["compacted"])
        self.assertEqual(client.calls, [])

    def test_empty_summary_does_not_discard_history(self):
        messages = [{"role": "system", "content": "rule"}, {"role": "user", "content": "long" * 100}, {"role": "user", "content": "recent"}]
        with self.assertRaises(ValueError):
            compact_history(Client([response("")]), "test", messages, threshold_chars=10, keep_recent=1)
        self.assertEqual(len(messages), 3)

    def test_analyze_multiple_logs_and_filter_keyword(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "a.log").write_text("INFO payment HTTP 200\nERROR payment HTTP 500\n")
            (path / "b.log").write_text("ERROR payment HTTP 500\nERROR search HTTP 503\n")
            result = analyze_logs(path, "payment")
            self.assertEqual(result["matching_lines"], 3)
            self.assertEqual(result["levels"], {"ERROR": 2, "INFO": 1})
            self.assertEqual(result["http_statuses"], {"200": 1, "500": 2})
            self.assertEqual(result["files_scanned"], 2)
            self.assertNotIn("ERROR payment HTTP 500", json.dumps(result))

    def test_agent_sends_aggregates_not_raw_lines_to_model(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "a.log").write_text("ERROR SECRET-RAW-LINE HTTP 500\n")
            call = SimpleNamespace(id="c1", type="function", function=SimpleNamespace(name="analyze_logs", arguments='{"keyword": ""}'))
            client = Client([response(tool_calls=[call], tokens=20), response("One error, HTTP 500.", tokens=30)])
            result = run_log_agent(client, "test", path, "Count errors")
            serialized = json.dumps(client.calls[-1]["messages"], default=str)
            self.assertNotIn("SECRET-RAW-LINE", serialized)
            self.assertIn('"matching_lines"', serialized.replace('\\"', '"'))
            self.assertEqual(result["prompt_tokens"], [20, 30])
            self.assertEqual(result["answer"], "One error, HTTP 500.")

if __name__ == "__main__":
    unittest.main()
