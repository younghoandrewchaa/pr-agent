# Remove claude-code Provider and Default to Vertex AI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the `claude-code` provider entirely and make `vertex` (Gemini) the default provider with `gemini-2.5-flash` as the default model.

**Architecture:** Three-layer cleanup: config defaults → implementation removal → CLI wiring. Each layer has its own task. Tests are updated before implementation in each task to keep failures honest.

**Tech Stack:** Python, Click, pytest, google-cloud-aiplatform.

---

## File Map

| File | Change |
|------|--------|
| `src/config.py` | Remove `claude_code_bin`; change `provider` default → `"vertex"`, `model` default → `"gemini-2.5-flash"` |
| `src/llm_client.py` | Delete `ClaudeCodeClient` class entirely |
| `src/pr_generator.py` | Replace `ClaudeCodeClient` with `VertexAIClient` in import and type hint |
| `src/cli.py` | Remove claude-code choice + dispatch branch; remove model substitution logic; fix `get_ticket_number` type hint |
| `tests/test_config.py` | Rewrite `TestProviderConfig` to reflect new defaults and removed field |
| `tests/test_llm_client.py` | Delete `TestClaudeCodeClient`; remove `ClaudeCodeClient` import |
| `tests/test_cli_provider.py` | Delete claude-code tests; update vertex model test |

---

## Task 1: Update Config — new defaults, remove `claude_code_bin`

**Files:**
- Modify: `src/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Update `TestProviderConfig` in `tests/test_config.py`**

Replace the entire `TestProviderConfig` class with the version below. The new version reflects:
- Default provider is `"vertex"` (not `"copilot"`)
- Default model is `"gemini-2.5-flash"` (not `"claude-haiku-4.5"`)
- `claude_code_bin` field and `PR_AGENT_CLAUDE_BIN` env var no longer exist

```python
class TestProviderConfig:

    def test_provider_default(self):
        config = Config()
        assert config.provider == "vertex"

    def test_model_default(self):
        config = Config()
        assert config.model == "gemini-2.5-flash"

    def test_provider_from_dict(self):
        config = Config.from_dict({"provider": "copilot"})
        assert config.provider == "copilot"

    def test_provider_from_dict_ignores_unknown_keys(self):
        config = Config.from_dict({"provider": "vertex", "unknown_key": "value"})
        assert config.provider == "vertex"

    def test_provider_from_env(self, monkeypatch):
        monkeypatch.setenv("PR_AGENT_PROVIDER", "copilot")
        config = Config.from_env()
        assert config.provider == "copilot"

    def test_provider_merge_with_cli_args(self):
        config = Config()
        merged = config.merge_with_cli_args(provider="copilot")
        assert merged.provider == "copilot"

    def test_provider_cli_arg_takes_precedence(self):
        config = Config(provider="copilot")
        merged = config.merge_with_cli_args(provider="vertex")
        assert merged.provider == "vertex"

    def test_provider_none_cli_arg_preserves_existing(self):
        config = Config(provider="copilot")
        merged = config.merge_with_cli_args(provider=None)
        assert merged.provider == "copilot"

    def test_load_config_provider_cli_arg(self):
        config = load_config(provider="copilot")
        assert config.provider == "copilot"
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
pytest tests/test_config.py::TestProviderConfig -v
```

Expected: FAIL — `Config().provider == "copilot"` not `"vertex"`, and `Config().model == "claude-haiku-4.5"` not `"gemini-2.5-flash"`.

- [ ] **Step 3: Update `src/config.py`**

**3a.** Change the `model` and `provider` defaults in the `Config` dataclass. Also remove the `claude_code_bin` field entirely:

```python
@dataclass
class Config:
    """Configuration for pr-agent."""

    # Model settings
    model: str = "gemini-2.5-flash"
    copilot_api_base: str = "https://api.githubcopilot.com"
    copilot_api_key: Optional[str] = None
    copilot_timeout: int = 60
    copilot_token_dir: Optional[str] = None

    # Provider settings
    provider: str = "vertex"

    # Vertex AI settings
    vertex_project: Optional[str] = None
    vertex_location: Optional[str] = None

    # Git settings
    default_base_branch: str = "main"
    ticket_pattern: str = r"STAR-(\d+)"

    # LLM settings
    max_diff_tokens: int = 8000
    temperature: float = 0.7

    # PR creation settings
    draft_pr: bool = False
    open_in_browser: bool = False
