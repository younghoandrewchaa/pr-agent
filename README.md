# PR Agent

Automated GitHub pull request creation using AI — supports **GitHub Copilot** (Claude Haiku 4.5) and **Google Gemini via Vertex AI** (default).

PR Agent is a CLI tool that analyzes your code changes and generates intelligent, comprehensive PR descriptions. It extracts ticket numbers from branch names, prompts you for context, and creates well-structured pull requests on GitHub.

## Features

- **Two LLM providers**: Gemini via Vertex AI (default) or Claude Haiku 4.5 via GitHub Copilot
- **Intelligent PR Descriptions**: Generates comprehensive PR descriptions based on code changes
- **Description Feedback Loop**: Reject and refine the generated description with feedback (up to 5 iterations)
- **Auto-Commit**: Offers to commit uncommitted changes with an AI-generated commit message
- **Smart Ticket Extraction**: AI-powered extraction handles any branch naming convention (regex → AI → auto-generate)
- **Auto-Detect Base Branch**: Automatically detects default branch (main, master, develop)
- **Git Integration**: Analyzes diffs, changed files, and commit messages
- **GitHub CLI**: Seamlessly creates PRs using the `gh` command
- **PR Templates**: Reads `.github/pull_request_template.md` from your repository automatically
- **Preview Mode**: Review generated content before creating the PR
- **Draft PR Support**: Create draft PRs for work-in-progress

## Prerequisites

- **Python 3.10+**
- **GitHub CLI** (`gh`) — authenticated with `gh auth login`

**Vertex AI provider (default):**
- A Google Cloud project with Vertex AI enabled
- Application Default Credentials: run `gcloud auth application-default login`

**Copilot provider:**
- GitHub Copilot subscription (individual or enterprise)
- Authentication is handled automatically via OAuth device flow on first run

## Installation

Install directly from GitHub (no cloning required):

```bash
pip install git+https://github.com/andrewchaa/pr-agent.git
```

