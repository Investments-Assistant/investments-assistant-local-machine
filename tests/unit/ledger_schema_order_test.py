"""The account ledger shares the execution identity sequence on fresh databases."""

from sqlalchemy import create_mock_engine

from src.execution.models import Base


def test_shared_identity_sequence_owner_precedes_ledger_and_drops_last():
    statements = []
    engine = create_mock_engine(
        "postgresql://", lambda sql, *args, **kwargs: statements.append(str(sql.compile(dialect=engine.dialect)))
    )
    Base.metadata.create_all(engine, checkfirst=False)
    execution = next(i for i, sql in enumerate(statements) if "CREATE TABLE execution_events (" in sql)
    ledger = next(i for i, sql in enumerate(statements) if "CREATE TABLE account_ledger_events (" in sql)
    assert execution < ledger
    assert "GENERATED ALWAYS AS IDENTITY" in statements[execution]
    assert "nextval('execution_events_ledger_sequence_seq')" in statements[ledger]

    statements.clear()
    Base.metadata.drop_all(engine, checkfirst=False)
    execution = next(i for i, sql in enumerate(statements) if "DROP TABLE execution_events" in sql)
    ledger = next(i for i, sql in enumerate(statements) if "DROP TABLE account_ledger_events" in sql)
    assert ledger < execution
