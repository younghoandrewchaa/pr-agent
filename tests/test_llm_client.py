"""Tests for LLM client module."""

import pytest
from unittest.mock import Mock, patch
from src.llm_client import CopilotClient
from src.exceptions import LLMError


class TestCopilotClient:
    """Test Copilot client functionality."""

    def test_initialization(self):
        """Test client initialization."""
        client = CopilotClient(
            api_base="https://api.githubcopilot.com", api_key="test-key", timeout=60
        )
        assert client.api_base == "https://api.githubcopilot.com/v1"
        assert client.api_key == "test-key"
        assert client.timeout == 60

    def test_api_base_normalization(self):
        """Test API base URL normalization."""
        client = CopilotClient(api_base="https://api.githubcopilot.com/", api_key="test-key")
        assert client.api_base == "https://api.githubcopilot.com/v1"

    @patch("requests.post")
    def test_generate_success(self, mock_post):
        """Test successful generation."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Generated content"}}]
        }
        mock_post.return_value = mock_response

        client = CopilotClient(api_base="https://api.githubcopilot.com", api_key="test-key")
        result = client.generate("Test prompt")
        assert result == "Generated content"

    @patch("requests.post")
    def test_generate_auth_failure(self, mock_post):
        """Test authentication failure."""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = Exception("Unauthorized")
        mock_post.return_value = mock_response

        client = CopilotClient(api_base="https://api.githubcopilot.com", api_key="invalid-key")
        with pytest.raises(LLMError, match="authentication failed"):
            client.generate("Test prompt")


import subprocess
from src.llm_client import ClaudeCodeClient


class TestClaudeCodeClient:
    """Test Claude Code CLI client."""

    def test_initialization(self):
        client = ClaudeCodeClient(model="claude-sonnet-4-6", bin="claude", timeout=30)
        assert client.model == "claude-sonnet-4-6"
        assert client.bin == "claude"
        assert client.timeout == 30

    @patch("subprocess.run")
    def test_generate_success(self, mock_run):
        mock_run.return_value = Mock(returncode=0, stdout="Generated content\n", stderr="")
        client = ClaudeCodeClient()
        result = client.generate("Test prompt")
        assert result == "Generated content"

    @patch("subprocess.run")
    def test_generate_with_system_prompt(self, mock_run):
        mock_run.return_value = Mock(returncode=0, stdout="Response\n", stderr="")
        client = ClaudeCodeClient()
        client.generate("Test prompt", system="You are helpful.")
        args = mock_run.call_args[0][0]
        assert "--system" in args
        assert "You are helpful." in args

    @patch("subprocess.run")
    def test_generate_passes_model_flag(self, mock_run):
        mock_run.return_value = Mock(returncode=0, stdout="Response\n", stderr="")
        client = ClaudeCodeClient(model="claude-sonnet-4-6")
        client.generate("prompt")
        args = mock_run.call_args[0][0]
        assert "--model" in args
        assert "claude-sonnet-4-6" in args

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_generate_binary_not_found(self, mock_run):
        client = ClaudeCodeClient()
        with pytest.raises(LLMError, match="claude CLI not found"):
            client.generate("prompt")

    @patch("subprocess.run")
    def test_generate_nonzero_exit(self, mock_run):
        mock_run.return_value = Mock(returncode=1, stdout="", stderr="some error")
        client = ClaudeCodeClient()
        with pytest.raises(LLMError, match="claude CLI failed"):
            client.generate("prompt")

    @patch("subprocess.run")
    def test_generate_empty_response(self, mock_run):
        mock_run.return_value = Mock(returncode=0, stdout="   \n", stderr="")
        client = ClaudeCodeClient()
        with pytest.raises(LLMError, match="empty response"):
            client.generate("prompt")

    @patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=60))
    def test_generate_timeout(self, mock_run):
        client = ClaudeCodeClient()
        with pytest.raises(LLMError, match="timed out"):
            client.generate("prompt")

    @patch("subprocess.run")
    def test_generate_with_context_truncates(self, mock_run):
        mock_run.return_value = Mock(returncode=0, stdout="ok\n", stderr="")
        client = ClaudeCodeClient()
        long_context = "x" * 10000
        client.generate_with_context("prompt", context=long_context, max_context_length=100)
        call_prompt = mock_run.call_args[0][0][2]  # -p arg
        assert "... (diff truncated)" in call_prompt
