"""Tests for git operations module."""

import pytest
from unittest.mock import Mock
from src.git_operations import GitOperations
from src.exceptions import NotInGitRepoError


class TestTicketExtraction:
    """Test ticket number extraction from branch names."""

    def test_extract_ticket_standard_format(self):
        """Test extraction with standard format."""
        git_ops = GitOperations()

        # Test with various branch name formats
        assert git_ops.extract_ticket_number("feature/STAR-12345-add-feature", r"STAR-(\d+)") == "STAR-12345"
        assert git_ops.extract_ticket_number("STAR-999-bugfix", r"STAR-(\d+)") == "STAR-999"
        assert git_ops.extract_ticket_number("bugfix/STAR-456-fix-leak", r"STAR-(\d+)") == "STAR-456"

    def test_extract_ticket_no_match(self):
        """Test extraction when no ticket found."""
        git_ops = GitOperations()

        assert git_ops.extract_ticket_number("feature-no-ticket", r"STAR-(\d+)") is None
        assert git_ops.extract_ticket_number("main", r"STAR-(\d+)") is None

    def test_extract_ticket_lowercase(self):
        """Test extraction with lowercase ticket in branch name."""
        git_ops = GitOperations()

        # Lowercase variants should work and return uppercase
        assert git_ops.extract_ticket_number("star-422270-test", r"STAR-(\d+)") == "STAR-422270"
        assert git_ops.extract_ticket_number("feature/star-12345-add-feature", r"STAR-(\d+)") == "STAR-12345"
        assert git_ops.extract_ticket_number("Star-999-bugfix", r"STAR-(\d+)") == "STAR-999"

    def test_extract_ticket_custom_pattern(self):
        """Test extraction with custom pattern."""
        git_ops = GitOperations()

        # JIRA-style
        assert git_ops.extract_ticket_number("feature/JIRA-123", r"JIRA-(\d+)") == "JIRA-123"
        assert git_ops.extract_ticket_number("feature/jira-123", r"JIRA-(\d+)") == "JIRA-123"

        # Linear-style
        assert git_ops.extract_ticket_number("ENG-456-feature", r"ENG-(\d+)") == "ENG-456"
        assert git_ops.extract_ticket_number("eng-456-feature", r"ENG-(\d+)") == "ENG-456"


class TestGenerateTicketPrefix:
    """Tests for generate_ticket_prefix() method."""

    def _make_git_ops(self, dir_name: str):
        """Create a GitOperations mock with a given working directory name."""
        mock_repo = Mock()
        mock_repo.working_dir = f"/some/path/{dir_name}"
        git_ops = GitOperations.__new__(GitOperations)
        git_ops.repo = mock_repo
        return git_ops

    def test_two_word_name(self):
        # pr-agent → P(pr) + A(agent) + G(gent) + E(nt) = PAGE
        git_ops = self._make_git_ops("pr-agent")
        assert git_ops.generate_ticket_prefix() == "PAGE"

    def test_three_word_name_with_one_char_padding(self):
        # my-cool-app → M + C + A + P(2nd char of app) = MCAP
        git_ops = self._make_git_ops("my-cool-app")
        assert git_ops.generate_ticket_prefix() == "MCAP"

    def test_single_word_name(self):
        # myapp → M + Y + A + P = MYAP
        git_ops = self._make_git_ops("myapp")
        assert git_ops.generate_ticket_prefix() == "MYAP"

    def test_two_char_word_cycles(self):
        # pr → P + R + P(wrap) + R = PRPR
        git_ops = self._make_git_ops("pr")
        assert git_ops.generate_ticket_prefix() == "PRPR"

    def test_single_char_word_cycles(self):
        # x → X + X + X + X = XXXX
        git_ops = self._make_git_ops("x")
        assert git_ops.generate_ticket_prefix() == "XXXX"

    def test_consecutive_separators_filtered(self):
        # my--app → words=[my, app] → M + A + P + P = MAPP
        git_ops = self._make_git_ops("my--app")
        assert git_ops.generate_ticket_prefix() == "MAPP"

    def test_all_numeric_falls_back_to_REPO(self):
        git_ops = self._make_git_ops("123-456")
        assert git_ops.generate_ticket_prefix() == "REPO"

    def test_empty_dir_name_falls_back_to_REPO(self):
        mock_repo = Mock()
        mock_repo.working_dir = "/"
        git_ops = GitOperations.__new__(GitOperations)
        git_ops.repo = mock_repo
        assert git_ops.generate_ticket_prefix() == "REPO"

    def test_four_or_more_words_uses_first_four(self):
        # my-cool-new-feature → M + C + N + F = MCNF (no padding needed)
        git_ops = self._make_git_ops("my-cool-new-feature")
        assert git_ops.generate_ticket_prefix() == "MCNF"

    def test_result_is_always_uppercase(self):
        git_ops = self._make_git_ops("lowercase-name")
        result = git_ops.generate_ticket_prefix()
        assert result == result.upper()

    def test_result_is_always_4_chars(self):
        for name in ["a", "ab", "abc", "abcd", "my-app", "pr-agent", "123-456"]:
            git_ops = self._make_git_ops(name)
            result = git_ops.generate_ticket_prefix()
            assert len(result) == 4, f"Expected 4 chars for '{name}', got '{result}'"
