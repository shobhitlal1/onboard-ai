"""Small orchestration functions; each write commits as one transaction."""

import json

from sqlalchemy import text
from sqlalchemy.orm import Session

from models import Client, Document, WorkflowEvent
from schemas import ClientExtraction
from validation import determine_status, missing_documents


def log_event(session: Session, client: Client, event_type: str, description: str) -> None:
    session.add(WorkflowEvent(client_id=client.id, event_type=event_type, description=description))


def recalculate_status(session: Session, client: Client) -> None:
    documents = {doc.document_type: doc.received for doc in client.documents}
    previous = client.status
    client.status = determine_status(documents)
    missing = missing_documents(documents)
    log_event(session, client, "VALIDATION_COMPLETED", f"Status: {client.status}. Missing documents: {', '.join(missing) or 'none'}.")
    if previous != client.status:
        log_event(session, client, "STATUS_CHANGED", f"{previous} → {client.status}")
        if previous == "INCOMPLETE" and client.status == "READY_FOR_REVIEW":
            payload = {
                "event": "client.ready_for_review",
                "client_id": client.id,
                "company_name": client.company_name,
            }
            # This is a local event only: no outgoing HTTP request is made.
            log_event(session, client, "WEBHOOK_TRIGGERED", json.dumps(payload))


def create_client(session: Session, extraction: ClientExtraction, mode: str) -> Client:
    with session.begin():
        client = Client(**extraction.model_dump(exclude={"documents"}), status="INCOMPLETE")
        session.add(client)
        session.flush()  # Assign the ID before inserting related rows.
        client.documents = [
            Document(document_type=name, received=received)
            for name, received in extraction.documents.model_dump(by_alias=True).items()
        ]
        log_event(session, client, "CLIENT_CREATED", "Client created from an onboarding note.")
        log_event(session, client, "AI_EXTRACTION_COMPLETED", f"Structured extraction validated with Pydantic. Source: {mode}.")
        recalculate_status(session, client)
    return client


def receive_document(session: Session, client_id: int, document_type: str) -> Client | None:
    # Serialize SQLite writers before reading status, avoiding duplicate transition
    # events if two requests arrive at once. This is sufficient for this local MVP.
    session.execute(text("BEGIN IMMEDIATE"))
    try:
        client = session.get(Client, client_id)
        if client is None:
            session.rollback()
            return None
        document = next(doc for doc in client.documents if doc.document_type == document_type)
        if not document.received:
            document.received = True
            log_event(session, client, "DOCUMENT_RECEIVED", f"{document_type} received.")
            recalculate_status(session, client)
        session.commit()
        return client
    except Exception:
        session.rollback()
        raise
