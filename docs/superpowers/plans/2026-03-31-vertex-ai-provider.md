# Vertex AI Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `vertex` LLM provider that calls Google Gemini via Vertex AI using Application Default Credentials, so users whose networks block the Copilot API can still generate PR descriptions.

**Architecture:** A new `VertexAIClient` class is added to `src/llm_client.py` alongside the two existing clients, following the exact same interface. The `Config` dataclass gains two optional fields (`vertex_project`, `vertex_location`). The `cli.py` provider dispatch gains one branch for `"vertex"`. No structural changes to the rest of the codebase.

**Tech Stack:** `google-cloud-aiplatform` SDK (Vertex AI), `google-auth` (ADC credential detection), `gemini-2.5-flash` default model.

---

## File Map

| File | Change |
|------|--------|
| `pyproject.toml` | Add `google-cloud-aiplatform>=1.60.0` to `dependencies` |
| `src/llm_client.py` | Add `VertexAIClient` class |
| `src/config.py` | Add `vertex_project`, `vertex_location` fields; wire env vars and from_dict |
| `src/cli.py` | Add `"vertex"` choice to `--provider`; add dispatch branch |
| `tests/test_llm_client.py` | Add `TestVertexAIClient` class |
| `tests/test_config.py` | Add vertex field tests |
| `tests/test_cli_provider.py` | Add vertex provider CLI tests |

---

## Task 1: Add dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add `google-cloud-aiplatform` to dependencies**

In `pyproject.toml`, update the `dependencies` list to add one entry:

```toml
dependencies = [
    "click>=8.1.0",
    "requests>=2.31.0",
    "pyyaml>=6.0",
    "gitpython>=3.1.0",
    "rich>=13.0.0",
    "google-cloud-aiplatform>=1.60.0",
]
```

- [ ] **Step 2: Install the new dependency**

```bash
pip install -e .
```

