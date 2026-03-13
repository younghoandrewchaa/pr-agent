"""
LLM prompt templates for PR generation.

Provides engineered prompts for generating high-quality PR descriptions
with focus on clarity, completeness, and reviewer value.
"""

from typing import List


class PRPrompts:
    """Collection of prompts for PR description generation."""

    SYSTEM_PROMPT = """You are a helpful assistant that writes clear, concise pull request descriptions.
Be direct and brief. Avoid headers, numbered sections, or verbose explanations.
Focus on practical information that helps reviewers understand the change quickly."""

    @staticmethod
    def extract_ticket_number_prompt(branch_name: str, ticket_prefix: str = "STAR") -> str:
        """
        Generate prompt for extracting ticket number from branch name using LLM.

        Args:
            branch_name: Branch name to extract ticket from
            ticket_prefix: Expected ticket prefix (e.g., "STAR", "JIRA", "ENG")

        Returns:
            Prompt for ticket extraction.
        """
        return f"""Extract the ticket number from this git branch name: "{branch_name}"

The ticket number typically starts with "{ticket_prefix}" followed by a dash and numbers.
Common formats include:
- {ticket_prefix}-12345
- {ticket_prefix.lower()}-12345
- {ticket_prefix.upper()}-12345

Branch name variations:
- feature/{ticket_prefix}-123-description
- {ticket_prefix}-123-some-feature
- bugfix-{ticket_prefix.lower()}-456-fix
- {ticket_prefix.lower()}_789_something
- and many other creative formats

Instructions:
1. Look for the ticket identifier in the branch name
2. Return ONLY the ticket number in the format: {ticket_prefix.upper()}-[number]
3. If you find the ticket, return just the ticket like: {ticket_prefix.upper()}-12345
4. If no ticket number is found, return exactly: NONE

Examples:
- "star-422270-test" → STAR-422270
- "feature/STAR-12345-add-auth" → STAR-12345
- "bugfix_star_999_memory_leak" → STAR-999
- "some-branch-without-ticket" → NONE

Now extract from: "{branch_name}"

Return ONLY the ticket number or NONE, nothing else."""

    @staticmethod
    def generate_title_prompt(ticket_number: str, branch_name: str, user_intent: str) -> str:
        """
        Generate prompt for PR title creation.

        Args:
            ticket_number: Ticket identifier (e.g., "STAR-12345")
            branch_name: Current branch name
            user_intent: User's description of the change

        Returns:
            Prompt for title generation.
        """
        return f"""Generate a concise PR title following this format: "{ticket_number}: <description>"

Branch name: {branch_name}
Change purpose: {user_intent}

Requirements:
- Start with the ticket number: {ticket_number}
- Follow with a colon and space
- Write a clear, actionable description (3-8 words)
- Use imperative mood (e.g., "Add", "Fix", "Update", not "Added", "Fixed", "Updated")
- Be specific but concise

Examples:
- STAR-123: Add user authentication flow
- STAR-456: Fix memory leak in data processor
- STAR-789: Update API error handling

Generate only the title, nothing else."""

    @staticmethod
    def generate_commit_message_prompt(
        ticket_number: str,
        changed_files: List[str],
        diff_summary: str
    ) -> str:
        """
        Generate prompt for commit message creation.

        Args:
            ticket_number: Ticket identifier (e.g., "STAR-41789")
            changed_files: List of modified files
            diff_summary: Summary of the diff

        Returns:
            Prompt for commit message generation.
        """
        files_str = "\n".join(f"- {f}" for f in changed_files[:10])
        if len(changed_files) > 10:
            files_str += f"\n... and {len(changed_files) - 10} more files"

        return f"""Generate a concise git commit message following this format: "{ticket_number}: <description>"

Files changed:
{files_str}

Changes summary:
{diff_summary[:1000]}

Requirements:
- Start with the ticket number: {ticket_number}
- Follow with a colon and space
- Write a clear, actionable description (3-8 words)
- Use imperative mood (e.g., "Add", "Fix", "Update", not "Added", "Fixed", "Updated")
- Be specific but concise
- Focus on WHAT changed, not WHY

Examples:
- STAR-123: Add user authentication middleware
- STAR-456: Fix memory leak in data processor
- STAR-789: Update error handling in API routes

Generate only the commit message, nothing else."""

    # Semantic boundary: Why section focuses on TECHNICAL problems (what's broken/missing/inadequate).
    # Deployment context (new code, adoption status, timing) belongs in Notes section.
    @staticmethod
    def generate_why_prompt(
        user_intent: str,
        changed_files: List[str],
        feedback_history: List[str] | None = None,
    ) -> str:
        """
        Generate prompt for "Why are you making this change?" section.

        Args:
            user_intent: User's description of the change purpose
            changed_files: List of modified files
            feedback_history: Optional list of user feedback from previous iterations

        Returns:
            Prompt for why section.
        """
        feedback_history = feedback_history or []
        files_str = "\n".join(f"- {f}" for f in changed_files[:10])  # Limit to 10 files
        if len(changed_files) > 10:
            files_str += f"\n... and {len(changed_files) - 10} more files"

        prompt = f"""Explain the technical problem this change solves in 1-2 concise sentences (max 50 words total).

User's purpose: {user_intent}
Files modified: {files_str}

Focus on: What was broken, missing, or inadequate in the code that required this change.
Stick to technical motivation only - do NOT mention deployment context, adoption status, or timing.
Be direct and concise. No headers, bullet points, or extra formatting."""

        # Append feedback if this is a regeneration
        if feedback_history:
            feedback_str = "\n".join(f"{i+1}. {fb}" for i, fb in enumerate(feedback_history))
            prompt += f"""

**IMPORTANT - User Feedback on Previous Versions:**
The user reviewed previous versions and provided this feedback:
{feedback_str}

Please regenerate the description incorporating all of the above feedback points.
Focus on addressing each piece of feedback while maintaining the overall structure and quality."""

        return prompt

    @staticmethod
    def generate_impact_prompt(
        changed_files: List[str],
        commit_messages: List[str],
        feedback_history: List[str] | None = None,
    ) -> str:
        """
        Generate prompt for "What are the possible impacts?" section.

        Args:
            changed_files: List of modified files
            commit_messages: List of commit messages
            feedback_history: Optional list of user feedback from previous iterations

        Returns:
            Prompt for impact section.
        """
        feedback_history = feedback_history or []
        files_str = "\n".join(f"- {f}" for f in changed_files[:15])
        if len(changed_files) > 15:
            files_str += f"\n... and {len(changed_files) - 15} more files"

        commits_str = ""
        if commit_messages:
            commits_str = "Commits:\n" + "\n".join(f"- {msg}" for msg in commit_messages[:5])

        prompt = f"""List the potential production impacts of this change.

Files modified:
{files_str}

{commits_str}

Requirements:
- Keep total response under 25 words
- Use 1-2 bullet points maximum, or a single concise statement
- Every word must add value - remove adjectives and filler phrases
- Only list REAL, concrete production impacts (performance degradation, breaking changes, data loss risk, etc.)
- Do NOT mention risks that are "minimal", "unlikely", or "low" - if a risk is minimal, skip it entirely
- Do NOT include generic "testing needed" points - assume all changes need testing
- Do NOT list theoretical risks that apply to any code change
- If truly low-risk: say "Low-risk change" or "No significant production impact expected"
- Be specific and actionable, not vague

Examples of GOOD impact statements:
- Breaking change: Removes deprecated API endpoint used by mobile app
- Performance: Database migration will lock table for ~5 minutes

Examples of BAD impact statements (DO NOT write these):
- Testing needed: Verify that changes don't break workflows
- Security risk: Could introduce vulnerabilities, though likely minimal
- Compatibility concern: Might affect existing configurations

NO headers, numbered lists, or summary sections - just simple bullet points or a single statement."""

        # Append feedback if this is a regeneration
        if feedback_history:
            feedback_str = "\n".join(f"{i+1}. {fb}" for i, fb in enumerate(feedback_history))
            prompt += f"""

**IMPORTANT - User Feedback on Previous Versions:**
The user reviewed previous versions and provided this feedback:
{feedback_str}

Please regenerate the description incorporating all of the above feedback points.
Focus on addressing each piece of feedback while maintaining the overall structure and quality."""

        return prompt

    # Semantic boundary: Notes section captures DEPLOYMENT context (new/unused code, adoption status)
    # and review guidance not covered by Impact section. Technical motivation belongs in Why section.
    @staticmethod
    def generate_notes_prompt(
        changed_files: List[str],
        diff_summary: str,
        feedback_history: List[str] | None = None,
    ) -> str:
        """
        Generate prompt for "Anything else reviewers should know?" section.

        Args:
            changed_files: List of modified files
            diff_summary: Summary or excerpt of the diff
            feedback_history: Optional list of user feedback from previous iterations

        Returns:
            Prompt for notes section.
        """
        feedback_history = feedback_history or []
        files_str = "\n".join(f"- {f}" for f in changed_files[:10])

        prompt = f"""List anything important for reviewers that was NOT already mentioned in the Impact section above.

Focus on deployment context and review guidance:
- Current state of affected code (new/unused/experimental/deprecated/heavily-used)
- When or where this will be used (adoption status, rollout plans, timing)
- Dependencies, config changes, migrations
- Tricky review areas or areas requiring extra scrutiny

Requirements:
- Do NOT repeat information from the Impact section
- Only mention NEW information not covered above
- If nothing new to add: "No additional notes."
- Maximum 2 bullet points, 40 words total

Files modified:
{files_str}

Change summary:
{diff_summary}

No headers or extra formatting."""

        # Append feedback if this is a regeneration
        if feedback_history:
            feedback_str = "\n".join(f"{i+1}. {fb}" for i, fb in enumerate(feedback_history))
            prompt += f"""

**IMPORTANT - User Feedback on Previous Versions:**
The user reviewed previous versions and provided this feedback:
{feedback_str}

Please regenerate the description incorporating all of the above feedback points.
Focus on addressing each piece of feedback while maintaining the overall structure and quality."""

        return prompt

    @staticmethod
    def find_related_prs_prompt(title: str, intent: str, history: list) -> str:
        """
        Generate prompt for detecting associations between a new PR and previous ones.

        Args:
            title: New PR title
            intent: User's stated purpose for the new PR
            history: List of history entries (pr_number, title, description, created_at)

        Returns:
            Prompt for association detection.
        """
        history_text = "\n\n".join(
            f"PR #{e['pr_number']} ({e['created_at'][:10]}): {e['title']}\n{e['description']}"
            for e in history
        )

        return f"""You are reviewing a new pull request to see if it is related to any previous PRs in the same repository.

New PR:
Title: {title}
Purpose: {intent}

Previous PRs in this repository:
{history_text}

If any previous PRs are clearly related to the new one (same feature area, continuation of work, depends on, builds upon, or fixes issues introduced by), write a brief 1-2 sentence summary naming the related PRs by number and explaining the relationship.

If no previous PRs are clearly related, respond with exactly: NONE

Do not speculate. Only mention PRs with a clear, specific connection. Do not list PRs just because they touch similar files."""

    @staticmethod
    def extract_diff_summary(diff: str, max_length: int = 1000) -> str:
        """
        Extract a meaningful summary from a git diff.

        Args:
            diff: Full git diff
            max_length: Maximum characters to include

        Returns:
            Summarized diff focusing on changed files and additions.
        """
        lines = diff.split('\n')
        summary_lines = []
        char_count = 0

        for line in lines:
            # Include file headers and some context
            if line.startswith('diff --git') or line.startswith('+++') or \
               line.startswith('---') or line.startswith('@@'):
                summary_lines.append(line)
                char_count += len(line)
            # Include added/removed lines sparingly
            elif line.startswith('+') or line.startswith('-'):
                if char_count < max_length * 0.7:  # Reserve space for headers
                    summary_lines.append(line)
                    char_count += len(line)

            if char_count >= max_length:
                summary_lines.append("... (diff truncated)")
                break

        return '\n'.join(summary_lines)
