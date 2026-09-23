# OnboardAI: interview study guide

## A short explanation you can give out loud

“I built a small fictional onboarding workflow in Python. A Streamlit UI sends a note to FastAPI. A dedicated service extracts structured fields using either offline fixtures or the OpenAI API, and Pydantic checks their shape and types. SQLAlchemy stores a client and four document records in SQLite. Python checks which documents are missing and decides the status. Each important action is recorded in an event table. When the checklist becomes complete, the app records a simulated webhook payload for a downstream review team.”

Be precise: mock mode does not call an AI model, the tests do not prove model accuracy, and received flags do not prove identity or compliance. This is not a real financial or regulatory system.

## What each file does

| File | Responsibility |
| --- | --- |
| `app.py` | Displays three Streamlit pages and sends HTTP requests to FastAPI. It never opens SQLite. |
| `api.py` | Defines six routes, translates expected errors into HTTP responses, and assembles response objects. |
| `database.py` | Creates the SQLite engine, enables foreign keys, initializes tables, and provides request-scoped sessions. |
| `models.py` | Defines the three database tables, columns, and relationships. |
| `schemas.py` | Defines the data shapes and validation rules for requests, extracted facts, and responses. |
| `validation.py` | Contains the required-document list and two pure Python checklist functions. |
| `workflow.py` | Writes client/document records, recalculates status, logs events, and simulates webhook handoffs. |
| `llm_service.py` | Contains the mock notes, fixture lookup, OpenAI adapter, and summary fallback. |
| `tests/conftest.py` | Gives every API test an isolated temporary database with mock mode enabled. |
| `tests/test_validation.py` | Checks rules, extraction types, and the default mock behavior. |
| `tests/test_api.py` | Exercises the HTTP routes and model-service error cases. |
| `tests/test_workflow.py` | Checks document completion, events, webhook behavior, and transaction rollback. |
| `requirements.txt` | Pins the direct packages used by the project. |
| `.env.example` | Shows configuration names; it is documentation, not automatically loaded. |
| `.streamlit/config.toml` | Sets the interface theme and disables Streamlit usage statistics. |
| `.gitignore` | Keeps local databases, environments, caches, and credentials out of Git. |

There is intentionally no application framework layered on top of these files.

## Follow one note through the application

1. You paste a note into Streamlit and click **Process Client**.
2. Streamlit sends JSON to `POST /clients/from-note`. The note stays in memory while processing; the app does not store the original text in SQLite.
3. FastAPI uses `NoteRequest` to reject missing, very short, or excessively long notes.
4. The route calls `llm_service.extract_client`. The default mode looks up a known example. Real mode calls OpenAI with `ClientExtraction` as the structured-output schema.
5. Pydantic checks the result. A string such as `"false"` is not accepted as a document boolean. Missing document keys, extra fields, blank company names, and negative or infinite volumes are rejected.
6. Python computes missing documents. The summary service receives only that list; it does not select the status.
7. `create_client` inserts a client, four related documents, and workflow events in one transaction.
8. `recalculate_status` uses the document flags to choose `INCOMPLETE` or `READY_FOR_REVIEW`. It records validation and any status change.
9. FastAPI serializes the response to JSON. Streamlit displays the fields and initial summary.

The route coordinates these operations, but neither SQL business logic nor model API calls are embedded directly in the route.

## What FastAPI does here

FastAPI runs behind Uvicorn on port 8000. A route maps an HTTP method and URL to a Python function. For example, posting a document type to `/clients/1/documents` invokes the document-receipt function for client 1. Dependencies give each request its own SQLAlchemy session and close it afterward.

Pydantic models tell FastAPI how to validate inputs and serialize responses. FastAPI also generates the interactive `/docs` page from the same definitions. HTTP 201 means created, 404 means the client does not exist, 422 means invalid input, and 502 means the model service could not supply valid extraction data.

The frontend calls the API over HTTP using HTTPX. This makes the REST boundary real and lets another client, such as curl or the generated docs page, use the same backend.

## What SQLite and SQLAlchemy do

SQLite is a relational database stored in a local file (`onboard.db`). It persists when the Python process stops. There is no separate database server to install. SQLAlchemy maps Python objects to SQL rows and manages transactions.

- One `Client` owns many `Document` rows.
- One `Client` owns many `WorkflowEvent` rows.
- A `client_id` foreign key connects each document or event to its owner.
- A unique constraint on `(client_id, document_type)` prevents two copies of the same document type for one client.

