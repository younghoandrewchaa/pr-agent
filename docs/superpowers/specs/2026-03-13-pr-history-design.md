# PR History & Association Detection — Design Spec

**Date:** 2026-03-13

## Overview

Store a history of created PRs per repository and, when creating a new PR, use AI to detect associations with previous PRs. If associations are found, the LLM naturally weaves references to related PRs into the new PR description.

## Storage

History is stored in the pr-agent global config directory, scoped per repository, to avoid polluting or accidentally committing files into user repositories.

**Location:** `~/.config/pr-agent/history/<owner>/<repo>.json`

**Format:** JSON array of entries, appended on each successful PR creation.

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

The PR number is extracted from the URL returned by `gh pr create` (e.g., `https://github.com/owner/repo/pull/42` → `42`).

## New Module: `src/pr_history.py`

Three functions:

### `get_history_path(owner: str, repo: str) -> Path`
Returns `~/.config/pr-agent/history/<owner>/<repo>.json`. Used internally.

### `save_pr(owner: str, repo: str, pr_number: int, title: str, description: str) -> None`
- Loads existing history (or starts with empty list if file doesn't exist)
- Appends a new entry with current UTC timestamp
- Writes back to the history file
- Creates parent directories if needed

### `find_related_prs(owner: str, repo: str, title: str, description: str, llm_client: CopilotClient) -> str`
- Loads history; returns empty string if no history exists
- Sends history entries + new PR title/description to LLM
- LLM identifies related PRs and returns a brief natural-language summary (e.g., "This builds on #42 which introduced the auth module, and is related to #51 which added token refresh logic")
- Returns the summary string, or empty string if no associations found

## Prompt Changes: `src/prompts.py`

The description generation prompt gains an optional `related_prs_context` parameter. When non-empty, it's included in the system/user prompt so the LLM can naturally reference related PRs anywhere in the description.

Example addition to prompt:
```
Context from previous related PRs in this repository:
{related_prs_context}

Incorporate references to related PRs naturally where relevant.
```

## Integration in `cli.py`

### `github_ops.get_repo_info()` called earlier
Currently called only for PR creation validation. Move/reuse it early in the flow to obtain `owner` and `repo` for history lookups.

### Point 1 — Before description generation (~line 374)
After title generation, fetch related PR context:
```python
related_prs_context = pr_history.find_related_prs(
    owner, repo, title, user_intent, llm_client
)
```
Pass `related_prs_context` into `pr_generator.generate_description()`.

### Point 2 — After successful PR creation (~line 474)
Extract PR number from the returned URL and save to history:
```python
pr_number = int(pr_url.rstrip("/").split("/")[-1])
pr_history.save_pr(owner, repo, pr_number, title, description)
```

## Data Flow

```
PR creation starts
    │
    ▼
get_repo_info() → owner, repo
    │
    ▼
find_related_prs(owner, repo, title, intent, llm_client)
    │  → loads ~/.config/pr-agent/history/<owner>/<repo>.json
    │  → LLM returns related PR summary string (or "")
    ▼
generate_description(..., related_prs_context=summary)
    │  → LLM weaves references into description naturally
    ▼
[user approves description]
    │
    ▼
create_pull_request() → pr_url
    │
    ▼
save_pr(owner, repo, pr_number, title, description)
    → appends to ~/.config/pr-agent/history/<owner>/<repo>.json
```

## Error Handling

- If history file is corrupt/unreadable: log a warning, skip association detection, continue PR creation normally.
- If LLM call for association detection fails: log a warning, proceed with empty context.
- History failures must never block PR creation.

## Testing

- Unit test `save_pr`: verify JSON file is created and entries are appended correctly.
- Unit test `find_related_prs`: mock LLM client, verify history is loaded and passed correctly; verify empty string returned when no history.
- Unit test `get_history_path`: verify correct path construction.
- Integration test in `cli.py`: mock `find_related_prs` and `save_pr`, verify they're called at the right points in the flow.
- Test corrupt history file: verify warning is logged and PR creation continues.
