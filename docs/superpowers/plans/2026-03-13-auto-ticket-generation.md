# Auto Ticket Generation Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When regex and AI ticket extraction both fail, auto-generate a ticket identifier (`XXXX-NNNNN`) from the repo directory name instead of prompting the user.

**Architecture:** Add `generate_ticket_prefix()` to `GitOperations` to derive a 4-letter prefix from the repo root directory name. In `cli.py`'s `get_ticket_number()`, replace the `Prompt.ask()` fallback with a call to this method plus `random.randint()`.

**Tech Stack:** Python stdlib (`re`, `random`, `pathlib`), GitPython (`self.repo.working_dir`)

**Spec:** `docs/superpowers/specs/2026-03-13-auto-ticket-generation-design.md`

---

## Chunk 1: `generate_ticket_prefix()` in `git_operations.py`

**Files:**
- Modify: `src/git_operations.py` — add `generate_ticket_prefix()` method after `get_repository_root()` (line 280)
- Test: `tests/test_git_operations.py`

---

### Task 1: Write failing tests for `generate_ticket_prefix`

- [ ] **Step 1: Add `Mock` import to `tests/test_git_operations.py`**

Open `tests/test_git_operations.py`. If `from unittest.mock import Mock` is not already in the imports, add it:

```python
from unittest.mock import Mock
```

- [ ] **Step 2: Add failing tests to `tests/test_git_operations.py`**

Add the following class at the bottom of the file:

```python
class TestGenerateTicketPrefix:
    """Tests for generate_ticket_prefix() method."""

    def _make_git_ops(self, dir_name: str):
        """Create a GitOperations mock with a given working directory name."""
        mock_repo = Mock()
        mock_repo.working_dir = f"/some/path/{dir_name}"
        git_ops = GitOperations.__new__(GitOperations)
        git_ops.repo = mock_repo
        return git_ops

    def test_two_word_name(self):
        # pr-agent → P(pr) + A(agent) + G(gent) + E(nt) = PAGE
        git_ops = self._make_git_ops("pr-agent")
        assert git_ops.generate_ticket_prefix() == "PAGE"

    def test_three_word_name_with_one_char_padding(self):
        # my-cool-app → M + C + A + P(2nd char of app) = MCAP
        git_ops = self._make_git_ops("my-cool-app")
        assert git_ops.generate_ticket_prefix() == "MCAP"

    def test_single_word_name(self):
        # myapp → M + Y + A + P = MYAP
        git_ops = self._make_git_ops("myapp")
        assert git_ops.generate_ticket_prefix() == "MYAP"

    def test_two_char_word_cycles(self):
        # pr → P + R + P(wrap) + R = PRPR
        git_ops = self._make_git_ops("pr")
        assert git_ops.generate_ticket_prefix() == "PRPR"

    def test_single_char_word_cycles(self):
        # x → X + X + X + X = XXXX
        git_ops = self._make_git_ops("x")
        assert git_ops.generate_ticket_prefix() == "XXXX"

    def test_consecutive_separators_filtered(self):
        # my--app → words=[my, app] → M + A + P + P = MAPP
        git_ops = self._make_git_ops("my--app")
        assert git_ops.generate_ticket_prefix() == "MAPP"

    def test_all_numeric_falls_back_to_REPO(self):
        git_ops = self._make_git_ops("123-456")
        assert git_ops.generate_ticket_prefix() == "REPO"

    def test_empty_dir_name_falls_back_to_REPO(self):
        mock_repo = Mock()
        mock_repo.working_dir = "/"
        git_ops = GitOperations.__new__(GitOperations)
        git_ops.repo = mock_repo
        assert git_ops.generate_ticket_prefix() == "REPO"

    def test_four_or_more_words_uses_first_four(self):
        # my-cool-new-feature → M + C + N + F = MCNF (no padding needed)
        git_ops = self._make_git_ops("my-cool-new-feature")
        assert git_ops.generate_ticket_prefix() == "MCNF"

    def test_result_is_always_uppercase(self):
        git_ops = self._make_git_ops("lowercase-name")
        result = git_ops.generate_ticket_prefix()
        assert result == result.upper()

    def test_result_is_always_4_chars(self):
        for name in ["a", "ab", "abc", "abcd", "my-app", "pr-agent", "123-456"]:
            git_ops = self._make_git_ops(name)
            result = git_ops.generate_ticket_prefix()
            assert len(result) == 4, f"Expected 4 chars for '{name}', got '{result}'"
```

