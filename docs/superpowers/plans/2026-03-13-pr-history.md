# PR History & Association Detection Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Store a history of created PRs per repository and use AI to detect associations with previous PRs, weaving related PR references naturally into new PR descriptions.

**Architecture:** A new `src/pr_history.py` module handles all history concerns (read, write, LLM query). `src/prompts.py` gains a prompt for association detection. `src/pr_generator.py`'s `generate_description()` accepts `related_prs_context` and passes it as an augmented system prompt to all section generators. `src/cli.py` wires everything together at two points: before description generation and after successful PR creation.

**Tech Stack:** Python stdlib (`json`, `pathlib`, `datetime`), existing `CopilotClient.generate()`, existing `PRPrompts`, Click/Rich CLI

**Spec:** `docs/superpowers/specs/2026-03-13-pr-history-design.md`

---

## Chunk 1: `src/pr_history.py` — History module

**Files:**
- Create: `src/pr_history.py`
- Create: `tests/test_pr_history.py`

---

### Task 1: Write failing tests for `get_history_path` and `save_pr`

- [ ] **Step 1: Create `tests/test_pr_history.py` with failing tests**

```python
"""Tests for PR history module."""

import json
import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from src.pr_history import get_history_path, save_pr, find_related_prs


class TestGetHistoryPath:
    def test_returns_correct_path(self):
        path = get_history_path("acme", "myrepo")
        expected = Path.home() / ".config" / "pr-agent" / "history" / "acme" / "myrepo.json"
        assert path == expected

    def test_different_owner_and_repo(self):
        path = get_history_path("org", "other-repo")
        assert path.name == "other-repo.json"
        assert path.parent.name == "org"


class TestSavePr:
    def test_creates_file_with_entry(self, tmp_path):
        history_file = tmp_path / "history.json"
        with patch("src.pr_history.get_history_path", return_value=history_file):
            save_pr("acme", "myrepo", 42, "STAR-1: Add auth", "## Why\nNeeded auth")

        data = json.loads(history_file.read_text())
        assert len(data) == 1
        assert data[0]["pr_number"] == 42
        assert data[0]["title"] == "STAR-1: Add auth"
        assert data[0]["description"] == "## Why\nNeeded auth"
        assert "created_at" in data[0]

    def test_appends_to_existing_history(self, tmp_path):
        history_file = tmp_path / "history.json"
        existing = [{"pr_number": 1, "title": "old", "description": "d", "created_at": "2025-01-01T00:00:00Z"}]
        history_file.write_text(json.dumps(existing))

        with patch("src.pr_history.get_history_path", return_value=history_file):
            save_pr("acme", "myrepo", 2, "STAR-2: New", "desc")

        data = json.loads(history_file.read_text())
        assert len(data) == 2
        assert data[-1]["pr_number"] == 2

    def test_trims_to_50_entries(self, tmp_path):
        history_file = tmp_path / "history.json"
        existing = [
            {"pr_number": i, "title": f"PR {i}", "description": "d", "created_at": "2025-01-01T00:00:00Z"}
            for i in range(55)
        ]
        history_file.write_text(json.dumps(existing))

        with patch("src.pr_history.get_history_path", return_value=history_file):
            save_pr("acme", "myrepo", 100, "New PR", "desc")

        data = json.loads(history_file.read_text())
        assert len(data) == 50
        # Most recent entry is last
        assert data[-1]["pr_number"] == 100

    def test_creates_parent_directories(self, tmp_path):
        history_file = tmp_path / "nested" / "dirs" / "history.json"
        with patch("src.pr_history.get_history_path", return_value=history_file):
            save_pr("acme", "myrepo", 1, "title", "desc")

        assert history_file.exists()

    def test_handles_write_io_error_silently(self, tmp_path):
        history_file = tmp_path / "history.json"
        with patch("src.pr_history.get_history_path", return_value=history_file):
            # patch.object(Path, "write_text") targets the write call; mkdir uses os.makedirs
            # internally and is unaffected by this patch
            with patch.object(Path, "write_text", side_effect=OSError("disk full")):
                # Must not raise
                save_pr("acme", "myrepo", 1, "title", "desc")

    def test_handles_read_io_error_silently(self, tmp_path):
        history_file = tmp_path / "history.json"
        history_file.write_text("[]")  # File exists so exists() returns True
        with patch("src.pr_history.get_history_path", return_value=history_file):
            with patch.object(Path, "read_text", side_effect=OSError("permission denied")):
                # Must not raise; _load_history returns [] and save_pr continues
                save_pr("acme", "myrepo", 1, "title", "desc")

    def test_handles_corrupt_history_file(self, tmp_path):
        history_file = tmp_path / "history.json"
        history_file.write_text("not valid json {{{")
        with patch("src.pr_history.get_history_path", return_value=history_file):
            # Should not raise; treats corrupt file as empty
            save_pr("acme", "myrepo", 1, "title", "desc")

        data = json.loads(history_file.read_text())
        assert len(data) == 1


class TestFindRelatedPrs:
    def test_returns_empty_when_no_history(self, tmp_path):
        history_file = tmp_path / "nonexistent.json"
        mock_client = Mock()
        with patch("src.pr_history.get_history_path", return_value=history_file):
            result = find_related_prs("acme", "myrepo", "STAR-1: title", "intent", mock_client)

        assert result == ""
        mock_client.generate.assert_not_called()

    def test_sends_truncated_descriptions_to_llm(self, tmp_path):
        history_file = tmp_path / "history.json"
        long_desc = "x" * 1000
        history = [{"pr_number": 1, "title": "PR 1", "description": long_desc, "created_at": "2025-01-01T00:00:00Z"}]
        history_file.write_text(json.dumps(history))

        mock_client = Mock()
        mock_client.generate.return_value = "Related to #1"

        with patch("src.pr_history.get_history_path", return_value=history_file):
            find_related_prs("acme", "myrepo", "title", "intent", mock_client)

        call_args = mock_client.generate.call_args
        prompt_sent = call_args.kwargs.get("prompt") or call_args.args[0]
        # Full 1000-char description must not appear; truncated 500-char version must
        assert "x" * 501 not in prompt_sent
        assert "x" * 500 in prompt_sent

    def test_caps_history_at_20_entries_sent_to_llm(self, tmp_path):
        history_file = tmp_path / "history.json"
        history = [
            {"pr_number": i, "title": f"PR {i}", "description": "desc", "created_at": "2025-01-01T00:00:00Z"}
            for i in range(30)
        ]
        history_file.write_text(json.dumps(history))

        mock_client = Mock()
        mock_client.generate.return_value = "NONE"

        with patch("src.pr_history.get_history_path", return_value=history_file):
            find_related_prs("acme", "myrepo", "title", "intent", mock_client)

        prompt_sent = mock_client.generate.call_args.kwargs.get("prompt") or mock_client.generate.call_args.args[0]
        # Only 20 most recent entries (PR 10..29) should appear
        assert "PR 29" in prompt_sent
        assert "PR 0" not in prompt_sent

    def test_returns_empty_string_when_llm_returns_NONE_sentinel(self, tmp_path):
        # LLM returns the string "NONE" (the sentinel value), not Python None
        history_file = tmp_path / "history.json"
        history = [{"pr_number": 1, "title": "PR 1", "description": "desc", "created_at": "2025-01-01T00:00:00Z"}]
        history_file.write_text(json.dumps(history))

        mock_client = Mock()
        mock_client.generate.return_value = "NONE"

        with patch("src.pr_history.get_history_path", return_value=history_file):
            result = find_related_prs("acme", "myrepo", "title", "intent", mock_client)

        assert result == ""

    def test_returns_empty_string_when_llm_raises(self, tmp_path):
        history_file = tmp_path / "history.json"
        history = [{"pr_number": 1, "title": "PR 1", "description": "desc", "created_at": "2025-01-01T00:00:00Z"}]
        history_file.write_text(json.dumps(history))

        mock_client = Mock()
        mock_client.generate.side_effect = Exception("LLM error")

        with patch("src.pr_history.get_history_path", return_value=history_file):
            result = find_related_prs("acme", "myrepo", "title", "intent", mock_client)

        assert result == ""

    def test_returns_llm_summary_when_related(self, tmp_path):
        history_file = tmp_path / "history.json"
        history = [{"pr_number": 42, "title": "STAR-1: Auth", "description": "Added auth", "created_at": "2025-01-01T00:00:00Z"}]
        history_file.write_text(json.dumps(history))

        mock_client = Mock()
        mock_client.generate.return_value = "This builds on #42 which introduced auth."

        with patch("src.pr_history.get_history_path", return_value=history_file):
            result = find_related_prs("acme", "myrepo", "STAR-2: Extend auth", "add OAuth", mock_client)

        assert result == "This builds on #42 which introduced auth."
```

