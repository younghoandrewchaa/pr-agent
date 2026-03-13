# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Development
```bash
# Install in development mode
pip install -e .

# Install with dev dependencies
pip install -e ".[dev]"

# Run the CLI
pr-agent create
```

### Testing
```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_cli.py

# Run with coverage
pytest --cov=src
```

All `pytest` runs are pre-approved and should execute without prompting for user confirmation.

## Git Workflow

Do NOT run `git add` or `git commit`. The user reviews all changes before committing.

### Code Quality
```bash
# Format code
black src/

# Lint code
ruff check src/
```

### Prerequisites for Testing
Ensure these are available before testing:
- GitHub Copilot subscription with API access
- For device flow testing: ability to authorize via browser

## Architecture

### Core Workflow
PR creation follows this pipeline:
1. **Validation** (cli.py) - Check git repo and GitHub CLI auth
2. **Authentication** (copilot_auth.py) - OAuth device flow for Copilot token
3. **Repo Info** (cli.py) - Fetch owner/repo for history (best-effort, failures non-fatal)
4. **Ticket Extraction** (cli.py) - Three-tier: regex → AI → auto-generate
5. **Content Generation** (pr_generator.py) - LLM generates title + description sections
6. **Association Detection** (pr_history.py) - AI finds related previous PRs (skipped in dry-run)
7. **GitHub Integration** (github_operations.py) - Push branch + create PR via `gh` CLI
8. **History Save** (pr_history.py) - Append PR to per-repo history file

### Component Responsibilities

**cli.py** - Main orchestrator
- Command parsing and user interaction
- Prerequisites validation
- Workflow coordination
- Uses Rich for terminal UI

**config.py** - Multi-source configuration
- Priority: CLI args → config file → env vars → defaults
- Default config: `~/.config/pr-agent/config.yaml`
- Supports repository-specific `.pr-agent.yaml`
- Token directory for OAuth credentials

**copilot_auth.py** - OAuth device flow authenticator
- Implements GitHub OAuth device flow
- Exchanges access token for Copilot API token
- Caches tokens locally (~/.config/pr-agent/copilot)
- Auto-refreshes expired tokens

**git_operations.py** - Git interactions via GitPython
- Diff and commit retrieval
- Ticket extraction from branch names (regex-based)
- Auto-detect default branch (checks `origin/HEAD`, then common names)
- Validates commits exist (not just diffs)
- `generate_ticket_prefix()` derives a 4-letter uppercase prefix from the repo directory name

**github_operations.py** - GitHub CLI wrapper
- All GitHub operations via `gh` command
- Creates PRs with title, body, base branch
- Pushes branches to remote
- Checks authentication status

**llm_client.py** - GitHub Copilot API client
- Generates PR content via Copilot REST API with Claude Haiku 4.5
- AI-powered ticket extraction from branch names
- Configurable temperature (0.1 for extraction, 0.7 for creative)
- Context truncation for large diffs (default: 8000 tokens)
- Required headers: copilot-integration-id, editor-version, user-agent, etc.

**pr_generator.py** - PR content generation
- Generates title (ticket + user intent)
- Generates description sections dynamically based on template
- Retrieves git context (files, commits, diffs)
- Handles empty diffs gracefully
- Maps template sections to appropriate generation methods
- Accepts `related_prs_context` to augment system prompt with related PR associations

**pr_history.py** - Per-repository PR history
- Stores created PRs in `~/.config/pr-agent/history/<owner>/<repo>.json` (max 50 entries)
- `save_pr()` appends new entries; never raises (failures logged as warnings)
- `find_related_prs()` uses AI to detect associations with previous PRs; returns empty string if none found or on failure
- Descriptions truncated to 500 chars; at most 20 entries sent to LLM