- [ ] **Step 3: Run tests to confirm they fail**

```bash
pytest tests/test_git_operations.py::TestGenerateTicketPrefix -v
```

Expected: `AttributeError: 'GitOperations' object has no attribute 'generate_ticket_prefix'`

---

### Task 2: Implement `generate_ticket_prefix`

- [ ] **Step 4: Add `generate_ticket_prefix()` to `src/git_operations.py`**

Add the following method to `GitOperations` after `get_repository_root()` (after line 280):

```python
def generate_ticket_prefix(self) -> str:
    """
    Derive a 4-letter uppercase ticket prefix from the repository directory name.

    Splits the directory name on non-alpha characters, collects the first
    letter of each word, then cycles through the last word's remaining
    characters until 4 letters are collected.

    Returns:
        4-letter uppercase prefix (e.g., "PAGE" for "pr-agent").
        Falls back to "REPO" if the directory name has no alphabetic characters.
    """
    dir_name = Path(self.repo.working_dir).name

    # Split on non-alpha characters and filter empty tokens
    words = [w for w in re.split(r'[^a-zA-Z]+', dir_name) if w]

    if not words:
        return "REPO"

    letters: List[str] = []

    # Collect the first letter of each word
    for word in words:
        letters.append(word[0].upper())
        if len(letters) == 4:
            return ''.join(letters)

    # Fewer than 4 letters — cycle through remaining chars of last word
    last_word = words[-1].upper()
    i = 1  # start after the first char (already collected above)
    while len(letters) < 4:
        if i >= len(last_word):
            i = 0  # wrap to beginning of last word
        letters.append(last_word[i])
        i += 1

    return ''.join(letters)
```

Note: `re`, `Path`, and `List` are already imported at the top of `git_operations.py` — no new imports needed.

- [ ] **Step 5: Run tests to confirm they pass**

```bash
pytest tests/test_git_operations.py::TestGenerateTicketPrefix -v
```

Expected: All 11 tests pass.

- [ ] **Step 6: Run full test suite to confirm no regressions**

```bash
pytest tests/test_git_operations.py -v
```

Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/git_operations.py tests/test_git_operations.py
git commit -m "feat: add generate_ticket_prefix to GitOperations"
```

---

## Chunk 2: CLI integration — replace manual prompt with auto-generation

**Files:**
- Modify: `src/cli.py` — add `import random`; replace `Prompt.ask()` fallback in `get_ticket_number()` with auto-generation
- Create: `tests/test_cli_ticket.py`

---

### Task 3: Write failing CLI integration test

- [ ] **Step 8: Create `tests/test_cli_ticket.py`**

```python
"""Tests for auto ticket generation in the create command."""

import re
import pytest
from unittest.mock import Mock, patch