- [ ] **Step 2: Run tests to confirm they all fail**

```bash
pytest tests/test_pr_history.py -v
```

Expected: `ImportError` — `src.pr_history` does not exist yet.

---

### Task 2: Implement `src/pr_history.py`

- [ ] **Step 3: Create `src/pr_history.py`**

```python
"""
PR history module.

Stores history of created PRs per repository and uses AI to detect
associations between a new PR and previous ones.
"""

import json
import logging
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MAX_HISTORY_ENTRIES = 50
MAX_ENTRIES_TO_LLM = 20
MAX_DESCRIPTION_CHARS = 500


def get_history_path(owner: str, repo: str) -> Path:
    """Return path to history file for a given repository."""
    return Path.home() / ".config" / "pr-agent" / "history" / owner / f"{repo}.json"


def _load_history(history_file: Path) -> list:
    """Load history from file. Returns empty list on any error."""
    if not history_file.exists():
        return []
    try:
        return json.loads(history_file.read_text()) or []
    except Exception:
        logger.warning("PR history file is corrupt or unreadable: %s", history_file)
        return []


def save_pr(owner: str, repo: str, pr_number: int, title: str, description: str) -> None:
    """
    Append a PR to the history file for the given repository.

    Trims history to MAX_HISTORY_ENTRIES most recent entries.
    Never raises — any failure is logged as a warning.
    """
    history_file = get_history_path(owner, repo)
    try:
        history = _load_history(history_file)
        history.append({
            "pr_number": pr_number,
            "title": title,
            "description": description,
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
        # Keep only the most recent entries
        history = history[-MAX_HISTORY_ENTRIES:]
        history_file.parent.mkdir(parents=True, exist_ok=True)
        history_file.write_text(json.dumps(history, indent=2))
    except Exception:
        logger.warning("Failed to save PR to history", exc_info=True)


def find_related_prs(
    owner: str,
    repo: str,
    title: str,
    intent: str,
    llm_client,
) -> str:
    """
    Use AI to find PRs in history related to the new PR.

    Returns a natural-language summary of related PRs, or "" if none found
    or if any error occurs. Never raises.
    """
    from src.prompts import PRPrompts

    history_file = get_history_path(owner, repo)
    history = _load_history(history_file)

    if not history:
        return ""

    # Use only the most recent entries, truncate descriptions
    recent = history[-MAX_ENTRIES_TO_LLM:]
    truncated = [
        {
            "pr_number": e["pr_number"],
            "title": e["title"],
            "description": e["description"][:MAX_DESCRIPTION_CHARS],
            "created_at": e.get("created_at", ""),
        }
        for e in recent
    ]

    prompt = PRPrompts.find_related_prs_prompt(title, intent, truncated)

    try:
        response = llm_client.generate(
            prompt=prompt,
            temperature=0.1,
        )
        response = response.strip()
        if response.upper() == "NONE" or not response:
            return ""
        return response
    except Exception:
        logger.warning("Failed to find related PRs via LLM", exc_info=True)
        return ""
```

