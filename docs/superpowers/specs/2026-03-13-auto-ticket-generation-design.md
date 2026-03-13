# Auto Ticket Generation — Design Spec

**Date:** 2026-03-13

## Overview

When regex and AI extraction both fail to find a ticket number in a branch name, automatically generate a ticket-like identifier from the repository directory name and a random number. No manual user prompt is shown.

## Behaviour

The existing three-tier ticket extraction in `get_ticket_number()` (`cli.py`) is updated — the manual prompt (tier 3) is replaced by auto-generation:

1. **Regex extraction** — fast, case-insensitive pattern match on branch name
2. **AI extraction** — LLM-based flexible extraction
3. **Auto-generation** — derives prefix from repo directory name + random 5-digit number *(replaces the previous manual Prompt.ask() call)*

When tiers 1 and 2 both fail, the tool silently auto-generates a ticket number, prints it to the terminal with a green checkmark, and continues PR creation without blocking.

## Prefix Derivation

A new method `generate_ticket_prefix(self) -> str` on `GitOperations` derives a 4-letter uppercase prefix from the repository root directory name.

**Algorithm:**
1. Get the repository root directory name (basename of `Path(self.repo.working_dir)` — this is always available when `GitOperations` is initialised; no exception is expected)
2. Split on non-alpha characters (hyphens, underscores, spaces, digits) and **filter out any empty tokens** that result from consecutive separators (e.g., `my--app` → `[my, app]`, not `[my, '', app]`)
3. If the resulting word list is empty or contains no alphabetic characters at all, return the fallback `REPO` immediately
4. Walk through the words collecting the first letter of each word until 4 letters are collected
5. If fewer than 4 letters collected after exhausting all words, cycle through the remaining characters of the last word (starting from its 2nd character). If the last word is a single character, skip directly to the wrap step. When the end of the last word is reached, wrap back to its beginning and repeat as needed
6. Return the first 4 collected characters, uppercased

**Examples:**

| Directory name | Words | Derivation | Result |
|---------------|-------|------------|--------|
| `pr-agent` | `[pr, agent]` | `P`(pr) + `A`(agent) + `G`(gent) + `E`(ent) | `PAGE` |
| `my-cool-app` | `[my, cool, app]` | `M`(my) + `C`(cool) + `A`(app) + `P`(pp, 2nd char of app) | `MCAP` |
| `myapp` | `[myapp]` | `M`(myapp) + `Y`(yapp) + `A`(app) + `P`(pp) | `MYAP` |
| `pr` | `[pr]` | `P`(pr) + `R`(r) + `P`(wrap→pr) + `R`(r) | `PRPR` |
| `x` | `[x]` | `X` × 4 (wrap→x, repeated) | `XXXX` |
| `my--app` | `[my, app]` | `M` + `A` + `P` + `P` | `MAPP` |
| `123-456` | `[]` (no alpha) | no alphabetic characters → fallback | `REPO` |
| `` (empty) | `[]` | empty → fallback | `REPO` |

## Number Generation

A random 5-digit integer in the range `[10000, 99999]` is generated using `random.randint(10000, 99999)`. This ensures the number is always exactly 5 digits.

## Output Format

`PREFIX-NNNNN` — e.g., `PAGE-38471`

## CLI Change (`cli.py`)

In `get_ticket_number()`, the `Prompt.ask()` fallback is removed. In its place:

```python
# Method 3: Auto-generate ticket number from repo directory name
prefix = git_ops.generate_ticket_prefix()
number = random.randint(10000, 99999)
ticket_number = f"{prefix}-{number}"
console.print(f"[green]✓ Auto-generated ticket number:[/green] {ticket_number}")
return ticket_number
```

`import random` is added with the other stdlib imports at the top of `cli.py` (alongside `import sys`, `from pathlib import Path`, etc.) — not inline, unlike the existing `import re` which is placed inline inside `get_ticket_number()`.

## Files Changed

- **Modify:** `src/git_operations.py` — add `generate_ticket_prefix()` method
- **Modify:** `src/cli.py` — replace manual prompt fallback with auto-generation; add `import random` at top

## Error Handling

`generate_ticket_prefix()` must never raise. The fallback `REPO` is returned when:
- The directory name is empty (e.g., repo at filesystem root)
- Splitting yields no tokens with alphabetic characters (e.g., all-numeric name like `123-456`)

## Testing

- Unit test `generate_ticket_prefix()` for:
  - Multi-word name (`pr-agent` → `PAGE`)
  - Three-word name with padding needed (`my-cool-app` → `MCAP`)
  - Single-word name (`myapp` → `MYAP`)
  - Single-character name (`x` → `XXXX`)
  - Two-character name with cycling past end of word (`pr` → `PRPR`)
  - Consecutive separators (`my--app` → `MAPP`)
  - All-numeric name (`123-456` → `REPO` fallback)
  - Empty directory name → `REPO` fallback
- Integration test: when regex and AI both return `None`, `get_ticket_number()` returns a string matching `^[A-Z]{4}-\d{5}$` without prompting the user
