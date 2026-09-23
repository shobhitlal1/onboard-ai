from types import SimpleNamespace

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

import llm_service
from llm_service import SAMPLE_NOTE
from models import Client


def test_health_initializes_three_tables(http, test_engine):
    assert http.get("/health").json() == {"status": "ok", "llm_mode": "mock"}
    assert set(inspect(test_engine).get_table_names()) == {"clients", "documents", "workflow_events"}


def test_creation_list_detail_and_sqlite_persistence(http, created, test_engine):
    assert created["status"] == "INCOMPLETE"
    assert created["summary_source"] == "mock"
    assert "Tax Form" in created["summary"]
    assert len(created["documents"]) == 4
    assert http.get("/clients").json()[0]["id"] == created["id"]
    assert http.get(f"/clients/{created['id']}").json()["company_name"] == "Alpha Capital LLC"
    with Session(test_engine) as session:
        saved = session.scalar(select(Client))
        assert saved.company_name == "Alpha Capital LLC"
        assert len(saved.documents) == 4
        assert len(saved.events) == 3


def test_unknown_client_returns_404(http):
    for path in ["/clients/999", "/clients/999/events"]:
        assert http.get(path).status_code == 404
    assert http.post("/clients/999/documents", json={"document_type": "Tax Form"}).status_code == 404


def test_invalid_requests_return_422(http, created):
    for body in [{}, {"note": " " * 30}, {"note": "x" * 10001}, {"note": SAMPLE_NOTE, "status": "READY_FOR_REVIEW"}]:
        assert http.post("/clients/from-note", json=body).status_code == 422
    assert http.post(f"/clients/{created['id']}/documents", json={"document_type": "Passport"}).status_code == 422


def test_unknown_mock_note_is_not_silently_replaced(http):
    response = http.post("/clients/from-note", json={"note": "An unknown company with no supplied account information."})
    assert response.status_code == 422
    assert "three provided sample notes" in response.json()["detail"]
    assert http.get("/clients").json() == []


def test_malformed_model_response_does_not_save_client(http, monkeypatch):
    monkeypatch.setattr(llm_service, "mock_extraction", lambda _: {"company_name": "Broken"})
    assert http.post("/clients/from-note", json={"note": SAMPLE_NOTE}).status_code == 502
    assert http.get("/clients").json() == []


def test_openai_mode_without_key_has_clear_error(http, monkeypatch):
    monkeypatch.setenv("MOCK_LLM", "false")
    response = http.post("/clients/from-note", json={"note": SAMPLE_NOTE})
    assert response.status_code == 502
    assert "OPENAI_API_KEY" in response.json()["detail"]
    assert http.get("/clients").json() == []


def test_real_adapter_calls_structured_output_and_handles_refusal(http, monkeypatch):
    extraction = llm_service.extract_client(SAMPLE_NOTE)
    calls = []

    class FakeOpenAI:
        responses = None

        def __init__(self):
            self.responses = self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def parse(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(output_parsed=extraction, status="completed")

        def create(self, **kwargs):
            return SimpleNamespace(output_text="Collect Tax Form and Beneficial Ownership.", status="completed")

    monkeypatch.setenv("MOCK_LLM", "false")
    monkeypatch.setattr(llm_service, "openai_client", FakeOpenAI)
    response = http.post("/clients/from-note", json={"note": SAMPLE_NOTE})
    assert response.status_code == 201
    assert response.json()["summary_source"] == "openai"
    assert calls[0]["text_format"] is llm_service.ClientExtraction
    assert calls[0]["store"] is False
    monkeypatch.setattr(FakeOpenAI, "parse", lambda self, **kwargs: SimpleNamespace(output_parsed=None, status="completed"))
    assert http.post("/clients/from-note", json={"note": SAMPLE_NOTE}).status_code == 502
    assert len(http.get("/clients").json()) == 1


def test_summary_failure_uses_deterministic_fallback(monkeypatch):
    monkeypatch.setenv("MOCK_LLM", "false")

    def unavailable():
        raise llm_service.LLMServiceError("Service unavailable")

    monkeypatch.setattr(llm_service, "openai_client", unavailable)
    summary, source = llm_service.summarize_missing(["Tax Form"])
    assert source == "rules"
    assert "Tax Form" in summary