- [ ] **Step 4: Run tests that don't depend on `find_related_prs_prompt`**

```bash
pytest tests/test_pr_history.py::TestGetHistoryPath tests/test_pr_history.py::TestSavePr -v
```

Expected: All pass. Do not run `TestFindRelatedPrs` yet — `find_related_prs_prompt` doesn't exist until Step 7. The full test suite for this file runs after Step 8.

---

## Chunk 2: Prompts and PR generator updates

**Files:**
- Modify: `src/prompts.py` — add `find_related_prs_prompt()` static method
- Modify: `src/pr_generator.py` — add `related_prs_context` param and `system_prompt` threading
- Modify: `tests/test_pr_generator.py` — add tests for new behaviour

---

### Task 3: Add `find_related_prs_prompt` to `src/prompts.py`

- [ ] **Step 5: Write a failing test for the prompt**

Add to `tests/test_pr_history.py` in `TestFindRelatedPrs` (or a new `TestPrompts` class at the bottom):

```python
class TestFindRelatedPrsPrompt:
    def test_prompt_includes_title_and_intent(self):
        from src.prompts import PRPrompts
        history = [{"pr_number": 1, "title": "PR 1", "description": "desc", "created_at": "2025-01-01T00:00:00Z"}]
        prompt = PRPrompts.find_related_prs_prompt("STAR-2: New feature", "add OAuth", history)
        assert "STAR-2: New feature" in prompt
        assert "add OAuth" in prompt

    def test_prompt_includes_history_entries(self):
        from src.prompts import PRPrompts
        history = [{"pr_number": 42, "title": "Old PR", "description": "Old desc", "created_at": "2025-01-01T00:00:00Z"}]
        prompt = PRPrompts.find_related_prs_prompt("New PR", "intent", history)
        assert "#42" in prompt
        assert "Old PR" in prompt
        assert "Old desc" in prompt
```

