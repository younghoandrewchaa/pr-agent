"""Tests for PR history module."""

import json
import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from src.pr_history import get_history_path, save_pr, find_related_prs


class TestGetHistoryPath:
    def test_returns_correct_path(self):
        path = get_history_path("acme", "myrepo")
        expected = Path.home() / ".config" / "pr-agent" / "history" / "acme" / "myrepo.json"
        assert path == expected

    def test_different_owner_and_repo(self):
        path = get_history_path("org", "other-repo")
        assert path.name == "other-repo.json"
        assert path.parent.name == "org"


class TestSavePr:
    def test_creates_file_with_entry(self, tmp_path):
        history_file = tmp_path / "history.json"
        with patch("src.pr_history.get_history_path", return_value=history_file):
            save_pr("acme", "myrepo", 42, "STAR-1: Add auth", "## Why\nNeeded auth")

        data = json.loads(history_file.read_text())
        assert len(data) == 1
        assert data[0]["pr_number"] == 42
        assert data[0]["title"] == "STAR-1: Add auth"
        assert data[0]["description"] == "## Why\nNeeded auth"
        assert "created_at" in data[0]

    def test_appends_to_existing_history(self, tmp_path):
        history_file = tmp_path / "history.json"
        existing = [{"pr_number": 1, "title": "old", "description": "d", "created_at": "2025-01-01T00:00:00Z"}]
        history_file.write_text(json.dumps(existing))

        with patch("src.pr_history.get_history_path", return_value=history_file):
            save_pr("acme", "myrepo", 2, "STAR-2: New", "desc")

        data = json.loads(history_file.read_text())
        assert len(data) == 2
        assert data[-1]["pr_number"] == 2

    def test_trims_to_50_entries(self, tmp_path):
        history_file = tmp_path / "history.json"
        existing = [
            {"pr_number": i, "title": f"PR {i}", "description": "d", "created_at": "2025-01-01T00:00:00Z"}
            for i in range(55)
        ]
        history_file.write_text(json.dumps(existing))

        with patch("src.pr_history.get_history_path", return_value=history_file):
            save_pr("acme", "myrepo", 100, "New PR", "desc")

        data = json.loads(history_file.read_text())
        assert len(data) == 50
        # Most recent entry is last
        assert data[-1]["pr_number"] == 100

    def test_creates_parent_directories(self, tmp_path):
        history_file = tmp_path / "nested" / "dirs" / "history.json"
        with patch("src.pr_history.get_history_path", return_value=history_file):
            save_pr("acme", "myrepo", 1, "title", "desc")

        assert history_file.exists()

    def test_handles_write_io_error_silently(self, tmp_path):
        history_file = tmp_path / "history.json"
        with patch("src.pr_history.get_history_path", return_value=history_file):
            with patch.object(Path, "write_text", side_effect=OSError("disk full")):
                # Must not raise
                save_pr("acme", "myrepo", 1, "title", "desc")

    def test_handles_read_io_error_silently(self, tmp_path):
        history_file = tmp_path / "history.json"
        history_file.write_text("[]")  # File exists so exists() returns True
        with patch("src.pr_history.get_history_path", return_value=history_file):
            with patch.object(Path, "read_text", side_effect=OSError("permission denied")):
                # Must not raise; _load_history returns [] and save_pr continues
                save_pr("acme", "myrepo", 1, "title", "desc")

    def test_handles_corrupt_history_file(self, tmp_path):
        history_file = tmp_path / "history.json"
        history_file.write_text("not valid json {{{")
        with patch("src.pr_history.get_history_path", return_value=history_file):
            # Should not raise; treats corrupt file as empty
            save_pr("acme", "myrepo", 1, "title", "desc")

        data = json.loads(history_file.read_text())
        assert len(data) == 1


