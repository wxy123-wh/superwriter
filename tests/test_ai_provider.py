"""Tests for AI provider configuration and client functionality."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.ai import AIProviderClient, AIProviderConfig, AIProviderTestResult, ProviderValidationError


def test_provider_config_validation():
    """Test that provider configuration validation works correctly."""
    # Valid configuration
    config = AIProviderConfig(
        provider_id="test_provider",
        provider_name="openai",
        base_url="https://api.openai.com/v1",
        api_key="test-key-123",
        model_name="gpt-4o",
        temperature=0.7,
        max_tokens=4096,
        is_active=True,
    )
    config.validate()  # Should not raise

    # Invalid temperature
    with pytest.raises(ProviderValidationError):
        bad_config = AIProviderConfig(
            provider_id="test_provider",
            provider_name="openai",
            base_url="https://api.openai.com/v1",
            api_key="test-key-123",
            model_name="gpt-4o",
            temperature=3.0,  # Invalid: > 2
            max_tokens=4096,
        )
        bad_config.validate()

    # Missing required field
    with pytest.raises(ProviderValidationError):
        bad_config = AIProviderConfig(
            provider_id="test_provider",
            provider_name="",  # Invalid: empty
            base_url="https://api.openai.com/v1",
            api_key="test-key-123",
            model_name="gpt-4o",
        )
        bad_config.validate()


def test_provider_config_storage_roundtrip():
    """Test that provider config can be stored and retrieved correctly."""
    from core.runtime import CanonicalStorage
    import tempfile

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test.sqlite3"
        storage = CanonicalStorage(db_path)

        # Save a provider config
        provider_id = storage.save_provider_config(
            provider_name="openai",
            base_url="https://api.openai.com/v1",
            api_key="sk-test123",
            model_name="gpt-4o",
            temperature=0.8,
            max_tokens=2048,
            is_active=True,
            created_by="test",
        )

        assert provider_id.startswith("ai_")

        # Retrieve the config
        retrieved = storage.get_provider_config(provider_id)
        assert retrieved is not None
        assert retrieved["provider_name"] == "openai"
        assert retrieved["base_url"] == "https://api.openai.com/v1"
        assert retrieved["api_key"] == "sk-test123"
        assert retrieved["model_name"] == "gpt-4o"
        assert retrieved["temperature"] == 0.8
        assert retrieved["max_tokens"] == 2048
        assert retrieved["is_active"] is True

        # List all providers
        all_providers = storage.list_provider_configs()
        assert len(all_providers) == 1
        assert all_providers[0]["provider_id"] == provider_id

        # Update the config
        storage.save_provider_config(
            provider_id=provider_id,
            provider_name="openai",
            base_url="https://api.openai.com/v1",
            api_key="sk-updated",
            model_name="gpt-4o-mini",
            temperature=0.5,
            max_tokens=8192,
            is_active=True,
            created_by="test",
        )

        updated = storage.get_provider_config(provider_id)
        assert updated["api_key"] == "sk-updated"
        assert updated["model_name"] == "gpt-4o-mini"

        # Delete the config
        deleted = storage.delete_provider_config(provider_id)
        assert deleted is True

        # Verify it's gone
        assert storage.get_provider_config(provider_id) is None


def test_active_provider_selection():
    """Test that the active provider can be set and retrieved."""
    from core.runtime import CanonicalStorage
    import tempfile

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test.sqlite3"
        storage = CanonicalStorage(db_path)

        # Create multiple providers
        provider1 = storage.save_provider_config(
            provider_name="openai",
            base_url="https://api.openai.com/v1",
            api_key="sk-key1",
            model_name="gpt-4o",
            created_by="test",
        )

        provider2 = storage.save_provider_config(
            provider_name="local",
            base_url="http://localhost:11434/v1",
            api_key="test",
            model_name="llama3",
            created_by="test",
        )

        # Initially, no active provider is set (get_active_provider_config returns None)
        # But the last created one might be active depending on implementation

        # Set provider2 as active
        success = storage.set_active_provider(provider2)
        assert success is True

        # Check that provider2 is now active
        active = storage.get_active_provider_config()
        assert active is not None
        assert active["provider_id"] == provider2
        assert active["provider_name"] == "local"


def test_ai_provider_client_initialization():
    """Test that AI provider client can be initialized."""
    config = AIProviderConfig(
        provider_id="test_client",
        provider_name="openai",
        base_url="https://api.openai.com/v1",
        api_key="sk-test",
        model_name="gpt-4o",
    )

    client = AIProviderClient(config)
    assert client.config == config
    assert client.config.provider_id == "test_client"


def test_ai_provider_client_mock_generation(monkeypatch):
    """Test AI provider client generation with mocked API calls."""
    from unittest.mock import Mock, patch

    config = AIProviderConfig(
        provider_id="test_mock",
        provider_name="openai",
        base_url="https://api.openai.com/v1",
        api_key="sk-test",
        model_name="gpt-4o",
    )

    client = AIProviderClient(config)

    # Mock the OpenAI client
    with patch("core.ai.provider.OpenAI") as mock_openai:
        mock_client = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "Test response"
        mock_response.choices[0].message.content = "Test response"
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        result = client.generate([{"role": "user", "content": "Hello"}])
        assert result == "Test response"


def test_prompt_template_structure():
    """Test that prompt templates are properly structured."""
    from core.ai.prompts import (
        build_outline_to_plot_prompt,
        build_plot_to_event_prompt,
        build_event_to_scene_prompt,
        build_scene_to_chapter_prompt,
    )

    # Test outline to plot prompt
    outline = {
        "title": "Chapter 1",
        "summary": "The hero begins their journey",
    }
    novel = {"title": "Test Novel", "premise": "A test story"}
    skills = []

    messages = build_outline_to_plot_prompt(outline, novel, skills)
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "Chapter 1" in str(messages[1])

    # Test scene to chapter prompt
    scene = {
        "title": "The Harbor",
        "summary": "A character arrives at the harbor",
        "setting": "Daytime, busy harbor",
        "pov_character": "John",
        "beat_breakdown": ["Arrival", "Meeting"],
    }
    style_rules = [{"rule": "Write in first person present tense"}]
    scene_skills = []

    messages = build_scene_to_chapter_prompt(
        scene=scene,
        novel_context=novel,
        style_rules=style_rules,
        skills=scene_skills,
        canonical_facts=[],
    )
    assert len(messages) == 2
    assert "The Harbor" in str(messages[1])


def test_dialogue_intent_classification():
    """Test that dialogue processor can classify intents."""
    from core.ai.dialogue import DialogueProcessor, DialogueRequest, DialogueIntent

    # Mock service
    class MockService:
        def _get_active_ai_provider(self):
            return None  # No AI for this test

        def get_workspace_snapshot(self, request):
            return type("obj", (object,), {"canonical_objects": []})()

    processor = DialogueProcessor(MockService())

    # Test intent classification
    request = DialogueRequest(
        session_id="test_session",
        user_message="请帮我将这个大纲扩展为剧情",
        project_id="test_project",
        novel_id="test_novel",
        actor="user",
    )

    response = processor.process_turn(request)

    # Should classify as outline_to_plot intent
    assert response.intent in (DialogueIntent.OUTLINE_TO_PLOT, DialogueIntent.CHAT)
    assert len(response.response_text) > 0
    assert isinstance(response.suggested_actions, list)


def test_diagnosis_basic_analysis():
    """Test that basic diagnosis works without AI."""
    from core.ai.diagnosis import IntelligentDiagnoser, DiagnosisRequest
    from core.runtime import WorkspaceSnapshotResult, WorkspaceObjectSummary

    # Mock workspace with gaps
    mock_workspace = type("obj", (object,), {
        "canonical_objects": [
            WorkspaceObjectSummary(
                family="outline_node",
                object_id="out_1",
                current_revision_id="rev_1",
                current_revision_number=1,
                payload={"title": "Chapter 1"},
            )
        ],
        "derived_artifacts": [],
        "review_proposals": [],
    })()

    # Mock AI client (None for basic diagnosis)
    diagnoser = IntelligentDiagnoser(ai_client=None)

    request = DiagnosisRequest(
        project_id="test_project",
        novel_id="test_novel",
        workspace_snapshot=mock_workspace,
    )

    report = diagnoser.diagnose(request)

    # Should detect missing plot nodes
    assert report.overall_health_score < 100
    assert len(report.issues_found) > 0
    assert any("剧情" in issue.title for issue in report.issues_found)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