- [ ] **Step 6: Run to confirm fail**

```bash
pytest tests/test_pr_history.py::TestFindRelatedPrsPrompt -v
```

Expected: `AttributeError: type object 'PRPrompts' has no attribute 'find_related_prs_prompt'`

- [ ] **Step 7: Add `find_related_prs_prompt` to `src/prompts.py`**

Add this static method to the `PRPrompts` class (after `generate_notes_prompt`):

```python
@staticmethod
def find_related_prs_prompt(title: str, intent: str, history: list) -> str:
    """
    Generate prompt for detecting associations between a new PR and previous ones.

    Args:
        title: New PR title
        intent: User's stated purpose for the new PR
        history: List of history entries (pr_number, title, description, created_at)

    Returns:
        Prompt for association detection.
    """
    history_text = "\n\n".join(
        f"PR #{e['pr_number']} ({e['created_at'][:10]}): {e['title']}\n{e['description']}"
        for e in history
    )

    return f"""You are reviewing a new pull request to see if it is related to any previous PRs in the same repository.

New PR:
Title: {title}
Purpose: {intent}

Previous PRs in this repository:
{history_text}

If any previous PRs are clearly related to the new one (same feature area, continuation of work, depends on, builds upon, or fixes issues introduced by), write a brief 1-2 sentence summary naming the related PRs by number and explaining the relationship.

If no previous PRs are clearly related, respond with exactly: NONE

Do not speculate. Only mention PRs with a clear, specific connection. Do not list PRs just because they touch similar files."""
```

- [ ] **Step 8: Run all history tests**

```bash
pytest tests/test_pr_history.py -v
```

Expected: All pass.

- [ ] **Step 9: Commit**

```bash
git add src/pr_history.py tests/test_pr_history.py src/prompts.py
git commit -m "feat: add PR history module and association detection prompt"
```

---

### Task 4: Update `src/pr_generator.py` to accept `related_prs_context`

- [ ] **Step 10: Write failing tests**

Add to `tests/test_pr_generator.py`:

