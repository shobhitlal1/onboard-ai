"""Six REST endpoints. Model calls live in llm_service, rules in validation."""

from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload

import llm_service
from database import get_session, init_db
from models import Client, WorkflowEvent
from schemas import ClientResponse, DocumentRequest, EventResponse, HealthResponse, NoteRequest
from validation import missing_documents
from workflow import create_client, receive_document


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="OnboardAI", version="1.0.0", lifespan=lifespan,
              description="Fictional client onboarding demonstration. No real KYC, AML, compliance, or financial decisions.")
DatabaseSession = Annotated[Session, Depends(get_session)]


def client_response(client: Client, summary: str | None = None, source: str = "rules") -> ClientResponse:
    missing = missing_documents({doc.document_type: doc.received for doc in client.documents})
    return ClientResponse(
        id=client.id, company_name=client.company_name, contact_name=client.contact_name,
        account_type=client.account_type, state=client.state,
        expected_monthly_volume=client.expected_monthly_volume, status=client.status,
        created_at=client.created_at, documents=client.documents, missing_documents=missing,
        summary=summary or llm_service.rule_summary(missing), summary_source=source,
    )


@app.get("/health", response_model=HealthResponse)
def health(session: DatabaseSession):
    session.execute(text("SELECT 1"))
    return {"status": "ok", "llm_mode": llm_service.llm_mode()}


@app.post("/clients/from-note", response_model=ClientResponse, status_code=201)
def from_note(request: NoteRequest, session: DatabaseSession):
    try:
        extraction = llm_service.extract_client(request.note)
    except llm_service.UnsupportedMockNote as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except llm_service.LLMServiceError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    missing = missing_documents(extraction.documents.model_dump(by_alias=True))
    summary, source = llm_service.summarize_missing(missing)
    client = create_client(session, extraction, llm_service.llm_mode())
    return client_response(client, summary, source)


@app.get("/clients", response_model=list[ClientResponse])
def list_clients(session: DatabaseSession):
    clients = session.scalars(select(Client).options(selectinload(Client.documents)).order_by(Client.id.desc()))
    return [client_response(client) for client in clients]


@app.get("/clients/{client_id}", response_model=ClientResponse)
def get_client(client_id: int, session: DatabaseSession):
    client = session.get(Client, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found.")
    return client_response(client)


@app.post("/clients/{client_id}/documents", response_model=ClientResponse)
def mark_document(client_id: int, request: DocumentRequest, session: DatabaseSession):
    client = receive_document(session, client_id, request.document_type)
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found.")
    return client_response(client)


@app.get("/clients/{client_id}/events", response_model=list[EventResponse])
def list_events(client_id: int, session: DatabaseSession):
    if session.get(Client, client_id) is None:
        raise HTTPException(status_code=404, detail="Client not found.")
    return session.scalars(select(WorkflowEvent).where(WorkflowEvent.client_id == client_id).order_by(WorkflowEvent.id)).all()
