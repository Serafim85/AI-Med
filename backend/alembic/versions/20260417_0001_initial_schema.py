"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-04-17

Creates all MVP tables: users, appointment_sessions, transcripts, protocols,
diagnosis_suggestions, red_flags, treatment_plans, treatment_plan_items,
audit_log — plus Postgres ENUM types and required indexes.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# --- ENUM type definitions (Postgres native) --------------------------------
# We declare them with create_type=False on per-column usage and create/drop
# them explicitly so the downgrade is deterministic.
patient_sex_enum = postgresql.ENUM(
    "male", "female", "other", name="patient_sex", create_type=False
)
appointment_type_enum = postgresql.ENUM(
    "primary", "follow_up", name="appointment_type", create_type=False
)
session_status_enum = postgresql.ENUM(
    "draft", "recording", "analyzed", "confirmed", "closed",
    name="session_status", create_type=False,
)
speaker_enum = postgresql.ENUM(
    "doctor", "patient", "unknown", name="speaker", create_type=False
)
red_flag_severity_enum = postgresql.ENUM(
    "low", "medium", "high", name="red_flag_severity", create_type=False
)
treatment_item_kind_enum = postgresql.ENUM(
    "medication", "investigation", "non_drug", "follow_up",
    name="treatment_item_kind", create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Create enum types explicitly once.
    patient_sex_enum.create(bind, checkfirst=True)
    appointment_type_enum.create(bind, checkfirst=True)
    session_status_enum.create(bind, checkfirst=True)
    speaker_enum.create(bind, checkfirst=True)
    red_flag_severity_enum.create(bind, checkfirst=True)
    treatment_item_kind_enum.create(bind, checkfirst=True)

    # 2. users
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=False)

    # 3. appointment_sessions
    op.create_table(
        "appointment_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("doctor_id", sa.Uuid(), nullable=False),
        sa.Column("patient_full_name", sa.String(length=255), nullable=False),
        sa.Column("patient_age", sa.Integer(), nullable=False),
        sa.Column("patient_sex", patient_sex_enum, nullable=False),
        sa.Column("appointment_type", appointment_type_enum, nullable=False),
        sa.Column(
            "status",
            session_status_enum,
            nullable=False,
            server_default=sa.text("'draft'::session_status"),
        ),
        sa.Column("consent_given_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["doctor_id"], ["users.id"], name="fk_appointment_sessions_doctor_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_appointment_sessions_doctor_id",
        "appointment_sessions",
        ["doctor_id"],
    )

    # 4. transcripts
    op.create_table(
        "transcripts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("speaker", speaker_enum, nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("started_at_ms", sa.Integer(), nullable=True),
        sa.Column("ended_at_ms", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column(
            "edited_by_user",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["appointment_sessions.id"],
            name="fk_transcripts_session_id", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_transcripts_session_id", "transcripts", ["session_id"])

    # 5. protocols
    op.create_table(
        "protocols",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("complaints", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("anamnesis", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("examination", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("allergies", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("medications", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("final_diagnosis", sa.Text(), nullable=True),
        sa.Column("icd10_code", sa.String(length=32), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["appointment_sessions.id"],
            name="fk_protocols_session_id", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", name="uq_protocols_session_id"),
    )

    # 6. diagnosis_suggestions
    op.create_table(
        "diagnosis_suggestions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("icd10_code", sa.String(length=32), nullable=True),
        sa.Column("probability", sa.Float(), nullable=True),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("supporting_symptoms", sa.Text(), nullable=True),
        sa.Column("contradicting_symptoms", sa.Text(), nullable=True),
        sa.Column(
            "is_selected",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["appointment_sessions.id"],
            name="fk_diagnosis_suggestions_session_id", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_diagnosis_suggestions_session_id",
        "diagnosis_suggestions",
        ["session_id"],
    )

    # 7. red_flags
    op.create_table(
        "red_flags",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("severity", red_flag_severity_enum, nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("doctor_note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["appointment_sessions.id"],
            name="fk_red_flags_session_id", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_red_flags_session_id", "red_flags", ["session_id"])

    # 8. treatment_plans
    op.create_table(
        "treatment_plans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["appointment_sessions.id"],
            name="fk_treatment_plans_session_id", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", name="uq_treatment_plans_session_id"),
    )

    # 9. treatment_plan_items
    op.create_table(
        "treatment_plan_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("kind", treatment_item_kind_enum, nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("dosage", sa.String(length=255), nullable=True),
        sa.Column("duration", sa.String(length=255), nullable=True),
        sa.Column(
            "order_index",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "is_confirmed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"], ["treatment_plans.id"],
            name="fk_treatment_plan_items_plan_id", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_treatment_plan_items_plan_id",
        "treatment_plan_items",
        ["plan_id"],
    )

    # 10. audit_log
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"],
            name="fk_audit_log_user_id", ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["appointment_sessions.id"],
            name="fk_audit_log_session_id", ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    bind = op.get_bind()

    op.drop_table("audit_log")

    op.drop_index("ix_treatment_plan_items_plan_id", table_name="treatment_plan_items")
    op.drop_table("treatment_plan_items")
    op.drop_table("treatment_plans")

    op.drop_index("ix_red_flags_session_id", table_name="red_flags")
    op.drop_table("red_flags")

    op.drop_index("ix_diagnosis_suggestions_session_id", table_name="diagnosis_suggestions")
    op.drop_table("diagnosis_suggestions")

    op.drop_table("protocols")

    op.drop_index("ix_transcripts_session_id", table_name="transcripts")
    op.drop_table("transcripts")

    op.drop_index("ix_appointment_sessions_doctor_id", table_name="appointment_sessions")
    op.drop_table("appointment_sessions")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

    treatment_item_kind_enum.drop(bind, checkfirst=True)
    red_flag_severity_enum.drop(bind, checkfirst=True)
    speaker_enum.drop(bind, checkfirst=True)
    session_status_enum.drop(bind, checkfirst=True)
    appointment_type_enum.drop(bind, checkfirst=True)
    patient_sex_enum.drop(bind, checkfirst=True)
