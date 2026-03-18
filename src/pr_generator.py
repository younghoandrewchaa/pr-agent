"""
PR generation logic module.

Coordinates LLM calls to generate comprehensive PR titles and descriptions
using git information and user input.
"""

from typing import List, Optional, Dict, Union

from src.llm_client import CopilotClient, ClaudeCodeClient
from src.prompts import PRPrompts
from src.git_operations import GitOperations
from src.template_parser import get_pr_template_sections


# Temperature settings for conciseness
TITLE_TEMPERATURE = 0.5  # Keep current
WHY_TEMPERATURE = 0.4    # Slightly lower for focus
IMPACT_TEMPERATURE = 0.3  # Factual, terse
NOTES_TEMPERATURE = 0.3   # Factual, no repetition

# Max token limits for sections
WHY_MAX_TOKENS = 100     # ~75 words
IMPACT_MAX_TOKENS = 50   # ~35-40 words (target ~25, allow buffer)
NOTES_MAX_TOKENS = 60    # ~45 words

# Diff context limits (reduced ~50%)
WHY_DIFF_LIMIT = 800     # Down from 1500
IMPACT_DIFF_LIMIT = 500  # Down from 1000
NOTES_DIFF_LIMIT = 500   # Down from 1000


class PRGenerator:
    """Generates PR titles and descriptions using LLM."""

    def __init__(
        self,
        llm_client: Union[CopilotClient, ClaudeCodeClient],
        git_ops: GitOperations,
        model: str = "claude-haiku-4.5",
        max_diff_tokens: int = 8000,
        repo_path: Optional[str] = None,
    ):
        """
        Initialize PR generator.

        Args:
            llm_client: Copilot client for LLM interactions
            git_ops: Git operations handler
            model: Model name (for compatibility, uses Copilot's claude-haiku-4.5)
            max_diff_tokens: Maximum characters for diff context
            repo_path: Path to repository root (used for template loading)
        """
        self.llm_client = llm_client
        self.git_ops = git_ops
        self.model = model
        self.max_diff_tokens = max_diff_tokens
        self.repo_path = repo_path
        self.prompts = PRPrompts()

    def _build_system_prompt(self, related_prs_context: str = "") -> str:
        """Build system prompt, optionally augmented with related PR context."""
        if not related_prs_context:
            return self.prompts.SYSTEM_PROMPT
        return (
            f"Context from related PRs previously created in this repository:\n"
            f"{related_prs_context}\n\n"
            f"Incorporate references to related PRs naturally where relevant in the description.\n\n"
            f"{self.prompts.SYSTEM_PROMPT}"
        )

    def generate_title(
        self,
        ticket_number: str,
        branch_name: str,
        user_intent: str,
    ) -> str:
        """
        Generate PR title.

        Args:
            ticket_number: Ticket identifier (e.g., "STAR-12345")
            branch_name: Current branch name
             user_intent: User's description of the change purpose

         Returns:
             Generated PR title in format: "STAR-XXX: Description"
        """
        prompt = self.prompts.generate_title_prompt(ticket_number, branch_name, user_intent)

        # Title generation uses the base system prompt — related PR context is only
        # injected into description sections where it provides meaningful value.
        title = self.llm_client.generate(
            prompt=prompt,
            system=self.prompts.SYSTEM_PROMPT,
            temperature=TITLE_TEMPERATURE,
        )

        # Ensure title starts with ticket number
        if not title.startswith(ticket_number):
            # Extract description from generated title if it doesn't have ticket
            if ":" in title:
                description = title.split(":", 1)[1].strip()
            else:
                description = title.strip()
            title = f"{ticket_number}: {description}"

        return title.strip()

    def generate_why_section(
        self,
        user_intent: str,
        changed_files: List[str],
        diff: Optional[str] = None,
        feedback_history: Optional[List[str]] = None,
        system_prompt: Optional[str] = None,
    ) -> str:
        """
        Generate "Why are you making this change?" section.

        Args:
            user_intent: User's description of change purpose
            changed_files: List of modified files
            diff: Optional git diff for additional context
            feedback_history: Optional list of user feedback from previous iterations

        Returns:
            Generated explanation text.
        """
        feedback_history = feedback_history or []
        prompt = self.prompts.generate_why_prompt(user_intent, changed_files, feedback_history)

        if diff and len(diff) < self.max_diff_tokens:
            diff_summary = self.prompts.extract_diff_summary(diff, WHY_DIFF_LIMIT)
            prompt += f"\n\nCode changes (summary):\n{diff_summary}"

        response = self.llm_client.generate(
            prompt=prompt,
            system=system_prompt or self.prompts.SYSTEM_PROMPT,
            temperature=WHY_TEMPERATURE,
            max_tokens=WHY_MAX_TOKENS,
        )

        return response.strip()

    def generate_impact_section(
        self,
        changed_files: List[str],
        commit_messages: List[str],
        diff: Optional[str] = None,
        feedback_history: Optional[List[str]] = None,
        system_prompt: Optional[str] = None,
    ) -> str:
        """
        Generate "What are the possible impacts?" section.

        Args:
            changed_files: List of modified files
            commit_messages: List of commit messages
            diff: Optional git diff for additional context
            feedback_history: Optional list of user feedback from previous iterations

        Returns:
            Generated impact analysis text.
        """
        feedback_history = feedback_history or []
        prompt = self.prompts.generate_impact_prompt(changed_files, commit_messages, feedback_history)

        if diff:
            diff_summary = self.prompts.extract_diff_summary(diff, IMPACT_DIFF_LIMIT)
            prompt += f"\n\nCode changes (summary):\n{diff_summary}"

        response = self.llm_client.generate(
            prompt=prompt,
            system=system_prompt or self.prompts.SYSTEM_PROMPT,
            temperature=IMPACT_TEMPERATURE,
            max_tokens=IMPACT_MAX_TOKENS,
        )

        return response.strip()

    def generate_notes_section(
        self,
        changed_files: List[str],
        diff: Optional[str] = None,
        feedback_history: Optional[List[str]] = None,
        system_prompt: Optional[str] = None,
    ) -> str:
        """
        Generate "Anything else reviewers should know?" section.

        Args:
            changed_files: List of modified files
            diff: Optional git diff for additional context
            feedback_history: Optional list of user feedback from previous iterations

         Returns:
            Generated notes text.
        """
        feedback_history = feedback_history or []
        diff_summary = ""
        if diff:
            diff_summary = self.prompts.extract_diff_summary(diff, NOTES_DIFF_LIMIT)

        prompt = self.prompts.generate_notes_prompt(changed_files, diff_summary, feedback_history)

        response = self.llm_client.generate(
            prompt=prompt,
            system=system_prompt or self.prompts.SYSTEM_PROMPT,
            temperature=NOTES_TEMPERATURE,
            max_tokens=NOTES_MAX_TOKENS,
        )

        return response.strip()

    def generate_description(
        self,
        user_intent: str,
        base_branch: str = "main",
        feedback_history: Optional[List[str]] = None,
        related_prs_context: str = "",
    ) -> str:
        """
        Generate complete PR description.

        Dynamically loads template sections from .github/pull_request_template.md
        if available, otherwise uses default sections.

        Args:
            user_intent: User's description of change purpose
            base_branch: Base branch for diff comparison
            feedback_history: Optional list of user feedback from previous iterations
            related_prs_context: Optional summary of related previous PRs to inject into the system prompt.

        Returns:
            Formatted PR description with all sections.
        """
        feedback_history = feedback_history or []
        system_prompt = self._build_system_prompt(related_prs_context)

        # Get git information
        changed_files = self.git_ops.get_changed_files(base_branch)
        commit_messages = self.git_ops.get_commit_messages(base_branch)

        # Get diff (allow empty in case there are commits but no file changes)
        try:
            diff = self.git_ops.get_diff(base_branch, allow_empty=True)
        except Exception:
            # Fallback to empty diff if something goes wrong
            diff = ""

        # Truncate diff if too large
        if diff and len(diff) > self.max_diff_tokens:
            diff = diff[: self.max_diff_tokens] + "\n\n... (diff truncated)"

        # Load template sections dynamically from repository
        if self.repo_path:
            template_sections = get_pr_template_sections(self.repo_path)
        else:
            # Fallback to defaults if no repo path provided
            from src.template_parser import DEFAULT_SECTIONS

            template_sections = DEFAULT_SECTIONS.copy()

        # Generate content for each section
        sections: Dict[str, str] = {}

        for i, section in enumerate(template_sections):
            # Map sections to generation methods based on keywords or position
            section_lower = section.lower()

            if "why" in section_lower or i == 0:
                # First section or "why" keyword - explain the change
                sections[f"section_{i}"] = self.generate_why_section(
                    user_intent, changed_files, diff, feedback_history, system_prompt=system_prompt
                )
            elif "impact" in section_lower or i == 1:
                # Second section or "impact" keyword - analyze impact
                sections[f"section_{i}"] = self.generate_impact_section(
                    changed_files, commit_messages, diff, feedback_history, system_prompt=system_prompt
                )
            else:
                # Other sections - additional notes
                sections[f"section_{i}"] = self.generate_notes_section(
                    changed_files, diff, feedback_history, system_prompt=system_prompt
                )

        # Format into final description
        return self.format_pr_body(sections, template_sections)

    def format_pr_body(
        self,
        sections: Dict[str, str],
        template_sections: List[str],
    ) -> str:
        """
        Format sections into final PR body template.

        Handles variable number of sections dynamically based on template.

        Args:
            sections: Generated content for each section (keyed by "section_N")
            template_sections: Section headers from template

        Returns:
            Formatted PR description.
        """
        body_parts = []

        # Iterate through all template sections
        for i, section_header in enumerate(template_sections):
            # Add section header
            body_parts.append(f"## {section_header}")
            body_parts.append("")  # Blank line after header

            # Get content for this section
            content = sections.get(f"section_{i}", "")

            # For the last section, handle "no additional notes" case
            if i == len(template_sections) - 1:
                if content and content.lower() != "no additional notes.":
                    body_parts.append(content)
                else:
                    body_parts.append("No additional notes.")
            else:
                body_parts.append(content)

            # Add spacing between sections
            body_parts.append("")

        return "\n".join(body_parts).strip()
