"""Preserve exact UTF-8 login IDs while bounding their unique index keys."""

from alembic import op
import sqlalchemy as sa

revision = "0019_flexible_credentials"
down_revision = "0018_job_lease_clock"
branch_labels = None
depends_on = None


def upgrade():
    # Existing text and password hashes are unchanged. A digest collision fails
    # closed at the unique index; application lookups also require exact text.
    op.alter_column("users", "username", existing_type=sa.String(128), type_=sa.Text(), nullable=False)
    op.add_column("users", sa.Column("username_key", sa.LargeBinary(32), nullable=True))
    op.execute("UPDATE users SET username_key = sha256(convert_to(username, 'UTF8'))")
    op.alter_column("users", "username_key", existing_type=sa.LargeBinary(32), nullable=False)
    op.drop_index("ix_users_username", table_name="users")
    op.create_index("ix_users_username_key", "users", ["username_key"], unique=True)
    op.create_check_constraint("ck_users_username_key_length", "users", "octet_length(username_key) = 32")
    # The trigger is authoritative for INSERTs, username changes, and attempts
    # to overwrite just the key. No pgcrypto extension or external dependency.
    op.execute("""CREATE FUNCTION ia_set_username_key() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $$
        BEGIN
            NEW.username_key := sha256(convert_to(NEW.username, 'UTF8'));
            RETURN NEW;
        END;
        $$""")
    op.execute("""CREATE TRIGGER users_username_key
        BEFORE INSERT OR UPDATE OF username, username_key ON users
        FOR EACH ROW EXECUTE FUNCTION ia_set_username_key()""")


def downgrade():
    raise RuntimeError("Credential rollback requires reviewed backup; long login IDs must never be truncated")