```

**3b.** In `from_dict()`, remove `"claude_code_bin"` from `valid_keys`:

```python
valid_keys = {
    "model",
    "copilot_api_base",
    "copilot_api_key",
    "copilot_timeout",
    "default_base_branch",
    "ticket_pattern",
    "max_diff_tokens",
    "temperature",
    "draft_pr",
    "open_in_browser",
    "provider",
    "vertex_project",
    "vertex_location",
}
```

**3c.** In `from_env()`, remove the `"PR_AGENT_CLAUDE_BIN": "claude_code_bin"` entry from `env_mapping`. The remaining mapping:

```python
env_mapping = {
    "PR_AGENT_MODEL": "model",
    "PR_AGENT_COPILOT_API_BASE": "copilot_api_base",
    "PR_AGENT_COPILOT_KEY": "copilot_api_key",
    "PR_AGENT_COPILOT_TIMEOUT": "copilot_timeout",
    "PR_AGENT_COPILOT_TOKEN_DIR": "copilot_token_dir",
    "PR_AGENT_BASE_BRANCH": "default_base_branch",
    "PR_AGENT_TICKET_PATTERN": "ticket_pattern",
    "PR_AGENT_MAX_DIFF_TOKENS": "max_diff_tokens",
    "PR_AGENT_PROVIDER": "provider",
    "PR_AGENT_VERTEX_PROJECT": "vertex_project",
    "PR_AGENT_VERTEX_LOCATION": "vertex_location",
}
```

**3d.** In `merge_with_cli_args()`, remove `claude_code_bin` from the method signature and from the `Config(...)` constructor call inside it:

```python
def merge_with_cli_args(
    self,
    base_branch: Optional[str] = None,
    model: Optional[str] = None,
    draft: Optional[bool] = None,
    web: Optional[bool] = None,
    provider: Optional[str] = None,
) -> "Config":
    new_config = Config(
        model=model or self.model,
        copilot_api_base=self.copilot_api_base,
        copilot_api_key=self.copilot_api_key,
        copilot_timeout=self.copilot_timeout,
        copilot_token_dir=self.copilot_token_dir,
        default_base_branch=base_branch or self.default_base_branch,
        ticket_pattern=self.ticket_pattern,
        max_diff_tokens=self.max_diff_tokens,
        temperature=self.temperature,
        draft_pr=draft if draft is not None else self.draft_pr,
        open_in_browser=web if web is not None else self.open_in_browser,
        provider=provider or self.provider,
        vertex_project=self.vertex_project,
        vertex_location=self.vertex_location,
    )
    return new_config
