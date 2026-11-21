"""Vocabulary consistency: Python enums, DDL CHECK lists and labels stay in sync."""

from __future__ import annotations

import re

import pytest

from app.enums import (
    LOST_REASON_LABELS,
    MEETING_TYPE_LABELS,
    ORIGIN_LABELS,
    OUTCOME_LABELS,
    STAGE_LABELS,
    STAGE_ORDER,
    LostReason,
    MeetingType,
    Origin,
    Outcome,
    Stage,
)
from tests.test_db_schema import constraint_definitions

VOCABULARIES = [
    (Origin, "opportunity", "ck_opportunity_origin"),
    (Stage, "opportunity", "ck_opportunity_stage"),
    (Outcome, "opportunity", "ck_opportunity_outcome"),
    (LostReason, "opportunity", "ck_opportunity_lost_reason"),
    (MeetingType, "opportunity_meeting", "ck_opportunity_meeting_type"),
    (Stage, "opportunity_stage_log", "ck_opportunity_stage_log_from"),
    (Stage, "opportunity_stage_log", "ck_opportunity_stage_log_to"),
]


@pytest.mark.parametrize(("enum_cls", "table", "constraint"), VOCABULARIES)
def test_every_enum_value_is_allowed_by_ddl(engine, enum_cls, table, constraint):
    definition = constraint_definitions(engine, table)[constraint]
    for member in enum_cls:
        assert f"'{member.value}'" in definition, f"{table}.{constraint} 缺少 {member.value}"


@pytest.mark.parametrize(("enum_cls", "table", "constraint"), VOCABULARIES)
def test_ddl_allows_nothing_beyond_the_enum(engine, enum_cls, table, constraint):
    """PostgreSQL rewrites ``IN (...)`` into ``= ANY (ARRAY[...])``; compare literals."""

    definition = constraint_definitions(engine, table)[constraint]
    literals = set(re.findall(r"'([a-z][a-z0-9_]*)'", definition))
    assert literals == {member.value for member in enum_cls}


def test_labels_cover_every_member():
    for enum_cls, labels in (
        (Origin, ORIGIN_LABELS),
        (Stage, STAGE_LABELS),
        (Outcome, OUTCOME_LABELS),
        (MeetingType, MEETING_TYPE_LABELS),
        (LostReason, LOST_REASON_LABELS),
    ):
        assert set(labels) == set(enum_cls)


def test_stage_order_covers_all_stages():
    assert set(STAGE_ORDER) == set(Stage)
    assert STAGE_ORDER[Stage.FOLLOW_UP] < STAGE_ORDER[Stage.MEETING]
    assert STAGE_ORDER[Stage.MEETING] < STAGE_ORDER[Stage.OUTCOME]
    assert STAGE_ORDER[Stage.OUTCOME] < STAGE_ORDER[Stage.CLOSED]