class TestFindRelatedPrs:
    def test_returns_empty_when_no_history(self, tmp_path):
        history_file = tmp_path / "nonexistent.json"
        mock_client = Mock()
        with patch("src.pr_history.get_history_path", return_value=history_file):
            result = find_related_prs("acme", "myrepo", "STAR-1: title", "intent", mock_client)

        assert result == ""
        mock_client.generate.assert_not_called()

    def test_sends_truncated_descriptions_to_llm(self, tmp_path):
        history_file = tmp_path / "history.json"
        long_desc = "x" * 1000
        history = [{"pr_number": 1, "title": "PR 1", "description": long_desc, "created_at": "2025-01-01T00:00:00Z"}]
        history_file.write_text(json.dumps(history))

        mock_client = Mock()
        mock_client.generate.return_value = "Related to #1"

        with patch("src.pr_history.get_history_path", return_value=history_file):
            find_related_prs("acme", "myrepo", "title", "intent", mock_client)

        call_args = mock_client.generate.call_args
        prompt_sent = call_args.kwargs.get("prompt") or call_args.args[0]
        # Full 1000-char description must not appear; truncated 500-char version must
        assert "x" * 501 not in prompt_sent
        assert "x" * 500 in prompt_sent

    def test_caps_history_at_20_entries_sent_to_llm(self, tmp_path):
        history_file = tmp_path / "history.json"
        history = [
            {"pr_number": i, "title": f"PR {i}", "description": "desc", "created_at": "2025-01-01T00:00:00Z"}
            for i in range(30)
        ]
        history_file.write_text(json.dumps(history))

        mock_client = Mock()
        mock_client.generate.return_value = "NONE"

        with patch("src.pr_history.get_history_path", return_value=history_file):
            find_related_prs("acme", "myrepo", "title", "intent", mock_client)

        prompt_sent = mock_client.generate.call_args.kwargs.get("prompt") or mock_client.generate.call_args.args[0]
        # Only 20 most recent entries (PR 10..29) should appear
        assert "PR 29" in prompt_sent
        assert "PR 0" not in prompt_sent

    def test_returns_empty_string_when_llm_returns_NONE_sentinel(self, tmp_path):
        # LLM returns the string "NONE" (the sentinel value), not Python None
        history_file = tmp_path / "history.json"
        history = [{"pr_number": 1, "title": "PR 1", "description": "desc", "created_at": "2025-01-01T00:00:00Z"}]
        history_file.write_text(json.dumps(history))

        mock_client = Mock()
        mock_client.generate.return_value = "NONE"

        with patch("src.pr_history.get_history_path", return_value=history_file):
            result = find_related_prs("acme", "myrepo", "title", "intent", mock_client)

        assert result == ""

    def test_returns_empty_string_when_llm_raises(self, tmp_path):
        history_file = tmp_path / "history.json"
        history = [{"pr_number": 1, "title": "PR 1", "description": "desc", "created_at": "2025-01-01T00:00:00Z"}]
        history_file.write_text(json.dumps(history))

        mock_client = Mock()
        mock_client.generate.side_effect = Exception("LLM error")

        with patch("src.pr_history.get_history_path", return_value=history_file):
            result = find_related_prs("acme", "myrepo", "title", "intent", mock_client)

        assert result == ""

    def test_returns_llm_summary_when_related(self, tmp_path):
        history_file = tmp_path / "history.json"
        history = [{"pr_number": 42, "title": "STAR-1: Auth", "description": "Added auth", "created_at": "2025-01-01T00:00:00Z"}]
        history_file.write_text(json.dumps(history))

        mock_client = Mock()
        mock_client.generate.return_value = "This builds on #42 which introduced auth."

        with patch("src.pr_history.get_history_path", return_value=history_file):
            result = find_related_prs("acme", "myrepo", "STAR-2: Extend auth", "add OAuth", mock_client)

        assert result == "This builds on #42 which introduced auth."


class TestFindRelatedPrsPrompt:
    def test_prompt_includes_title_and_intent(self):
        from src.prompts import PRPrompts
        history = [{"pr_number": 1, "title": "PR 1", "description": "desc", "created_at": "2025-01-01T00:00:00Z"}]
        prompt = PRPrompts.find_related_prs_prompt("STAR-2: New feature", "add OAuth", history)
        assert "STAR-2: New feature" in prompt
        assert "add OAuth" in prompt

    def test_prompt_includes_history_entries(self):
        from src.prompts import PRPrompts
        history = [{"pr_number": 42, "title": "Old PR", "description": "Old desc", "created_at": "2025-01-01T00:00:00Z"}]
        prompt = PRPrompts.find_related_prs_prompt("New PR", "intent", history)
        assert "#42" in prompt
        assert "Old PR" in prompt
        assert "Old desc" in prompt

    def test_prompt_instructs_llm_to_respond_with_NONE_when_unrelated(self):
        from src.prompts import PRPrompts
        history = [{"pr_number": 1, "title": "PR 1", "description": "desc", "created_at": "2025-01-01T00:00:00Z"}]
        prompt = PRPrompts.find_related_prs_prompt("New PR", "intent", history)
        assert "NONE" in prompt
