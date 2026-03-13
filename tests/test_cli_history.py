"""Integration tests for PR history calls in the create command."""

from click.testing import CliRunner
from unittest.mock import Mock, patch, ANY

from src.cli import cli


def _setup_mocks():
    """Return pre-configured mocks for a successful create run."""
    mock_git = Mock()
    mock_git.validate_git_repo.return_value = True
    mock_git.get_current_branch.return_value = "feature/STAR-1-auth"
    mock_git.extract_ticket_number.return_value = "STAR-1"
    mock_git.has_uncommitted_changes.return_value = False
    mock_git.get_commit_count.return_value = 1
    mock_git.get_changed_files.return_value = ["src/auth.py"]
    mock_git.get_commit_messages.return_value = ["STAR-1: Add auth"]
    mock_git.get_diff.return_value = "diff"
    mock_git.get_default_branch.return_value = "main"
    mock_git.branch_exists.return_value = True
    mock_git.get_repository_root.return_value = "/repo"

    mock_github = Mock()
    mock_github.check_gh_installed.return_value = True
    mock_github.check_gh_auth.return_value = True
    mock_github.get_repo_info.return_value = {"owner": "acme", "name": "myrepo"}
    mock_github.check_remote_branch_exists.return_value = True
    mock_github.create_pull_request.return_value = "https://github.com/acme/myrepo/pull/99"

    mock_auth = Mock()
    mock_auth.return_value.get_copilot_token.return_value = "token"

    mock_llm_cls = Mock()
    mock_llm = Mock()
    mock_llm.extract_ticket_number.return_value = None
    mock_llm_cls.return_value = mock_llm

    mock_gen_cls = Mock()
    mock_gen = Mock()
    mock_gen.generate_title.return_value = "STAR-1: Add auth"
    mock_gen.generate_description.return_value = "## Why\nNeeded auth"
    mock_gen_cls.return_value = mock_gen

    return mock_git, mock_github, mock_auth, mock_llm_cls, mock_gen_cls, mock_llm


class TestCliPrHistory:
    def _run_create(self, mock_git, mock_github, mock_auth, mock_llm_cls, mock_gen_cls,
                    extra_input="add auth\ny\ny\n", extra_args=None, mock_history=None):
        runner = CliRunner()
        args = ["create"] + (extra_args or [])
        with patch("src.cli.GitOperations", return_value=mock_git), \
             patch("src.cli.GitHubOperations", return_value=mock_github), \
             patch("src.cli.CopilotAuthenticator", mock_auth), \
             patch("src.cli.CopilotClient", mock_llm_cls), \
             patch("src.cli.PRGenerator", mock_gen_cls), \
             patch("src.cli.pr_history", mock_history or Mock()):
            return runner.invoke(cli, args, input=extra_input, catch_exceptions=False)

    def test_find_related_prs_called_after_title_generation(self):
        mock_git, mock_github, mock_auth, mock_llm_cls, mock_gen_cls, _ = _setup_mocks()
        mock_hist = Mock()
        mock_hist.find_related_prs.return_value = ""

        self._run_create(mock_git, mock_github, mock_auth, mock_llm_cls, mock_gen_cls,
                         mock_history=mock_hist)

        mock_hist.find_related_prs.assert_called_once_with(
            "acme", "myrepo", "STAR-1: Add auth", "add auth", ANY
        )

    def test_save_pr_called_after_successful_creation(self):
        mock_git, mock_github, mock_auth, mock_llm_cls, mock_gen_cls, _ = _setup_mocks()
        mock_hist = Mock()
        mock_hist.find_related_prs.return_value = ""

        self._run_create(mock_git, mock_github, mock_auth, mock_llm_cls, mock_gen_cls,
                         mock_history=mock_hist)

        mock_hist.save_pr.assert_called_once_with("acme", "myrepo", 99, "STAR-1: Add auth", "## Why\nNeeded auth")

    def test_find_related_prs_skipped_in_dry_run(self):
        mock_git, mock_github, mock_auth, mock_llm_cls, mock_gen_cls, _ = _setup_mocks()
        mock_hist = Mock()

        self._run_create(mock_git, mock_github, mock_auth, mock_llm_cls, mock_gen_cls,
                         extra_args=["--dry-run"], mock_history=mock_hist)

        mock_hist.find_related_prs.assert_not_called()
        mock_hist.save_pr.assert_not_called()

    def test_history_disabled_when_get_repo_info_fails(self):
        mock_git, mock_github, mock_auth, mock_llm_cls, mock_gen_cls, _ = _setup_mocks()
        mock_github.get_repo_info.side_effect = Exception("gh error")
        mock_hist = Mock()

        result = self._run_create(mock_git, mock_github, mock_auth, mock_llm_cls, mock_gen_cls,
                                  mock_history=mock_hist)

        # PR creation must still succeed
        assert result.exit_code == 0
        mock_hist.find_related_prs.assert_not_called()
        mock_hist.save_pr.assert_not_called()