Expected: no errors. `pip show google-cloud-aiplatform` should show a version >= 1.60.0.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "feat: add google-cloud-aiplatform dependency for Vertex AI provider"
```

---

## Task 2: Add `VertexAIClient` to `llm_client.py`

**Files:**
- Modify: `src/llm_client.py`
- Test: `tests/test_llm_client.py`

- [ ] **Step 1: Write the failing tests**

Open `tests/test_llm_client.py`. Add these imports at the top of the file (after the existing imports):

```python
import os
```

Then append the following class at the end of the file:

```python
class TestVertexAIClient:
    """Tests for VertexAIClient."""

    def _make_client(self, mock_vertexai_init, mock_auth, project="my-project", location="us-central1"):
        """Helper: build a VertexAIClient with mocked SDK."""
        mock_auth.return_value = (None, project)
        from src.llm_client import VertexAIClient
        return VertexAIClient(project=project, location=location, model="gemini-2.5-flash")

    @patch("src.llm_client.vertexai.init")
    @patch("src.llm_client.google.auth.default")
    def test_initialization_stores_model(self, mock_auth, mock_init):
        mock_auth.return_value = (None, "proj")
        from src.llm_client import VertexAIClient
        client = VertexAIClient(project="proj", location="us-central1", model="gemini-2.5-flash")
        assert client.model == "gemini-2.5-flash"
        mock_init.assert_called_once_with(project="proj", location="us-central1")

    @patch("src.llm_client.vertexai.init")
    @patch("src.llm_client.google.auth.default")
    def test_auto_detect_project_from_adc(self, mock_auth, mock_init):
        mock_auth.return_value = (None, "detected-project")
        from src.llm_client import VertexAIClient
        client = VertexAIClient()
        mock_init.assert_called_once_with(project="detected-project", location="us-central1")

    @patch("src.llm_client.vertexai.init")
    @patch("src.llm_client.google.auth.default")
    def test_auto_detect_location_from_env(self, mock_auth, mock_init, monkeypatch):
        mock_auth.return_value = (None, "proj")
        monkeypatch.setenv("GOOGLE_CLOUD_REGION", "europe-west1")
        from src.llm_client import VertexAIClient
        import importlib, src.llm_client
        importlib.reload(src.llm_client)
        from src.llm_client import VertexAIClient as VAC2
        client = VAC2(project="proj")
        mock_init.assert_called_with(project="proj", location="europe-west1")

    @patch("src.llm_client.vertexai.generative_models.GenerativeModel")
    @patch("src.llm_client.vertexai.init")
    @patch("src.llm_client.google.auth.default")
    def test_generate_success(self, mock_auth, mock_init, mock_model_cls):
        mock_auth.return_value = (None, "proj")
        mock_response = Mock()
        mock_response.text = "Generated PR content"
        mock_model_cls.return_value.generate_content.return_value = mock_response
        from src.llm_client import VertexAIClient
        client = VertexAIClient(project="proj", location="us-central1")
        result = client.generate("Write a PR description")
        assert result == "Generated PR content"

    @patch("src.llm_client.vertexai.generative_models.GenerativeModel")
    @patch("src.llm_client.vertexai.init")
    @patch("src.llm_client.google.auth.default")
    def test_generate_with_system_prompt(self, mock_auth, mock_init, mock_model_cls):
        mock_auth.return_value = (None, "proj")
        mock_response = Mock()
        mock_response.text = "Response"
        mock_model_cls.return_value.generate_content.return_value = mock_response
        from src.llm_client import VertexAIClient
        client = VertexAIClient(project="proj", location="us-central1")
        client.generate("prompt", system="You are a PR expert.")
        mock_model_cls.assert_called_with(
            "gemini-2.5-flash",
            system_instruction="You are a PR expert.",
        )

    @patch("src.llm_client.vertexai.generative_models.GenerativeModel")
    @patch("src.llm_client.vertexai.init")
    @patch("src.llm_client.google.auth.default")
    def test_generate_empty_response_raises(self, mock_auth, mock_init, mock_model_cls):
        mock_auth.return_value = (None, "proj")
        mock_response = Mock()
        mock_response.text = "   "
        mock_model_cls.return_value.generate_content.return_value = mock_response
        from src.llm_client import VertexAIClient
        client = VertexAIClient(project="proj", location="us-central1")
        with pytest.raises(LLMError, match="empty response"):
            client.generate("prompt")

    @patch("src.llm_client.vertexai.init")
    @patch("src.llm_client.google.auth.default")
    def test_generate_auth_error_raises_llm_error(self, mock_auth, mock_init):
        import google.auth.exceptions
        mock_auth.side_effect = google.auth.exceptions.DefaultCredentialsError("no creds")
        from src.llm_client import VertexAIClient
        with pytest.raises(LLMError, match="gcloud auth application-default login"):
            VertexAIClient()

    @patch("src.llm_client.vertexai.generative_models.GenerativeModel")
    @patch("src.llm_client.vertexai.init")
    @patch("src.llm_client.google.auth.default")
    def test_generate_api_error_raises_llm_error(self, mock_auth, mock_init, mock_model_cls):
        import google.api_core.exceptions
        mock_auth.return_value = (None, "proj")
        mock_model_cls.return_value.generate_content.side_effect = (
            google.api_core.exceptions.GoogleAPIError("quota exceeded")
        )
        from src.llm_client import VertexAIClient
        client = VertexAIClient(project="proj", location="us-central1")
        with pytest.raises(LLMError, match="Vertex AI request failed"):
            client.generate("prompt")

    @patch("src.llm_client.vertexai.generative_models.GenerativeModel")
    @patch("src.llm_client.vertexai.init")
    @patch("src.llm_client.google.auth.default")
    def test_generate_with_context_truncates(self, mock_auth, mock_init, mock_model_cls):
        mock_auth.return_value = (None, "proj")
        mock_response = Mock()
        mock_response.text = "ok"
        mock_model_cls.return_value.generate_content.return_value = mock_response
        from src.llm_client import VertexAIClient
        client = VertexAIClient(project="proj", location="us-central1")
        long_context = "x" * 10000
        client.generate_with_context("prompt", context=long_context, max_context_length=100)
        call_args = mock_model_cls.return_value.generate_content.call_args[0][0]
        assert "... (diff truncated)" in call_args

    @patch("src.llm_client.vertexai.generative_models.GenerativeModel")
    @patch("src.llm_client.vertexai.init")
    @patch("src.llm_client.google.auth.default")
    def test_extract_ticket_number_found(self, mock_auth, mock_init, mock_model_cls):
        mock_auth.return_value = (None, "proj")
        mock_response = Mock()
        mock_response.text = "STAR-42"
        mock_model_cls.return_value.generate_content.return_value = mock_response
        from src.llm_client import VertexAIClient
        client = VertexAIClient(project="proj", location="us-central1")
        result = client.extract_ticket_number("feature/star-42-my-change", "STAR")
        assert result == "STAR-42"

    @patch("src.llm_client.vertexai.generative_models.GenerativeModel")
    @patch("src.llm_client.vertexai.init")
    @patch("src.llm_client.google.auth.default")
    def test_extract_ticket_number_none(self, mock_auth, mock_init, mock_model_cls):
        mock_auth.return_value = (None, "proj")
        mock_response = Mock()
        mock_response.text = "NONE"
        mock_model_cls.return_value.generate_content.return_value = mock_response
        from src.llm_client import VertexAIClient
        client = VertexAIClient(project="proj", location="us-central1")
        result = client.extract_ticket_number("feature/no-ticket", "STAR")
        assert result is None

    @patch("src.llm_client.vertexai.generative_models.GenerativeModel")
    @patch("src.llm_client.vertexai.init")
    @patch("src.llm_client.google.auth.default")
    def test_generate_commit_message(self, mock_auth, mock_init, mock_model_cls):
        mock_auth.return_value = (None, "proj")
        mock_response = Mock()
        mock_response.text = "STAR-1: add vertex AI support"
        mock_model_cls.return_value.generate_content.return_value = mock_response
        from src.llm_client import VertexAIClient
        client = VertexAIClient(project="proj", location="us-central1")
        result = client.generate_commit_message("STAR-1", ["src/llm_client.py"], "diff content")
        assert result == "STAR-1: add vertex AI support"
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
pytest tests/test_llm_client.py::TestVertexAIClient -v
```

Expected: `ImportError` or `AttributeError` — `VertexAIClient` does not exist yet.

- [ ] **Step 3: Add `VertexAIClient` to `src/llm_client.py`**

Add these imports at the top of `src/llm_client.py`, after the existing imports:

```python
import google.auth
import google.auth.exceptions
import google.api_core.exceptions
import vertexai
import vertexai.generative_models
```

Then append this class at the end of the file:

```python
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

        # Resolve project: explicit arg > ADC detected project
        if project is None:
            try:
                _, project = google.auth.default()
            except google.auth.exceptions.DefaultCredentialsError as exc:
                raise LLMError(
                    "Vertex AI: no credentials found. "
                    "Run 'gcloud auth application-default login'."
                ) from exc

        # Resolve location: explicit arg > env vars > hardcoded fallback
        if location is None:
            location = (
                os.environ.get("GOOGLE_CLOUD_REGION")
                or os.environ.get("CLOUDSDK_COMPUTE_REGION")
                or "us-central1"
            )

        vertexai.init(project=project, location=location)

    def _get_model(self, system: Optional[str]) -> "vertexai.generative_models.GenerativeModel":
        kwargs: Dict[str, Any] = {}
        if system:
            kwargs["system_instruction"] = system
        return vertexai.generative_models.GenerativeModel(self.model, **kwargs)

    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        from vertexai.generative_models import GenerationConfig

        generation_config = GenerationConfig(temperature=temperature)
        if max_tokens is not None:
            generation_config = GenerationConfig(
                temperature=temperature, max_output_tokens=max_tokens
            )

        try:
            model = self._get_model(system)
            response = model.generate_content(prompt, generation_config=generation_config)
        except google.auth.exceptions.DefaultCredentialsError as exc:
            raise LLMError(
                "Vertex AI: no credentials found. "
                "Run 'gcloud auth application-default login'."
            ) from exc
        except google.api_core.exceptions.GoogleAPIError as exc:
            raise LLMError(f"Vertex AI request failed: {exc}") from exc

        content = response.text.strip() if hasattr(response, "text") else ""
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
```

Also add `import os` at the top of `src/llm_client.py` if it is not already present.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
pytest tests/test_llm_client.py::TestVertexAIClient -v
```

