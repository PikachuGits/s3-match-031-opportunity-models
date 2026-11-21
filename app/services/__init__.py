"""Domain services for the matching opportunity module."""

from __future__ import annotations

from app.services.opportunities import (
    OpportunityValidationError,
    add_contributor,
    advance_stage,
    close_opportunity,
    create_opportunity,
    record_meeting,
    record_outcome,
    stage_history,
)

__all__ = [
    "OpportunityValidationError",
    "add_contributor",
    "advance_stage",
    "close_opportunity",
    "create_opportunity",
    "record_meeting",
    "record_outcome",
    "stage_history",
]
