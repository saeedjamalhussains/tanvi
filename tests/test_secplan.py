import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from secplan import providers, server
from secplan.baseline import CATALOG, assess
from secplan.models import OrgProfile
from secplan.prompts import build_plan_prompt

EXAMPLE = json.loads((Path(__file__).parent.parent / "examples" / "saas-startup.json").read_text())


@pytest.fixture
def client():
    return TestClient(server.app)


def test_empty_profile_scores_zero_with_all_gaps():
    result = assess(OrgProfile())
    assert result["maturity_score"] == 0
    assert result["tier"] == 1
    assert len(result["gaps"]) == len(CATALOG)


def test_full_profile_scores_100():
    result = assess(OrgProfile(controls={c.id: True for c in CATALOG}))
    assert result["maturity_score"] == 100
    assert result["tier"] == 4
    assert result["gaps"] == []


def test_context_raises_gap_priority():
    plain = {g["id"]: g for g in assess(OrgProfile())["gaps"]}
    ot = {g["id"]: g for g in assess(OrgProfile(infrastructure=["OT / ICS"]))["gaps"]}
    assert ot["network_segmentation"]["priority"] > plain["network_segmentation"]["priority"]


def test_gaps_sorted_by_priority():
    gaps = assess(OrgProfile.model_validate(EXAMPLE))["gaps"]
    assert [g["priority"] for g in gaps] == sorted((g["priority"] for g in gaps), reverse=True)


def test_prompt_contains_profile_and_timeframe():
    profile = OrgProfile.model_validate(EXAMPLE)
    prompt = build_plan_prompt(profile, assess(profile))
    assert "Example SaaS Co" in prompt
    assert "Months 4-12" in prompt
    assert "<baseline_assessment>" in prompt


def test_providers_endpoint_hides_keys(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-value")
    body = client.get("/api/providers").json()
    assert "sk-secret-value" not in json.dumps(body)
    openai = next(p for p in body["providers"] if p["id"] == "openai")
    assert openai["key_in_env"] is True


def test_baseline_endpoint(client):
    res = client.post("/api/baseline", json=EXAMPLE)
    assert res.status_code == 200
    assert 0 < res.json()["maturity_score"] < 100


def test_plan_missing_key_is_clean_400(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    res = client.post("/api/plan", json={"profile": EXAMPLE, "provider": "anthropic"})
    assert res.status_code == 400
    assert "API key" in res.json()["detail"]


def test_plan_streams_and_passes_key_and_followup(client, monkeypatch):
    seen = {}

    def fake_stream(provider_id, *, system, messages, model, api_key, base_url):
        seen.update(provider=provider_id, messages=messages, api_key=api_key, model=model)
        yield "# Security Strategy"
        yield ": Example"

    monkeypatch.setattr(server, "stream_chat", fake_stream)
    res = client.post(
        "/api/plan",
        headers={"X-API-Key": "test-key"},
        json={"profile": EXAMPLE, "provider": "groq", "model": "m",
              "conversation": [{"role": "assistant", "content": "plan"}],
              "followup": "Make it cheaper"},
    )
    assert res.status_code == 200
    assert res.text == "# Security Strategy: Example"
    assert seen["api_key"] == "test-key"
    assert [m["role"] for m in seen["messages"]] == ["user", "assistant", "user"]
    assert seen["messages"][-1]["content"] == "Make it cheaper"


def test_followup_required_when_continuing(client):
    res = client.post("/api/plan", json={
        "profile": EXAMPLE, "conversation": [{"role": "assistant", "content": "x"}]})
    assert res.status_code == 400


def test_custom_base_url_can_be_disabled(client, monkeypatch):
    monkeypatch.setenv("SECPLAN_ALLOW_CUSTOM_BASE_URL", "0")
    res = client.post("/api/plan", json={
        "profile": EXAMPLE, "provider": "custom", "model": "x", "base_url": "http://10.0.0.1/v1"})
    assert res.status_code == 400


def test_unknown_provider_rejected():
    with pytest.raises(providers.ProviderError):
        list(providers.stream_chat("nope", system="s", messages=[]))


def test_env_key_used_when_none_supplied(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "from-env")
    spec = providers.get_provider("groq")
    assert providers.resolve_key(spec, None) == "from-env"
    assert providers.resolve_key(spec, " pasted ") == "pasted"


def test_index_served(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "SecPlan" in res.text