Or with [pipx](https://pipx.pypa.io/) for isolated CLI installs (recommended):

```bash
pipx install git+https://github.com/andrewchaa/pr-agent.git
```

To upgrade to the latest version:

```bash
pip install --upgrade git+https://github.com/andrewchaa/pr-agent.git
# or
pipx upgrade pr-agent
```

## Quick Start

1. Make some code changes in a git repository
2. Run PR Agent:
   ```bash
   pr-agent create
   ```
3. **First run with Vertex AI**: ensure you have run `gcloud auth application-default login`
4. **First run with Copilot**: follow the device flow shown in the terminal to authorize
5. Answer the prompt about your change purpose
6. Review the generated PR description — provide feedback to regenerate if needed
7. Confirm to create the PR

**Note:** You can run `pr-agent create` with uncommitted changes — it will offer to commit them with an AI-generated commit message before creating the PR.

## Usage

### Basic Usage

```bash
pr-agent create
```

### Select Provider

```bash
# Use GitHub Copilot (Claude Haiku 4.5)
pr-agent create --provider copilot

# Use Vertex AI / Gemini (default)
pr-agent create --provider vertex
```

### Specify Model

```bash
pr-agent create --model gemini-2.5-pro
```

### Specify Base Branch

```bash
pr-agent create --base-branch develop
```

### Preview Without Creating

```bash
pr-agent create --dry-run
```

### Create Draft PR

```bash
pr-agent create --draft
```

### Open PR in Browser

```bash
pr-agent create --web
```

### Use Custom Config File

```bash
pr-agent create --config ~/my-config.yaml
```

## Configuration

Configuration sources (highest to lowest priority):

1. **Command-line arguments** (highest priority)
2. **Config file**: `~/.config/pr-agent/config.yaml`
3. **Environment variables**
4. **Defaults** (lowest priority)

### Create Default Config File

```bash
pr-agent init-config
```

This creates `~/.config/pr-agent/config.yaml` with default settings.

### Configuration Options

```yaml
# Provider: "vertex" (default) or "copilot"
provider: "vertex"

# Model (default depends on provider)
model: "gemini-2.5-flash"

# Vertex AI settings (required when provider is "vertex")
# vertex_project: "my-gcp-project"
# vertex_location: "europe-west2"

# Copilot settings (used when provider is "copilot")
copilot_api_base: "https://api.githubcopilot.com"
copilot_timeout: 60

# Git settings
default_base_branch: "main"
ticket_pattern: "STAR-(\\d+)"

# LLM settings
max_diff_tokens: 8000
```

### Environment Variables

```bash
# Provider
export PR_AGENT_PROVIDER="vertex"

# Vertex AI
export PR_AGENT_VERTEX_PROJECT="my-gcp-project"
export PR_AGENT_VERTEX_LOCATION="europe-west2"

# Copilot
export PR_AGENT_COPILOT_TOKEN_DIR="/custom/path"

# General
export PR_AGENT_BASE_BRANCH="develop"
export PR_AGENT_MODEL="gemini-2.5-pro"
```

## Branch Naming Convention

PR Agent uses **intelligent ticket extraction** with a three-step approach:

1. **Regex Pattern Matching** (fast) — tries pattern matching first
2. **AI Extraction** (flexible) — if regex fails, uses the LLM to extract the ticket
3. **Auto-generate** — derives a 4-letter prefix from the repo name + random number (e.g. `PAGE-38471`)

### Supported Branch Name Formats

```
feature/STAR-12345-add-feature
STAR-999-bugfix
star-422270-test              ← lowercase, AI handles it
feature_star_123_something    ← underscores
bugfix-with-star-789-somewhere
```

Default pattern: `STAR-(\d+)` — customizable in config.

## How It Works

1. **Validation**: checks for git repo and GitHub CLI authentication
2. **Provider setup**: connects to Vertex AI (default) or authenticates with GitHub Copilot
3. **Repo info**: fetches owner/repo for PR history (best-effort, failures non-fatal)
4. **Ticket extraction**: regex → AI → auto-generate
5. **Auto-commit** (if uncommitted changes): offers to stage and commit with an AI-generated message
6. **User intent**: prompts you to describe the purpose of your change
7. **PR generation**: generates title and description based on your diff, commits, and template
8. **Related PRs**: finds associated previous PRs to add context to the description
9. **Feedback loop**: lets you reject and refine the description with up to 5 iterations
10. **Create PR**: pushes branch if needed, creates the PR on GitHub, saves to history

## Troubleshooting

### Vertex AI: no credentials found

Run the following and follow the prompts:

```bash
gcloud auth application-default login
```

Alternatively, set a service account key:

```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/key.json"
```

### Vertex AI: project not set

Specify your project in the config or as an environment variable:

```bash
export PR_AGENT_VERTEX_PROJECT="my-gcp-project"
```

Or in `~/.config/pr-agent/config.yaml`:

```yaml
vertex_project: "my-gcp-project"
```

### Copilot: authentication failed

Clear cached tokens and re-authenticate:

```bash
rm -rf ~/.config/pr-agent/copilot
pr-agent create --provider copilot
```

Then follow the device flow:
1. Visit the URL shown (e.g., `github.com/login/device`)
2. Enter the 8-character code displayed
3. Click "Authorize"

### Error: Not in a git repository

Make sure you're running the command from within a git repository.

### Error: GitHub CLI not authenticated

Run `gh auth login` to authenticate with GitHub.

### Error: Base branch 'main' not found

PR Agent auto-detects your default branch. You can also specify it explicitly:

```bash
pr-agent create --base-branch master
```

Or set a default in `~/.config/pr-agent/config.yaml`:

```yaml
default_base_branch: "master"
```

### Empty or poor quality PR descriptions

- Provide a clear description when prompted for change purpose
- Try increasing `max_diff_tokens` in config for complex changes

### PR creation fails

- Check that you have push permissions to the repository
- Verify GitHub CLI is authenticated with `gh auth status`

## Development

### Project Structure

```
pr-agent/
├── src/
│   ├── __init__.py           # Package initialization
│   ├── __main__.py           # Module entry point
│   ├── cli.py                # Main CLI interface
│   ├── config.py             # Configuration management
│   ├── copilot_auth.py       # OAuth device flow authenticator
│   ├── git_operations.py     # Git interactions
│   ├── github_operations.py  # GitHub CLI wrapper
│   ├── llm_client.py         # Copilot and Vertex AI clients
│   ├── pr_generator.py       # PR generation logic
│   ├── pr_history.py         # Per-repo PR history
│   ├── prompts.py            # LLM prompt templates
│   ├── template_parser.py    # PR template parsing
│   └── exceptions.py         # Custom exceptions
├── tests/                    # Test suite
├── pyproject.toml            # Project configuration
└── release.sh                # Release script
```

### Running Tests

```bash
pip install -e ".[dev]"
pytest
```

### Code Formatting

```bash
black src/
ruff check src/
```

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## License

MIT License

## Acknowledgments

- Uses [Google Gemini](https://deepmind.google/technologies/gemini/) via [Vertex AI](https://cloud.google.com/vertex-ai) (default provider)
- Uses [Claude Haiku 4.5](https://www.anthropic.com/claude) via [GitHub Copilot](https://github.com/features/copilot) (alternative provider)
- Powered by [GitHub CLI](https://cli.github.com/)
