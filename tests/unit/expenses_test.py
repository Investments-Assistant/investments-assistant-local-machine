"""Unit coverage for expense categorisation, import, and user scoping."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.web.auth import hash_password
from src.db.models import ExpenseTransaction


def _client() -> TestClient:
    from src.web.routes import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False)


def _settings():
    cfg = MagicMock()
    cfg.is_development = False
    cfg.is_production = True
    cfg.is_ip_allowed = MagicMock(return_value=True)
    cfg.trust_proxy_headers = False
    cfg.auth_username = "admin"
    cfg.auth_password_hash = hash_password("a-long-and-private-password")
    cfg.auth_session_secret = "test-session-secret"
    cfg.auth_session_ttl_minutes = 10
    cfg.auth_require_login = True
    cfg.auth_cookie_secure = False
    cfg.auth_allow_signup = True
    cfg.authentication_ready = True
    return cfg


def _user(cfg):
    user = MagicMock()
    user.id = "user-a"
    user.username = "admin"
    user.display_name = "Admin"
    user.password_hash = cfg.auth_password_hash
    user.is_active = True
    return user


def _db_session(*execute_results):
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.execute = AsyncMock(side_effect=list(execute_results))
    session.commit = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.mark.unit
class TestExpenseNormalisation:
    def test_maps_common_psd2_debit_and_categorises_food(self):
        from src.expenses.sync import normalise_transaction

        result = normalise_transaction(
            {
                "transactionId": "bank-1",
                "transactionAmount": {"amount": "-42.50", "currency": "EUR"},
                "bookingDate": "2026-08-10",
                "debtorName": "Pingo Doce",
                "remittanceInformationUnstructured": "Weekly shop",
            },
            "gocardless",
            "Main account",
        )

        assert result["external_id"] == "bank-1"
        assert result["amount"] == 42.5
        assert result["transaction_type"] == "expense"
        assert result["category"] == "food"
        assert result["subcategory"] == "groceries"

    def test_maps_positive_salary_as_income(self):
        from src.expenses.sync import normalise_transaction

        result = normalise_transaction(
            {
                "id": "salary-1",
                "amount": 2500,
                "currency": "EUR",
                "date": "2026-08-01",
                "direction": "credit",
            },
            "bank_feed",
        )

        assert result["transaction_type"] == "income"
        assert result["category"] == "income"


@pytest.mark.unit
class TestExpenseEndpoints:
    @pytest.fixture(autouse=True)
    def current_session_store(self):
        # Route/expense persistence is mocked here; account revocation has a real
        # PostgreSQL tier in sessions_test and a browser logout replay test.
        with patch("src.web.auth.validate_principal", new_callable=AsyncMock):
            yield

    def test_summary_is_scoped_to_authenticated_user(self):
        cfg = _settings()
        user = _user(cfg)
        login_result = MagicMock()
        login_result.scalar_one_or_none.return_value = user
        row = ExpenseTransaction(
            id="expense-1",
            user_id="user-a",
            provider="gocardless",
            external_id="tx-1",
            account_name="Main account",
            merchant="Galp",
            description="Fuel",
            amount=60.0,
            currency="EUR",
            transaction_type="expense",
            category="transport",
            subcategory="car fuel",
            occurred_at=datetime(2026, 8, 10, tzinfo=UTC),
            synced_at=datetime(2026, 8, 10, tzinfo=UTC),
        )
        expense_result = MagicMock()
        expense_result.scalars.return_value.all.return_value = [row]
        session = _db_session(login_result, expense_result)

        with (
            patch("src.web.routes.settings", cfg),
            patch("src.web.auth.config.settings", cfg),
            patch("src.web.routes.async_session", return_value=session),
            patch(
                "src.expenses.status.sync_clocks",
                new=AsyncMock(
                    return_value={
                        "last_received_at": "2026-08-10T00:00:00+00:00",
                        "provider_last_success_at": None,
                    }
                ),
            ),
        ):
            client = _client()
            assert (
                client.post(
                    "/api/auth/login",
                    json={"username": "admin", "password": "a-long-and-private-password"},
                ).status_code
                == 200
            )
            response = client.get("/api/expenses?period=year")

        assert response.status_code == 200
        data = response.json()
        assert data["total_expenses"] == 60.0
        assert data["category_totals"][0]["label"] == "Transport"
        query = str(session.execute.call_args_list[-1].args[0])
        assert "expense_transactions.user_id" in query

    def test_import_sets_authenticated_owner_and_is_idempotent_shape(self):
        cfg = _settings()
        user = _user(cfg)
        login_result = MagicMock()
        login_result.scalar_one_or_none.return_value = user
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = None
        session = _db_session(login_result, existing_result)

        with (
            patch("src.web.routes.settings", cfg),
            patch("src.web.auth.config.settings", cfg),
            patch("src.web.routes.async_session", return_value=session),
            patch(
                "src.expenses.persistence.upsert_transaction", new=AsyncMock(return_value=True)
            ) as upsert,
        ):
            client = _client()
            assert (
                client.post(
                    "/api/auth/login",
                    json={"username": "admin", "password": "a-long-and-private-password"},
                ).status_code
                == 200
            )
            response = client.post(
                "/api/expenses/import",
                headers={"X-CSRF-Token": client.cookies.get("ia_csrf")},
                json={
                    "provider": "gocardless",
                    "account_name": "Main account",
                    "transactions": [
                        {
                            "transactionId": "tx-1",
                            "amount": "-12.30",
                            "currency": "EUR",
                            "date": "2026-08-20",
                            "merchant": "Cafe Lisboa",
                        }
                    ],
                },
            )

        assert response.status_code == 200
        assert response.json()["imported"] == 1
        values = upsert.call_args.kwargs
        assert values["user_id"] == "user-a"
        assert values["item"]["external_id"] == "tx-1"
        assert values["item"]["category"] == "food"