```python
class TestGenerateDescriptionWithRelatedPrs:
    """Test that related_prs_context is threaded into section generation."""

    def _make_generator(self):
        mock_llm = Mock()
        mock_llm.generate.return_value = "Generated content"
        mock_git = Mock()
        mock_git.get_changed_files.return_value = ["src/auth.py"]
        mock_git.get_commit_messages.return_value = ["STAR-1: Add auth"]
        mock_git.get_diff.return_value = ""
        return PRGenerator(mock_llm, mock_git), mock_llm

    def test_related_prs_context_added_to_system_prompt(self):
        generator, mock_llm = self._make_generator()
        generator.generate_description(
            user_intent="add auth",
            base_branch="main",
            related_prs_context="This builds on #42.",
        )
        # Every LLM call should use an augmented system prompt
        for call in mock_llm.generate.call_args_list:
            system = call.kwargs.get("system") or ""
            assert "This builds on #42." in system

    def test_no_related_prs_context_uses_default_system_prompt(self):
        generator, mock_llm = self._make_generator()
        generator.generate_description(
            user_intent="add auth",
            base_branch="main",
        )
        for call in mock_llm.generate.call_args_list:
            system = call.kwargs.get("system") or ""
            # Default system prompt should be used — no extra context injected
            assert "Context from related PRs" not in system

    def test_generate_description_accepts_related_prs_context_param(self):
        generator, _ = self._make_generator()
        # Should not raise
        generator.generate_description(
            user_intent="add auth",
            base_branch="main",
            related_prs_context="",
        )
```

- [ ] **Step 11: Run to confirm fail**

```bash
pytest tests/test_pr_generator.py::TestGenerateDescriptionWithRelatedPrs -v
```

Expected: `TypeError` — `generate_description()` doesn't accept `related_prs_context`.

- [ ] **Step 12: Update `src/pr_generator.py`**

**1. Add `_build_system_prompt` private method to `PRGenerator`** (after `__init__`):

```python
def _build_system_prompt(self, related_prs_context: str = "") -> str:
    """Build system prompt, optionally augmented with related PR context."""
    if not related_prs_context:
        return self.prompts.SYSTEM_PROMPT
    return (
        f"{self.prompts.SYSTEM_PROMPT}\n\n"
        f"Context from related PRs previously created in this repository:\n"
        f"{related_prs_context}\n\n"
        f"Incorporate references to related PRs naturally where relevant in the description."
    )
```

**2. Add `system_prompt: Optional[str] = None` parameter to the three section generators.**

In `generate_why_section`, change:
```python
response = self.llm_client.generate(
    prompt=prompt,
    system=self.prompts.SYSTEM_PROMPT,
    temperature=WHY_TEMPERATURE,
    max_tokens=WHY_MAX_TOKENS,
)
```
to:
```python
response = self.llm_client.generate(
    prompt=prompt,
    system=system_prompt or self.prompts.SYSTEM_PROMPT,
    temperature=WHY_TEMPERATURE,
    max_tokens=WHY_MAX_TOKENS,
)
```

Apply the same change to `generate_impact_section` and `generate_notes_section`.

Also add `system_prompt: Optional[str] = None` to each method signature:
- `def generate_why_section(self, user_intent, changed_files, diff=None, feedback_history=None, system_prompt=None)`
- `def generate_impact_section(self, changed_files, commit_messages, diff=None, feedback_history=None, system_prompt=None)`
- `def generate_notes_section(self, changed_files, diff=None, feedback_history=None, system_prompt=None)`

**3. Update `generate_description` signature and pass `system_prompt` to section calls:**

```python
def generate_description(
    self,
    user_intent: str,
    base_branch: str = "main",
    feedback_history: Optional[List[str]] = None,
    related_prs_context: str = "",
) -> str:
```

At the top of `generate_description`, after `feedback_history = feedback_history or []`:
```python
system_prompt = self._build_system_prompt(related_prs_context)
```

Then pass `system_prompt=system_prompt` to each section call. For example:
```python
sections[f"section_{i}"] = self.generate_why_section(
    user_intent, changed_files, diff, feedback_history,
    system_prompt=system_prompt,
)
```
Apply the same for `generate_impact_section` and `generate_notes_section`.

- [ ] **Step 13: Run all generator tests**

```bash
pytest tests/test_pr_generator.py -v
```

Expected: All pass.

- [ ] **Step 14: Commit**

```bash
git add src/pr_generator.py tests/test_pr_generator.py
git commit -m "feat: thread related_prs_context through description generation"
```

---

## Chunk 3: `cli.py` integration

