# PR History & Association Detection — Design Spec

**Date:** 2026-03-13

## Overview

Store a history of created PRs per repository and, when creating a new PR, use AI to detect associations with previous PRs. If associations are found, the LLM naturally weaves references to related PRs into the new PR description.

## Storage

History is stored in the pr-agent global config directory, scoped per repository, to avoid polluting or accidentally committing files into user repositories.

**Location:** `~/.config/pr-agent/history/<owner>/<repo>.json`

**Format:** JSON array of up to 50 most recent entries. Older entries are dropped on write to keep the file bounded.

```json
[
  {
    "pr_number": 42,
    "title": "STAR-456: Add user authentication",
    "description": "## Why\nUsers need to log in...",
    "created_at": "2026-03-13T10:30:00Z"
  }
]
```

The PR number is extracted from the URL returned by `gh pr create` (e.g., `https://github.com/owner/repo/pull/42` → `42`). `create_pull_request()` already normalises multi-line output to the last line, so parsing is safe.

## New Module: `src/pr_history.py`

Three functions:

### `get_history_path(owner: str, repo: str) -> Path`
Returns `~/.config/pr-agent/history/<owner>/<repo>.json`. Used internally.

### `save_pr(owner: str, repo: str, pr_number: int, title: str, description: str) -> None`
- Loads existing history (or starts with empty list if file doesn't exist)
- Appends a new entry with current UTC timestamp
- Trims the list to the 50 most recent entries before writing
- Writes back to the history file; creates parent directories if needed
- On any failure (IO error, etc.): logs a warning and returns without raising — saving to history must never block or crash PR creation

### `find_related_prs(owner: str, repo: str, title: str, intent: str, llm_client: CopilotClient) -> str`
- `intent` is the user's stated purpose for the change (collected before description generation)
- Loads history; returns empty string if no history exists
- Before sending to the LLM, truncates each history entry's `description` field to 500 characters to keep the prompt size manageable, and caps the number of entries sent to the LLM at 20 (most recent)
- Sends the truncated history + new PR title and intent to the LLM
- LLM returns a brief natural-language summary of related PRs (e.g., "This builds on #42 which introduced the auth module, and is related to #51 which added token refresh logic"), or an empty response if none are found
- Returns the summary string, or empty string if no associations found or LLM call fails

## Prompt Changes: `src/prompts.py` and `src/pr_generator.py`

`generate_description()` in `pr_generator.py` already generates multiple sections (why, impact, notes) by calling separate section generators. The `related_prs_context` is added as an optional parameter to `generate_description()` and injected into the system prompt that is shared across all section generation calls — not into any single section — so the LLM has the context available when generating any section and decides naturally where references fit best.

New `generate_description` signature:
```python
def generate_description(
    self,
    user_intent: str,
    base_branch: str,
    feedback_history: list[str] | None = None,
    related_prs_context: str = "",
) -> str:
```

When `related_prs_context` is non-empty, it is prepended to the system/context prompt:
```
Context from related PRs previously created in this repository:
{related_prs_context}

Incorporate references to related PRs naturally where relevant in the description.
```

## Integration in `cli.py`

### New call to `github_ops.get_repo_info()`
This is a **new call** added early in the `create` command flow (after prerequisites are validated, before ticket extraction). It is currently not called anywhere in the `create` command.

If `get_repo_info()` raises `GitHubError` (e.g., repo not yet on GitHub, auth issue), the error is caught, a warning is logged, and `owner`/`repo` are set to `None`. All subsequent history calls (`find_related_prs`, `save_pr`) are no-ops when `owner` or `repo` is `None`. PR creation continues normally.

### Point 1 — After user intent is collected and title is generated, before description generation
`find_related_prs` requires the `title` (generated from ticket + intent) and the `user_intent`. Both are available after title generation (~line 388 in current code).

**Skip in `--dry-run` mode** — association detection makes an LLM call and since no PR will be created (and nothing saved to history), `find_related_prs` is skipped entirely in dry-run.

```python
related_prs_context = ""
if not dry_run and owner and repo:
    related_prs_context = pr_history.find_related_prs(
        owner, repo, title, user_intent, llm_client
    )
```

Then pass `related_prs_context` into `generate_description()`.

### Point 2 — After successful PR creation
Extract the PR number from the returned URL and save to history. URL parsing can fail if `pr_url` is unexpected — this is caught and logged as a warning without raising.

```python
if owner and repo:
    try:
        pr_number = int(pr_url.rstrip("/").split("/")[-1])
        pr_history.save_pr(owner, repo, pr_number, title, description)
    except (ValueError, IndexError):
        console.print("[yellow]Warning: could not save PR to history[/yellow]")
```

## Data Flow

```
PR creation starts
    │
    ▼
validate_prerequisites()
    │
    ▼
get_repo_info() → owner, repo
    │  (on failure: owner=None, repo=None; continue)
    │
    ▼
ticket extraction, uncommitted changes check, commit count check
    │
    ▼
prompt_user_intent() → user_intent
    │
    ▼
generate_title() → title
    │
    ▼
[if not dry_run and owner and repo]
find_related_prs(owner, repo, title, user_intent, llm_client)
    │  → loads ~/.config/pr-agent/history/<owner>/<repo>.json (last 20 entries, descriptions truncated to 500 chars)
    │  → LLM returns related PR summary string (or "" on failure/no history)
    ▼
generate_description(..., related_prs_context=summary)
    │  → LLM weaves references into description naturally
    ▼
[user approval loop]
    │
    ▼
[if not dry_run] create_pull_request() → pr_url
    │
    ▼
[if owner and repo] save_pr(owner, repo, pr_number, title, description)
    → appends to ~/.config/pr-agent/history/<owner>/<repo>.json (trimmed to 50 entries)
```

## Error Handling

All history failures are non-fatal. PR creation must never be blocked by history operations.

| Failure | Behaviour |
|---------|-----------|
| `get_repo_info()` raises `GitHubError` | Log warning; set `owner=None, repo=None`; skip all history calls |
| History file corrupt/unreadable | Log warning; treat as empty history; continue |
| LLM call in `find_related_prs` fails | Log warning; return `""`; continue with empty context |
| `pr_url` parsing fails (non-numeric segment) | Log warning; skip `save_pr`; continue |
| `save_pr` IO error | Log warning; return without raising |

## Testing

- Unit test `save_pr`: verify JSON file is created, entries are appended, and list is trimmed to 50 entries.
- Unit test `find_related_prs`: mock LLM client; verify history is loaded and truncated before sending; verify `""` returned when no history; verify `""` returned when LLM raises.
- Unit test `get_history_path`: verify correct path construction.
- Unit test history size cap: write 55 entries, call `save_pr`, verify only 50 remain.
- Integration test in `cli.py`: mock `find_related_prs` and `save_pr`; verify called at the right points; verify skipped in `--dry-run`; verify skipped when `owner=None`.
- Test corrupt history file: verify warning logged and PR creation continues.
- Test `get_repo_info()` failure: verify warning logged and history calls are skipped.
