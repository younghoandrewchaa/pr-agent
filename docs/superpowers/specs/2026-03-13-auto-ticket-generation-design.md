# Auto Ticket Generation — Design Spec

**Date:** 2026-03-13

## Overview

When regex and AI extraction both fail to find a ticket number in a branch name, automatically generate a ticket-like identifier from the repository directory name and a random number. No manual user prompt is shown.

## Behaviour

The existing three-tier ticket extraction in `get_ticket_number()` (`cli.py`) becomes two tiers:

1. **Regex extraction** — fast, case-insensitive pattern match on branch name
2. **AI extraction** — LLM-based flexible extraction
3. ~~Manual user prompt~~ → **Auto-generation** (replaces this)

When tiers 1 and 2 both fail, the tool silently auto-generates a ticket number and prints it to the terminal with a green checkmark, then continues PR creation without blocking.

## Prefix Derivation

A new method `generate_ticket_prefix(self) -> str` on `GitOperations` derives a 4-letter uppercase prefix from the repository root directory name.

**Algorithm:**
1. Get the repository root directory name (basename of `git_ops.get_repository_root()`)
2. Split on non-alpha characters (hyphens, underscores, spaces, digits) to produce a word list
3. Walk through the words collecting the first letter of each word
4. If fewer than 4 letters collected after exhausting all words, cycle through the remaining characters of the last word (skipping the already-used first character), then repeat from the beginning of the last word as needed
5. Return the first 4 collected characters, uppercased

**Examples:**

| Directory name | Words | Result |
|---------------|-------|--------|
| `pr-agent` | `[pr, agent]` | `P` + `A` + `G` + `E` = `PAGE` |
| `my-cool-app` | `[my, cool, app]` | `M` + `C` + `A` + `P` = `MCAP` |
| `myapp` | `[myapp]` | `M` + `Y` + `A` + `P` = `MYAP` |
| `pr` | `[pr]` | `P` + `R` + `P` + `R` = `PRPR` |
| `x` | `[x]` | `X` + `X` + `X` + `X` = `XXXX` |

## Number Generation

A random 5-digit integer in the range `[10000, 99999]` is generated using `random.randint(10000, 99999)`. This ensures the number is always exactly 5 digits.

## Output Format

`PREFIX-NNNNN` — e.g., `PAGE-38471`

## CLI Change (`cli.py`)

In `get_ticket_number()`, the `Prompt.ask()` fallback is removed. In its place:

```python
# Method 3 (was: manual prompt) → Auto-generation
prefix = git_ops.generate_ticket_prefix()
number = random.randint(10000, 99999)
ticket_number = f"{prefix}-{number}"
console.print(f"[green]✓ Auto-generated ticket number:[/green] {ticket_number}")
return ticket_number
```

The `import random` statement is added at the top of `cli.py`.

## Files Changed

- **Modify:** `src/git_operations.py` — add `generate_ticket_prefix()` method
- **Modify:** `src/cli.py` — remove manual prompt fallback, add auto-generation call

## Error Handling

`generate_ticket_prefix()` must never raise. If the repo root cannot be determined or produces no usable characters, fall back to `REPO` as the prefix. This ensures a ticket number is always returned.

## Testing

- Unit test `generate_ticket_prefix()` for: multi-word names, single-word names, single-character names, names with digits/hyphens/underscores mixed in
- Unit test the cycling behaviour when fewer than 4 words
- Integration test in `get_ticket_number()`: verify that when regex and AI both return nothing, a ticket in `XXXX-NNNNN` format is returned without user input
