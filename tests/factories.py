"""Fictional object builders; no real company, person or event data is used."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models import Opportunity, OpportunityMeeting, OpportunityStageLog


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()


def opportunity_values(**overrides: Any) -> dict[str, Any]:
    """A valid ``ai_match`` opportunity payload, overridable field by field."""

    values: dict[str, Any] = {
        "org_id": new_uuid(),
        "site_id": new_uuid(),
        "party_a_company_id": new_uuid(),
        "party_b_company_id": new_uuid(),
        "origin": "ai_match",
        "match_id": new_uuid(),
        "owner_staff_id": new_uuid(),
        "created_by": new_uuid(),
        "contributors": [],
    }
    values.update(overrides)
    return values


def make_opportunity(session: Session, **overrides: Any) -> Opportunity:
    """Insert an opportunity through the ORM only (no service validation)."""

    opportunity = Opportunity(id=new_uuid(), **opportunity_values(**overrides))
    session.add(opportunity)
    session.flush()
    return opportunity


def make_meeting(
    session: Session, opportunity: Opportunity, **overrides: Any
) -> OpportunityMeeting:
    values: dict[str, Any] = {
        "org_id": opportunity.org_id,
        "site_id": opportunity.site_id,
        "opportunity_id": opportunity.id,
        "meeting_type": "one_on_one",
        "meeting_at": datetime.now(UTC),
        "participants": [{"role": "party_a", "company_id": str(opportunity.party_a_company_id)}],
    }
    values.update(overrides)
    meeting = OpportunityMeeting(id=new_uuid(), **values)
    session.add(meeting)
    session.flush()
    return meeting


def make_stage_log(
    session: Session, opportunity: Opportunity, **overrides: Any
) -> OpportunityStageLog:
    values: dict[str, Any] = {
        "org_id": opportunity.org_id,
        "site_id": opportunity.site_id,
        "opportunity_id": opportunity.id,
        "from_stage": None,
        "to_stage": "follow_up",
    }
    values.update(overrides)
    log = OpportunityStageLog(id=new_uuid(), **values)
    session.add(log)
    session.flush()
    return log
