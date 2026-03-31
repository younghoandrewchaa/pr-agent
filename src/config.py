"""
Configuration management module.

Handles loading and merging configuration from multiple sources:
1. Command line arguments (highest priority)
2. Config file (~/.config/pr-agent/config.yaml)
3. Environment variables
4. Defaults (lowest priority)
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any

import yaml

from src.exceptions import ConfigError


@dataclass
class Config:
    """Configuration for pr-agent."""

    # Model settings
    model: str = "gemini-2.5-flash"
    copilot_api_base: str = "https://api.githubcopilot.com"
    copilot_api_key: Optional[str] = None
    copilot_timeout: int = 60
    copilot_token_dir: Optional[str] = None

    # Provider settings
    provider: str = "vertex"

    # Vertex AI settings
    vertex_project: Optional[str] = None
    vertex_location: Optional[str] = None

    # Git settings
    default_base_branch: str = "main"
    ticket_pattern: str = r"STAR-(\d+)"

    # LLM settings
    max_diff_tokens: int = 8000
    temperature: float = 0.7

    # PR creation settings
    draft_pr: bool = False
    open_in_browser: bool = False

    @classmethod
    def from_file(cls, config_path: Optional[Path] = None) -> "Config":
        """
        Load configuration from YAML file.

        Args:
            config_path: Path to config file. If None, uses default location.

        Returns:
            Config instance with values from file.

        Raises:
            ConfigError: If config file is invalid.
        """
        if config_path is None:
            config_path = cls.get_default_config_path()

        if not config_path.exists():
            # Return default config if file doesn't exist
            return cls()

        try:
            with open(config_path, "r") as f:
                data = yaml.safe_load(f) or {}

            return cls.from_dict(data)

        except yaml.YAMLError as e:
            raise ConfigError(f"Invalid YAML in config file: {e}")
        except Exception as e:
            raise ConfigError(f"Failed to load config file: {e}")

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Config":
        """
        Create Config from dictionary.

        Args:
            data: Configuration dictionary

        Returns:
            Config instance.
        """
        # Filter out unknown keys and nested structures
        valid_keys = {
            "model",
            "copilot_api_base",
            "copilot_api_key",
            "copilot_timeout",
            "default_base_branch",
            "ticket_pattern",
            "max_diff_tokens",
            "temperature",
            "draft_pr",
            "open_in_browser",
            "provider",
            "vertex_project",
            "vertex_location",
        }

        filtered_data = {k: v for k, v in data.items() if k in valid_keys}

        return cls(**filtered_data)

    @classmethod
    def from_env(cls) -> "Config":
        """
        Load configuration from environment variables.

        Environment variables should be prefixed with PR_AGENT_
        e.g., PR_AGENT_MODEL, PR_AGENT_BASE_BRANCH

        Returns:
            Config instance with values from environment.
        """
        config = cls()

        # Map environment variables to config attributes
        env_mapping = {
            "PR_AGENT_MODEL": "model",
            "PR_AGENT_COPILOT_API_BASE": "copilot_api_base",
            "PR_AGENT_COPILOT_KEY": "copilot_api_key",
            "PR_AGENT_COPILOT_TIMEOUT": "copilot_timeout",
            "PR_AGENT_COPILOT_TOKEN_DIR": "copilot_token_dir",
            "PR_AGENT_BASE_BRANCH": "default_base_branch",
            "PR_AGENT_TICKET_PATTERN": "ticket_pattern",
            "PR_AGENT_MAX_DIFF_TOKENS": "max_diff_tokens",
            "PR_AGENT_PROVIDER": "provider",
            "PR_AGENT_VERTEX_PROJECT": "vertex_project",
            "PR_AGENT_VERTEX_LOCATION": "vertex_location",
        }

        for env_var, attr_name in env_mapping.items():
            value = os.getenv(env_var)
            if value is not None:
                # Convert to appropriate type
                if attr_name in {"max_diff_tokens", "copilot_timeout"}:
                    value = int(value)
                setattr(config, attr_name, value)

        return config

    @staticmethod
    def get_default_config_path() -> Path:
        """
        Get default configuration file path.

        Returns:
            Path to ~/.config/pr-agent/config.yaml
        """
        config_dir = Path.home() / ".config" / "pr-agent"
        return config_dir / "config.yaml"

    @staticmethod
    def create_default_config_file(path: Optional[Path] = None) -> Path:
        """
        Create a default configuration file.

        Args:
            path: Where to create the file. If None, uses default location.

        Returns:
            Path to created config file.
        """
        if path is None:
            path = Config.get_default_config_path()

        # Create directory if it doesn't exist
        path.parent.mkdir(parents=True, exist_ok=True)

        default_config = {
            "model": "gemini-2.5-flash",
            "provider": "vertex",
            "copilot_api_base": "https://api.githubcopilot.com",
            "copilot_timeout": 60,
            "default_base_branch": "main",
            "ticket_pattern": "STAR-(\\d+)",
            "max_diff_tokens": 8000,
        }

        with open(path, "w") as f:
            yaml.dump(default_config, f, default_flow_style=False, sort_keys=False)

        return path

    def merge_with_cli_args(
        self,
        base_branch: Optional[str] = None,
        model: Optional[str] = None,
        draft: Optional[bool] = None,
        web: Optional[bool] = None,
        provider: Optional[str] = None,
    ) -> "Config":
        """
        Create new config with CLI arguments taking precedence.

        Args:
            base_branch: Base branch override
            model: Model name override
            draft: Draft PR flag
            web: Open in browser flag
            provider: LLM provider override

        Returns:
            New Config instance with merged values.
        """
        new_config = Config(
            model=model or self.model,
            copilot_api_base=self.copilot_api_base,
            copilot_api_key=self.copilot_api_key,
            copilot_timeout=self.copilot_timeout,
            copilot_token_dir=self.copilot_token_dir,
            default_base_branch=base_branch or self.default_base_branch,
            ticket_pattern=self.ticket_pattern,
            max_diff_tokens=self.max_diff_tokens,
            temperature=self.temperature,
            draft_pr=draft if draft is not None else self.draft_pr,
            open_in_browser=web if web is not None else self.open_in_browser,
            provider=provider or self.provider,
            vertex_project=self.vertex_project,
            vertex_location=self.vertex_location,
        )

        return new_config


def load_config(
    config_file: Optional[Path] = None,
    base_branch: Optional[str] = None,
    model: Optional[str] = None,
    draft: Optional[bool] = None,
    web: Optional[bool] = None,
    provider: Optional[str] = None,
) -> Config:
    """
    Load configuration with proper priority.

    Priority (highest to lowest):
    1. CLI arguments
    2. Config file
    3. Environment variables
    4. Defaults

    Args:
        config_file: Path to config file
        base_branch: CLI base branch override
        model: CLI model override
        draft: CLI draft flag
        web: CLI web flag
        provider: CLI provider override ("copilot" or "claude-code")

    Returns:
        Merged configuration.
    """
    # Start with environment variables
    config = Config.from_env()

    # Merge with config file if it exists
    if config_file or Config.get_default_config_path().exists():
        file_config = Config.from_file(config_file)
        # Merge: file config takes precedence over env
        for attr in [
            "model",
            "copilot_api_base",
            "copilot_api_key",
            "copilot_timeout",
            "copilot_token_dir",
            "default_base_branch",
            "ticket_pattern",
            "max_diff_tokens",
            "provider",
            "vertex_project",
            "vertex_location",
        ]:
            file_value = getattr(file_config, attr)
            # Only use file value if it's not the default
            default_value = getattr(Config(), attr)
            if file_value != default_value:
                setattr(config, attr, file_value)

    # Merge with CLI arguments (highest priority)
    config = config.merge_with_cli_args(
        base_branch=base_branch,
        model=model,
        draft=draft,
        web=web,
        provider=provider,
    )

    return config
