"""Integration tests for --provider flag in the create command."""

from click.testing import CliRunner
from unittest.mock import Mock, patch

from src.cli import cli


def _base_mocks():
    """Shared mock setup for a successful create run."""
    mock_git = Mock()
    mock_git.validate_git_repo.return_value = True
    mock_git.get_current_branch.return_value = "feature/STAR-1-test"
    mock_git.extract_ticket_number.return_value = "STAR-1"
    mock_git.has_uncommitted_changes.return_value = False
    mock_git.get_commit_count.return_value = 1
    mock_git.get_changed_files.return_value = ["src/foo.py"]
    mock_git.get_commit_messages.return_value = ["STAR-1: test"]
    mock_git.get_diff.return_value = "diff"
    mock_git.get_default_branch.return_value = "main"
    mock_git.branch_exists.return_value = True
    mock_git.get_repository_root.return_value = "/repo"

    mock_github = Mock()
    mock_github.check_gh_installed.return_value = True
    mock_github.check_gh_auth.return_value = True
    mock_github.get_repo_info.return_value = {"owner": "acme", "name": "repo"}
    mock_github.check_remote_branch_exists.return_value = True
    mock_github.create_pull_request.return_value = "https://github.com/acme/repo/pull/1"

    mock_gen = Mock()
    mock_gen.generate_title.return_value = "STAR-1: test"
    mock_gen.generate_description.return_value = "## Why\ntest"

    return mock_git, mock_github, mock_gen


class TestCliProvider:

    def test_copilot_provider_triggers_auth(self):
        """Default (copilot) provider runs Copilot auth."""
        mock_git, mock_github, mock_gen = _base_mocks()
        mock_auth = Mock()
        mock_auth.return_value.get_copilot_token.return_value = "token"

        with patch("src.cli.GitOperations", return_value=mock_git), \
             patch("src.cli.GitHubOperations", return_value=mock_github), \
             patch("src.cli.CopilotAuthenticator", mock_auth), \
             patch("src.cli.CopilotClient") as mock_copilot_cls, \
             patch("src.cli.PRGenerator", return_value=mock_gen), \
             patch("src.cli.pr_history"):
            mock_copilot_cls.return_value.extract_ticket_number.return_value = None
            runner = CliRunner()
            result = runner.invoke(cli, ["create", "--dry-run"], input="test intent\ny\n")

        assert result.exit_code == 0
        mock_auth.return_value.get_copilot_token.assert_called_once()
        mock_copilot_cls.assert_called_once()

    def test_claude_code_provider_skips_auth(self):
        """claude-code provider skips Copilot authentication entirely."""
        mock_git, mock_github, mock_gen = _base_mocks()
        mock_auth = Mock()

        with patch("src.cli.GitOperations", return_value=mock_git), \
             patch("src.cli.GitHubOperations", return_value=mock_github), \
             patch("src.cli.CopilotAuthenticator", mock_auth), \
             patch("src.cli.ClaudeCodeClient") as mock_cc_cls, \
             patch("src.cli.CopilotClient") as mock_copilot_cls, \
             patch("src.cli.PRGenerator", return_value=mock_gen), \
             patch("src.cli.pr_history"):
            mock_cc_cls.return_value.extract_ticket_number.return_value = None
            runner = CliRunner()
            result = runner.invoke(
                cli, ["create", "--provider", "claude-code", "--dry-run"],
                input="test intent\ny\n"
            )

        assert result.exit_code == 0
        mock_auth.return_value.get_copilot_token.assert_not_called()
        mock_copilot_cls.assert_not_called()
        mock_cc_cls.assert_called_once()

    def test_claude_code_provider_passes_model(self):
        """ClaudeCodeClient receives the model from --model flag."""
        mock_git, mock_github, mock_gen = _base_mocks()

        with patch("src.cli.GitOperations", return_value=mock_git), \
             patch("src.cli.GitHubOperations", return_value=mock_github), \
             patch("src.cli.CopilotAuthenticator"), \
             patch("src.cli.ClaudeCodeClient") as mock_cc_cls, \
             patch("src.cli.PRGenerator", return_value=mock_gen), \
             patch("src.cli.pr_history"):
            mock_cc_cls.return_value.extract_ticket_number.return_value = None
            runner = CliRunner()
            result = runner.invoke(
                cli,
                ["create", "--provider", "claude-code", "--model", "claude-sonnet-4-6", "--dry-run"],
                input="test intent\ny\n"
            )

        assert result.exit_code == 0
        assert mock_cc_cls.call_args.kwargs.get("model") == "claude-sonnet-4-6"