```

**3e.** In `load_config()`, remove `"claude_code_bin"` from the list of attributes iterated when merging file config:

```python
for attr in [
    "model",
    "copilot_api_base",
    "copilot_api_key",
    "copilot_timeout",
    "copilot_token_dir",
    "default_base_branch",
    "ticket_pattern",
    "max_diff_tokens",
    "provider",
    "vertex_project",
    "vertex_location",
]:
```

**3f.** In `create_default_config_file()`, update the default config dict:

```python
default_config = {
    "model": "gemini-2.5-flash",
    "provider": "vertex",
    "copilot_api_base": "https://api.githubcopilot.com",
    "copilot_timeout": 60,
    "default_base_branch": "main",
    "ticket_pattern": "STAR-(\\d+)",
    "max_diff_tokens": 8000,
}
```

- [ ] **Step 4: Run the config tests to verify they pass**

```bash
pytest tests/test_config.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/config.py tests/test_config.py
git commit -m "feat: default provider to vertex, model to gemini-2.5-flash, remove claude_code_bin"
```

---

## Task 2: Remove `ClaudeCodeClient`

**Files:**
- Modify: `src/llm_client.py`
- Modify: `src/pr_generator.py`
- Test: `tests/test_llm_client.py`

- [ ] **Step 1: Remove `TestClaudeCodeClient` and update imports in `tests/test_llm_client.py`**

At the top of the file, change:
```python
from src.llm_client import CopilotClient, ClaudeCodeClient
```
to:
```python
from src.llm_client import CopilotClient, VertexAIClient
```

Also remove `import subprocess` if it's only used by `TestClaudeCodeClient`. Check: `subprocess` is used in `@patch("subprocess.run", side_effect=subprocess.TimeoutExpired(...))` and `subprocess.run` mocks — all inside `TestClaudeCodeClient`. Remove the `import subprocess` line.

Delete the entire `TestClaudeCodeClient` class (all tests from `class TestClaudeCodeClient:` through the end of that class).

- [ ] **Step 2: Run the tests to confirm they still collect cleanly**

```bash
pytest tests/test_llm_client.py -v --collect-only
```

Expected: Only `TestCopilotClient` and `TestVertexAIClient` appear. No import errors.

- [ ] **Step 3: Remove `ClaudeCodeClient` from `src/llm_client.py`**

Delete the entire `ClaudeCodeClient` class — from `class ClaudeCodeClient:` through its last method `generate_commit_message`. Keep all imports, `CopilotClient`, and `VertexAIClient` unchanged.

Also remove `import subprocess` from the top of `src/llm_client.py` since it was only used by `ClaudeCodeClient`.

- [ ] **Step 4: Update `src/pr_generator.py`**

Change line 10:
```python
from src.llm_client import CopilotClient, ClaudeCodeClient
```
to:
```python
from src.llm_client import CopilotClient, VertexAIClient
```

Change the `__init__` type hint (line 38):
```python
llm_client: Union[CopilotClient, ClaudeCodeClient],
```
to:
```python
llm_client: Union[CopilotClient, VertexAIClient],
```

Change the default model (line 40):
```python
model: str = "claude-haiku-4.5",
```
to:
```python
model: str = "gemini-2.5-flash",
```

- [ ] **Step 5: Run all LLM client tests**

```bash
pytest tests/test_llm_client.py -v
```

Expected: All tests PASS. No `TestClaudeCodeClient` tests appear.

- [ ] **Step 6: Commit**

```bash
git add src/llm_client.py src/pr_generator.py tests/test_llm_client.py
git commit -m "feat: remove ClaudeCodeClient, update PRGenerator to accept VertexAIClient"
```

---

## Task 3: Clean up CLI

**Files:**
- Modify: `src/cli.py`
- Test: `tests/test_cli_provider.py`

- [ ] **Step 1: Update `tests/test_cli_provider.py`**

**1a.** Delete `test_claude_code_provider_skips_auth` and `test_claude_code_provider_passes_model` from `TestCliProvider`.

**1b.** Replace `test_vertex_provider_default_model_substitution` with a simpler test that verifies the default model flows through without any substitution logic (since the default is now `gemini-2.5-flash`):

```python
def test_vertex_provider_passes_default_model(self):
    """Default model (gemini-2.5-flash) is passed to VertexAIClient."""
    mock_git, mock_github, mock_gen = _base_mocks()

    with patch("src.cli.GitOperations", return_value=mock_git), \
         patch("src.cli.GitHubOperations", return_value=mock_github), \
         patch("src.cli.CopilotAuthenticator"), \
         patch("src.cli.VertexAIClient") as mock_vertex_cls, \
         patch("src.cli.PRGenerator", return_value=mock_gen), \
         patch("src.cli.pr_history"), \
         patch("src.cli.load_config") as mock_load_config:
        from src.config import Config
        mock_load_config.return_value = Config(provider="vertex")
        mock_vertex_cls.return_value.extract_ticket_number.return_value = None
        runner = CliRunner()
        result = runner.invoke(
            cli, ["create", "--provider", "vertex", "--dry-run"],
            input="test intent\ny\n"
        )

    assert result.exit_code == 0, result.output
    assert mock_vertex_cls.call_args.kwargs.get("model") == "gemini-2.5-flash"
