"""Tests for PR generator module."""

import pytest
from unittest.mock import Mock
from src.pr_generator import PRGenerator
from src.prompts import PRPrompts


class TestPRGenerator:
    """Test PR generation functionality."""

    def test_format_pr_body(self):
        """Test PR body formatting."""
        mock_llm = Mock()
        mock_git = Mock()

        generator = PRGenerator(mock_llm, mock_git)

        sections = {
            "section_0": "This change adds authentication.",
            "section_1": "May affect login flow.",
            "section_2": "No additional notes."
        }

        template_sections = [
            "Why are you making this change?",
            "What are the possible impacts?",
            "Anything else?"
        ]

        body = generator.format_pr_body(sections, template_sections)

        assert "## Why are you making this change?" in body
        assert "This change adds authentication." in body
        assert "## What are the possible impacts?" in body

    def test_format_pr_body_variable_sections(self):
        """Test PR body formatting with variable number of sections."""
        mock_llm = Mock()
        mock_git = Mock()

        generator = PRGenerator(mock_llm, mock_git)

        # Test with 4 sections
        sections = {
            "section_0": "Section 1 content",
            "section_1": "Section 2 content",
            "section_2": "Section 3 content",
            "section_3": "Section 4 content",
        }

        template_sections = [
            "Custom Section 1",
            "Custom Section 2",
            "Custom Section 3",
            "Custom Section 4",
        ]

        body = generator.format_pr_body(sections, template_sections)

        assert "## Custom Section 1" in body
        assert "Section 1 content" in body
        assert "## Custom Section 2" in body
        assert "Section 2 content" in body
        assert "## Custom Section 3" in body
        assert "Section 3 content" in body
        assert "## Custom Section 4" in body
        assert "Section 4 content" in body


class TestPRPrompts:
    """Test prompt generation."""

    def test_extract_diff_summary(self):
        """Test diff summary extraction."""
        diff = """diff --git a/file.py b/file.py
+++ b/file.py
@@ -1,5 +1,5 @@
+new line
-old line
"""

        summary = PRPrompts.extract_diff_summary(diff, max_length=500)

        assert "diff --git" in summary
        assert "+new line" in summary


class TestGenerateDescriptionWithRelatedPrs:
    """Test that related_prs_context is threaded into section generation."""

    def _make_generator(self):
        mock_llm = Mock()
        mock_llm.generate.return_value = "Generated content"
        mock_git = Mock()
        mock_git.get_changed_files.return_value = ["src/auth.py"]
        mock_git.get_commit_messages.return_value = ["STAR-1: Add auth"]
        mock_git.get_diff.return_value = ""
        return PRGenerator(mock_llm, mock_git), mock_llm

    def test_related_prs_context_added_to_system_prompt(self):
        generator, mock_llm = self._make_generator()
        generator.generate_description(
            user_intent="add auth",
            base_branch="main",
            related_prs_context="This builds on #42.",
        )
        # Every LLM call should use an augmented system prompt
        for call in mock_llm.generate.call_args_list:
            system = call.kwargs.get("system") or ""
            assert "This builds on #42." in system
            # Context should appear BEFORE the base system prompt text
            assert system.index("This builds on #42.") < system.index("You are")

    def test_no_related_prs_context_uses_default_system_prompt(self):
        generator, mock_llm = self._make_generator()
        generator.generate_description(
            user_intent="add auth",
            base_branch="main",
        )
        for call in mock_llm.generate.call_args_list:
            system = call.kwargs.get("system") or ""
            # Default system prompt should be used — no extra context injected
            assert "Context from related PRs" not in system

    def test_generate_description_accepts_related_prs_context_param(self):
        generator, _ = self._make_generator()
        # Should not raise
        generator.generate_description(
            user_intent="add auth",
            base_branch="main",
            related_prs_context="",
        )