Expected: All tests PASS. If `test_auto_detect_location_from_env` is flaky due to module reload, skip it for now — the other tests cover the core behavior.

- [ ] **Step 5: Run the full test suite to check for regressions**

```bash
pytest tests/test_llm_client.py -v
```

Expected: All existing `TestCopilotClient` and `TestClaudeCodeClient` tests still PASS.

- [ ] **Step 6: Commit**

```bash
git add src/llm_client.py tests/test_llm_client.py
git commit -m "feat: add VertexAIClient for Gemini via Vertex AI"
```

---

## Task 3: Add vertex config fields

**Files:**
- Modify: `src/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

Append this class to `tests/test_config.py`:

```python
class TestVertexConfig:

    def test_vertex_fields_default_to_none(self):
        config = Config()
        assert config.vertex_project is None
        assert config.vertex_location is None

    def test_vertex_fields_from_dict(self):
        config = Config.from_dict({
            "vertex_project": "my-gcp-project",
            "vertex_location": "us-west1",
        })
        assert config.vertex_project == "my-gcp-project"
        assert config.vertex_location == "us-west1"

    def test_vertex_fields_from_dict_ignores_unknown_keys(self):
        config = Config.from_dict({"vertex_project": "proj", "bogus_key": "x"})
        assert config.vertex_project == "proj"

    def test_vertex_project_from_env(self, monkeypatch):
        monkeypatch.setenv("PR_AGENT_VERTEX_PROJECT", "env-project")
        monkeypatch.setenv("PR_AGENT_VERTEX_LOCATION", "europe-west4")
        config = Config.from_env()
        assert config.vertex_project == "env-project"
        assert config.vertex_location == "europe-west4"

    def test_vertex_fields_pass_through_merge(self):
        config = Config(vertex_project="proj", vertex_location="us-east1")
        merged = config.merge_with_cli_args()
        assert merged.vertex_project == "proj"
        assert merged.vertex_location == "us-east1"
