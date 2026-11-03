"""Rename the default output spec from its customer-named id to `standard.8col`.

Revision ID: 023
Revises: 022
Create Date: 2026-11-03

The shipped deliverable spec used to carry a customer's name in its id and
display name. The product is deployed to other customers now, so the id is
neutral. Every stored reference follows: the spec row itself, each supplier
profile's `output_spec_id`, and the profile-authoring sessions' column (and
its server default).
"""

import json

import sqlalchemy as sa
from alembic import op

revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None

OLD_ID = "temforce.standard"
NEW_ID = "standard.8col"
OLD_NAME = "TemForce Standard (8-column)"
NEW_NAME = "Standard (8-column)"


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _rename(old_id: str, new_id: str, old_name: str, new_name: str) -> None:
    bind = op.get_bind()
    tables = _tables()

    if "output_specs" in tables:
        rows = bind.execute(
            sa.text("SELECT spec_id, name, data FROM output_specs WHERE spec_id = :old"), {"old": old_id}
        ).fetchall()
        for spec_id, name, data in rows:
            payload = json.loads(data) if isinstance(data, str) else dict(data or {})
            payload["spec_id"] = new_id
            if payload.get("name") == old_name:
                payload["name"] = new_name
            bind.execute(
                sa.text(
                    "UPDATE output_specs SET spec_id = :new, name = :name, data = :data WHERE spec_id = :old"
                ),
                {
                    "new": new_id,
                    "name": new_name if name == old_name else name,
                    "data": json.dumps(payload),
                    "old": spec_id,
                },
            )

    if "supplier_profiles" in tables:
        rows = bind.execute(sa.text("SELECT profile_id, data FROM supplier_profiles")).fetchall()
        for profile_id, data in rows:
            payload = json.loads(data) if isinstance(data, str) else dict(data or {})
            if payload.get("output_spec_id") != old_id:
                continue
            payload["output_spec_id"] = new_id
            bind.execute(
                sa.text("UPDATE supplier_profiles SET data = :data WHERE profile_id = :pid"),
                {"data": json.dumps(payload), "pid": profile_id},
            )

    if "profile_authoring_sessions" in tables:
        bind.execute(
            sa.text("UPDATE profile_authoring_sessions SET output_spec_id = :new WHERE output_spec_id = :old"),
            {"new": new_id, "old": old_id},
        )
        op.alter_column(
            "profile_authoring_sessions",
            "output_spec_id",
            existing_type=sa.String(128),
            existing_nullable=False,
            server_default=new_id,
        )


def upgrade() -> None:
    _rename(OLD_ID, NEW_ID, OLD_NAME, NEW_NAME)


def downgrade() -> None:
    _rename(NEW_ID, OLD_ID, NEW_NAME, OLD_NAME)
