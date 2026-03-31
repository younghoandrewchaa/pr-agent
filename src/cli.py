"""
CLI interface for pr-agent.

Main command-line interface that orchestrates PR creation workflow.
"""

import random
import sys
from pathlib import Path
from typing import Optional, Union

import click
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.markdown import Markdown
from rich import print as rprint

from src.config import load_config, Config
from src.git_operations import GitOperations
from src.github_operations import GitHubOperations
from src.llm_client import CopilotClient, ClaudeCodeClient, VertexAIClient
from src.pr_generator import PRGenerator
from src.copilot_auth import CopilotAuthenticator
from src.exceptions import (
    PRAgentError,
    NotInGitRepoError,
    NotAuthenticatedError,
    CopilotAuthError,
    CopilotConfigError,
    NoChangesError,
    GitError,
    LLMError,
)
from src import pr_history

console = Console()


def validate_prerequisites(
    git_ops: GitOperations,
    github_ops: GitHubOperations,
) -> bool:
    """
    Validate all prerequisites for PR creation.

    Args:
        git_ops: Git operations handler
        github_ops: GitHub operations handler

    Returns:
        True if all checks pass.

    Raises:
        PRAgentError: If any prerequisite check fails.
    """
    console.print("[bold blue]Validating prerequisites...[/bold blue]")

    # Check 1: Git repository
    try:
        git_ops.validate_git_repo()
        console.print("✓ Git repository detected", style="green")
    except NotInGitRepoError as e:
        console.print(f"✗ {e}", style="red")
        raise

    # Check 2: GitHub CLI authentication
    try:
        github_ops.check_gh_auth()
        console.print("✓ GitHub CLI authenticated", style="green")
    except NotAuthenticatedError as e:
        console.print(f"✗ {e}", style="red")
        raise

    console.print()
    return True


def get_ticket_number(
    git_ops: GitOperations,
    config: Config,
    llm_client: Optional[Union[CopilotClient, ClaudeCodeClient]] = None,
) -> str:
    """
    Extract or prompt for ticket number.

    Tries multiple methods in order:
    1. Regex pattern matching (fast)
    2. LLM extraction (flexible, handles variations)
    3. Manual user input (fallback)

    Args:
        git_ops: Git operations handler
        config: Configuration
        llm_client: Optional LLM client for intelligent extraction

    Returns:
        Ticket number.
    """
    branch_name = git_ops.get_current_branch()

    # Method 1: Try regex extraction first (fast)
    ticket_number = git_ops.extract_ticket_number(branch_name, config.ticket_pattern)

    if ticket_number:
        console.print(f"[green]✓ Detected ticket number (regex):[/green] {ticket_number}")
        return ticket_number

    # Method 2: Try LLM extraction (handles variations)
    if llm_client:
        console.print(f"[yellow]Regex pattern didn't match. Trying AI extraction...[/yellow]")
        try:
            # Extract ticket prefix from pattern (e.g., "STAR-(\d+)" -> "STAR")
            import re

            pattern_match = re.match(r"([A-Z]+)-", config.ticket_pattern)
            ticket_prefix = pattern_match.group(1) if pattern_match else "STAR"

            with console.status("[bold cyan]Analyzing branch name with AI...[/bold cyan]"):
                ticket_number = llm_client.extract_ticket_number(
                    branch_name=branch_name,
                    ticket_prefix=ticket_prefix,
                )

            if ticket_number:
                console.print(f"[green]✓ Detected ticket number (AI):[/green] {ticket_number}")
                return ticket_number
        except Exception as e:
            console.print(f"[yellow]AI extraction failed: {e}[/yellow]")

    # Method 3: Auto-generate from repo directory name
    prefix = git_ops.generate_ticket_prefix()
    number = random.randint(10000, 99999)
    ticket_number = f"{prefix}-{number}"
    console.print(f"[green]✓ Auto-generated ticket number:[/green] {ticket_number}")
    return ticket_number


def prompt_user_intent() -> str:
    """
    Prompt user for the purpose of their change.

    Returns:
        User's description of the change purpose.
    """
    console.print()
    console.print("[bold cyan]What is the purpose of this change?[/bold cyan]")
    console.print(
        "[dim]Describe what you're trying to achieve (this helps generate better PR descriptions)[/dim]"
    )
    console.print()

    user_intent = Prompt.ask("Purpose")

    while not user_intent.strip():
        console.print("[red]Please provide a description of your changes.[/red]")
        user_intent = Prompt.ask("Purpose")

    return user_intent.strip()


