"""Tests for config module — provider and claude_code_bin fields."""

from src.config import Config, load_config


class TestProviderConfig:

    def test_provider_default(self):
        config = Config()
        assert config.provider == "vertex"

    def test_model_default(self):
        config = Config()
        assert config.model == "gemini-2.5-flash"

    def test_provider_from_dict(self):
        config = Config.from_dict({"provider": "copilot"})
        assert config.provider == "copilot"

    def test_provider_from_dict_ignores_unknown_keys(self):
        config = Config.from_dict({"provider": "vertex", "unknown_key": "value"})
        assert config.provider == "vertex"

    def test_provider_from_env(self, monkeypatch):
        monkeypatch.setenv("PR_AGENT_PROVIDER", "copilot")
        config = Config.from_env()
        assert config.provider == "copilot"

    def test_provider_merge_with_cli_args(self):
        config = Config()
        merged = config.merge_with_cli_args(provider="copilot")
        assert merged.provider == "copilot"

    def test_provider_cli_arg_takes_precedence(self):
        config = Config(provider="copilot")
        merged = config.merge_with_cli_args(provider="vertex")
        assert merged.provider == "vertex"

    def test_provider_none_cli_arg_preserves_existing(self):
        config = Config(provider="copilot")
        merged = config.merge_with_cli_args(provider=None)
        assert merged.provider == "copilot"

    def test_load_config_provider_cli_arg(self):
        config = load_config(provider="copilot")
        assert config.provider == "copilot"

class TestVertexConfig:

    def test_vertex_fields_default_to_none(self):
        config = Config()
        assert config.vertex_project is None
        assert config.vertex_location is None

    def test_vertex_fields_from_dict(self):
        config = Config.from_dict({
            "vertex_project": "my-gcp-project",
            "vertex_location": "us-west1",
        })
        assert config.vertex_project == "my-gcp-project"
        assert config.vertex_location == "us-west1"

    def test_vertex_fields_from_dict_ignores_unknown_keys(self):
        config = Config.from_dict({"vertex_project": "proj", "bogus_key": "x"})
        assert config.vertex_project == "proj"

    def test_vertex_project_from_env(self, monkeypatch):
        monkeypatch.setenv("PR_AGENT_VERTEX_PROJECT", "env-project")
        monkeypatch.setenv("PR_AGENT_VERTEX_LOCATION", "europe-west4")
        config = Config.from_env()
        assert config.vertex_project == "env-project"
        assert config.vertex_location == "europe-west4"

    def test_vertex_fields_pass_through_merge(self):
        config = Config(vertex_project="proj", vertex_location="us-east1")
        merged = config.merge_with_cli_args()
        assert merged.vertex_project == "proj"
        assert merged.vertex_location == "us-east1"