**Files:**
- Modify: `src/cli.py` — add `get_repo_info()` call, `find_related_prs` before description, `save_pr` after creation

> Note: `cli.py` is integration-heavy and hard to unit test directly. The key tests here verify the calls happen at the right points using mocking.

---

### Task 5: Integrate history calls in `src/cli.py`

- [ ] **Step 15a: Write failing integration tests for cli.py history behaviour**

Create `tests/test_cli_history.py`:

```python
"""Integration tests for PR history calls in the create command."""

import pytest
from click.testing import CliRunner
from unittest.mock import Mock, patch, MagicMock, call

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
                    extra_input="add auth\ny\n", extra_args=None, mock_history=None):
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
            "acme", "myrepo", "STAR-1: Add auth", "add auth", pytest.ANY
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
```

- [ ] **Step 15b: Run to confirm tests fail**

```bash
pytest tests/test_cli_history.py -v
```

Expected: `ImportError` or `AttributeError` — `src.cli` does not import `pr_history` yet.

- [ ] **Step 15: Make the changes to `src/cli.py`**

**Change 1 — Add import at top of file:**

After the existing imports, add:
```python
from src import pr_history
```

**Change 2 — Fetch repo info early in `create` command.**

Find the block after `validate_prerequisites(git_ops, github_ops)` and before the Copilot auth block (~line 238). Add:

```python
# Fetch repo info for PR history (best-effort — failures don't block PR creation)
owner = None
repo_name = None
try:
    repo_info = github_ops.get_repo_info()
    owner = repo_info["owner"]
    repo_name = repo_info["name"]
except Exception:
    console.print("[yellow]Warning: could not fetch repo info — PR history disabled[/yellow]")
```

**Change 3 — Fetch related PRs after title generation, before the description generation loop.**

Find the line `title = pr_generator.generate_title(...)`. After it, add:

```python
# Find related PRs from history (skipped in dry-run)
related_prs_context = ""
if not dry_run and owner and repo_name:
    with console.status("[bold cyan]Checking PR history for related PRs...[/bold cyan]"):
        related_prs_context = pr_history.find_related_prs(
            owner, repo_name, title, user_intent, llm_client
        )
```

**Change 4 — Pass `related_prs_context` to `generate_description`.**

In both places `generate_description` is called (initial call and the regeneration call in the feedback loop), add `related_prs_context=related_prs_context`:

```python
description = pr_generator.generate_description(
    user_intent=user_intent,
    base_branch=cfg.default_base_branch,
    related_prs_context=related_prs_context,
)
```
and in the feedback regeneration branch:
```python
description = pr_generator.generate_description(
    user_intent=user_intent,
    base_branch=cfg.default_base_branch,
    feedback_history=feedback_history,
    related_prs_context=related_prs_context,
)
```

**Change 5 — Save PR to history after successful creation.**

Find the success block after `pr_url = github_ops.create_pull_request(...)`. Add the code there — it is naturally unreachable in dry-run mode because `cli.py` already calls `sys.exit(0)` before `create_pull_request` when `--dry-run` is set. No additional dry-run guard is needed.

```python
# Save PR to history
if owner and repo_name:
    try:
        pr_number = int(pr_url.rstrip("/").split("/")[-1])
        pr_history.save_pr(owner, repo_name, pr_number, title, description)
    except (ValueError, IndexError):
        console.print("[yellow]Warning: could not save PR to history[/yellow]")
```

- [ ] **Step 16: Run the full test suite to verify no regressions**

```bash
pytest -v
```

Expected: All existing tests pass. `tests/test_cli_history.py` and all previous new tests pass.

- [ ] **Step 17: Commit**

```bash
git add src/cli.py tests/test_cli_history.py
git commit -m "feat: integrate PR history into create command"
```

---

## Final verification

- [ ] **Step 18: Run full test suite one final time**

```bash
pytest --tb=short
```

Expected: All tests pass, no warnings about missing imports.

- [ ] **Step 19: Confirm file structure**

```bash
python -c "from src.pr_history import get_history_path, save_pr, find_related_prs; print('OK')"
```

Expected: `OK`