class TestGetTicketNumber:
    """Tests for get_ticket_number() auto-generation behaviour."""

    def _call_get_ticket_number(self, branch_name: str, regex_result=None, ai_result=None):
        """
        Call get_ticket_number() with controlled extraction results.

        Both regex and AI extraction return None by default (simulating
        no ticket found), triggering auto-generation.
        """
        from src.cli import get_ticket_number
        from src.config import Config

        mock_git = Mock()
        mock_git.get_current_branch.return_value = branch_name
        mock_git.extract_ticket_number.return_value = regex_result
        mock_git.generate_ticket_prefix.return_value = "PAGE"

        mock_llm = Mock()
        mock_llm.extract_ticket_number.return_value = ai_result

        cfg = Config()

        with patch("src.cli.random") as mock_random:
            mock_random.randint.return_value = 38471
            result = get_ticket_number(mock_git, cfg, mock_llm)

        return result, mock_git, mock_llm, mock_random

    def test_auto_generates_when_regex_and_ai_both_fail(self):
        result, _, _, _ = self._call_get_ticket_number(
            "feature/no-ticket-here", regex_result=None, ai_result=None
        )
        assert result == "PAGE-38471"

    def test_auto_generated_format_matches_pattern(self):
        result, _, _, _ = self._call_get_ticket_number("random-branch")
        assert re.match(r'^[A-Z]{4}-\d{5}$', result), f"Expected XXXX-NNNNN format, got: {result}"

    def test_uses_generate_ticket_prefix_for_prefix(self):
        _, mock_git, _, _ = self._call_get_ticket_number("some-branch")
        mock_git.generate_ticket_prefix.assert_called_once()

    def test_uses_random_5_digit_number(self):
        _, _, _, mock_random = self._call_get_ticket_number("some-branch")
        mock_random.randint.assert_called_once_with(10000, 99999)

    def test_regex_result_returned_directly_without_auto_generation(self):
        result, mock_git, _, _ = self._call_get_ticket_number(
            "feature/STAR-123-auth", regex_result="STAR-123"
        )
        assert result == "STAR-123"
        mock_git.generate_ticket_prefix.assert_not_called()

    def test_ai_result_returned_directly_without_auto_generation(self):
        result, mock_git, _, _ = self._call_get_ticket_number(
            "feature/star_456_auth", regex_result=None, ai_result="STAR-456"
        )
        assert result == "STAR-456"
        mock_git.generate_ticket_prefix.assert_not_called()

    def test_auto_generates_when_no_llm_client_and_regex_fails(self):
        # get_ticket_number() accepts llm_client=None (skips AI tier entirely)
        # auto-generation must still trigger in this case
        from src.cli import get_ticket_number
        from src.config import Config

        mock_git = Mock()
        mock_git.get_current_branch.return_value = "no-ticket-branch"
        mock_git.extract_ticket_number.return_value = None
        mock_git.generate_ticket_prefix.return_value = "PAGE"

        cfg = Config()

        with patch("src.cli.random") as mock_random:
            mock_random.randint.return_value = 55555
            result = get_ticket_number(mock_git, cfg, llm_client=None)

        assert result == "PAGE-55555"
        mock_git.generate_ticket_prefix.assert_called_once()
```

- [ ] **Step 9: Run tests to confirm they fail**

```bash
pytest tests/test_cli_ticket.py -v
```

Expected: `AssertionError` or `AttributeError` — `get_ticket_number()` still calls `Prompt.ask()` and doesn't call `generate_ticket_prefix()`.

---

### Task 4: Update `get_ticket_number` in `src/cli.py`

- [ ] **Step 10: Add `import random` at the top of `src/cli.py`**

In `src/cli.py`, find the stdlib imports block (lines 7–9):
```python
import sys
from pathlib import Path
from typing import Optional
```

Add `import random` so the block reads:
```python
import random
import sys
from pathlib import Path
from typing import Optional
```

- [ ] **Step 11: Replace the manual prompt fallback in `get_ticket_number()`**

In `src/cli.py`, find the `get_ticket_number()` function. Replace the manual prompt block:

```python
# Method 3: Manual input (fallback)
console.print(f"[yellow]Could not extract ticket number from branch '{branch_name}'[/yellow]")
ticket_number = Prompt.ask("Please enter ticket number (e.g., STAR-12345)", default="STAR-0000")
return ticket_number
```

with:

```python
# Method 3: Auto-generate from repo directory name
prefix = git_ops.generate_ticket_prefix()
number = random.randint(10000, 99999)
ticket_number = f"{prefix}-{number}"
console.print(f"[green]✓ Auto-generated ticket number:[/green] {ticket_number}")
return ticket_number
```

- [ ] **Step 12: Run the CLI tests to confirm they pass**

```bash
pytest tests/test_cli_ticket.py -v
```

Expected: All 7 tests pass.

- [ ] **Step 13: Run full test suite to confirm no regressions**

```bash
pytest -v
```

Expected: All tests pass.

- [ ] **Step 14: Commit**

```bash
git add src/cli.py tests/test_cli_ticket.py
git commit -m "feat: auto-generate ticket number from repo directory name"
```

---

## Final verification

- [ ] **Step 15: Confirm `Prompt.ask` is no longer used for ticket number fallback**

```bash
grep -n "Please enter ticket number" src/cli.py
```

Expected: No output (line removed).

- [ ] **Step 16: Confirm `generate_ticket_prefix` is exported from the module**

```bash
python -c "from src.git_operations import GitOperations; print(hasattr(GitOperations, 'generate_ticket_prefix'))"
```

Expected: `True`