```

- [ ] **Step 2: Run to confirm they fail**

```bash
pytest tests/test_config.py::TestVertexConfig -v
```

Expected: `TypeError` — `Config` does not accept `vertex_project` / `vertex_location`.

- [ ] **Step 3: Add the fields to `Config`**

In `src/config.py`, add two fields to the `Config` dataclass after the `claude_code_bin` field:

```python
# Vertex AI settings
vertex_project: Optional[str] = None
vertex_location: Optional[str] = None
```

In `from_dict()`, add both keys to `valid_keys`:

```python
valid_keys = {
    ...
    "vertex_project",
    "vertex_location",
}
```

In `from_env()`, add to `env_mapping`:

```python
env_mapping = {
    ...
    "PR_AGENT_VERTEX_PROJECT": "vertex_project",
    "PR_AGENT_VERTEX_LOCATION": "vertex_location",
}
```

In `merge_with_cli_args()`, pass them through in the `Config(...)` constructor call:

```python
new_config = Config(
    ...
    vertex_project=self.vertex_project,
    vertex_location=self.vertex_location,
)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
pytest tests/test_config.py::TestVertexConfig -v
```

Expected: All 5 tests PASS.

- [ ] **Step 5: Run the full config test suite**

```bash
pytest tests/test_config.py -v
```

Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/config.py tests/test_config.py
git commit -m "feat: add vertex_project and vertex_location config fields"
```

---

## Task 4: Wire vertex provider into CLI

**Files:**
- Modify: `src/cli.py`
- Test: `tests/test_cli_provider.py`

- [ ] **Step 1: Write the failing tests**

