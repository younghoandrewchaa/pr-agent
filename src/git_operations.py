"""
Git operations module.

Handles all git-related operations including branch name extraction,
ticket number parsing, diff retrieval, and repository validation.
"""

import re
from pathlib import Path
from typing import Optional, List

import git
from git.exc import InvalidGitRepositoryError

from src.exceptions import NotInGitRepoError, NoChangesError, BranchNameError


class GitOperations:
    """Handles git operations for PR creation."""

    def __init__(self, repo_path: Optional[Path] = None):
        """
        Initialize GitOperations.

        Args:
            repo_path: Path to git repository. Defaults to current directory.

        Raises:
            NotInGitRepoError: If the path is not a git repository.
        """
        try:
            self.repo = git.Repo(repo_path or Path.cwd(), search_parent_directories=True)
        except InvalidGitRepositoryError:
            raise NotInGitRepoError()

    def validate_git_repo(self) -> bool:
        """
        Validate that we're in a git repository.

        Returns:
            True if in a valid git repository.

        Raises:
            NotInGitRepoError: If not in a git repository.
        """
        if self.repo.bare:
            raise NotInGitRepoError()
        return True

    def get_current_branch(self) -> str:
        """
        Get the name of the current branch.

        Returns:
            Current branch name.

        Raises:
            GitError: If unable to determine current branch.
        """
        try:
            return self.repo.active_branch.name
        except TypeError:
            # Detached HEAD state
            raise BranchNameError("Detached HEAD state. Please checkout a branch.")

    def extract_ticket_number(self, branch_name: Optional[str] = None,
                             pattern: str = r"STAR-(\d+)") -> Optional[str]:
        """
        Extract ticket number from branch name using regex pattern.

        Args:
            branch_name: Branch name to parse. If None, uses current branch.
            pattern: Regex pattern to extract ticket number. Default: "STAR-(\\d+)"

        Returns:
            Ticket number (e.g., "STAR-12345") or None if not found.

        Examples:
            >>> git_ops.extract_ticket_number("feature/STAR-12345-add-feature")
            "STAR-12345"
            >>> git_ops.extract_ticket_number("STAR-999-bugfix")
            "STAR-999"
            >>> git_ops.extract_ticket_number("feature-no-ticket")
            None
        """
        if branch_name is None:
            branch_name = self.get_current_branch()

        match = re.search(pattern, branch_name, re.IGNORECASE)
        if match:
            # Return the full match in uppercase (e.g., "STAR-12345")
            return match.group(0).upper()
        return None

    def get_diff(self, base_branch: str = "main", allow_empty: bool = False) -> str:
        """
        Get unified diff against base branch.

        Args:
            base_branch: Branch to diff against. Default: "main"
            allow_empty: If True, returns empty string instead of raising error. Default: False

        Returns:
            Unified diff string.

        Raises:
            NoChangesError: If there are no changes and allow_empty is False.
        """
        try:
            # Get diff between base branch and current HEAD
            diff = self.repo.git.diff(f"{base_branch}...HEAD")

            if not diff.strip():
                if allow_empty:
                    return ""
                raise NoChangesError()

            return diff
        except git.exc.GitCommandError as e:
            if "unknown revision" in str(e).lower() or "bad revision" in str(e).lower():
                # Provide helpful error message with suggestions
                available_branches = self.get_available_branches()
                error_msg = f"Base branch '{base_branch}' not found.\n"

                if available_branches:
                    # Suggest common alternatives
                    common = [b for b in ['main', 'master', 'develop'] if b in available_branches]
                    if common:
                        error_msg += f"\nTry one of these instead: {', '.join(common)}"
                        error_msg += f"\nExample: pr-agent create --base-branch {common[0]}"
                    else:
                        error_msg += f"\nAvailable branches: {', '.join(available_branches[:5])}"
                        if len(available_branches) > 5:
                            error_msg += f" (and {len(available_branches) - 5} more)"

                raise BranchNameError(error_msg)
            raise

    def get_changed_files(self, base_branch: str = "main") -> List[str]:
        """
        Get list of files changed compared to base branch.

        Args:
            base_branch: Branch to compare against. Default: "main"

        Returns:
            List of file paths that have been modified.
        """
        try:
            # Get list of changed files
            changed = self.repo.git.diff(
                f"{base_branch}...HEAD",
                name_only=True
            ).strip().split('\n')

            # Filter out empty strings
            return [f for f in changed if f]
        except git.exc.GitCommandError:
            return []

    def get_commit_messages(self, base_branch: str = "main") -> List[str]:
        """
        Get commit messages from current branch compared to base.

        Args:
            base_branch: Branch to compare against. Default: "main"

        Returns:
            List of commit messages.
        """
        try:
            log = self.repo.git.log(
                f"{base_branch}..HEAD",
                pretty="format:%s"
            ).strip()

            if not log:
                return []

            return log.split('\n')
        except git.exc.GitCommandError:
            return []

    def has_uncommitted_changes(self) -> bool:
        """
        Check if there are uncommitted changes.

        Returns:
            True if there are uncommitted changes.
        """
        return self.repo.is_dirty()

    def get_uncommitted_diff(self) -> str:
        """
        Get the diff of uncommitted changes.

        Returns:
            Diff of both staged and unstaged changes.
        """
        return self.repo.git.diff('HEAD')

    def stage_all_changes(self) -> None:
        """
        Stage all changes (git add -A).

        Raises:
            GitError: If staging fails.
        """
        from src.exceptions import GitError
        try:
            self.repo.git.add('-A')
        except git.exc.GitCommandError as e:
            raise GitError(f"Failed to stage changes: {e}")

    def create_commit(self, message: str) -> None:
        """
        Create a commit with the given message.

        Args:
            message: Commit message

        Raises:
            GitError: If commit fails.
        """
        from src.exceptions import GitError
        try:
            self.repo.index.commit(message)
        except git.exc.GitCommandError as e:
            raise GitError(f"Failed to create commit: {e}")

    def has_commits_ahead(self, base_branch: str = "main") -> bool:
        """
        Check if current branch has commits ahead of base branch.

        Args:
            base_branch: Branch to compare against. Default: "main"

        Returns:
            True if current branch has commits not in base branch.
        """
        try:
            # Get commits that are in HEAD but not in base_branch
            commits = self.repo.git.log(
                f"{base_branch}..HEAD",
                pretty="format:%H",
                max_count=1  # Just check if at least one exists
            ).strip()

            return bool(commits)
        except git.exc.GitCommandError:
            return False

    def get_commit_count(self, base_branch: str = "main") -> int:
        """
        Get number of commits ahead of base branch.

        Args:
            base_branch: Branch to compare against. Default: "main"

        Returns:
            Number of commits.
        """
        try:
            count = self.repo.git.rev_list(
                f"{base_branch}..HEAD",
                count=True
            ).strip()

            return int(count) if count else 0
        except (git.exc.GitCommandError, ValueError):
            return 0

    def get_repository_root(self) -> Path:
        """
        Get the root directory of the git repository.

        Returns:
            Path to repository root.
        """
        return Path(self.repo.working_dir)

    def generate_ticket_prefix(self) -> str:
        """
        Derive a 4-letter uppercase ticket prefix from the repository directory name.

        Splits the directory name on non-alpha characters, collects the first
        letter of each word, then cycles through the last word's remaining
        characters until 4 letters are collected.

        Returns:
            4-letter uppercase prefix (e.g., "PAGE" for "pr-agent").
            Falls back to "REPO" if the directory name has no alphabetic characters.
        """
        dir_name = Path(self.repo.working_dir).name

        # Split on non-alpha characters and filter empty tokens
        words = [w for w in re.split(r'[^a-zA-Z]+', dir_name) if w]

        if not words:
            return "REPO"

        letters: List[str] = []

        # Collect the first letter of each word
        for word in words:
            letters.append(word[0].upper())
            if len(letters) == 4:
                return ''.join(letters)

        # Fewer than 4 letters — cycle through remaining chars of last word
        last_word = words[-1].upper()
        i = 1  # start after the first char (already collected above)
        while len(letters) < 4:
            if i >= len(last_word):
                i = 0  # wrap to beginning of last word
            letters.append(last_word[i])
            i += 1

        return ''.join(letters)

    def get_default_branch(self) -> Optional[str]:
        """
        Detect the default branch of the repository.

        Tries to determine the default branch by:
        1. Checking the remote HEAD (origin/HEAD)
        2. Trying common branch names (main, master, develop)

        Returns:
            Default branch name or None if not found.
        """
        try:
            # Method 1: Try to get the default branch from remote HEAD
            try:
                remote_head = self.repo.git.symbolic_ref("refs/remotes/origin/HEAD")
                # Extract branch name from "refs/remotes/origin/main"
                if remote_head:
                    return remote_head.split('/')[-1]
            except git.exc.GitCommandError:
                pass

            # Method 2: Try common branch names
            common_branches = ['main', 'master', 'develop', 'development']
            for branch in common_branches:
                if self.branch_exists(branch):
                    return branch

            return None
        except Exception:
            return None

    def branch_exists(self, branch_name: str) -> bool:
        """
        Check if a branch exists (local or remote).

        Args:
            branch_name: Branch name to check

        Returns:
            True if branch exists.
        """
        try:
            # Check local branches
            for ref in self.repo.refs:
                if ref.name == branch_name:
                    return True

            # Check remote branches
            try:
                self.repo.git.rev_parse(f"origin/{branch_name}")
                return True
            except git.exc.GitCommandError:
                pass

            return False
        except Exception:
            return False

    def get_available_branches(self) -> List[str]:
        """
        Get list of available branches (local and remote).

        Returns:
            List of branch names.
        """
        try:
            branches = []

            # Get local branches
            for ref in self.repo.refs:
                if not ref.name.startswith('origin/'):
                    branches.append(ref.name)

            # Get remote branches
            try:
                remote_refs = self.repo.git.branch('-r').strip().split('\n')
                for ref in remote_refs:
                    ref = ref.strip()
                    if ref and not ref.startswith('origin/HEAD'):
                        # Remove 'origin/' prefix
                        branch = ref.replace('origin/', '')
                        if branch not in branches:
                            branches.append(branch)
            except git.exc.GitCommandError:
                pass

            return sorted(branches)
        except Exception:
            return []
