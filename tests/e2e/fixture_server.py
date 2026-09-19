"""Isolated browser tier: real routes/PostgreSQL; deterministic inference stub.

Never run against a database without the disposable marker. No scheduler, external
news, broker connection, or real model is started by this test-only entrypoint.
"""

import os
from pathlib import Path
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text, select
from cryptography.fernet import Fernet
from fastapi.staticfiles import StaticFiles

from src import config

TEST_URL = os.environ["TEST_DATABASE_URL"]
config.settings = config.Settings(
    _env_file=None,
    DATABASE_URL=TEST_URL,
    environment="production",
    allowed_ips="127.0.0.1/32",
    trust_proxy_headers=False,
    auth_username="fixture-browser-a",
    auth_password_hash="fixture-unusable-bootstrap",
    auth_session_secret=secrets.token_urlsafe(32),
    auth_cookie_secure=False,
    broker_credentials_key=Fernet.generate_key().decode(),
    autonomous_scans_enabled=False,
    reports_dir="/tmp/ia-browser-reports",
    live_trading_enabled=False,
)

from src.agent import clients  # noqa: E402


class DeterministicReadClient:
    async def stream_response(self, messages, system, max_tokens=None):
        from src.tools.dispatcher import dispatch_tool

        if "NO_TOOL_CALLING" in system:
            yield {
                "type": "final_answer",
                "text": "Synthetic report fixture. Base currency EUR. "
                "Realized and unrealized returns unavailable; no external execution is claimed.",
            }
            yield {"type": "done"}
            return
        name = "generate_report" if "report" in messages[-1]["content"].lower() else "get_portfolio_summary"
        arguments = {"period_start": "2026-09-01", "period_end": "2026-09-07"} if name == "generate_report" else {}
        yield {"type": "tool_call", "name": name, "input": arguments, "id": "fixture-read"}
        result = await dispatch_tool(name, arguments)
        yield {"type": "tool_result", "name": name, "result": result, "id": "fixture-read"}
        yield {"type": "final_answer", "text": "Synthetic browser test evidence " + result}
        yield {"type": "done"}


clients.create_llm_client = lambda: DeterministicReadClient()

from src.web.auth import hash_password  # noqa: E402
from src.db.models import User  # noqa: E402

# Only external evidence collection is stubbed in this tier. Real renderer,
# persistence, authorization and downloads run through application code.
from src.scheduler import reporter  # noqa: E402
from src.web.routes import router  # noqa: E402
from src.db.database import engine, async_session, create_all_tables  # noqa: E402


async def fixture_report_context(period_start, period_end):
    return {
        "period": {"start": period_start, "end": period_end},
        "fixture": True,
        "base_currency": "EUR",
        "as_of": "2026-09-08T00:00:00Z",
        "portfolio": {"available": False, "reason": "No external broker in browser fixture"},
        "internal_trade_audit": [],
        "simulations": [],
        "market_overview": {},
    }


reporter._collect_report_context = fixture_report_context


def fixture_history(symbols, start, end, base_currency):
    from decimal import Decimal
    from datetime import UTC, datetime, timedelta

    from src.research.replay import Bar

    opened = datetime(2024, 1, 29, 8, tzinfo=UTC)
    return {
        symbol: [
            Bar(
                symbol,
                opened + timedelta(days=i),
                opened + timedelta(days=i, hours=8),
                Decimal(price),
                Decimal(price),
                Decimal(100000),
                base_currency,
                Decimal(1),
                opened + timedelta(days=i),
            )
            for i, price in enumerate([100, 110, 120, 130, 200])
        ]
        for symbol in symbols
    }, {"fixture": True, "limitations": ["Synthetic source bars; no provider connection"]}


from src.tools import simulator  # noqa: E402

simulator._download = fixture_history


@asynccontextmanager
async def lifespan(app):
    async with engine.connect() as connection:
        name = await connection.scalar(text("SELECT current_database()"))
        token = await connection.scalar(text("SELECT token FROM public.ia_disposable_marker"))
        if not name.startswith("test_") or token != os.environ["TEST_DATABASE_DISPOSABLE_TOKEN"]:
            raise RuntimeError("Refusing a database not marked for disposable tests")
    await create_all_tables()
    async with async_session.begin() as session:
        for username in os.environ["BROWSER_FIXTURE_USERS"].split(","):
            if not await session.scalar(select(User.id).where(User.username == username)):
                session.add(
                    User(
                        username=username,
                        password_hash=hash_password("fixture-browser-password"),
                        is_active=True,
                    )
                )
    yield
    await engine.dispose()


app = FastAPI(lifespan=lifespan)
app.include_router(router)
app.mount("/static", StaticFiles(directory=Path("src/web/static")), name="static")

# Broker evidence browser coverage uses real persistence and a synthetic worker.
# Even accidental calls through other IBKR reads cannot open a socket in this tier.
from src.execution import broker_monitor  # noqa: E402
from src.tools.brokers import ibkr  # noqa: E402


def deny_fixture_broker_connection(*args, **kwargs):
    raise RuntimeError("EXTERNAL_BROKER_FORBIDDEN_IN_BROWSER_FIXTURE")


def fixture_broker_observations(account):
    from datetime import UTC, datetime, timedelta

    from src.execution.broker_observations import OBSERVATION

    assert account.config["broker_account_id"] == "SYNTHETIC-BROWSER-ONLY"
    stamp = datetime.now(UTC) - timedelta(seconds=1)
    common = dict(actual_account=account.config["broker_account_id"], event_id="browser.fixture.1", observed_at=stamp)
    events = [
        dict(
            common,
            kind="execution",
            con_id=123,
            client_id=77,
            order_id=1,
            permanent_id=9,
            side="BOT",
            quantity="0.004",
            price="100",
            currency="EUR",
            executed_at=stamp,
        ),
        dict(common, kind="commission", amount="0.01", currency="EUR"),
        dict(
            common,
            kind="balance_snapshot",
            event_id="browser.balance.1",
            balances=dict(
                request_started_at=stamp - timedelta(seconds=1),
                positions=[
                    dict(con_id=123, currency="EUR", security_type="STK", quantity="0.004", average_cost_reported="100")
                ],
                cash=[dict(currency="EUR", amount="999.59", source_tag="CashBalance")],
                position_request_complete=True,
                cash_request_complete=True,
            ),
        ),
    ]
    return dict(
        observations=[OBSERVATION.validate_python(item) for item in events],
        status="observed",
        request_finished=True,
        failures=[],
        late_commissions_complete=False,
        coverage="synthetic_browser_fixture",
        execution_authority="none",
    )


ibkr._connection = deny_fixture_broker_connection
broker_monitor.collect_ibkr_observations = fixture_broker_observations