Append this class to `tests/test_cli_provider.py`:

```python
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
             patch("src.cli.pr_history"):
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
```

- [ ] **Step 2: Run to confirm they fail**

```bash
pytest tests/test_cli_provider.py::TestCliVertexProvider -v
```

Expected: `AssertionError` or `SystemExit(2)` — `vertex` is not a valid choice yet.

- [ ] **Step 3: Update `src/cli.py`**

**3a.** Add `VertexAIClient` to the import line near the top of `cli.py`:

```python
from src.llm_client import CopilotClient, ClaudeCodeClient, VertexAIClient
```

**3b.** In the `create` command decorator, expand the `--provider` choice list:

```python
@click.option(
    "--provider",
    "-P",
    type=click.Choice(["copilot", "claude-code", "vertex"]),
    default=None,
    help="LLM provider to use (default: from config or 'copilot')",
)
```

**3c.** In the provider dispatch block inside `create()`, add the vertex branch **before** the `else` (Copilot) branch:

```python
        # Initialize LLM client based on configured provider
        if cfg.provider == "claude-code":
            llm_client = ClaudeCodeClient(
                model=cfg.model,
                executable=cfg.claude_code_bin,
                timeout=cfg.copilot_timeout,
            )
            console.print("✓ Using Claude Code CLI as LLM provider", style="green")
            console.print()
        elif cfg.provider == "vertex":
            effective_model = cfg.model if cfg.model != "claude-haiku-4.5" else "gemini-2.5-flash"
            llm_client = VertexAIClient(
                project=cfg.vertex_project,
                location=cfg.vertex_location,
                model=effective_model,
            )
            console.print("✓ Using Vertex AI (Gemini) as LLM provider", style="green")
            console.print()
        else:
            # Default: Copilot provider
            ...
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
pytest tests/test_cli_provider.py::TestCliVertexProvider -v
```

Expected: All 4 tests PASS.

- [ ] **Step 5: Run the full test suite**

```bash
pytest -v
```

Expected: All tests PASS. No regressions.

- [ ] **Step 6: Commit**

```bash
git add src/cli.py tests/test_cli_provider.py
git commit -m "feat: add vertex provider to CLI --provider flag"
```

---

## Self-Review

**Spec coverage:**
- [x] ADC authentication → Task 2 (`VertexAIClient.__init__` uses `google.auth.default()`)
- [x] `google-cloud-aiplatform` SDK → Task 1 (dependency) + Task 2 (implementation)
- [x] `gemini-2.5-flash` default model → Task 2 (`model="gemini-2.5-flash"` default arg)
- [x] Auto-detect project from ADC → Task 2 (`google.auth.default()`)
- [x] Auto-detect location from env vars → Task 2 (`GOOGLE_CLOUD_REGION`, `CLOUDSDK_COMPUTE_REGION`, fallback `"us-central1"`)
- [x] `vertex_project` / `vertex_location` config fields → Task 3
- [x] Env vars `PR_AGENT_VERTEX_PROJECT` / `PR_AGENT_VERTEX_LOCATION` → Task 3
- [x] `--provider vertex` CLI choice → Task 4
- [x] Model substitution (`claude-haiku-4.5` → `gemini-2.5-flash`) → Task 4
- [x] `project` / `location` forwarded from config to client → Task 4 (test 4)
- [x] Error mapping: `DefaultCredentialsError` → `LLMError` → Task 2 (test + impl)
- [x] Error mapping: `GoogleAPIError` → `LLMError` → Task 2 (test + impl)
- [x] Empty response → `LLMError` → Task 2 (test + impl)

**Placeholder scan:** No TBDs, all code blocks complete.

**Type consistency:** `VertexAIClient` constructor signature used in Task 2 (`project`, `location`, `model`, `timeout`) matches the kwargs used in Task 4 CLI dispatch (`project=cfg.vertex_project`, `location=cfg.vertex_location`, `model=effective_model`). `_get_model()` private helper is defined in Task 2 and only called within Task 2's `generate()` method.