```

- [ ] **Step 2: Run the CLI provider tests to confirm the deleted tests are gone and the updated test fails**

```bash
pytest tests/test_cli_provider.py -v
```

Expected: `test_claude_code_*` tests no longer appear. `test_vertex_provider_passes_default_model` fails if CLI still has substitution logic.

- [ ] **Step 3: Update `src/cli.py`**

**3a.** Change the import line to remove `ClaudeCodeClient`:

```python
from src.llm_client import CopilotClient, VertexAIClient
```

**3b.** Update `get_ticket_number()` type hint to replace `ClaudeCodeClient` with `VertexAIClient`:

```python
def get_ticket_number(
    git_ops: GitOperations,
    config: Config,
    llm_client: Optional[Union[CopilotClient, VertexAIClient]] = None,
) -> str:
```

**3c.** In the `--provider` option, remove `"claude-code"` from choices:

```python
@click.option(
    "--provider",
    "-P",
    type=click.Choice(["copilot", "vertex"]),
    default=None,
    help="LLM provider to use (default: from config or 'vertex')",
)
```

**3d.** In the provider dispatch block, remove the entire `if cfg.provider == "claude-code":` branch and simplify the vertex branch to use `cfg.model` directly (no substitution needed):

```python
        # Initialize LLM client based on configured provider
        if cfg.provider == "vertex":
            llm_client = VertexAIClient(
                project=cfg.vertex_project,
                location=cfg.vertex_location,
                model=cfg.model,
                timeout=cfg.copilot_timeout,
            )
            console.print(f"✓ Using Vertex AI (Gemini) as LLM provider", style="green")
            console.print()
        else:
            # copilot provider
            console.print("[bold blue]Authenticating with GitHub Copilot...[/bold blue]")
            authenticator = CopilotAuthenticator(token_dir=cfg.copilot_token_dir)

            try:
                copilot_token = authenticator.get_copilot_token()
                console.print("✓ Copilot authentication successful", style="green")
                console.print()
            except CopilotAuthError as e:
                console.print(f"✗ {e}", style="red")
                console.print("\n[yellow]To authenticate:[/yellow]")
                console.print("  Run this command again and follow the device flow instructions.")
                raise

            llm_client = CopilotClient(
                api_base=cfg.copilot_api_base,
                api_key=copilot_token,
                timeout=cfg.copilot_timeout,
            )
```

- [ ] **Step 4: Run CLI provider tests**

```bash
pytest tests/test_cli_provider.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Run the full test suite**

```bash
pytest -v
```

Expected: All tests PASS. No references to `ClaudeCodeClient` or `claude-code` remain.

- [ ] **Step 6: Commit**

```bash
git add src/cli.py tests/test_cli_provider.py
git commit -m "feat: remove claude-code provider from CLI, default to vertex"
```

---

## Self-Review

**Spec coverage:**
- [x] Remove `claude-code` provider → Task 2 (ClaudeCodeClient deleted) + Task 3 (CLI branch removed)
- [x] Default provider → `"vertex"` → Task 1 (`Config.provider = "vertex"`)
- [x] Default model → `"gemini-2.5-flash"` → Task 1 (`Config.model = "gemini-2.5-flash"`) + Task 2 (`PRGenerator` default)
- [x] Remove `claude_code_bin` field → Task 1
- [x] Remove model substitution logic → Task 3 (dispatch uses `cfg.model` directly)
- [x] Fix Pyright type errors → Task 2 (`pr_generator.py` union type) + Task 3 (`cli.py` union type + choices)

**Placeholder scan:** No TBDs, all code blocks complete.

**Type consistency:** `VertexAIClient` used in Task 2 (`pr_generator.py` import + type hint) matches the class name in `src/llm_client.py`. `Union[CopilotClient, VertexAIClient]` used consistently in both `pr_generator.py` and `cli.py` (Task 3).
