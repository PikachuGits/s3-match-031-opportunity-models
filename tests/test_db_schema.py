"""Physical schema assertions: columns, types, defaults, indexes, FKs, CHECKs."""

from __future__ import annotations

import pytest
from sqlalchemy import inspect, text


def constraint_definitions(engine, table: str) -> dict[str, str]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT conname, pg_get_constraintdef(oid) "
                "FROM pg_constraint WHERE conrelid = to_regclass(:table) AND contype = 'c'"
            ),
            {"table": table},
        ).all()
    return {name: definition for name, definition in rows}


@pytest.fixture(scope="module")
def inspector(engine):
    return inspect(engine)


def test_all_three_tables_exist(inspector):
    assert set(inspector.get_table_names()) >= {
        "opportunity",
        "opportunity_meeting",
        "opportunity_stage_log",
    }


def test_opportunity_columns_and_types(inspector):
    columns = {column["name"]: column for column in inspector.get_columns("opportunity")}
    expected_types = {
        "id": "UUID",
        "org_id": "UUID",
        "site_id": "UUID",
        "created_at": "TIMESTAMP",
        "created_by": "UUID",
        "updated_at": "TIMESTAMP",
        "deleted_at": "TIMESTAMP",
        "source_item_id": "UUID",
        "match_id": "UUID",
        "connect_request_id": "UUID",
        "party_a_company_id": "UUID",
        "party_b_company_id": "UUID",
        "origin": "VARCHAR(20)",
        "event_id": "UUID",
        "owner_staff_id": "UUID",
        "stage": "VARCHAR(20)",
        "stage_entered_at": "TIMESTAMP",
        "first_contacted_at": "TIMESTAMP",
        "party_a_confirmed_at": "TIMESTAMP",
        "party_b_confirmed_at": "TIMESTAMP",
        "outcome": "VARCHAR(15)",
        "lost_reason": "VARCHAR(30)",
        "deal_cents": "BIGINT",
        "feedback_a": "SMALLINT",
        "feedback_b": "SMALLINT",
        "closed_at": "TIMESTAMP",
        "contributors": "ARRAY",
    }
    assert set(columns) == set(expected_types)
    for name, expected in expected_types.items():
        assert str(columns[name]["type"]).startswith(expected), name


@pytest.mark.parametrize(
    "column",
    [
        "org_id",
        "site_id",
        "party_a_company_id",
        "party_b_company_id",
        "origin",
        "owner_staff_id",
        "stage",
        "stage_entered_at",
        "contributors",
    ],
)
def test_opportunity_required_columns(inspector, column):
    columns = {c["name"]: c for c in inspector.get_columns("opportunity")}
    assert columns[column]["nullable"] is False


@pytest.mark.parametrize(
    "column",
    [
        "source_item_id",
        "match_id",
        "connect_request_id",
        "event_id",
        "created_by",
        "deleted_at",
        "first_contacted_at",
        "party_a_confirmed_at",
        "party_b_confirmed_at",
        "outcome",
        "lost_reason",
        "deal_cents",
        "feedback_a",
        "feedback_b",
        "closed_at",
    ],
)
def test_opportunity_optional_columns(inspector, column):
    columns = {c["name"]: c for c in inspector.get_columns("opportunity")}
    assert columns[column]["nullable"] is True


def test_stage_defaults_to_follow_up(inspector):
    columns = {c["name"]: c for c in inspector.get_columns("opportunity")}
    assert "follow_up" in (columns["stage"]["default"] or "")


def test_contributors_defaults_to_empty_array(inspector):
    columns = {c["name"]: c for c in inspector.get_columns("opportunity")}
    assert "uuid[]" in (columns["contributors"]["default"] or "")


def test_indexes(inspector):
    opportunity_indexes = {index["name"] for index in inspector.get_indexes("opportunity")}
    assert {
        "ix_opportunity_org_site",
        "ix_opportunity_party_a",
        "ix_opportunity_party_b",
        "ix_opportunity_owner_staff",
        "ix_opportunity_stage",
        "ix_opportunity_created_at",
    } <= opportunity_indexes

    meeting_indexes = {index["name"] for index in inspector.get_indexes("opportunity_meeting")}
    assert "ix_opportunity_meeting_opportunity" in meeting_indexes

    log_indexes = {index["name"] for index in inspector.get_indexes("opportunity_stage_log")}
    assert "ix_opportunity_stage_log_opportunity" in log_indexes


@pytest.mark.parametrize(
    ("table", "constraint"),
    [
        ("opportunity", "ck_opportunity_party_distinct"),
        ("opportunity", "ck_opportunity_deal_cents_nonneg"),
        ("opportunity", "ck_opportunity_origin"),
        ("opportunity", "ck_opportunity_stage"),
        ("opportunity", "ck_opportunity_outcome"),
        ("opportunity", "ck_opportunity_lost_reason"),
        ("opportunity", "ck_opportunity_feedback_a_range"),
        ("opportunity", "ck_opportunity_feedback_b_range"),
        ("opportunity_meeting", "ck_opportunity_meeting_type"),
        ("opportunity_meeting", "ck_opportunity_meeting_participants_array"),
        ("opportunity_stage_log", "ck_opportunity_stage_log_from"),
        ("opportunity_stage_log", "ck_opportunity_stage_log_to"),
    ],
)
def test_check_constraints(engine, table, constraint):
    assert constraint in constraint_definitions(engine, table)


def test_foreign_keys_cascade(inspector):
    meeting_fks = inspector.get_foreign_keys("opportunity_meeting")
    assert any(
        fk["referred_table"] == "opportunity"
        and fk["constrained_columns"] == ["opportunity_id"]
        and fk.get("options", {}).get("ondelete") == "CASCADE"
        for fk in meeting_fks
    )

    log_fks = inspector.get_foreign_keys("opportunity_stage_log")
    assert any(
        fk["referred_table"] == "opportunity"
        and fk["constrained_columns"] == ["opportunity_id"]
        and fk.get("options", {}).get("ondelete") == "CASCADE"
        for fk in log_fks
    )


def test_meeting_participants_is_jsonb(inspector):
    columns = {c["name"]: c for c in inspector.get_columns("opportunity_meeting")}
    assert str(columns["participants"]["type"]) == "JSONB"
    assert "[]" in (columns["participants"]["default"] or "")