class TestCliVertexProvider:

    def test_vertex_provider_instantiates_vertex_client(self):
        """--provider vertex creates a VertexAIClient, skips Copilot auth."""
        mock_git, mock_github, mock_gen = _base_mocks()
        mock_auth = Mock()

        with patch("src.cli.GitOperations", return_value=mock_git), \
             patch("src.cli.GitHubOperations", return_value=mock_github), \
             patch("src.cli.CopilotAuthenticator", mock_auth), \
             patch("src.cli.CopilotClient") as mock_copilot_cls, \
             patch("src.cli.VertexAIClient") as mock_vertex_cls, \
             patch("src.cli.PRGenerator", return_value=mock_gen), \
             patch("src.cli.pr_history"):
            mock_vertex_cls.return_value.extract_ticket_number.return_value = None
            runner = CliRunner()
            result = runner.invoke(
                cli, ["create", "--provider", "vertex", "--dry-run"],
                input="test intent\ny\n"
            )

        assert result.exit_code == 0, result.output
        mock_auth.return_value.get_copilot_token.assert_not_called()
        mock_copilot_cls.assert_not_called()
        mock_vertex_cls.assert_called_once()

    def test_vertex_provider_default_model_substitution(self):
        """When model is still claude-haiku-4.5 (default), vertex uses gemini-2.5-flash."""
        mock_git, mock_github, mock_gen = _base_mocks()

        with patch("src.cli.GitOperations", return_value=mock_git), \
             patch("src.cli.GitHubOperations", return_value=mock_github), \
             patch("src.cli.CopilotAuthenticator"), \
             patch("src.cli.VertexAIClient") as mock_vertex_cls, \
             patch("src.cli.PRGenerator", return_value=mock_gen), \
             patch("src.cli.pr_history"), \
             patch("src.cli.load_config") as mock_load_config:
            from src.config import Config
            mock_load_config.return_value = Config(provider="vertex", model="claude-haiku-4.5")
            mock_vertex_cls.return_value.extract_ticket_number.return_value = None
            runner = CliRunner()
            result = runner.invoke(
                cli, ["create", "--provider", "vertex", "--dry-run"],
                input="test intent\ny\n"
            )

        assert result.exit_code == 0, result.output
        assert mock_vertex_cls.call_args.kwargs.get("model") == "gemini-2.5-flash"

    def test_vertex_provider_respects_explicit_model(self):
        """When --model is set explicitly, it is passed to VertexAIClient."""
        mock_git, mock_github, mock_gen = _base_mocks()

        with patch("src.cli.GitOperations", return_value=mock_git), \
             patch("src.cli.GitHubOperations", return_value=mock_github), \
             patch("src.cli.CopilotAuthenticator"), \
             patch("src.cli.VertexAIClient") as mock_vertex_cls, \
             patch("src.cli.PRGenerator", return_value=mock_gen), \
             patch("src.cli.pr_history"):
            mock_vertex_cls.return_value.extract_ticket_number.return_value = None
            runner = CliRunner()
            result = runner.invoke(
                cli,
                ["create", "--provider", "vertex", "--model", "gemini-2.0-flash", "--dry-run"],
                input="test intent\ny\n"
            )

        assert result.exit_code == 0, result.output
        assert mock_vertex_cls.call_args.kwargs.get("model") == "gemini-2.0-flash"

    def test_vertex_provider_passes_project_and_location_from_config(self):
        """vertex_project and vertex_location from config are forwarded to VertexAIClient."""
        mock_git, mock_github, mock_gen = _base_mocks()

        with patch("src.cli.GitOperations", return_value=mock_git), \
             patch("src.cli.GitHubOperations", return_value=mock_github), \
             patch("src.cli.CopilotAuthenticator"), \
             patch("src.cli.VertexAIClient") as mock_vertex_cls, \
             patch("src.cli.PRGenerator", return_value=mock_gen), \
             patch("src.cli.pr_history"), \
             patch("src.cli.load_config") as mock_load_config:
            from src.config import Config
            cfg = Config(
                provider="vertex",
                vertex_project="my-gcp-project",
                vertex_location="europe-west4",
            )
            mock_load_config.return_value = cfg
            mock_vertex_cls.return_value.extract_ticket_number.return_value = None
            runner = CliRunner()
            result = runner.invoke(
                cli, ["create", "--provider", "vertex", "--dry-run"],
                input="test intent\ny\n"
            )

        assert result.exit_code == 0, result.output
        call_kwargs = mock_vertex_cls.call_args.kwargs
        assert call_kwargs.get("project") == "my-gcp-project"
        assert call_kwargs.get("location") == "europe-west4"
