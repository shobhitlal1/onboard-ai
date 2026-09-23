import json

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

import workflow
from llm_service import SAMPLE_NOTE, SAMPLE_NOTES, extract_client
from models import Client


def test_document_updates_transition_once_and_emit_webhook(http, created):
    path = f"/clients/{created['id']}"
    first = http.post(f"{path}/documents", json={"document_type": "Tax Form"})
    assert first.status_code == 200
    assert first.json()["status"] == "INCOMPLETE"
    assert first.json()["missing_documents"] == ["Beneficial Ownership"]
    second = http.post(f"{path}/documents", json={"document_type": "Beneficial Ownership"})
    assert second.json()["status"] == "READY_FOR_REVIEW"
    assert second.json()["missing_documents"] == []
    events = http.get(f"{path}/events").json()
    types = [event["event_type"] for event in events]
    assert types == ["CLIENT_CREATED", "AI_EXTRACTION_COMPLETED", "VALIDATION_COMPLETED",
                     "DOCUMENT_RECEIVED", "VALIDATION_COMPLETED", "DOCUMENT_RECEIVED",
                     "VALIDATION_COMPLETED", "STATUS_CHANGED", "WEBHOOK_TRIGGERED"]
    assert json.loads(events[-1]["description"]) == {
        "event": "client.ready_for_review", "client_id": created["id"], "company_name": "Alpha Capital LLC"
    }
    assert all(event["created_at"].endswith("Z") for event in events)
    http.post(f"{path}/documents", json={"document_type": "Beneficial Ownership"})
    assert http.get(f"{path}/events").json() == events


def test_initially_complete_client_triggers_one_handoff(http):
    note = list(SAMPLE_NOTES.values())[1]
    created = http.post("/clients/from-note", json={"note": note}).json()
    assert created["status"] == "READY_FOR_REVIEW"
    events = http.get(f"/clients/{created['id']}/events").json()
    assert sum(event["event_type"] == "WEBHOOK_TRIGGERED" for event in events) == 1


def test_incomplete_client_does_not_trigger_webhook(http, created):
    events = http.get(f"/clients/{created['id']}/events").json()
    assert len(events) == 3
    assert not any(event["event_type"] == "WEBHOOK_TRIGGERED" for event in events)


def test_event_failure_rolls_back_client_and_documents(http, test_engine, monkeypatch):
    def failed_event(*args):
        raise RuntimeError("Simulated database failure")

    monkeypatch.setattr(workflow, "log_event", failed_event)
    with Session(test_engine) as session:
        with pytest.raises(RuntimeError):
            workflow.create_client(session, extract_client(SAMPLE_NOTE), "mock")
    with Session(test_engine) as fresh_session:
        assert fresh_session.scalar(select(Client)) is None
