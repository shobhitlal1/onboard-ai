"""Business rules. No model call can decide or override workflow status."""

from collections.abc import Mapping
from typing import Literal

DocumentType = Literal[
    "Identity Verification", "Tax Form", "Corporate Registration", "Beneficial Ownership"
]
Status = Literal["INCOMPLETE", "READY_FOR_REVIEW"]
REQUIRED_DOCUMENTS: tuple[DocumentType, ...] = (
    "Identity Verification", "Tax Form", "Corporate Registration", "Beneficial Ownership"
)


def missing_documents(documents: Mapping[str, bool]) -> list[DocumentType]:
    return [name for name in REQUIRED_DOCUMENTS if documents.get(name) is not True]


def determine_status(documents: Mapping[str, bool]) -> Status:
    return "INCOMPLETE" if missing_documents(documents) else "READY_FOR_REVIEW"
