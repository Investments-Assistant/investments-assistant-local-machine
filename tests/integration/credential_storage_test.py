"""Exact credentials in real disposable PostgreSQL, including migrated writers."""

import json
import uuid
import hashlib
from pathlib import Path
from contextlib import asynccontextmanager
import importlib.util

import pytest
from sqlalchemy import text, select
from sqlalchemy.exc import IntegrityError
from alembic.migration import MigrationContext
from alembic.operations import Operations

from src.db.models import User
from src.security.identifiers import username_key

pytestmark = pytest.mark.integration


def long_username():
    # Diverse text stays larger than a btree entry even after TOAST compression.
    return "  " + "".join(hashlib.sha256(str(i).encode()).hexdigest() + "áçã €|" for i in range(512)) + "  "


@asynccontextmanager
async def migrated_users(engine):
    """Apply the new migration to the frozen pre0019 users table, then rollback."""
    async with engine.connect() as connection:
        outer = await connection.begin()
        schema = "credential_" + uuid.uuid4().hex
        try:
            await connection.execute(text(f"CREATE SCHEMA {schema}"))
            await connection.execute(text(f"SET LOCAL search_path TO {schema}"))
            reviewed = json.loads(Path("migrations/reviewed_schema.json").read_text())
            statements = [statement for statement in reviewed if (
                statement.lstrip().startswith("CREATE TABLE users (")
                or statement.startswith("CREATE UNIQUE INDEX ix_users_username ")
            )]
            assert len(statements) == 2
            for statement in statements:
                await connection.execute(text(statement))
            await connection.execute(text("""INSERT INTO users
                (id,username,password_hash,display_name,description,preferences,trading_mode,
                 is_active,created_at,updated_at)
                VALUES ('legacy-owner',:username,'retained-scrypt-hash','Original display','',
                        '{}','recommend',true,now(),now())"""), {"username": '  Luís | "€$#  '})

            def upgrade(sync_connection):
                spec = importlib.util.spec_from_file_location(
                    "credential_upgrade", "migrations/versions/0019_flexible_credentials.py",
                )
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                with Operations.context(MigrationContext.configure(sync_connection)):
                    module.upgrade()

            await connection.run_sync(upgrade)
            yield connection, schema
        finally:
            await outer.rollback()


async def raw_insert(connection, identifier, username, key=None):
    if key is None:
        columns, value = "", ""
    else:
        columns, value = ",username_key", ",:key"
    await connection.execute(text(f"""INSERT INTO users
        (id,username,password_hash,display_name,description,preferences,trading_mode,
         is_active,created_at,updated_at{columns})
        VALUES (:id,:username,'fixture-non-login-hash','','','{{}}','recommend',true,now(),now(){value})"""),
        {"id": identifier, "username": username, "key": key})


async def test_credential_upgrade_preserves_existing_identity_and_hash(integration_engine):
    async with migrated_users(integration_engine) as (connection, schema):
        row = (await connection.execute(text("""SELECT id,username,password_hash,display_name,username_key
            FROM users WHERE id='legacy-owner'"""))).one()
        assert tuple(row[:4]) == ('legacy-owner', '  Luís | "€$#  ', 'retained-scrypt-hash', 'Original display')
        assert row.username_key == username_key(row.username)
        assert await connection.scalar(text("""SELECT data_type FROM information_schema.columns
            WHERE table_schema=:schema AND table_name='users' AND column_name='username'"""),
            {"schema": schema}) == "text"
        indexes = (await connection.execute(text("""SELECT indexname,indexdef FROM pg_indexes
            WHERE schemaname=:schema AND tablename='users'"""), {"schema": schema})).all()
        assert "ix_users_username" not in {row.indexname for row in indexes}
        assert any(row.indexname == "ix_users_username_key" and "UNIQUE INDEX" in row.indexdef for row in indexes)


async def test_migrated_trigger_handles_long_raw_inserts_updates_and_key_tampering(integration_engine):
    async with migrated_users(integration_engine) as (connection, _schema):
        original = long_username()
        assert len(original.encode("utf-8")) > 2704
        await raw_insert(connection, "long-owner", original, key=b"x" * 32)
        row = (await connection.execute(text("SELECT username,username_key FROM users WHERE id='long-owner'"))).one()
        assert row.username == original and row.username_key == username_key(original)
        changed = original + " Ç"
        await connection.execute(text("UPDATE users SET username=:username WHERE id='long-owner'"),
                                 {"username": changed})
        selected = await connection.scalar(text("SELECT username_key FROM users WHERE id='long-owner'"))
        assert selected == username_key(changed)
        await connection.execute(text("UPDATE users SET username_key=:key WHERE id='long-owner'"), {"key": b"z" * 32})
        selected = await connection.scalar(text("SELECT username_key FROM users WHERE id='long-owner'"))
        assert selected == username_key(changed)
        assert await connection.scalar(select(User.id).where(User.username_matches(changed))) == "long-owner"
        assert await connection.scalar(select(User.id).where(User.username_matches(original))) is None


async def test_migrated_identifiers_remain_exact_and_duplicate_writes_fail_closed(integration_engine):
    async with migrated_users(integration_engine) as (connection, _schema):
        names = ["Luís", "luís", " Luís", "Luís ", "Lui\u0301s", "a|b", "a b", "a'b\"$#€\\"]
        for index, name in enumerate(names):
            await raw_insert(connection, "distinct-" + str(index), name)
            selected = await connection.scalar(select(User.id).where(User.username_matches(name)))
            assert selected == "distinct-" + str(index)
        for statement, values in [
            (None, None),
            ("UPDATE users SET username=:name WHERE id='distinct-1'", {"name": names[0]}),
        ]:
            with pytest.raises(IntegrityError):
                async with connection.begin_nested():
                    if statement is None:
                        await raw_insert(connection, "duplicate-owner", names[0], key=b"q" * 32)
                    else:
                        await connection.execute(text(statement), values)
        assert await connection.scalar(select(User.id).where(User.username_matches(names[1]))) == "distinct-1"
        await connection.execute(text("""INSERT INTO users
            (id,username,password_hash,display_name,description,preferences,trading_mode,
             is_active,created_at,updated_at)
            VALUES ('replayed-owner',:name,'fixture','','','{}','recommend',true,now(),now())
            ON CONFLICT (username_key) DO NOTHING"""), {"name": names[0]})
        assert await connection.scalar(text("SELECT count(*) FROM users WHERE id='replayed-owner'")) == 0


async def test_metadata_orm_defaults_updates_and_unrelated_revocation_preserve_keys(db_session, monkeypatch):
    original = long_username()
    owner = User(
        id=str(uuid.uuid4()), username=original, password_hash="fixture-non-login", username_key=b"x" * 32,
    )
    db_session.add(owner)
    await db_session.flush()
    assert owner.username_key == username_key(original)
    changed = original + " | ç "
    owner.username = changed
    await db_session.flush()
    assert owner.username_key == username_key(changed)
    owner.is_active = False
    await db_session.flush()
    assert owner.username_key == username_key(changed)
    owner.username_key = b"z" * 32
    await db_session.flush()
    assert owner.username_key == username_key(changed)
    # Even a faulty/colliding candidate digest cannot authenticate different text.
    monkeypatch.setattr("src.db.models.derive_username_key", lambda _value: owner.username_key)
    assert await db_session.scalar(select(User.id).where(User.username_matches("another login"))) is None
