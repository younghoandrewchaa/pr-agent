# Vertex AI (Gemini) Provider Design

**Date:** 2026-03-31
**Status:** Approved

## Problem

The GitHub Copilot API endpoints are blocked on the company network. The `claude-code` provider requires a local Claude Code installation. A third provider backed by Google Gemini via Vertex AI is needed so users can generate PR descriptions using GCP credentials they already have.

## Scope

Add a `vertex` provider option to pr-agent. When selected, the tool authenticates via Application Default Credentials (ADC) and calls the Vertex AI Generative Models API using the `google-cloud-aiplatform` SDK.

## Architecture

No structural changes to the existing architecture. A third client class is added to `llm_client.py` following the exact same pattern as `CopilotClient` and `ClaudeCodeClient`. The provider dispatch in `cli.py` gains one more branch.

```
cli.py  -->  VertexAIClient  -->  vertexai SDK  -->  Vertex AI API (Gemini)
              (llm_client.py)       (ADC auth)
```

## Components

### 1. `VertexAIClient` (new class in `src/llm_client.py`)

**Interface:** Identical to `CopilotClient` and `ClaudeCodeClient`:
- `generate(prompt, system, temperature, max_tokens) -> str`
- `generate_with_context(prompt, context, max_context_length) -> str`
- `extract_ticket_number(branch_name, ticket_prefix) -> Optional[str]`
- `generate_commit_message(ticket_number, changed_files, diff) -> str`

**Construction:**
```python
VertexAIClient(project=None, location=None, model="gemini-2.5-flash", timeout=60)
```

- `project`: GCP project ID. If `None`, auto-detected via `google.auth.default()`.
- `location`: GCP region. If `None`, checked in order: `GOOGLE_CLOUD_REGION` env var → `CLOUDSDK_COMPUTE_REGION` env var → `"us-central1"` hardcoded fallback.
- Calls `vertexai.init(project=..., location=...)` once in `__init__`.
- Uses `vertexai.generative_models.GenerativeModel` with `system_instruction` for system prompts and `GenerationConfig` for temperature/max_tokens.

**Error mapping:**
- `google.auth.exceptions.DefaultCredentialsError` → `LLMError("Vertex AI: no credentials found. Run 'gcloud auth application-default login'.")`
- `google.api_core.exceptions.GoogleAPIError` → `LLMError(f"Vertex AI request failed: {e}")`
- Empty/missing response → `LLMError("Vertex AI returned empty response")`

### 2. `Config` changes (`src/config.py`)

Two new optional fields:
```python
vertex_project: Optional[str] = None
vertex_location: Optional[str] = None
```

- Added to `valid_keys` in `from_dict()` for YAML config file support.
- Added to `from_env()` mapping:
  - `PR_AGENT_VERTEX_PROJECT` → `vertex_project`
  - `PR_AGENT_VERTEX_LOCATION` → `vertex_location`
- Passed through in `merge_with_cli_args()` unchanged (copy-through, no new CLI flags).

### 3. CLI wiring (`src/cli.py`)

**`--provider` choice list** expands to `["copilot", "claude-code", "vertex"]`.

**Provider dispatch** gains a third branch in the `create` command:
```python
elif cfg.provider == "vertex":
    effective_model = cfg.model if cfg.model != "claude-haiku-4.5" else "gemini-2.5-flash"
    llm_client = VertexAIClient(
        project=cfg.vertex_project,
        location=cfg.vertex_location,
        model=effective_model,
    )
    console.print("✓ Using Vertex AI (Gemini) as LLM provider", style="green")
```

The model substitution (`claude-haiku-4.5` → `gemini-2.5-flash`) handles the case where a user runs `--provider vertex` without specifying `--model`, so they don't accidentally pass a Copilot model name to the Vertex API.

### 4. Dependency (`pyproject.toml`)

Add to `dependencies`:
```
"google-cloud-aiplatform>=1.60.0",
```

## Configuration

Users can configure the Vertex AI provider in `~/.config/pr-agent/config.yaml`:

```yaml
provider: vertex
vertex_project: my-gcp-project   # optional; auto-detected if omitted
vertex_location: us-central1     # optional; auto-detected if omitted
model: gemini-2.5-flash          # optional; this is the default for vertex
```

Or via environment variables:
```bash
export PR_AGENT_PROVIDER=vertex
export PR_AGENT_VERTEX_PROJECT=my-gcp-project
export PR_AGENT_VERTEX_LOCATION=us-central1
```

Or via CLI flags:
```bash
pr-agent create --provider vertex --model gemini-2.5-flash
```

## Authentication

Users must run once:
```bash
gcloud auth application-default login
```

No tokens are cached by pr-agent for this provider — the `vertexai` SDK and underlying `google-auth` library handle credential lifecycle automatically.

## Testing

**`tests/test_llm_client.py`** — new `TestVertexAIClient` class:
- Mock `vertexai.init` and `vertexai.generative_models.GenerativeModel`
- Test: successful `generate()` returns stripped text
- Test: empty response raises `LLMError`
- Test: `DefaultCredentialsError` raises `LLMError` with helpful message
- Test: `GoogleAPIError` raises `LLMError`
- Test: `generate_with_context()` truncates context at `max_context_length`
- Test: `extract_ticket_number()` parses ticket from response
- Test: `generate_commit_message()` returns stripped string

**`tests/test_cli.py`** — new test for `--provider vertex`:
- Patch `VertexAIClient` and assert it is instantiated with correct args
- Assert `llm_client` used downstream is the `VertexAIClient` instance
- Test model substitution: when `cfg.model == "claude-haiku-4.5"`, effective model is `"gemini-2.5-flash"`

## Non-Goals

- No support for Gemini API (ai.google.dev) — only Vertex AI
- No streaming responses
- No multimodal (image) inputs
- No new CLI flags for project/location (env vars and config file are sufficient)
