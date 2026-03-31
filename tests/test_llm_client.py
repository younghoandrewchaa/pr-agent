"""Tests for LLM client module."""

import os
import pytest
from unittest.mock import Mock, patch
from src.llm_client import CopilotClient, VertexAIClient
from src.exceptions import LLMError


class TestCopilotClient:
    """Test Copilot client functionality."""

    def test_initialization(self):
        """Test client initialization."""
        client = CopilotClient(
            api_base="https://api.githubcopilot.com", api_key="test-key", timeout=60
        )
        assert client.api_base == "https://api.githubcopilot.com"
        assert client.api_key == "test-key"
        assert client.timeout == 60

    def test_api_base_normalization(self):
        """Test API base URL normalization."""
        client = CopilotClient(api_base="https://api.githubcopilot.com/", api_key="test-key")
        assert client.api_base == "https://api.githubcopilot.com"

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
        from requests.exceptions import HTTPError
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = HTTPError("Unauthorized")
        mock_post.return_value = mock_response

        client = CopilotClient(api_base="https://api.githubcopilot.com", api_key="invalid-key")
        with pytest.raises(LLMError, match="authentication failed"):
            client.generate("Test prompt")


class TestVertexAIClient:
    """Test for Vertex AI client."""

    @patch("src.llm_client.genai.Client")
    @patch("src.llm_client.google.auth.default")
    def test_initialization_stores_model(self, mock_auth, mock_client_cls):
        mock_auth.return_value = (None, "proj")
        from src.llm_client import VertexAIClient
        client = VertexAIClient(project="proj", location="loc", model="gemini-2.5-flash")
        assert client.model == "gemini-2.5-flash"
        kw = mock_client_cls.call_args.kwargs
        assert kw["vertexai"] is True
        assert kw["project"] == "proj"
        assert kw["location"] == "loc"

    @patch("src.llm_client.genai.Client")
    @patch("src.llm_client.google.auth.default")
    def test_auto_detect_project_from_adc(self, mock_auth, mock_client_cls):
        mock_auth.return_value = (None, "detected-project")
        from src.llm_client import VertexAIClient
        VertexAIClient()
        kw = mock_client_cls.call_args.kwargs
        assert kw["project"] == "detected-project"
        assert kw["location"] == "europe-west2"

    @patch("src.llm_client.genai.Client")
    @patch("src.llm_client.google.auth.default")
    def test_auto_detect_location_from_env(self, mock_auth, mock_client_cls, monkeypatch):
        mock_auth.return_value = (None, "proj")
        monkeypatch.setenv("GOOGLE_CLOUD_REGION", "europe-west1")
        from src.llm_client import VertexAIClient
        VertexAIClient(project="proj")
        kw = mock_client_cls.call_args.kwargs
        assert kw["project"] == "proj"
        assert kw["location"] == "europe-west1"

    @patch("src.llm_client.genai.Client")
    @patch("src.llm_client.google.auth.default")
    def test_generate_success(self, mock_auth, mock_client_cls):
        mock_auth.return_value = (None, "proj")
        mock_response = Mock()
        mock_response.text = "Generated PR content"
        mock_client_cls.return_value.models.generate_content.return_value = mock_response
        from src.llm_client import VertexAIClient
        client = VertexAIClient(project="proj", location="us-central1")
        result = client.generate("Write a PR description")
        assert result == "Generated PR content"

    @patch("src.llm_client.genai.Client")
    @patch("src.llm_client.google.auth.default")
    def test_generate_with_system_prompt(self, mock_auth, mock_client_cls):
        mock_auth.return_value = (None, "proj")
        mock_response = Mock()
        mock_response.text = "Response"
        mock_client_cls.return_value.models.generate_content.return_value = mock_response
        from src.llm_client import VertexAIClient
        client = VertexAIClient(project="proj", location="us-central1")
        client.generate("prompt", system="You are a PR expert.")
        call_kwargs = mock_client_cls.return_value.models.generate_content.call_args.kwargs
        assert call_kwargs["config"].system_instruction == "You are a PR expert."

    @patch("src.llm_client.genai.Client")
    @patch("src.llm_client.google.auth.default")
    def test_generate_empty_response_raises(self, mock_auth, mock_client_cls):
        mock_auth.return_value = (None, "proj")
        mock_response = Mock()
        mock_response.text = "   "
        mock_client_cls.return_value.models.generate_content.return_value = mock_response
        from src.llm_client import VertexAIClient
        client = VertexAIClient(project="proj", location="us-central1")
        with pytest.raises(LLMError, match="empty response"):
            client.generate("prompt")

    @patch("src.llm_client.google.auth.default")
    def test_generate_auth_error_raises_llm_error(self, mock_auth):
        import google.auth.exceptions
        mock_auth.side_effect = google.auth.exceptions.DefaultCredentialsError("no creds")
        from src.llm_client import VertexAIClient
        with pytest.raises(LLMError, match="gcloud auth application-default login"):
            VertexAIClient()

    @patch("src.llm_client.genai.Client")
    @patch("src.llm_client.google.auth.default")
    def test_generate_api_error_raises_llm_error(self, mock_auth, mock_client_cls):
        from google.genai import errors as genai_errors
        mock_auth.return_value = (None, "proj")
        mock_client_cls.return_value.models.generate_content.side_effect = (
            genai_errors.APIError(code=429, response_json={"error": {"message": "quota exceeded"}})
        )
        from src.llm_client import VertexAIClient
        client = VertexAIClient(project="proj", location="us-central1")
        with pytest.raises(LLMError, match="Vertex AI API error"):
            client.generate("prompt")

    @patch("src.llm_client.genai.Client")
    @patch("src.llm_client.google.auth.default")
    def test_generate_with_context_truncates(self, mock_auth, mock_client_cls):
        mock_auth.return_value = (None, "proj")
        mock_response = Mock()
        mock_response.text = "ok"
        mock_client_cls.return_value.models.generate_content.return_value = mock_response
        from src.llm_client import VertexAIClient
        client = VertexAIClient(project="proj", location="us-central1")
        long_context = "x" * 10000
        client.generate_with_context("prompt", context=long_context, max_context_length=100)
        call_kwargs = mock_client_cls.return_value.models.generate_content.call_args.kwargs
        assert "... (diff truncated)" in call_kwargs["contents"]

    @patch("src.llm_client.genai.Client")
    @patch("src.llm_client.google.auth.default")
    def test_extract_ticket_number_found(self, mock_auth, mock_client_cls):
        mock_auth.return_value = (None, "proj")
        mock_response = Mock()
        mock_response.text = "STAR-42"
        mock_client_cls.return_value.models.generate_content.return_value = mock_response
        from src.llm_client import VertexAIClient
        client = VertexAIClient(project="proj", location="us-central1")
        result = client.extract_ticket_number("feature/star-42-my-change", "STAR")
        assert result == "STAR-42"

    @patch("src.llm_client.genai.Client")
    @patch("src.llm_client.google.auth.default")
    def test_extract_ticket_number_none(self, mock_auth, mock_client_cls):
        mock_auth.return_value = (None, "proj")
        mock_response = Mock()
        mock_response.text = "NONE"
        mock_client_cls.return_value.models.generate_content.return_value = mock_response
        from src.llm_client import VertexAIClient
        client = VertexAIClient(project="proj", location="us-central1")
        result = client.extract_ticket_number("feature/no-ticket", "STAR")
        assert result is None

    @patch("src.llm_client.genai.Client")
    @patch("src.llm_client.google.auth.default")
    def test_generate_commit_message(self, mock_auth, mock_client_cls):
        mock_auth.return_value = (None, "proj")
        mock_response = Mock()
        mock_response.text = "STAR-1: add vertex AI support"
        mock_client_cls.return_value.models.generate_content.return_value = mock_response
        from src.llm_client import VertexAIClient
        client = VertexAIClient(project="proj", location="us-central1")
        result = client.generate_commit_message("STAR-1", ["src/llm_client.py"], "diff content")
        assert result == "STAR-1: add vertex AI support"

    @patch("src.llm_client.genai.Client")
    @patch("src.llm_client.google.auth.default")
    def test_generate_with_timeout(self, mock_auth, mock_client_cls):
        mock_auth.return_value = (None, "proj")
        mock_response = Mock()
        mock_response.text = "Response"
        mock_client_cls.return_value.models.generate_content.return_value = mock_response
        from src.llm_client import VertexAIClient
        VertexAIClient(project="proj", location="us-central1", timeout=45)
        kw = mock_client_cls.call_args.kwargs
        assert kw["http_options"].timeout == 45 * 1000

