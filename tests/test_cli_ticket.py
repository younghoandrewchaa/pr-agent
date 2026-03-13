"""Tests for auto ticket generation in the create command."""

import re
import pytest
from unittest.mock import Mock, patch


class TestGetTicketNumber:
    """Tests for get_ticket_number() auto-generation behaviour."""

    def _call_get_ticket_number(self, branch_name: str, regex_result=None, ai_result=None):
        """
        Call get_ticket_number() with controlled extraction results.

        Both regex and AI extraction return None by default (simulating
        no ticket found), triggering auto-generation.
        """
        from src.cli import get_ticket_number
        from src.config import Config

        mock_git = Mock()
        mock_git.get_current_branch.return_value = branch_name
        mock_git.extract_ticket_number.return_value = regex_result
        mock_git.generate_ticket_prefix.return_value = "PAGE"

        mock_llm = Mock()
        mock_llm.extract_ticket_number.return_value = ai_result

        cfg = Config()

        with patch("src.cli.random") as mock_random:
            mock_random.randint.return_value = 38471
            result = get_ticket_number(mock_git, cfg, mock_llm)

        return result, mock_git, mock_llm, mock_random

    def test_auto_generates_when_regex_and_ai_both_fail(self):
        result, _, _, _ = self._call_get_ticket_number(
            "feature/no-ticket-here", regex_result=None, ai_result=None
        )
        assert result == "PAGE-38471"

    def test_auto_generated_format_matches_pattern(self):
        result, _, _, _ = self._call_get_ticket_number("random-branch")
        assert re.match(r'^[A-Z]{4}-\d{5}$', result), f"Expected XXXX-NNNNN format, got: {result}"

    def test_uses_generate_ticket_prefix_for_prefix(self):
        _, mock_git, _, _ = self._call_get_ticket_number("some-branch")
        mock_git.generate_ticket_prefix.assert_called_once()

    def test_uses_random_5_digit_number(self):
        _, _, _, mock_random = self._call_get_ticket_number("some-branch")
        mock_random.randint.assert_called_once_with(10000, 99999)

    def test_regex_result_returned_directly_without_auto_generation(self):
        result, mock_git, _, _ = self._call_get_ticket_number(
            "feature/STAR-123-auth", regex_result="STAR-123"
        )
        assert result == "STAR-123"
        mock_git.generate_ticket_prefix.assert_not_called()

    def test_ai_result_returned_directly_without_auto_generation(self):
        result, mock_git, _, _ = self._call_get_ticket_number(
            "feature/star_456_auth", regex_result=None, ai_result="STAR-456"
        )
        assert result == "STAR-456"
        mock_git.generate_ticket_prefix.assert_not_called()

    def test_auto_generates_when_no_llm_client_and_regex_fails(self):
        # get_ticket_number() accepts llm_client=None (skips AI tier entirely)
        # auto-generation must still trigger in this case
        from src.cli import get_ticket_number
        from src.config import Config

        mock_git = Mock()
        mock_git.get_current_branch.return_value = "no-ticket-branch"
        mock_git.extract_ticket_number.return_value = None
        mock_git.generate_ticket_prefix.return_value = "PAGE"

        cfg = Config()

        with patch("src.cli.random") as mock_random:
            mock_random.randint.return_value = 55555
            result = get_ticket_number(mock_git, cfg, llm_client=None)

        assert result == "PAGE-55555"
        mock_git.generate_ticket_prefix.assert_called_once()
