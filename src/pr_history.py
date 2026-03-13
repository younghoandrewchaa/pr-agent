"""
PR history module.

Stores history of created PRs per repository and uses AI to detect
associations between a new PR and previous ones.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

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
    except (OSError, json.JSONDecodeError):
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