`session.flush()` sends pending SQL writes without committing, making the new client's ID available for related records. `commit()` makes a transaction durable. A rollback undoes all pending changes if an event or document write fails. The context manager in `create_client` commits on success and rolls back on exceptions.

The document-update function takes a SQLite write lock before reading the current state. That keeps two simultaneous updates from independently emitting the same readiness transition. It is a small local-app technique, not a distributed event-delivery guarantee.

All timestamps are created in UTC. SQLite returns naive datetime objects; response models attach UTC explicitly before JSON serialization. The UI labels times as UTC.

## Why AI does not decide status

A model can help interpret prose, but the checklist rule is unambiguous. Python checks that all four flags are exactly true. A missing or false flag means incomplete. The extraction schema does not even accept a `status` field, so a model cannot return an authoritative status.

This separation makes the rule reproducible and easy to test. It does **not** eliminate model mistakes: an incorrectly extracted receipt flag still affects the rule's input. A human must verify that input before any real use. Here, all data is fictional.

Optional contact, state, or volume can be unknown (`null`). They are displayed as “Not provided.” Status only measures the four specified documents, not the overall quality of the client record.

## How the LLM adapter works

Real mode calls `client.responses.parse(..., text_format=ClientExtraction)`. The SDK requests a structured object using the Pydantic schema. The service rejects refused or incomplete responses and validates the parsed result again at the application boundary.

Another Responses call writes a short summary using the list of missing documents. If that call fails, a Python sentence template describes the same list, labeled `rules`. The initial summary is returned to the UI, not stored in an extra table or column. Later reads and document updates return a fresh rule-based summary so an old AI sentence cannot misdescribe the current checklist.

Mock mode recognizes three complete sample notes, allowing whitespace and capitalization changes. This deliberately limited behavior is visible in the UI and produces a clear error for unsupported notes. The same schemas, database logic, and workflow rules still run. Tests replace the real SDK client with a fake object to exercise adapter behavior without making paid network calls.

## What Pydantic does—and does not do

Pydantic is a data-validation library. A schema defines names, allowed values, and types. `StrictBool` accepts actual booleans rather than loosely converting arbitrary text. `extra="forbid"` prevents unrecognized fields, including a model-supplied status. Constraints reject negative or non-finite volumes.

Validating an object proves it fits the expected shape. It does not prove John Smith exists, a document was actually received, or the source note is accurate. Distinguishing structural validation from factual verification is a useful interview point.

## What the simulated webhook demonstrates

A webhook normally sends an HTTP request to another system when something happens. This project only records the payload as a `WEBHOOK_TRIGGERED` event. No network request is sent.

When the previous status is `INCOMPLETE` and the new status is `READY_FOR_REVIEW`, the event contains `client.ready_for_review`, the client ID, and company name. The record demonstrates event-driven handoff without introducing a queue, external receiver, credentials, or retries.

An already-complete intake begins as incomplete within its creation transaction, transitions to ready, and records a handoff immediately. Repeating a receipt update does nothing because that document is already marked received. This is idempotency: repeating the same action has the same final effect.

## How the tests give confidence

Run `python -m pytest -v`. There are 18 tests, not a benchmark or accuracy evaluation. Temporary SQLite files prevent tests from modifying demo data. The fixture overrides FastAPI's database dependency so every request uses the test database.

Rule tests try each missing item. API tests create clients and read them back from a separate database session, check validation errors, and simulate model failures. Workflow tests complete documents step by step, inspect exact event order and webhook JSON, repeat updates, and deliberately fail an event write to verify rollback. A fake OpenAI client checks the structured-output adapter without credentials.

Browser verification complements the automated suite: create a sample, view the extracted details, mark documents received, inspect the timeline, and revisit the dashboard. A separate server restart confirms persistence on disk. A passing test suite is evidence for those behaviors, not a promise of production readiness.

## Useful interview tradeoffs

- SQLite avoids infrastructure; this demo does not need a hosted database.
- Streamlit keeps the whole project in Python; detailed frontend customization is intentionally limited.
- An event table explains workflow changes without adding a messaging system.
- Receipt flags keep scope small; handling actual files would introduce storage, privacy, and verification work.
- AI output validation and deterministic rules solve different problems. Both are needed, but neither proves facts.
- There is no authentication or client editing because the scope is a local fictional-data demonstration.

Study the source and run the sample yourself before using the resume bullets. Be ready to explain the mock/real distinction and the untested live-provider path honestly.
