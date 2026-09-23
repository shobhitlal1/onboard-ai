import pytest
from pydantic import ValidationError

from llm_service import SAMPLE_NOTE, extract_client, mock_extraction
from schemas import ClientExtraction
from validation import REQUIRED_DOCUMENTS, determine_status, missing_documents


def test_missing_documents_are_reported_in_checklist_order():
    assert missing_documents({"Identity Verification": True, "Corporate Registration": True}) == ["Tax Form", "Beneficial Ownership"]


def test_incomplete_status_requires_every_document():
    for absent in REQUIRED_DOCUMENTS:
        docs = {name: name != absent for name in REQUIRED_DOCUMENTS}
        assert determine_status(docs) == "INCOMPLETE"
    assert determine_status({}) == "INCOMPLETE"


def test_complete_checklist_is_ready_for_review():
    assert determine_status(dict.fromkeys(REQUIRED_DOCUMENTS, True)) == "READY_FOR_REVIEW"


def test_mock_extraction_never_needs_credentials(monkeypatch):
    monkeypatch.delenv("MOCK_LLM", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = extract_client(SAMPLE_NOTE)
    assert result.company_name == "Alpha Capital LLC"
    assert result.expected_monthly_volume == 2000000
    assert result.documents.tax_form is False


def test_pydantic_rejects_malformed_extractions():
    original = mock_extraction(SAMPLE_NOTE)
    for changes in [{"expected_monthly_volume": -1}, {"expected_monthly_volume": float("inf")},
                    {"company_name": " "}, {"status": "READY_FOR_REVIEW"},
                    {"documents": {**original["documents"], "Tax Form": "false"}},
                    {"documents": {"Tax Form": True}}]:
        with pytest.raises(ValidationError):
            ClientExtraction.model_validate({**original, **changes})