def display_preview(title: str, body: str, base_branch: str) -> None:
    """
    Display PR preview with Rich formatting.

    Args:
        title: PR title
        body: PR description
        base_branch: Base branch name
    """
    console.print()
    console.print("[bold green]PR Preview:[/bold green]")
    console.print()

    # Display title
    console.print(Panel(f"[bold]{title}[/bold]", title="Title", border_style="cyan"))

    # Display base branch
    console.print(f"[dim]Base branch:[/dim] {base_branch}")
    console.print()

    # Display body
    md = Markdown(body)
    console.print(Panel(md, title="Description", border_style="cyan"))
    console.print()


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """PR Agent - Automated GitHub PR creation using local LLM."""
    pass


@cli.command()
@click.option(
    "--base-branch",
    "-b",
    default=None,
    help="Base branch for the PR (default: from config or 'main')",
)
@click.option(
    "--model",
    "-m",
    default=None,
    help="LLM model to use (default: from config or 'claude-haiku-4.5')",
)
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Path to config file (default: ~/.config/pr-agent/config.yaml)",
)
@click.option("--draft", "-d", is_flag=True, help="Create as draft PR")
@click.option("--web", "-w", is_flag=True, help="Open PR in browser after creation")
@click.option("--dry-run", is_flag=True, help="Preview PR without creating it")
@click.option(
    "--provider",
    "-P",
    type=click.Choice(["copilot", "claude-code", "vertex"]),
    default=None,
    help="LLM provider to use (default: from config or 'copilot')",
)
def create(
    base_branch: Optional[str],
    model: Optional[str],
    config: Optional[Path],
    draft: bool,
    web: bool,
    dry_run: bool,
    provider: Optional[str],
):
    """Create a new pull request with AI-generated description."""
    try:
        # Load configuration
        cfg = load_config(
            config_file=config,
            base_branch=base_branch,
            model=model,
            draft=draft,
            web=web,
            provider=provider,
        )

        # Initialize components
        git_ops = GitOperations()
        github_ops = GitHubOperations()

        # Validate prerequisites first
        validate_prerequisites(git_ops, github_ops)

        # Fetch repo info for PR history (best-effort — failures don't block PR creation)
        owner = None
        repo_name = None
        try:
            repo_info = github_ops.get_repo_info()
        except Exception:
            console.print("[yellow]Warning: could not fetch repo info — PR history disabled[/yellow]")
        else:
            owner = repo_info["owner"]
            repo_name = repo_info["name"]

        # Initialize LLM client based on configured provider
        if cfg.provider == "claude-code":
            llm_client = ClaudeCodeClient(
                model=cfg.model,
                executable=cfg.claude_code_bin,
                timeout=cfg.copilot_timeout,
            )
            console.print("✓ Using Claude Code CLI as LLM provider", style="green")
            console.print()
        elif cfg.provider == "vertex":
            effective_model = cfg.model if cfg.model != "claude-haiku-4.5" else "gemini-2.5-flash"
            llm_client = VertexAIClient(
                project=cfg.vertex_project,
                location=cfg.vertex_location,
                model=effective_model,
                timeout=cfg.copilot_timeout
            )
            console.print(f"✓ Using Vertex AI as LLM provider (model: {effective_model})", style="green")
            console.print()
        else:
            # Default: Copilot provider
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

        # Auto-detect base branch if not explicitly set
        if not base_branch:  # Only auto-detect if user didn't specify
            detected_base = git_ops.get_default_branch()
            if detected_base and detected_base != cfg.default_base_branch:
                console.print(
                    f"[cyan]Auto-detected base branch:[/cyan] {detected_base} "
                    f"[dim](instead of default '{cfg.default_base_branch}')[/dim]"
                )
                cfg.default_base_branch = detected_base
            elif not git_ops.branch_exists(cfg.default_base_branch):
                # Config default doesn't exist, try to find one
                if detected_base:
                    console.print(
                        f"[yellow]Base branch '{cfg.default_base_branch}' not found. "
                        f"Using '{detected_base}' instead.[/yellow]"
                    )
                    cfg.default_base_branch = detected_base

        # Get branch and ticket information
        branch_name = git_ops.get_current_branch()
        console.print(f"[blue]Current branch:[/blue] {branch_name}")
        console.print()

        ticket_number = get_ticket_number(git_ops, cfg, llm_client)

        # Check for uncommitted changes
        if git_ops.has_uncommitted_changes():
            console.print("[yellow]You have uncommitted changes.[/yellow]")
            console.print()

            # Offer to commit changes
            if Confirm.ask("Would you like me to commit these changes?", default=True):
                try:
                    # Get uncommitted changes info
                    diff = git_ops.get_uncommitted_diff()
                    changed_files = (
                        git_ops.repo.git.diff("HEAD", name_only=True).strip().split("\n")
                    )
                    changed_files = [f for f in changed_files if f]  # Filter empty

                    if not changed_files:
                        console.print("[yellow]No files to commit.[/yellow]")
                    else:
                        # Generate commit message
                        console.print()
                        with console.status(
                            "[bold cyan]Generating commit message with AI...[/bold cyan]"
                        ):
                            commit_message = llm_client.generate_commit_message(
                                ticket_number=ticket_number,
                                changed_files=changed_files,
                                diff=diff,
                            )

                        # Display and confirm
                        console.print()
                        console.print("[cyan]Suggested commit message:[/cyan]")
                        console.print(f"  {commit_message}")
                        console.print()

                        if Confirm.ask("Use this commit message?", default=True):
                            with console.status("[bold green]Committing changes...[/bold green]"):
                                git_ops.stage_all_changes()
                                git_ops.create_commit(commit_message)
                            console.print("[green]✓ Changes committed successfully[/green]")
                            console.print()
                        else:
                            # User rejected message, ask if they want to continue without committing
                            console.print("[yellow]Commit cancelled.[/yellow]")
                            if not Confirm.ask("Continue without committing?", default=False):
                                console.print("[red]Aborted.[/red]")
                                sys.exit(0)
                except (GitError, LLMError) as e:
                    console.print(f"[red]Error during auto-commit: {e}[/red]")
                    console.print()
                    if not Confirm.ask("Continue without committing?", default=False):
                        console.print("[red]Aborted.[/red]")
                        sys.exit(0)
            else:
                # User doesn't want to commit
                if not Confirm.ask("Continue without committing?", default=False):
                    console.print("[red]Aborted.[/red]")
                    sys.exit(0)

        # Check if there are commits to create PR for
        commit_count = git_ops.get_commit_count(cfg.default_base_branch)

        if commit_count == 0:
            console.print(
                f"[red]No commits found on '{branch_name}' compared to '{cfg.default_base_branch}'.[/red]"
            )
            console.print()
            console.print("This could mean:")
            console.print("  • You're on the base branch itself")
            console.print("  • Your changes haven't been committed yet")
            console.print("  • Your branch is already merged")
            console.print()
            console.print("To create a PR, you need to:")
            console.print("  1. Make some changes")
            console.print(
                "  2. Commit them: [cyan]git add . && git commit -m 'your message'[/cyan]"
            )
            console.print(f"  3. Make sure you're not on '{cfg.default_base_branch}'")
            sys.exit(1)

        console.print(f"[green]✓ Found {commit_count} commit(s) to include in PR[/green]")
        console.print()

        # Prompt for user intent
        user_intent = prompt_user_intent()

        # Generate PR content
        console.print()
        with console.status("[bold green]Generating PR description with AI...[/bold green]"):
            pr_generator = PRGenerator(
                llm_client=llm_client,
                git_ops=git_ops,
                model=cfg.model,
                max_diff_tokens=cfg.max_diff_tokens,
                repo_path=str(git_ops.get_repository_root()),
            )

            # Generate title (once, outside loop)
            title = pr_generator.generate_title(
                ticket_number=ticket_number,
                branch_name=branch_name,
                user_intent=user_intent,
            )

        # Find related PRs from history (skipped in dry-run)
        related_prs_context = ""
        if not dry_run and owner and repo_name:
            with console.status("[bold cyan]Checking PR history for related PRs...[/bold cyan]"):
                related_prs_context = pr_history.find_related_prs(
                    owner, repo_name, title, user_intent, llm_client
                )

        # Generate description with regeneration loop
        feedback_history = []
        max_iterations = 5  # Prevent infinite loops
        iteration = 0

        while iteration < max_iterations:
            iteration += 1

            # Generate or regenerate description
            if feedback_history:
                console.print(f"\n[cyan]Regenerating description (attempt {iteration})...[/cyan]")
                with console.status("[bold green]Regenerating with your feedback...[/bold green]"):
                    description = pr_generator.generate_description(
                        user_intent=user_intent,
                        base_branch=cfg.default_base_branch,
                        feedback_history=feedback_history,
                        related_prs_context=related_prs_context,
                    )
            else:
                description = pr_generator.generate_description(
                    user_intent=user_intent,
                    base_branch=cfg.default_base_branch,
                    related_prs_context=related_prs_context,
                )

            # Display preview
            display_preview(title, description, cfg.default_base_branch)

            # Description approval checkpoint
            if Confirm.ask("Are you happy with the description?", default=True):
                # User approved - break out of loop
                break
            else:
                # User rejected - collect feedback
                console.print("\n[yellow]Let's improve the description.[/yellow]")
                feedback = Prompt.ask(
                    "What would you like to change? (or type 'exit' to quit)",
                    default=""
                )

                if feedback.lower() in ['exit', 'quit', 'cancel', '']:
                    console.print("[yellow]Description regeneration cancelled. Exiting.[/yellow]")
                    sys.exit(0)

                feedback_history.append(feedback)

                # Check if we've hit max iterations
                if iteration >= max_iterations:
                    console.print(f"[yellow]Reached maximum regeneration attempts ({max_iterations}). Using current version.[/yellow]")
                    break

        # Dry run mode - exit here
        if dry_run:
            console.print("[yellow]Dry run mode - PR not created[/yellow]")
            sys.exit(0)

        # Confirm creation
        if not Confirm.ask("Create this pull request?", default=True):
            console.print("[yellow]PR creation cancelled.[/yellow]")
            sys.exit(0)

        # Check if branch is pushed to remote
        console.print()
        if not github_ops.check_remote_branch_exists(branch_name):
            console.print("[yellow]Branch not pushed to remote yet.[/yellow]")
            if Confirm.ask("Push branch now?", default=True):
                with console.status("[bold green]Pushing branch...[/bold green]"):
                    github_ops.push_current_branch()
                console.print("[green]✓ Branch pushed successfully[/green]")
            else:
                console.print("[red]Cannot create PR without pushing branch first.[/red]")
                sys.exit(1)

        # Create PR
        console.print()
        with console.status("[bold green]Creating pull request...[/bold green]"):
            pr_url = github_ops.create_pull_request(
                title=title,
                body=description,
                base=cfg.default_base_branch,
                draft=cfg.draft_pr,
                web=cfg.open_in_browser,
            )

        # Save PR to history
        if owner and repo_name:
            try:
                pr_number = int(pr_url.rstrip("/").split("/")[-1])  # save_pr never raises internally
            except (ValueError, IndexError):
                console.print("[yellow]Warning: could not save PR to history[/yellow]")
            else:
                pr_history.save_pr(owner, repo_name, pr_number, title, description)

        # Success!
        console.print()
        console.print("[bold green]✓ Pull request created successfully![/bold green]")
        console.print(f"[blue]URL:[/blue] {pr_url}")

    except PRAgentError as e:
        console.print(f"\n[red]Error:[/red] {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled by user.[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(f"\n[red]Unexpected error:[/red] {e}")
        if "--debug" in sys.argv:
            raise
        sys.exit(1)


@cli.command()
def init_config():
    """Create a default configuration file."""
    try:
        config_path = Config.create_default_config_file()
        console.print(f"[green]✓ Created default config file at:[/green] {config_path}")
        console.print()
        console.print("[dim]Edit this file to customize pr-agent settings.[/dim]")
    except Exception as e:
        console.print(f"[red]Failed to create config file:[/red] {e}")
        sys.exit(1)


def main():
    """Main entry point for CLI."""
    cli()


if __name__ == "__main__":
    main()