**template_parser.py** - PR template parsing
- Reads `.github/pull_request_template.md` from repository
- Parses markdown headers (## or ###) to extract section questions
- Falls back to default sections if template doesn't exist
- Supports multiple template locations (.github, docs)

**prompts.py** - LLM prompt engineering
- All prompt templates for title, sections, ticket extraction
- Controls LLM output format and quality
- `find_related_prs_prompt()` generates the association detection prompt

**exceptions.py** - Custom exception hierarchy
- PRAgentError → GitError/GitHubError/LLMError/ConfigError
- Specific exceptions for validation failures

### Key Design Patterns

**Ticket Extraction (Three-Tier)**
1. Regex pattern matching (fast, case-insensitive, normalizes to uppercase)
2. AI extraction via LLM (flexible, handles unconventional names)
3. Auto-generation: `generate_ticket_prefix()` derives 4-letter prefix from repo directory name + `random.randint(10000, 99999)` → e.g. `PAGE-38471`

**PR History & Association Detection**
- History stored at `~/.config/pr-agent/history/<owner>/<repo>.json` (not in the repo)
- After title generation, `find_related_prs()` queries the LLM with the last 20 history entries; result injected as context into `generate_description()`
- After successful PR creation, the PR is appended to history (trimmed to 50 entries)
- All history operations are best-effort — failures never block PR creation
- Skipped entirely in `--dry-run` mode and when `get_repo_info()` fails

**Base Branch Auto-Detection**
1. Check `origin/HEAD` symbolic ref
2. Try common names: main → master → develop
3. Use config default
4. Show helpful suggestions on error

**Committed Changes Support**
- Counts commits between branches (not just diff)
- Works with already-pushed commits
- Validates commits exist before proceeding

**Dynamic PR Template Loading**
- Automatically reads `.github/pull_request_template.md` from repository at runtime
- Parses markdown headers (## or ###) to extract section questions
- Falls back to default sections if template doesn't exist
- Supports variable number of sections (not limited to 3)
- Maps sections to generation methods via keywords (why, impact) or position

**OAuth Device Flow Authentication**
- Two-step process: GitHub access token → Copilot API token
- User authorizes via browser (github.com/login/device)
- Tokens cached locally (~/.config/pr-agent/copilot)
- Access token: long-lived, stored as plain text
- API token: short-lived (~2 hours), stored with expiration
- Auto-refresh on expiry

## Configuration

Configuration sources (highest to lowest priority):
1. CLI arguments
2. Config file (`~/.config/pr-agent/config.yaml`)
3. Environment variables (`PR_AGENT_*`)
4. Hardcoded defaults

Key configurable options:
- `model` - Model name (default: claude-haiku-4.5)
- `copilot_api_base` - Copilot API URL (default: https://api.githubcopilot.com)
- `copilot_token_dir` - Token cache directory (default: ~/.config/pr-agent/copilot)
- `default_base_branch` - Base branch for PRs (default: main)
- `ticket_pattern` - Regex for ticket extraction (default: STAR-(\d+))
- `max_diff_tokens` - Token limit for diffs (default: 8000)

Note: PR description sections are now loaded dynamically from `.github/pull_request_template.md` in each repository. The `template.sections` configuration option has been removed.

## Important Behaviors

**Commits Required**
PR Agent requires committed changes. It analyzes commits, not uncommitted files. Always validate commits exist before generating PRs.

**Empty Diff Handling**
The tool handles already-pushed commits by checking commit count instead of relying solely on diffs. Use `allow_empty=True` when retrieving diffs.

**Branch Naming**
Ticket extraction is extremely flexible:
- Regex: case-insensitive, normalizes to uppercase
- AI: handles any format (underscores, middle of name, no separators)
- Auto-generation: derives prefix from repo directory name, no user prompt needed

**PR Template Parsing**
PR Agent automatically reads and parses repository-specific PR templates:
- Checks `.github/pull_request_template.md` (and other common locations)
- Extracts section headers from markdown (## or ### level)
- Falls back to default sections if no template exists
- Supports any number of sections (not limited to 3)

**Error Messages**
Provide helpful suggestions when validation fails (e.g., suggest available branches when base branch not found).

## Testing Notes

When writing tests:
- Mock external dependencies (Copilot API, GitHub CLI, git operations)
- Test three-tier ticket extraction flow
- Test base branch auto-detection logic
- Test committed changes validation
- Test configuration precedence
- Test PR template parsing with various markdown formats
- Test fallback to defaults when template doesn't exist
- Test dynamic section generation with variable section counts
- Test OAuth device flow (mock GitHub OAuth endpoints)
- Test token caching and expiration handling
- Test `generate_ticket_prefix()` with edge cases (single char, all-numeric, consecutive separators)
- Test `save_pr` / `find_related_prs` using `tmp_path` and `patch("src.pr_history.get_history_path")`
- Test CLI history integration by patching `src.cli.pr_history` as a module mock

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
