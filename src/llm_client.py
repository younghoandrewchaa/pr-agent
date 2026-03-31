"""
LLM client module.

Provides LLM client implementations for PR generation:
- CopilotClient: calls the GitHub Copilot API
- VertexAIClient: calls Google Gemini via Vertex AI
"""

import google.auth
import google.auth.exceptions
from google import genai
from google.genai import types
from google.genai import errors as genai_errors
import json
import os
import uuid
from typing import Optional, Dict, Any

import requests
from requests.exceptions import HTTPError

from src.exceptions import LLMError


COPILOT_VERSION = "0.26.7"
EDITOR_VERSION = "vscode/1.95.0"
EDITOR_PLUGIN_VERSION = f"copilot-chat/{COPILOT_VERSION}"
USER_AGENT = f"GitHubCopilotChat/{COPILOT_VERSION}"
API_VERSION = "2025-04-01"


class CopilotClient:
    """Client for interacting with GitHub Copilot API."""

    def __init__(self, api_base: str, api_key: str, timeout: int = 60):
        """
        Initialize Copilot client.

        Args:
            api_base: Base URL for Copilot API
            api_key: GitHub Copilot API key
            timeout: Request timeout in seconds. Default: 60
        """
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.chat_url = f"{self.api_base}/chat/completions"

    def _get_headers(self) -> Dict[str, str]:
        """Get required Copilot API headers."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "copilot-integration-id": "vscode-chat",
            "editor-version": EDITOR_VERSION,
            "editor-plugin-version": EDITOR_PLUGIN_VERSION,
            "user-agent": USER_AGENT,
            "openai-intent": "conversation-panel",
            "x-github-api-version": API_VERSION,
            "x-request-id": str(uuid.uuid4()),
        }

    def _post(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        headers = self._get_headers()

        response = requests.post(
            self.chat_url,
            headers=headers,
            json=payload,
            timeout=self.timeout,
        )

        try:
            response.raise_for_status()
        except HTTPError as exc:
            if response.status_code == 401:
                raise LLMError(
                    "Copilot authentication failed. Ensure your GitHub token has Copilot access."
                )
            raise LLMError(f"Copilot request failed: {exc}")

        try:
            return response.json()
        except json.JSONDecodeError as exc:
            raise LLMError(f"Failed to parse Copilot response: {exc}")

    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload: Dict[str, Any] = {
            "model": "claude-haiku-4.5",
            "temperature": temperature,
            "messages": messages,
        }

        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        data = self._post(payload)

        choices = data.get("choices") or []
        if not choices:
            raise LLMError("Copilot returned no choices")

        message = choices[0].get("message", {})
        content = message.get("content")
        if isinstance(content, list):
            # Copilot responses often include structured content blocks
            text_blocks = [block.get("text", "") for block in content if block.get("text")]
            content = "\n".join(text_blocks)

        if not isinstance(content, str):
            raise LLMError("Copilot response missing text content")

        return content.strip()

    def generate_with_context(
        self,
        prompt: str,
        context: Optional[str] = None,
        max_context_length: int = 8000,
    ) -> str:
        full_prompt = prompt

        if context:
            if len(context) > max_context_length:
                context = context[:max_context_length] + "\n\n... (diff truncated)"
            full_prompt = f"{prompt}\n\nContext:\n{context}"

        return self.generate(full_prompt)

    def extract_ticket_number(
        self,
        branch_name: str,
        ticket_prefix: str = "STAR",
    ) -> Optional[str]:
        from src.prompts import PRPrompts

        prompt = PRPrompts.extract_ticket_number_prompt(branch_name, ticket_prefix)

        response = self.generate(
            prompt=prompt,
            temperature=0.1,
        )

        response = response.strip().upper()
        if response == "NONE" or not response:
            return None

        import re

        match = re.search(rf"{ticket_prefix.upper()}-\d+", response)
        if match:
            return match.group(0)

        return None

    def generate_commit_message(
        self,
        ticket_number: str,
        changed_files: list,
        diff: str,
    ) -> str:
        from src.prompts import PRPrompts

        diff_summary = PRPrompts.extract_diff_summary(diff, max_length=2000)

        prompt = PRPrompts.generate_commit_message_prompt(
            ticket_number=ticket_number,
            changed_files=changed_files,
            diff_summary=diff_summary,
        )

        response = self.generate(
            prompt=prompt,
            temperature=0.3,
        )

        return response.strip()


class VertexAIClient:
    """Client for interacting with Google Gemini via Vertex AI."""

    def __init__(
            self,
            project: Optional[str] = None,
            location: Optional[str] = None,
            model: str = "gemini-2.5-flash",
            timeout: int = 60,
    ):
        self.model = model
        self.timeout = timeout

        if project is None:
            try:
                _, project = google.auth.default()
            except google.auth.exceptions.DefaultCredentialsError as exc:
                raise LLMError(
                    "Vertex AI: no credentials found. "
                    "Run `gcloud auth application-default login` to set up credentials, or specify a project explicitly."
                ) from exc

        if location is None:
            location = (
                os.environ.get("GOOGLE_CLOUD_REGION")
                or os.environ.get("CLOUDSDK_COMPUTE_REGION")
                or "europe-west2"
            )

        self.client = genai.Client(
            vertexai=True,
            project=project,
            location=location,
            http_options=types.HttpOptions(timeout=timeout * 1000),  # milliseconds
        )

    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            thinking_config=types.ThinkingConfig(thinking_budget=1024),
            max_output_tokens=32768,
        )

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=config,
            )
        except google.auth.exceptions.DefaultCredentialsError as exc:
            raise LLMError(
                "Vertex AI: no credentials found. "
                "Run `gcloud auth application-default login` to set up credentials."
            ) from exc
        except genai_errors.APIError as exc:
            raise LLMError(f"Vertex AI API error: {exc}") from exc

        # Extract text from response. response.text raises when there are no output
        # text parts (e.g. only thinking parts). Fall back to manual extraction.
        try:
            raw = response.text
            content = raw.strip() if raw is not None else ""
        except Exception as exc:
            content = ""
            candidates = getattr(response, "candidates", None) or []
            if candidates:
                candidate = candidates[0]
                cc = getattr(candidate, "content", None)
                for part in (getattr(cc, "parts", None) or []):
                    if not getattr(part, "thought", False) and getattr(part, "text", ""):
                        content += part.text
            content = content.strip()
            if not content:
                finish = getattr(candidates[0] if candidates else None, "finish_reason", "unknown")
                raise LLMError(
                    f"Vertex AI returned empty response (finish_reason={finish}): {exc}"
                ) from exc
        if not content:
            raise LLMError("Vertex AI returned empty response")

        return content

    def generate_with_context(
        self,
        prompt: str,
        context: Optional[str] = None,
        max_context_length: int = 8000,
    ) -> str:
        full_prompt = prompt
        if context:
            if len(context) > max_context_length:
                context = context[:max_context_length] + "\n\n... (diff truncated)"
            full_prompt = f"{prompt}\n\nContext:\n{context}"
        return self.generate(full_prompt)

    def extract_ticket_number(
        self,
        branch_name: str,
        ticket_prefix: str = "STAR",
    ) -> Optional[str]:
        from src.prompts import PRPrompts
        import re

        prompt = PRPrompts.extract_ticket_number_prompt(branch_name, ticket_prefix)
        response = self.generate(prompt=prompt, temperature=0.1)
        response = response.strip().upper()
        if response == "NONE" or not response:
            return None
        match = re.search(rf"{ticket_prefix.upper()}-\d+", response)
        if match:
            return match.group(0)
        return None

    def generate_commit_message(
        self,
        ticket_number: str,
        changed_files: list,
        diff: str,
    ) -> str:
        from src.prompts import PRPrompts

        diff_summary = PRPrompts.extract_diff_summary(diff, max_length=2000)
        prompt = PRPrompts.generate_commit_message_prompt(
            ticket_number=ticket_number,
            changed_files=changed_files,
            diff_summary=diff_summary,
        )
        return self.generate(prompt=prompt, temperature=0.3).strip()

