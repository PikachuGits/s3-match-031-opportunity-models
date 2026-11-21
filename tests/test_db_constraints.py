"""Database-level rejection tests (``IntegrityError``), independent of services."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Opportunity, OpportunityMeeting, OpportunityStageLog
from tests.factories import (
    make_meeting,
    make_opportunity,
    make_stage_log,
    new_uuid,
    opportunity_values,
)


def _expect_integrity_error(session, call):
    with pytest.raises(IntegrityError):
        call()
    session.rollback()


def test_party_a_and_party_b_must_differ(session):
    same = new_uuid()
    _expect_integrity_error(
        session,
        lambda: make_opportunity(session, party_a_company_id=same, party_b_company_id=same),
    )


def test_deal_cents_must_be_non_negative(session):
    _expect_integrity_error(session, lambda: make_opportunity(session, deal_cents=-1))


def test_deal_cents_zero_is_allowed(session):
    opportunity = make_opportunity(session, deal_cents=0)
    assert opportunity.deal_cents == 0


def test_deal_cents_accepts_large_integer(session):
    opportunity = make_opportunity(session, deal_cents=10**15)
    assert opportunity.deal_cents == 10**15


@pytest.mark.parametrize("stage", ["negotiating", "won", "", "FOLLOW_UP"])
def test_invalid_stage_rejected(session, stage):
    _expect_integrity_error(session, lambda: make_opportunity(session, stage=stage))


@pytest.mark.parametrize("outcome", ["won", "lost", "closed", "", "DEAL"])
def test_invalid_outcome_rejected(session, outcome):
    _expect_integrity_error(session, lambda: make_opportunity(session, outcome=outcome))


@pytest.mark.parametrize("origin", ["referral", "manual", "", "AI_MATCH"])
def test_invalid_origin_rejected(session, origin):
    _expect_integrity_error(session, lambda: make_opportunity(session, origin=origin))


@pytest.mark.parametrize("lost_reason", ["price", "too_expensive", ""])
def test_invalid_lost_reason_rejected(session, lost_reason):
    _expect_integrity_error(session, lambda: make_opportunity(session, lost_reason=lost_reason))


@pytest.mark.parametrize(
    ("field", "value"), [("feedback_a", 0), ("feedback_a", 6), ("feedback_b", 0), ("feedback_b", 6)]
)
def test_feedback_out_of_range_rejected(session, field, value):
    _expect_integrity_error(session, lambda: make_opportunity(session, **{field: value}))


@pytest.mark.parametrize("value", [1, 5])
def test_feedback_bounds_allowed(session, value):
    opportunity = make_opportunity(session, feedback_a=value, feedback_b=value)
    assert opportunity.feedback_a == value


def test_contributors_cannot_be_null(session):
    """Bypass the ORM default with a Core INSERT to reach the NOT NULL column."""

    values = {**opportunity_values(), "id": new_uuid(), "contributors": None}
    with pytest.raises(IntegrityError):
        session.execute(Opportunity.__table__.insert().values(**values))
        session.flush()
    session.rollback()


def test_meeting_type_must_be_known(session):
    opportunity = make_opportunity(session)
    _expect_integrity_error(
        session, lambda: make_meeting(session, opportunity, meeting_type="dinner")
    )


def test_meeting_participants_must_be_array(session):
    opportunity = make_opportunity(session)
    _expect_integrity_error(
        session,
        lambda: make_meeting(session, opportunity, participants={"role": "party_a"}),
    )


def test_stage_log_to_stage_must_be_known(session):
    opportunity = make_opportunity(session)
    _expect_integrity_error(
        session, lambda: make_stage_log(session, opportunity, to_stage="review")
    )


def test_stage_log_from_stage_must_be_known_or_null(session):
    opportunity = make_opportunity(session)
    _expect_integrity_error(
        session, lambda: make_stage_log(session, opportunity, from_stage="review")
    )


def test_stage_log_null_from_stage_is_allowed(session):
    opportunity = make_opportunity(session)
    log = make_stage_log(session, opportunity, from_stage=None, to_stage="follow_up")
    assert log.from_stage is None


def test_meeting_requires_existing_opportunity(session):
    orphan = uuid.uuid4()

    with pytest.raises(IntegrityError):
        session.add(
            OpportunityMeeting(
                id=new_uuid(),
                org_id=new_uuid(),
                site_id=new_uuid(),
                opportunity_id=orphan,
                meeting_type="salon",
                meeting_at=datetime.now(UTC),
                participants=[],
            )
        )
        session.flush()
    session.rollback()


def test_cascade_delete_removes_children(session):
    opportunity = make_opportunity(session)
    make_meeting(session, opportunity)
    make_stage_log(session, opportunity)
    opportunity_id = opportunity.id

    session.execute(
        Opportunity.__table__.delete().where(Opportunity.__table__.c.id == opportunity_id)
    )
    session.flush()

    assert session.query(OpportunityStageLog).filter_by(opportunity_id=opportunity_id).count() == 0
    assert session.query(OpportunityMeeting).filter_by(opportunity_id=opportunity_id).count() == 0
