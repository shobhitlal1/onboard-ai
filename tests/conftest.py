import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

import database
from api import app
from database import Base, get_session, make_engine
from llm_service import SAMPLE_NOTE


@pytest.fixture
def test_engine(tmp_path, monkeypatch):
    monkeypatch.setenv("MOCK_LLM", "true")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setattr(database, "engine", engine)
    yield engine
    engine.dispose()


@pytest.fixture
def http(test_engine):
    sessions = sessionmaker(bind=test_engine)

    def override_session():
        with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def created(http):
    response = http.post("/clients/from-note", json={"note": SAMPLE_NOTE})
    assert response.status_code == 201
    return response.json()
