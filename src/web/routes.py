"""FastAPI routes: REST API and WebSocket chat endpoint."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import json
import math
from pathlib import Path
import re
import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    StreamingResponse,
)
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete, or_, select, text
from sqlalchemy.exc import IntegrityError

from src.agent.utils.logger import get_logger
from src.config import settings
from src.db.database import async_session
from src.db.models import (
    BrokerAccount,
    ChatMessage,
    Conversation,
    DailyPnL,
    ExpenseTransaction,
    Project,
    Report,
    SimulationResult,
    Trade,
    User,
)
from src.expenses.categories import CATEGORY_TAXONOMY, category_label
from src.expenses.sync import normalise_transaction
from src.scheduler.jobs import get_latest_snapshot
from src.tools.broker_accounts import (
    BROKER_FIELDS,
    SECRET_FIELDS,
    SUPPORTED_BROKERS,
    BrokerAccountConfig,
    BrokerVaultUnavailable,
    decrypt_config,
    encrypt_config,
    ensure_broker_vault,
    load_user_broker_accounts,
    validate_broker_config,
)
from src.tools.portfolio import get_portfolio_summary
from src.tools.simulator import run_simulation
from src.web.auth import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    clear_login_failures,
    create_session,
    hash_password,
    login_allowed,
    record_login_failure,
    record_registration_attempt,
    registration_allowed,
    require_authenticated,
    require_csrf,
    require_mcp_or_browser,
    verify_password,
    websocket_origin_allowed,
    websocket_principal,
)

logger = get_logger(__name__)

router = APIRouter()

# The local deployment runs a single app process. This in-process fan-out keeps
# the dashboard responsive when a sync adapter imports new rows. A future
# multi-worker deployment can replace this registry with Redis/Postgres NOTIFY
# without changing the browser contract.
_expense_streams: dict[str, set[asyncio.Queue[dict]]] = {}

STATIC_DIR = Path(__file__).parent / "static"
templates = Jinja2Templates(directory=str(STATIC_DIR))


# ── IP Whitelist middleware ────────────────────────────────────────────────────


def _get_client_ip(request: Request | WebSocket) -> str:
    # Nginx overwrites X-Real-IP in this deployment.  X-Forwarded-For is kept
    # as a compatibility fallback for tests and other trusted reverse proxies.
    if settings.trust_proxy_headers:
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
        xff = request.headers.get("X-Forwarded-For")
        if xff:
            return xff.split(",")[0].strip()
    return request.client.host if request.client else "0.0.0.0"


def require_allowed_ip(request: Request) -> None:
    """FastAPI dependency that raises 403 for non-whitelisted IPs."""
    ip = _get_client_ip(request)
    if not settings.is_development and not settings.is_ip_allowed(ip):
        logger.warning("Blocked request from %s", ip)
        raise HTTPException(status_code=403, detail="Access denied")


# ── Chat WebSocket ─────────────────────────────────────────────────────────────


@router.websocket("/ws/chat/{session_id}")
async def websocket_chat(websocket: WebSocket, session_id: str) -> None:
    """WebSocket endpoint for real-time streaming chat with the agent."""
    # IP check for WebSocket
    ip = _get_client_ip(websocket)
    if not settings.is_development and not settings.is_ip_allowed(ip):
        logger.warning("WS blocked from %s", ip)
        await websocket.close(code=4003, reason="Access denied")
        return
    if not websocket_origin_allowed(websocket):
        await websocket.close(code=4003, reason="Origin not allowed")
        return
    principal = websocket_principal(websocket)
    if principal is None:
        await websocket.close(code=4001, reason="Authentication required")
        return
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,36}", session_id):
        await websocket.close(code=4400, reason="Invalid session")
        return
    if principal.user_id:
        # Signed cookies are deliberately stateless, so check the account's
        # active flag when a WebSocket is opened. This makes local account
        # deactivation effective without waiting for cookie expiry.
        try:
            async with async_session() as db_session:
                result = await db_session.execute(
                    select(User).where(
                        User.id == principal.user_id,
                        User.is_active.is_(True),
                    )
                )
                if result.scalar_one_or_none() is None:
                    await websocket.close(code=4001, reason="Authentication required")
                    return
        except Exception as exc:
            logger.error("WebSocket account lookup failed: %s", exc)
            await websocket.close(code=1013, reason="Authentication service unavailable")
            return

    await websocket.accept()
    logger.info("WebSocket connected: session=%s ip=%s", session_id, ip)

    from src.agent.orchestrator import get_or_create_session

    session = get_or_create_session(session_id, principal.user_id)
    await session.load_history_from_db()

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
                user_message = data.get("message", "").strip()
            except json.JSONDecodeError:
                user_message = raw.strip()

            if not user_message:
                continue
            if len(user_message) > settings.max_chat_message_chars:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": (
                            f"Message is limited to {settings.max_chat_message_chars} characters."
                        ),
                    }
                )
                continue

            # Stream agent response events back over WebSocket
            async for event in session.chat(user_message):
                await websocket.send_json(event)

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected: session=%s", session_id)
    except Exception as exc:
        logger.exception("WebSocket error: %s", exc)
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass


# ── REST API ──────────────────────────────────────────────────────────────────


@router.get("/api/health")
async def health() -> dict:
    return {
        "status": "ok",
        "timestamp": datetime.now(UTC).isoformat(),
        "trading_mode": settings.trading_mode,
        "model": settings.llm_model_path,
        "local_reasoning": True,
    }


@router.get("/api/ready")
async def ready() -> dict:
    """Readiness probe used by Compose; it checks the DB and model file."""
    checks = {"database": False, "model": False}
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception as exc:
        logger.warning("Readiness database check failed: %s", exc)
    checks["model"] = Path(settings.llm_model_path).is_file()
    if not all(checks.values()):
        raise HTTPException(status_code=503, detail={"status": "not_ready", "checks": checks})
    return {"status": "ready", "checks": checks, "timestamp": datetime.now(UTC).isoformat()}


@router.get(
    "/login",
    response_class=HTMLResponse,
    response_model=None,
    dependencies=[Depends(require_allowed_ip)],
)
async def login_page(request: Request) -> HTMLResponse | RedirectResponse:
    """Serve the login form without exposing any private application data."""
    if request.cookies.get(SESSION_COOKIE) and settings.is_development is False:
        # A redirect is only an optimisation; private routes still verify the
        # signature and expiry on every request.
        from src.web.auth import verify_session

        if verify_session(request.cookies.get(SESSION_COOKIE)) is not None:
            return RedirectResponse("/", status_code=303)
    return HTMLResponse(content=(STATIC_DIR / "login.html").read_text(), status_code=200)


@router.get(
    "/signup",
    response_class=HTMLResponse,
    response_model=None,
    dependencies=[Depends(require_allowed_ip)],
)
async def signup_page(request: Request) -> HTMLResponse | RedirectResponse:
    """Serve the public local account-creation form."""
    if not getattr(settings, "auth_allow_signup", True):
        return RedirectResponse("/login", status_code=303)
    if request.cookies.get(SESSION_COOKIE) and settings.is_production:
        from src.web.auth import verify_session

        if verify_session(request.cookies.get(SESSION_COOKIE)) is not None:
            return RedirectResponse("/", status_code=303)
    return HTMLResponse(content=(STATIC_DIR / "signup.html").read_text(), status_code=200)


def _authenticated_response(user: User, status_code: int = 200) -> JSONResponse:
    """Issue the same user-bound browser cookies after login or signup."""
    response = JSONResponse(
        {
            "authenticated": True,
            "username": user.username,
            "display_name": user.display_name,
            "user_id": user.id,
        },
        status_code=status_code,
    )
    secure = bool(settings.auth_cookie_secure and settings.is_production)
    response.set_cookie(
        SESSION_COOKIE,
        create_session(user.username, user.id),
        httponly=True,
        secure=secure,
        samesite="strict",
        max_age=max(300, settings.auth_session_ttl_minutes * 60),
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        secrets.token_urlsafe(32),
        httponly=False,
        secure=secure,
        samesite="strict",
        max_age=max(300, settings.auth_session_ttl_minutes * 60),
        path="/",
    )
    return response


@router.post("/api/auth/login", dependencies=[Depends(require_allowed_ip)])
async def login(request: Request) -> JSONResponse:
    """Authenticate a local user and issue a user-bound session cookie."""
    ip = _get_client_ip(request)
    if not login_allowed(ip):
        raise HTTPException(status_code=429, detail="Too many failed login attempts")
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    username = str(body.get("username", ""))
    password = str(body.get("password", ""))
    user = None
    if len(username) <= 128 and len(password) <= 256 and username and password:
        try:
            async with async_session() as session:
                result = await session.execute(
                    select(User).where(User.username == username, User.is_active.is_(True))
                )
                user = result.scalar_one_or_none()
        except Exception as exc:
            logger.error("User lookup failed during login: %s", exc)
            raise HTTPException(
                status_code=503, detail="Authentication service unavailable"
            ) from exc

    valid = user is not None and verify_password(password, user.password_hash)
    if not valid:
        record_login_failure(ip)
        # Do not distinguish an unknown ID from a bad password.
        raise HTTPException(status_code=401, detail="Invalid ID or password")
    assert user is not None

    clear_login_failures(ip)
    return _authenticated_response(user)


@router.post("/api/auth/register", dependencies=[Depends(require_allowed_ip)])
async def register(request: Request) -> JSONResponse:
    """Create and sign in a new isolated local user account."""
    if not getattr(settings, "auth_allow_signup", True):
        raise HTTPException(status_code=403, detail="New account registration is disabled")
    ip = _get_client_ip(request)
    if not registration_allowed(ip):
        raise HTTPException(status_code=429, detail="Too many registration attempts")
    record_registration_attempt(ip)
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    username = str(body.get("username", "")).strip()
    password = str(body.get("password", ""))
    confirmation = str(body.get("password_confirmation", ""))
    display_name = str(body.get("display_name", "")).strip()
    if not re.fullmatch(r"[A-Za-z0-9_.@-]{3,128}", username):
        raise HTTPException(
            status_code=400,
            detail=(
                "Username must be 3-128 characters using letters, numbers, "
                "dot, underscore, @, or hyphen"
            ),
        )
    if len(password) < 12 or len(password) > 256:
        raise HTTPException(status_code=400, detail="Password must contain 12-256 characters")
    if password != confirmation:
        raise HTTPException(status_code=400, detail="Passwords do not match")
    if len(display_name) > 128:
        raise HTTPException(status_code=400, detail="Display name is limited to 128 characters")
    try:
        password_hash = hash_password(password)
        async with async_session() as session:
            user = User(
                id=str(uuid.uuid4()),
                username=username,
                password_hash=password_hash,
                display_name=display_name or username,
                trading_mode=settings.trading_mode,
            )
            session.add(user)
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise HTTPException(status_code=409, detail="Username is already in use") from exc
            return _authenticated_response(user, status_code=201)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Could not register user: %s", exc)
        raise HTTPException(status_code=503, detail="Account could not be created") from exc


@router.get(
    "/api/auth/me",
    dependencies=[Depends(require_allowed_ip), Depends(require_authenticated)],
)
async def auth_me(request: Request) -> dict:
    principal = require_authenticated(request)
    return {
        "authenticated": True,
        "username": principal.username,
        "user_id": principal.user_id,
    }


def _valid_session_id(session_id: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_-]{1,36}", session_id))


def _profile_payload(user: User) -> dict:
    return {
        "user_id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "description": user.description,
        "preferences": user.preferences or {},
        "trading_mode": getattr(user, "trading_mode", settings.trading_mode),
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
    }


@router.get(
    "/api/profile",
    dependencies=[Depends(require_allowed_ip), Depends(require_authenticated)],
)
async def get_profile(request: Request) -> dict:
    """Return the authenticated user's durable assistant preferences."""
    principal = require_authenticated(request)
    if not principal.user_id:
        return {
            "user_id": None,
            "username": principal.username,
            "display_name": principal.username,
            "description": "",
            "preferences": {},
            "trading_mode": settings.trading_mode,
            "updated_at": None,
        }
    try:
        async with async_session() as session:
            result = await session.execute(select(User).where(User.id == principal.user_id))
            user = result.scalar_one_or_none()
            if user is None or not user.is_active:
                raise HTTPException(status_code=401, detail="Authentication required")
            return _profile_payload(user)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Profile service unavailable") from exc


@router.put(
    "/api/profile",
    dependencies=[
        Depends(require_allowed_ip),
        Depends(require_authenticated),
        Depends(require_csrf),
    ],
)
async def update_profile(request: Request) -> dict:
    """Persist bounded user description and preference data."""
    principal = require_authenticated(request)
    if not principal.user_id:
        raise HTTPException(status_code=503, detail="Profile persistence is unavailable")
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    display_name = str(body.get("display_name", "")).strip()
    description = str(body.get("description", "")).strip()
    preferences = body.get("preferences", {})
    if len(display_name) > 128:
        raise HTTPException(status_code=400, detail="display_name is limited to 128 characters")
    if len(description) > 4_000:
        raise HTTPException(status_code=400, detail="description is limited to 4000 characters")
    if not isinstance(preferences, dict):
        raise HTTPException(status_code=400, detail="preferences must be a JSON object")
    try:
        encoded_preferences = json.dumps(preferences, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400, detail="preferences must be JSON serialisable"
        ) from exc
    if len(encoded_preferences) > 8_000 or len(preferences) > 64:
        raise HTTPException(status_code=400, detail="preferences are too large")

    try:
        async with async_session() as session:
            result = await session.execute(select(User).where(User.id == principal.user_id))
            user = result.scalar_one_or_none()
            if user is None or not user.is_active:
                raise HTTPException(status_code=401, detail="Authentication required")
            user.display_name = display_name[:128]
            user.description = description[:4_000]
            user.preferences = preferences
            await session.commit()
            return _profile_payload(user)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Profile persistence failed") from exc


@router.put(
    "/api/profile/trading-mode",
    dependencies=[
        Depends(require_allowed_ip),
        Depends(require_authenticated),
        Depends(require_csrf),
    ],
)
async def update_trading_mode(request: Request) -> dict:
    """Persist a user's trading mode without mutating the process-global default."""
    principal = require_authenticated(request)
    if not principal.user_id:
        raise HTTPException(status_code=503, detail="Trading mode persistence is unavailable")
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc
    mode = body.get("mode") if isinstance(body, dict) else None
    if mode not in {"recommend", "auto"}:
        raise HTTPException(status_code=400, detail="mode must be 'recommend' or 'auto'")
    try:
        async with async_session() as session:
            result = await session.execute(select(User).where(User.id == principal.user_id))
            user = result.scalar_one_or_none()
            if user is None or not user.is_active:
                raise HTTPException(status_code=401, detail="Authentication required")
            user.trading_mode = mode
            await session.commit()
            return _profile_payload(user)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Trading mode persistence failed") from exc


def _broker_account_public(row: BrokerAccount, config: dict) -> dict:
    return BrokerAccountConfig(
        id=row.id,
        user_id=row.user_id,
        broker=row.broker,
        display_name=row.display_name,
        config=config,
    ).public | {"active": bool(row.is_active)}


def _broker_account_body(request_body: object) -> tuple[str, str, dict, bool | None]:
    if not isinstance(request_body, dict):
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    broker = str(request_body.get("broker", "")).lower().strip()
    if broker not in SUPPORTED_BROKERS:
        raise HTTPException(status_code=400, detail=f"Unknown broker: {broker or 'missing'}")
    display_name = str(request_body.get("display_name", "")).strip()
    if not display_name or len(display_name) > 128:
        raise HTTPException(
            status_code=400,
            detail="display_name is required and limited to 128 characters",
        )
    config = request_body.get("config", {})
    if not isinstance(config, dict):
        raise HTTPException(status_code=400, detail="config must be a JSON object")
    active = request_body.get("active")
    if active is not None and not isinstance(active, bool):
        raise HTTPException(status_code=400, detail="active must be a boolean")
    return broker, display_name, config, active


def _validated_account_config(
    broker: str,
    raw_config: dict,
    existing: dict | None = None,
) -> dict:
    merged = dict(existing or {})
    secret_fields = SECRET_FIELDS[broker]
    for field, value in raw_config.items():
        # An empty secret in the edit form means "keep the existing secret";
        # the UI never needs to read a secret back from the server.
        if field in secret_fields and value == "" and field in merged:
            continue
        merged[field] = value
    try:
        normalized = validate_broker_config(broker, merged)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    missing = [
        field
        for field in secret_fields
        if not str(normalized.get(field, "")).strip()
    ]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required credential field(s): {', '.join(sorted(missing))}",
        )
    return normalized


@router.get(
    "/api/broker-accounts/providers",
    dependencies=[Depends(require_allowed_ip), Depends(require_authenticated)],
)
async def broker_account_providers() -> dict:
    """Describe supported connection fields without exposing any credentials."""
    return {
        "providers": {
            broker: {
                "fields": sorted(BROKER_FIELDS[broker]),
                "secret_fields": sorted(SECRET_FIELDS[broker]),
            }
            for broker in SUPPORTED_BROKERS
        }
    }


@router.get(
    "/api/broker-accounts",
    dependencies=[Depends(require_allowed_ip), Depends(require_authenticated)],
)
async def list_broker_accounts(request: Request) -> dict:
    """List the authenticated user's accounts with secrets masked."""
    principal = require_authenticated(request)
    if not principal.user_id:
        raise HTTPException(status_code=503, detail="Broker account persistence is unavailable")
    try:
        ensure_broker_vault()
        accounts = await load_user_broker_accounts(principal.user_id)
        return {"vault_configured": True, "accounts": [account.public for account in accounts]}
    except BrokerVaultUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Could not list broker accounts: %s", exc)
        raise HTTPException(status_code=503, detail="Broker account service unavailable") from exc


@router.post(
    "/api/broker-accounts",
    dependencies=[
        Depends(require_allowed_ip),
        Depends(require_authenticated),
        Depends(require_csrf),
    ],
)
async def create_broker_account(request: Request) -> dict:
    """Create one encrypted broker configuration owned by the current user."""
    principal = require_authenticated(request)
    if not principal.user_id:
        raise HTTPException(status_code=503, detail="Broker account persistence is unavailable")
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc
    broker, display_name, raw_config, active = _broker_account_body(body)
    config = _validated_account_config(broker, raw_config)
    try:
        encrypted = encrypt_config(config)
        async with async_session() as session:
            row = BrokerAccount(
                id=str(uuid.uuid4()),
                user_id=principal.user_id,
                broker=broker,
                display_name=display_name,
                config_encrypted=encrypted,
                is_active=True if active is None else active,
            )
            session.add(row)
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise HTTPException(
                    status_code=409,
                    detail="An account with this provider and name already exists.",
                ) from exc
            return _broker_account_public(row, config)
    except BrokerVaultUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Could not create broker account: %s", exc)
        raise HTTPException(status_code=503, detail="Broker account could not be saved") from exc


@router.put(
    "/api/broker-accounts/{account_id}",
    dependencies=[
        Depends(require_allowed_ip),
        Depends(require_authenticated),
        Depends(require_csrf),
    ],
)
async def update_broker_account(account_id: str, request: Request) -> dict:
    """Update one owned account; blank secret fields preserve the old secret."""
    principal = require_authenticated(request)
    if not principal.user_id:
        raise HTTPException(status_code=503, detail="Broker account persistence is unavailable")
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    try:
        async with async_session() as session:
            result = await session.execute(
                select(BrokerAccount).where(
                    BrokerAccount.id == account_id,
                    BrokerAccount.user_id == principal.user_id,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                raise HTTPException(status_code=404, detail="Broker account not found")
            existing = decrypt_config(row.config_encrypted)
            broker = row.broker
            display_name = str(body.get("display_name", row.display_name)).strip()
            if not display_name or len(display_name) > 128:
                raise HTTPException(
                    status_code=400,
                    detail="display_name is required and limited to 128 characters",
                )
            raw_config = body.get("config", {})
            if not isinstance(raw_config, dict):
                raise HTTPException(status_code=400, detail="config must be a JSON object")
            config = _validated_account_config(broker, raw_config, existing)
            row.display_name = display_name
            row.config_encrypted = encrypt_config(config)
            if isinstance(body.get("active"), bool):
                row.is_active = body["active"]
            await session.commit()
            return _broker_account_public(row, config)
    except BrokerVaultUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except HTTPException:
        raise
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Broker account update conflicted") from exc
    except Exception as exc:
        logger.error("Could not update broker account %s: %s", account_id, exc)
        raise HTTPException(status_code=503, detail="Broker account could not be updated") from exc


@router.delete(
    "/api/broker-accounts/{account_id}",
    dependencies=[
        Depends(require_allowed_ip),
        Depends(require_authenticated),
        Depends(require_csrf),
    ],
)
async def deactivate_broker_account(account_id: str, request: Request) -> dict:
    """Disable an account without destroying its encrypted audit/config record."""
    principal = require_authenticated(request)
    if not principal.user_id:
        raise HTTPException(status_code=503, detail="Broker account persistence is unavailable")
    try:
        async with async_session() as session:
            result = await session.execute(
                select(BrokerAccount).where(
                    BrokerAccount.id == account_id,
                    BrokerAccount.user_id == principal.user_id,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                raise HTTPException(status_code=404, detail="Broker account not found")
            row.is_active = False
            await session.commit()
            return {"success": True, "id": row.id, "active": False}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Could not deactivate broker account %s: %s", account_id, exc)
        raise HTTPException(status_code=503, detail="Broker account could not be disabled") from exc


def _portfolio_number(value: object) -> float | None:
    """Convert provider values to finite JSON-safe numbers."""
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return round(number, 2) if math.isfinite(number) else None


def _first_portfolio_number(data: dict, *keys: str) -> float | None:
    for key in keys:
        value = _portfolio_number(data.get(key))
        if value is not None:
            return value
    return None


def _portfolio_position(position: dict) -> dict:
    """Expose a consistent, non-secret position shape to the dashboard."""
    symbol = (
        position.get("symbol")
        or position.get("asset")
        or position.get("currency")
        or "Unknown"
    )
    value = _first_portfolio_number(position, "market_value", "value", "usd_value")
    quantity = _first_portfolio_number(position, "qty", "quantity", "available", "free")
    price = _first_portfolio_number(position, "current_price", "market_price", "price")
    pnl = _first_portfolio_number(position, "unrealized_pnl", "unrealized_pl")
    return {
        **position,
        "symbol": str(symbol),
        "quantity": quantity,
        "price_usd": price,
        "value_usd": value,
        "pnl_usd": pnl,
    }


def _portfolio_account(account: dict) -> dict:
    """Expose normalized account metrics without credentials or raw provider blobs."""
    balances = account.get("balances")
    if not isinstance(balances, list):
        balances = []
    cash = _first_portfolio_number(
        account,
        "cash",
        "cash_balance",
        "available_cash",
        "available_funds",
    )
    if cash is None:
        usd_balances = [
            balance
            for balance in balances
            if isinstance(balance, dict)
            and str(balance.get("currency") or balance.get("asset") or "").upper() == "USD"
        ]
        balance_values = [
            _first_portfolio_number(balance, "available", "free", "amount")
            for balance in usd_balances
        ]
        usable_values = [value for value in balance_values if value is not None]
        cash = round(sum(usable_values), 2) if usable_values else None
    return {
        "broker": account.get("broker", "unknown"),
        "account_id": account.get("account_id"),
        "account_name": account.get("account_name") or account.get("broker", "Account"),
        "equity_usd": _first_portfolio_number(
            account, "equity", "portfolio_value", "net_liquidation"
        ),
        "cash_usd": cash,
        "unrealized_pnl_usd": _first_portfolio_number(
            account, "unrealized_pnl", "unrealized_pl"
        ),
        "status": "connected",
    }


@router.get(
    "/api/portfolio",
    dependencies=[Depends(require_allowed_ip), Depends(require_authenticated)],
)
async def portfolio_snapshot(request: Request) -> dict:
    """Return the authenticated user's live, broker-backed portfolio snapshot."""
    principal = require_authenticated(request)
    if not principal.user_id:
        raise HTTPException(status_code=503, detail="Portfolio persistence is unavailable")
    try:
        ensure_broker_vault()
        accounts = await load_user_broker_accounts(principal.user_id)
        summary = await asyncio.to_thread(get_portfolio_summary, accounts=accounts)
    except BrokerVaultUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Could not load portfolio snapshot: %s", exc)
        raise HTTPException(status_code=503, detail="Portfolio service unavailable") from exc

    positions = [_portfolio_position(position) for position in summary.get("positions", [])]
    account_metrics = [_portfolio_account(account) for account in summary.get("accounts", [])]
    errors = [
        {
            "broker": str(error.get("broker") or "unknown"),
            "account_id": error.get("account_id"),
            "account_name": error.get("account_name"),
            "error": str(error.get("error") or "Portfolio data unavailable"),
        }
        for error in summary.get("errors", [])
    ]
    errors_by_account = {
        error.get("account_id")
        for error in errors
        if error.get("account_id")
    }
    connected_accounts = [
        account.public
        | {
            "status": "error" if account.id in errors_by_account else "connected",
            "error": next(
                (
                    error["error"]
                    for error in errors
                    if error.get("account_id") == account.id
                ),
                None,
            ),
        }
        for account in accounts
    ]

    allocation_by_symbol: dict[str, float] = {}
    for position in positions:
        value = position.get("value_usd")
        if value is not None and value > 0:
            symbol = position["symbol"]
            allocation_by_symbol[symbol] = round(
                allocation_by_symbol.get(symbol, 0.0) + value, 2
            )
    market_value = _portfolio_number(summary.get("total_market_value_usd")) or 0.0
    allocation_total = round(sum(allocation_by_symbol.values()), 2)
    allocation = [
        {
            "symbol": symbol,
            "value_usd": value,
            "percentage": round((value / allocation_total) * 100, 1) if allocation_total else 0.0,
        }
        for symbol, value in sorted(
            allocation_by_symbol.items(), key=lambda item: item[1], reverse=True
        )
    ]
    cash_values = [
        account["cash_usd"]
        for account in account_metrics
        if account.get("cash_usd") is not None
    ]
    equity_values = [
        account["equity_usd"]
        for account in account_metrics
        if account.get("equity_usd") is not None
    ]
    cash = round(sum(cash_values), 2) if cash_values else None
    equity = round(sum(equity_values), 2) if equity_values else None
    if equity is None and (market_value or cash is not None):
        equity = round(market_value + (cash or 0.0), 2)

    empty_state: str | None
    if not accounts:
        status = "empty"
        empty_state = "connect_broker"
    elif errors and not positions and not account_metrics:
        status = "error"
        empty_state = "provider_error"
    elif errors:
        status = "warning"
        empty_state = "no_positions" if not positions else None
    elif not positions:
        status = "ready"
        empty_state = "no_positions"
    else:
        status = "ready"
        empty_state = None

    return {
        "updated_at": datetime.now(UTC).isoformat(),
        "currency": "USD",
        "status": status,
        "empty_state": empty_state,
        "connected_accounts": connected_accounts,
        "accounts": account_metrics,
        "positions": positions,
        "errors": errors,
        "total_market_value_usd": market_value,
        "total_equity_usd": equity,
        "cash_usd": cash,
        "total_unrealized_pnl_usd": _portfolio_number(
            summary.get("total_unrealized_pnl_usd")
        )
        or 0.0,
        "day_change_usd": None,
        "day_change_pct": None,
        "allocation": allocation,
    }


def _conversation_payload(
    conversation: Conversation,
    project_name: str | None,
    message_count: int = 0,
    preview: str = "",
) -> dict:
    return {
        "id": conversation.id,
        "title": conversation.title or "New chat",
        "project_id": conversation.project_id,
        "project_name": project_name,
        "message_count": message_count,
        "preview": preview,
        "created_at": conversation.created_at.isoformat(),
        "updated_at": conversation.updated_at.isoformat(),
        "last_message_at": (
            conversation.last_message_at.isoformat()
            if conversation.last_message_at
            else None
        ),
    }


async def _conversation_rows(
    session,
    user_id: str,
    search: str = "",
    project_id: str | None = None,
    limit: int = 200,
) -> list[dict]:
    """Load user-owned conversations with recent message previews."""
    query = (
        select(Conversation, Project.name)
        .outerjoin(
            Project,
            (Project.id == Conversation.project_id) & (Project.user_id == user_id),
        )
        .where(Conversation.user_id == user_id)
    )
    if project_id:
        query = query.where(Conversation.project_id == project_id)
    if search.strip():
        term = f"%{search.strip()[:128]}%"
        matching_messages = select(ChatMessage.session_id).where(
            ChatMessage.user_id == user_id,
            ChatMessage.content.ilike(term),
        )
        query = query.where(
            or_(Conversation.title.ilike(term), Conversation.id.in_(matching_messages))
        )
    query = query.order_by(
        Conversation.last_message_at.desc().nullslast(),
        Conversation.updated_at.desc(),
    ).limit(min(max(limit, 1), 500))
    result = await session.execute(query)
    rows = result.all()
    if not rows:
        return []

    conversation_ids = [conversation.id for conversation, _ in rows]
    message_result = await session.execute(
        select(
            ChatMessage.session_id,
            ChatMessage.role,
            ChatMessage.content,
        )
        .where(
            ChatMessage.user_id == user_id,
            ChatMessage.session_id.in_(conversation_ids),
            ChatMessage.role.in_(["user", "assistant"]),
        )
        .order_by(ChatMessage.created_at.desc())
    )
    stats: dict[str, dict[str, object]] = {}
    for session_id, _role, content in message_result.all():
        item = stats.setdefault(session_id, {"count": 0, "preview": ""})
        count = item.get("count", 0)
        item["count"] = (count if isinstance(count, int) else 0) + 1
        if not item["preview"]:
            item["preview"] = str(content or "")[:180]

    payloads: list[dict] = []
    for conversation, project_name in rows:
        item = stats.get(conversation.id, {})
        count = item.get("count", 0)
        preview = item.get("preview", "")
        payloads.append(
            _conversation_payload(
                conversation,
                project_name,
                count if isinstance(count, int) else 0,
                str(preview),
            )
        )
    return payloads


async def _owned_project(session, user_id: str, project_id: str | None) -> Project | None:
    if not project_id:
        return None
    if not _valid_session_id(project_id):
        raise HTTPException(status_code=400, detail="Invalid project ID")
    project = await session.scalar(
        select(Project).where(Project.id == project_id, Project.user_id == user_id)
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get(
    "/api/projects",
    dependencies=[Depends(require_allowed_ip), Depends(require_authenticated)],
)
async def list_projects(request: Request, search: str = "") -> dict:
    """Return the authenticated user's projects and grouped chat history."""
    principal = require_authenticated(request)
    if not principal.user_id:
        raise HTTPException(status_code=503, detail="Conversation persistence is unavailable")
    try:
        async with async_session() as session:
            projects = list(
                (
                    await session.execute(
                        select(Project)
                        .where(Project.user_id == principal.user_id)
                        .order_by(Project.updated_at.desc(), Project.name.asc())
                    )
                ).scalars()
            )
            conversations = await _conversation_rows(
                session, principal.user_id, search=search, limit=500
            )
            grouped: dict[str, list[dict]] = {}
            unassigned: list[dict] = []
            for conversation in conversations:
                if conversation["project_id"]:
                    grouped.setdefault(conversation["project_id"], []).append(conversation)
                else:
                    unassigned.append(conversation)
            project_payload = [
                {
                    "id": project.id,
                    "name": project.name,
                    "updated_at": project.updated_at.isoformat(),
                    "conversations": grouped.get(project.id, []),
                }
                for project in projects
                if not search.strip() or project.id in grouped
            ]
            return {
                "projects": project_payload,
                "unassigned": unassigned,
                "recent": conversations,
                "total": len(conversations),
            }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Could not list conversation projects: %s", exc)
        raise HTTPException(status_code=503, detail="Conversation history unavailable") from exc


@router.get(
    "/api/conversations",
    dependencies=[Depends(require_allowed_ip), Depends(require_authenticated)],
)
async def list_conversations(
    request: Request,
    search: str = "",
    project_id: str | None = None,
    limit: int = 200,
) -> list[dict]:
    """Return resumable conversations sorted by most recent activity."""
    principal = require_authenticated(request)
    if not principal.user_id:
        raise HTTPException(status_code=503, detail="Conversation persistence is unavailable")
    try:
        async with async_session() as session:
            await _owned_project(session, principal.user_id, project_id)
            return await _conversation_rows(
                session,
                principal.user_id,
                search=search,
                project_id=project_id,
                limit=limit,
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Could not list conversations: %s", exc)
        raise HTTPException(status_code=503, detail="Conversation history unavailable") from exc


@router.post(
    "/api/projects",
    dependencies=[
        Depends(require_allowed_ip),
        Depends(require_authenticated),
        Depends(require_csrf),
    ],
)
async def create_project(request: Request) -> dict:
    """Create a project owned by the authenticated user."""
    principal = require_authenticated(request)
    if not principal.user_id:
        raise HTTPException(status_code=503, detail="Project persistence is unavailable")
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc
    name = str(body.get("name", "")).strip() if isinstance(body, dict) else ""
    if not name or len(name) > 128:
        raise HTTPException(
            status_code=400,
            detail="Project name is required and limited to 128 characters",
        )
    project = Project(user_id=principal.user_id, name=name)
    try:
        async with async_session() as session:
            session.add(project)
            await session.commit()
            return {
                "id": project.id,
                "name": project.name,
                "updated_at": project.updated_at.isoformat(),
                "conversations": [],
            }
    except IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="A project with that name already exists",
        ) from exc
    except Exception as exc:
        logger.error("Could not create project: %s", exc)
        raise HTTPException(status_code=503, detail="Project could not be created") from exc


@router.patch(
    "/api/projects/{project_id}",
    dependencies=[
        Depends(require_allowed_ip),
        Depends(require_authenticated),
        Depends(require_csrf),
    ],
)
async def update_project(project_id: str, request: Request) -> dict:
    """Rename one project without affecting its conversations."""
    principal = require_authenticated(request)
    if not principal.user_id or not _valid_session_id(project_id):
        raise HTTPException(status_code=400, detail="Invalid project ID")
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc
    name = str(body.get("name", "")).strip() if isinstance(body, dict) else ""
    if not name or len(name) > 128:
        raise HTTPException(
            status_code=400,
            detail="Project name is required and limited to 128 characters",
        )
    try:
        async with async_session() as session:
            project = await session.scalar(
                select(Project).where(
                    Project.id == project_id,
                    Project.user_id == principal.user_id,
                )
            )
            if project is None:
                raise HTTPException(status_code=404, detail="Project not found")
            project.name = name
            project.updated_at = datetime.now(UTC)
            await session.commit()
            return {
                "id": project.id,
                "name": project.name,
                "updated_at": project.updated_at.isoformat(),
            }
    except HTTPException:
        raise
    except IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="A project with that name already exists",
        ) from exc
    except Exception as exc:
        logger.error("Could not update project %s: %s", project_id, exc)
        raise HTTPException(status_code=503, detail="Project could not be updated") from exc


@router.post(
    "/api/conversations",
    dependencies=[
        Depends(require_allowed_ip),
        Depends(require_authenticated),
        Depends(require_csrf),
    ],
)
async def create_conversation(request: Request) -> dict:
    """Create an empty conversation ready for a new chat turn."""
    principal = require_authenticated(request)
    if not principal.user_id:
        raise HTTPException(status_code=503, detail="Conversation persistence is unavailable")
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc
    body = body if isinstance(body, dict) else {}
    title = str(body.get("title", "New chat")).strip() or "New chat"
    if len(title) > 200:
        raise HTTPException(
            status_code=400,
            detail="Conversation title is limited to 200 characters",
        )
    try:
        async with async_session() as session:
            requested_project_id = body.get("project_id")
            if requested_project_id is not None and not isinstance(requested_project_id, str):
                raise HTTPException(status_code=400, detail="Invalid project ID")
            project = await _owned_project(
                session, principal.user_id, requested_project_id
            )
            conversation = Conversation(
                id=str(uuid.uuid4()),
                user_id=principal.user_id,
                project_id=project.id if project else None,
                title=title,
            )
            session.add(conversation)
            await session.commit()
            return _conversation_payload(conversation, project.name if project else None)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Could not create conversation: %s", exc)
        raise HTTPException(status_code=503, detail="Conversation could not be created") from exc


@router.get(
    "/api/conversations/{conversation_id}",
    dependencies=[Depends(require_allowed_ip), Depends(require_authenticated)],
)
async def get_conversation(conversation_id: str, request: Request) -> dict:
    """Return one owned conversation and its complete visible transcript."""
    principal = require_authenticated(request)
    if not principal.user_id or not _valid_session_id(conversation_id):
        raise HTTPException(status_code=400, detail="Invalid conversation ID")
    try:
        async with async_session() as session:
            row = await session.execute(
                select(Conversation, Project.name)
                .outerjoin(
                    Project,
                    (Project.id == Conversation.project_id)
                    & (Project.user_id == principal.user_id),
                )
                .where(
                    Conversation.id == conversation_id,
                    Conversation.user_id == principal.user_id,
                )
            )
            result = row.first()
            if result is None:
                raise HTTPException(status_code=404, detail="Conversation not found")
            conversation, project_name = result
            messages = await session.execute(
                select(ChatMessage)
                .where(
                    ChatMessage.user_id == principal.user_id,
                    ChatMessage.session_id == conversation_id,
                    ChatMessage.role.in_(["user", "assistant"]),
                )
                .order_by(ChatMessage.created_at.asc())
            )
            message_list = list(messages.scalars().all())
            payload = _conversation_payload(
                conversation,
                project_name,
                message_count=len(message_list),
            )
            payload["messages"] = [
                {
                    "id": message.id,
                    "role": message.role,
                    "content": message.content,
                    "created_at": message.created_at.isoformat(),
                }
                for message in message_list
            ]
            return payload
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Could not load conversation %s: %s", conversation_id, exc)
        raise HTTPException(status_code=503, detail="Conversation could not be loaded") from exc


@router.patch(
    "/api/conversations/{conversation_id}",
    dependencies=[
        Depends(require_allowed_ip),
        Depends(require_authenticated),
        Depends(require_csrf),
    ],
)
async def update_conversation(conversation_id: str, request: Request) -> dict:
    """Rename or move one owned conversation between projects."""
    principal = require_authenticated(request)
    if not principal.user_id or not _valid_session_id(conversation_id):
        raise HTTPException(status_code=400, detail="Invalid conversation ID")
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc
    body = body if isinstance(body, dict) else {}
    try:
        async with async_session() as session:
            conversation = await session.scalar(
                select(Conversation).where(
                    Conversation.id == conversation_id,
                    Conversation.user_id == principal.user_id,
                )
            )
            if conversation is None:
                raise HTTPException(status_code=404, detail="Conversation not found")
            if "title" in body:
                title = str(body.get("title", "")).strip() or "New chat"
                if len(title) > 200:
                    raise HTTPException(
                        status_code=400,
                        detail="Conversation title is limited to 200 characters",
                    )
                conversation.title = title
            if "project_id" in body:
                requested_project_id = body.get("project_id")
                if requested_project_id is not None and not isinstance(
                    requested_project_id, str
                ):
                    raise HTTPException(status_code=400, detail="Invalid project ID")
                project = await _owned_project(
                    session, principal.user_id, requested_project_id
                )
                conversation.project_id = project.id if project else None
                if project:
                    project.updated_at = datetime.now(UTC)
            conversation.updated_at = datetime.now(UTC)
            await session.commit()
            project_name = None
            if conversation.project_id:
                project = await session.scalar(
                    select(Project).where(Project.id == conversation.project_id)
                )
                project_name = project.name if project else None
            return _conversation_payload(conversation, project_name)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Could not update conversation %s: %s", conversation_id, exc)
        raise HTTPException(status_code=503, detail="Conversation could not be updated") from exc


@router.delete(
    "/api/conversations/{conversation_id}",
    dependencies=[
        Depends(require_allowed_ip),
        Depends(require_authenticated),
        Depends(require_csrf),
    ],
)
async def delete_conversation(conversation_id: str, request: Request) -> dict:
    """Permanently delete one owned conversation and its transcript."""
    principal = require_authenticated(request)
    if not principal.user_id or not _valid_session_id(conversation_id):
        raise HTTPException(status_code=400, detail="Invalid conversation ID")
    try:
        async with async_session() as session:
            conversation = await session.scalar(
                select(Conversation).where(
                    Conversation.id == conversation_id,
                    Conversation.user_id == principal.user_id,
                )
            )
            if conversation is None:
                raise HTTPException(status_code=404, detail="Conversation not found")
            await session.execute(
                delete(ChatMessage).where(
                    ChatMessage.user_id == principal.user_id,
                    ChatMessage.session_id == conversation_id,
                )
            )
            await session.delete(conversation)
            await session.commit()
            return {"deleted": True, "id": conversation_id}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Could not delete conversation %s: %s", conversation_id, exc)
        raise HTTPException(status_code=503, detail="Conversation could not be deleted") from exc


@router.get(
    "/api/chat/history",
    dependencies=[Depends(require_allowed_ip), Depends(require_authenticated)],
)
async def chat_history(request: Request, session_id: str, limit: int = 200) -> list[dict]:
    """Return only the authenticated user's messages for one conversation."""
    principal = require_authenticated(request)
    if not _valid_session_id(session_id):
        raise HTTPException(status_code=400, detail="Invalid session")
    limit = min(max(1, limit), 200)
    user_filter = (
        ChatMessage.user_id == principal.user_id
        if principal.user_id
        else ChatMessage.user_id.is_(None)
    )
    try:
        async with async_session() as session:
            result = await session.execute(
                select(ChatMessage)
                .where(user_filter, ChatMessage.session_id == session_id)
                .order_by(ChatMessage.created_at.desc())
                .limit(limit)
            )
            messages = list(reversed(result.scalars().all()))
            return [
                {
                    "role": message.role,
                    "content": message.content,
                    "created_at": message.created_at.isoformat(),
                }
                for message in messages
                if message.role in {"user", "assistant"}
            ]
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Chat history unavailable") from exc


@router.post(
    "/api/auth/logout",
    dependencies=[
        Depends(require_allowed_ip),
        Depends(require_authenticated),
        Depends(require_csrf),
    ],
)
async def logout() -> JSONResponse:
    response = JSONResponse({"authenticated": False})
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    return response


def _expense_date(value: str, label: str) -> datetime:
    """Parse a dashboard date filter as a UTC midnight."""
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{label} must be YYYY-MM-DD") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def _expense_window(
    period: str, from_date: str | None, to_date: str | None
) -> tuple[datetime, datetime]:
    now = datetime.now(UTC)
    if from_date or to_date:
        start = _expense_date(from_date, "from_date") if from_date else now - timedelta(days=30)
        end = (
            _expense_date(to_date, "to_date") + timedelta(days=1)
            if to_date
            else now + timedelta(days=1)
        )
        if start >= end:
            raise HTTPException(status_code=400, detail="from_date must be before to_date")
        return start, end

    period_days = {"7d": 7, "30d": 30, "90d": 90, "year": 365}
    if period == "month":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0), now + timedelta(
            days=1
        )
    if period not in period_days:
        raise HTTPException(status_code=400, detail="period must be month, 7d, 30d, 90d, or year")
    return now - timedelta(days=period_days[period]), now + timedelta(days=1)


def _expense_payload(row: ExpenseTransaction) -> dict:
    return {
        "id": row.id,
        "provider": row.provider,
        "external_id": row.external_id,
        "account_name": row.account_name,
        "merchant": row.merchant,
        "description": row.description,
        "amount": round(float(row.amount), 2),
        "currency": row.currency,
        "transaction_type": row.transaction_type,
        "category": row.category,
        "category_label": category_label(row.category),
        "subcategory": row.subcategory,
        "occurred_at": row.occurred_at.isoformat(),
        "pending": bool(row.pending),
    }


def _expense_provider_payload() -> dict:
    return {
        "providers": {
            "gocardless": {
                "name": "GoCardless Bank Account Data",
                "configured": False,
                "coverage": "EEA / PSD2 banks",
                "history": "Up to 24 months where the bank supports it",
                "access": "Bank-controlled access, commonly up to 90 days before consent renewal",
                "mode": "Consent link + transaction sync",
                "message": (
                    "The expense data contract and live-update channel are ready. "
                    "Add a provider consent flow before storing bank credentials."
                ),
            }
        }
    }


async def _publish_expense_event(user_id: str, event: dict) -> None:
    for queue in list(_expense_streams.get(user_id, set())):
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            # The next normal dashboard refresh will recover a slow client.
            continue


@router.get(
    "/api/expenses/categories",
    dependencies=[Depends(require_allowed_ip), Depends(require_authenticated)],
)
async def expense_categories() -> dict:
    """Return the stable category taxonomy used by the expense dashboard."""
    return {
        "categories": [
            {
                "key": key,
                "label": str(definition["label"]),
                "icon": str(definition["icon"]),
                "subcategories": [str(item) for item in definition["subcategories"]],
            }
            for key, definition in CATEGORY_TAXONOMY.items()
        ]
    }


@router.get(
    "/api/expenses/providers",
    dependencies=[Depends(require_allowed_ip), Depends(require_authenticated)],
)
async def expense_providers() -> dict:
    """Describe supported bank-feed options without exposing any secrets."""
    return _expense_provider_payload()


@router.get(
    "/api/expenses",
    dependencies=[Depends(require_allowed_ip), Depends(require_authenticated)],
)
async def list_expenses(
    request: Request,
    period: str = "month",
    from_date: str | None = None,
    to_date: str | None = None,
    category: str | None = None,
    limit: int = 200,
) -> dict:
    """Return user-scoped expenses, category totals, and sync metadata."""
    principal = require_authenticated(request)
    if not principal.user_id:
        raise HTTPException(status_code=503, detail="Expense persistence is unavailable")
    start, end = _expense_window(period, from_date, to_date)
    limit = min(max(1, limit), 500)
    try:
        async with async_session() as session:
            result = await session.execute(
                select(ExpenseTransaction)
                .where(
                    ExpenseTransaction.user_id == principal.user_id,
                    ExpenseTransaction.occurred_at >= start,
                    ExpenseTransaction.occurred_at < end,
                    *(
                        [ExpenseTransaction.category == category.strip().lower()]
                        if category and category.strip()
                        else []
                    ),
                )
                .order_by(ExpenseTransaction.occurred_at.desc())
            )
            rows = result.scalars().all()
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Could not load expenses: %s", exc)
        raise HTTPException(status_code=503, detail="Expense service unavailable") from exc

    expenses = [row for row in rows if row.transaction_type == "expense"]
    income = [row for row in rows if row.transaction_type == "income"]
    transfers = [row for row in rows if row.transaction_type == "transfer"]
    total_expenses = round(sum(float(row.amount) for row in expenses), 2)
    total_income = round(sum(float(row.amount) for row in income), 2)
    category_buckets: dict[str, dict[str, float | int]] = {}
    day_buckets: dict[str, float] = {}
    for row in expenses:
        bucket = category_buckets.setdefault(row.category, {"amount": 0.0, "transaction_count": 0})
        bucket["amount"] = round(float(bucket["amount"]) + float(row.amount), 2)
        bucket["transaction_count"] = int(bucket["transaction_count"]) + 1
        day_key = row.occurred_at.date().isoformat()
        day_buckets[day_key] = round(day_buckets.get(day_key, 0.0) + float(row.amount), 2)
    category_totals = [
        {
            "category": key,
            "label": category_label(key),
            "amount": values["amount"],
            "transaction_count": values["transaction_count"],
            "percentage": round((float(values["amount"]) / total_expenses) * 100, 1)
            if total_expenses
            else 0.0,
        }
        for key, values in sorted(
            category_buckets.items(), key=lambda item: float(item[1]["amount"]), reverse=True
        )
    ]
    last_synced = max((row.synced_at for row in rows if row.synced_at), default=None)
    currencies = [row.currency for row in rows if row.currency]
    currency = max(set(currencies), key=currencies.count) if currencies else "EUR"
    provider_payload = _expense_provider_payload()
    provider_names = [row.provider for row in rows if row.provider]
    sync_status = "imported" if rows else "not_configured"
    return {
        "period": period,
        "period_start": start.date().isoformat(),
        "period_end": (end - timedelta(days=1)).date().isoformat(),
        "currency": currency,
        "total_expenses": total_expenses,
        "total_income": total_income,
        "net_cashflow": round(total_income - total_expenses, 2),
        "transaction_count": len(expenses),
        "income_count": len(income),
        "transfer_count": len(transfers),
        "category_totals": category_totals,
        "daily_totals": [
            {"date": key, "amount": value} for key, value in sorted(day_buckets.items())
        ],
        "transactions": [_expense_payload(row) for row in rows[:limit]],
        "sync": {
            "status": sync_status,
            "provider": provider_names[0] if provider_names else None,
            "last_synced_at": last_synced.isoformat() if last_synced else None,
            "stream": "sse",
            "poll_interval_seconds": 30,
            "provider_options": provider_payload["providers"],
            "message": (
                "Transactions will update in this view as a connected provider imports them."
                if rows
                else "Connect a bank-data provider to start receiving transactions."
            ),
        },
    }


@router.get(
    "/api/expenses/stream",
    dependencies=[Depends(require_allowed_ip), Depends(require_authenticated)],
)
async def expense_stream(request: Request) -> StreamingResponse:
    """Stream expense-import events to the current user's open dashboard."""
    principal = require_authenticated(request)
    if not principal.user_id:
        raise HTTPException(status_code=503, detail="Expense streaming is unavailable")
    user_id = principal.user_id
    queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=10)
    _expense_streams.setdefault(user_id, set()).add(queue)

    async def event_generator():
        try:
            yield 'event: ready\ndata: {"stream":"expenses"}\n\n'
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=25)
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield f"event: expenses_updated\ndata: {json.dumps(event)}\n\n"
        finally:
            subscribers = _expense_streams.get(user_id)
            if subscribers is not None:
                subscribers.discard(queue)
                if not subscribers:
                    _expense_streams.pop(user_id, None)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/api/expenses/import",
    dependencies=[
        Depends(require_allowed_ip),
        Depends(require_authenticated),
        Depends(require_csrf),
    ],
)
async def import_expenses(request: Request) -> dict:
    """Import provider-normalised transactions idempotently for one user.

    This is the adapter boundary used by a future GoCardless/Enable Banking
    sync job. It also makes local fixture imports possible without pretending
    that a bank API is already connected.
    """
    principal = require_authenticated(request)
    if not principal.user_id:
        raise HTTPException(status_code=503, detail="Expense persistence is unavailable")
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    provider = str(body.get("provider") or "bank_feed").strip().lower()
    if not re.fullmatch(r"[a-z0-9_-]{2,32}", provider):
        raise HTTPException(
            status_code=400, detail="provider must be 2-32 letters, numbers, _ or -"
        )
    transactions = body.get("transactions")
    if not isinstance(transactions, list) or not transactions or len(transactions) > 500:
        raise HTTPException(status_code=400, detail="transactions must contain 1-500 items")
    account_name = str(body.get("account_name") or "Bank account").strip()[:128]
    try:
        normalised = [normalise_transaction(item, provider, account_name) for item in transactions]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    synced_at = datetime.now(UTC)
    imported = 0
    updated = 0
    try:
        async with async_session() as session:
            for item in normalised:
                result = await session.execute(
                    select(ExpenseTransaction).where(
                        ExpenseTransaction.user_id == principal.user_id,
                        ExpenseTransaction.provider == item["provider"],
                        ExpenseTransaction.external_id == item["external_id"],
                    )
                )
                row = result.scalar_one_or_none()
                if row is None:
                    row = ExpenseTransaction(
                        id=str(uuid.uuid4()), user_id=principal.user_id, **item
                    )
                    session.add(row)
                    imported += 1
                else:
                    for key, value in item.items():
                        setattr(row, key, value)
                    updated += 1
                row.synced_at = synced_at
            await session.commit()
    except Exception as exc:
        logger.error("Could not import expenses: %s", exc)
        raise HTTPException(status_code=503, detail="Expense import failed") from exc

    event = {
        "synced_at": synced_at.isoformat(),
        "provider": provider,
        "imported": imported,
        "updated": updated,
    }
    await _publish_expense_event(principal.user_id, event)
    return {"success": True, **event}


@router.get(
    "/api/market/snapshot",
    dependencies=[Depends(require_allowed_ip), Depends(require_authenticated)],
)
async def market_snapshot() -> dict:
    """Return the latest cached market data snapshot."""
    snap = get_latest_snapshot()
    if not snap:
        return {"message": "Snapshot not yet available — check back in a few minutes."}
    return snap


@router.get(
    "/api/safety",
    dependencies=[Depends(require_allowed_ip), Depends(require_authenticated)],
)
async def safety_status(request: Request) -> dict:
    """Expose the effective execution policy to the authenticated UI."""
    daily_halted: bool | None = None
    principal = require_authenticated(request)
    trading_mode = settings.trading_mode
    try:
        if principal.user_id:
            async with async_session() as session:
                user_result = await session.execute(
                    select(User).where(
                        User.id == principal.user_id,
                        User.is_active.is_(True),
                    )
                )
                user = user_result.scalar_one_or_none()
                if user is None:
                    raise HTTPException(status_code=401, detail="Authentication required")
                trading_mode = getattr(user, "trading_mode", settings.trading_mode)
        if not principal.user_id:
            raise HTTPException(status_code=503, detail="User safety policy is unavailable")
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        async with async_session() as session:
            result = await session.execute(
                select(DailyPnL).where(
                    DailyPnL.user_id == principal.user_id,
                    DailyPnL.date == today,
                )
            )
            record = result.scalar_one_or_none()
            daily_halted = bool(record and record.auto_trading_halted)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Could not read daily halt status: %s", exc)
    return {
        "trading_mode": trading_mode,
        "auto_max_trade_usd": settings.auto_max_trade_usd,
        "auto_daily_loss_limit_usd": settings.auto_daily_loss_limit_usd,
        "auto_allowed_symbols": sorted(settings.auto_allowed_symbols_set),
        "auto_allow_market_orders": settings.auto_allow_market_orders,
        "live_trading_enabled": settings.live_trading_enabled,
        "daily_halted": daily_halted,
        "confirmation_required_in_recommend_mode": True,
        "database_failure_blocks_auto_trading": True,
    }


@router.post(
    "/api/safety/kill-switch",
    dependencies=[
        Depends(require_allowed_ip),
        Depends(require_authenticated),
        Depends(require_csrf),
    ],
)
async def activate_kill_switch(request: Request) -> dict:
    """Halt future auto orders for today; do not claim to cancel broker orders."""
    principal = require_authenticated(request)
    if not principal.user_id:
        raise HTTPException(status_code=503, detail="User safety policy is unavailable")
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    try:
        async with async_session() as session:
            result = await session.execute(
                select(DailyPnL).where(
                    DailyPnL.user_id == principal.user_id,
                    DailyPnL.date == today,
                )
            )
            record = result.scalar_one_or_none()
            if record is None:
                record = DailyPnL(
                    user_id=principal.user_id,
                    date=today,
                    realized_usd=0.0,
                )
                session.add(record)
            record.auto_trading_halted = True
            await session.commit()
        logger.warning("Auto-trading kill switch activated for %s", today)
        return {
            "halted": True,
            "date": today,
            "message": "Future auto orders are blocked for today; check brokers for open orders.",
        }
    except Exception as exc:
        logger.error("Could not persist auto-trading kill switch: %s", exc)
        raise HTTPException(status_code=503, detail="Could not persist kill switch") from exc


def _simulation_payload(simulation: SimulationResult) -> dict:
    """Serialize one user-owned simulation result for the dashboard."""
    return {
        "id": simulation.id,
        "name": simulation.name,
        "strategy": simulation.strategy,
        "initial_capital": simulation.initial_capital,
        "final_value": simulation.final_value,
        "total_return_pct": simulation.total_return_pct,
        "sharpe_ratio": simulation.sharpe_ratio,
        "max_drawdown_pct": simulation.max_drawdown_pct,
        "trades_count": simulation.trades_count,
        "period_start": simulation.period_start,
        "period_end": simulation.period_end,
        "equity_curve": simulation.equity_curve,
        "created_at": simulation.created_at.isoformat(),
        "money_mode": "simulated",
        "data_source": "historical market data",
    }


def _normalise_simulation_symbols(value: object) -> list[str]:
    if isinstance(value, str):
        raw_symbols = re.split(r"[,\s]+", value)
    elif isinstance(value, list):
        raw_symbols = value
    else:
        raw_symbols = []
    symbols: list[str] = []
    for raw in raw_symbols:
        symbol = str(raw).strip().upper()
        if not symbol:
            continue
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9._=/\-]{0,15}", symbol):
            raise HTTPException(status_code=400, detail=f"Invalid simulation symbol: {symbol}")
        if symbol not in symbols:
            symbols.append(symbol)
    if not symbols or len(symbols) > 20:
        raise HTTPException(status_code=400, detail="Provide between 1 and 20 symbols")
    return symbols


def _validate_simulation_body(body: object) -> dict:
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    symbols = _normalise_simulation_symbols(body.get("symbols"))
    strategy = body.get("strategy")
    if not isinstance(strategy, dict):
        raise HTTPException(status_code=400, detail="strategy must be an object")
    strategy_type = str(strategy.get("type", "")).strip()
    if strategy_type not in {"buy_and_hold", "sma_crossover", "rsi_mean_reversion", "momentum"}:
        raise HTTPException(status_code=400, detail="Unsupported simulation strategy")
    params = strategy.get("params", {})
    if not isinstance(params, dict):
        raise HTTPException(status_code=400, detail="strategy.params must be an object")
    try:
        initial_capital = float(body.get("initial_capital", 10_000))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="initial_capital must be numeric") from exc
    if not math.isfinite(initial_capital) or initial_capital <= 0 or initial_capital > 100_000_000:
        raise HTTPException(
            status_code=400,
            detail="initial_capital must be between 0 and 100,000,000",
        )
    period_start = str(body.get("period_start", "")).strip()
    period_end = str(body.get("period_end", "")).strip() or None
    try:
        datetime.fromisoformat(period_start)
        if period_end:
            datetime.fromisoformat(period_end)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Dates must use YYYY-MM-DD format") from exc
    return {
        "name": str(body.get("name", "Paper simulation")).strip()[:256] or "Paper simulation",
        "symbols": symbols,
        "strategy": {"type": strategy_type, "params": params},
        "initial_capital": initial_capital,
        "period_start": period_start,
        "period_end": period_end,
    }


@router.get(
    "/api/simulations",
    dependencies=[Depends(require_allowed_ip), Depends(require_authenticated)],
)
async def list_simulations(request: Request) -> list[dict]:
    """List saved fake-money simulations for the authenticated user."""
    principal = require_authenticated(request)
    user_filter = (
        SimulationResult.user_id == principal.user_id
        if principal.user_id
        else SimulationResult.user_id.is_(None)
    )
    try:
        async with async_session() as session:
            result = await session.execute(
                select(SimulationResult)
                .where(user_filter)
                .order_by(SimulationResult.created_at.desc())
                .limit(30)
            )
            return [_simulation_payload(row) for row in result.scalars().all()]
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Simulation history unavailable") from exc


@router.post(
    "/api/simulations",
    dependencies=[
        Depends(require_allowed_ip),
        Depends(require_authenticated),
        Depends(require_csrf),
    ],
)
async def create_simulation(request: Request) -> dict:
    """Run and save a historical fake-money simulation; never contacts a broker."""
    principal = require_authenticated(request)
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc
    simulation_input = _validate_simulation_body(body)
    result = await asyncio.to_thread(run_simulation, **simulation_input)
    if result.get("error"):
        raise HTTPException(status_code=502, detail=str(result["error"]))

    try:
        async with async_session() as session:
            simulation = SimulationResult(
                user_id=principal.user_id,
                name=result["name"],
                strategy=result["strategy"],
                initial_capital=result["initial_capital"],
                final_value=result["final_value"],
                total_return_pct=result.get("total_return_pct", 0.0),
                sharpe_ratio=result.get("sharpe_ratio"),
                max_drawdown_pct=result.get("max_drawdown_pct"),
                trades_count=result["trades_count"],
                period_start=result["period_start"],
                period_end=result["period_end"],
                equity_curve=result["equity_curve"],
            )
            session.add(simulation)
            await session.commit()
            payload = _simulation_payload(simulation)
            payload["trades_sample"] = result.get("trades_sample", [])
            return payload
    except Exception as exc:
        logger.error("Could not persist simulation: %s", exc)
        raise HTTPException(status_code=503, detail="Simulation could not be saved") from exc


@router.get(
    "/api/reports",
    dependencies=[Depends(require_allowed_ip), Depends(require_authenticated)],
    responses={500: {"description": "Database error"}},
)
async def list_reports(request: Request) -> list[dict]:
    """List all generated reports."""
    principal = require_authenticated(request)
    report_filter = (
        Report.user_id == principal.user_id if principal.user_id else Report.user_id.is_(None)
    )
    try:
        async with async_session() as session:
            result = await session.execute(
                select(Report).where(report_filter).order_by(Report.created_at.desc()).limit(20)
            )
            reports = result.scalars().all()
            return [
                {
                    "id": r.id,
                    "title": r.title,
                    "period_start": r.period_start.isoformat(),
                    "period_end": r.period_end.isoformat(),
                    "pdf_available": r.pdf_path is not None,
                    "created_at": r.created_at.isoformat(),
                }
                for r in reports
            ]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/api/reports/{report_id}/pdf",
    dependencies=[Depends(require_allowed_ip), Depends(require_authenticated)],
    responses={
        404: {"description": "Report not found or PDF not available"},
        500: {"description": "Database error"},
    },
)
async def download_report_pdf(report_id: str, request: Request) -> FileResponse:
    """Download a report as PDF."""
    principal = require_authenticated(request)
    report_filter = (
        Report.user_id == principal.user_id if principal.user_id else Report.user_id.is_(None)
    )
    try:
        async with async_session() as session:
            result = await session.execute(
                select(Report).where(Report.id == report_id, report_filter)
            )
            report = result.scalar_one_or_none()
            if not report:
                raise HTTPException(status_code=404, detail="Report not found")
            if not report.pdf_path or not Path(report.pdf_path).exists():
                raise HTTPException(status_code=404, detail="PDF not available")
            report_path = Path(report.pdf_path).resolve()
            reports_root = Path(settings.reports_dir).resolve()
            if reports_root not in report_path.parents:
                logger.error("Refusing report path outside reports directory: %s", report_path)
                raise HTTPException(status_code=404, detail="PDF not available")
            return FileResponse(
                report_path,
                media_type="application/pdf",
                filename=report_path.name,
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/api/trades",
    dependencies=[Depends(require_allowed_ip), Depends(require_authenticated)],
    responses={500: {"description": "Database error"}},
)
async def list_trades(request: Request, limit: int = 50) -> list[dict]:
    """List recent trades recorded in the database."""
    principal = require_authenticated(request)
    limit = min(max(1, limit), 100)
    user_filter = (
        Trade.user_id == principal.user_id if principal.user_id else Trade.user_id.is_(None)
    )
    try:
        async with async_session() as session:
            result = await session.execute(
                select(Trade).where(user_filter).order_by(Trade.created_at.desc()).limit(limit)
            )
            trades = result.scalars().all()
            return [
                {
                    "id": t.id,
                    "broker": t.broker,
                    "symbol": t.symbol,
                    "side": t.side,
                    "quantity": t.quantity,
                    "price": t.price,
                    "order_type": t.order_type,
                    "status": t.status,
                    "mode": t.mode,
                    "reason": t.reason,
                    "created_at": t.created_at.isoformat(),
                }
                for t in trades
            ]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── MCP tool invocation ───────────────────────────────────────────────────────


@router.post(
    "/api/tools/invoke",
    dependencies=[Depends(require_allowed_ip), Depends(require_mcp_or_browser)],
    responses={400: {"description": "Missing tool_name"}, 500: {"description": "Tool error"}},
)
async def invoke_tool(request: Request) -> dict:
    """Invoke any agent tool by name. Used by the MCP server to forward Claude Desktop calls."""
    principal = require_mcp_or_browser(request)
    if principal.mechanism != "bearer":
        require_csrf(request)
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc

    tool_name = body.get("tool_name")
    if not tool_name:
        raise HTTPException(status_code=400, detail="Missing 'tool_name'")

    tool_input = body.get("tool_input", {})

    from src.tools.dispatcher import dispatch_tool, tool_context

    trading_mode = None
    if principal.user_id:
        try:
            async with async_session() as session:
                user_result = await session.execute(
                    select(User).where(
                        User.id == principal.user_id,
                        User.is_active.is_(True),
                    )
                )
                user = user_result.scalar_one_or_none()
                if user is None:
                    raise HTTPException(status_code=401, detail="Authentication required")
                trading_mode = getattr(user, "trading_mode", settings.trading_mode)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=503, detail="User settings unavailable") from exc

    with tool_context("api", principal.user_id, trading_mode):
        result_json = await dispatch_tool(tool_name, tool_input)
    return {"result": result_json}


# ── Main chat UI ───────────────────────────────────────────────────────────────


@router.get(
    "/",
    response_class=HTMLResponse,
    response_model=None,
    dependencies=[Depends(require_allowed_ip)],
)
async def chat_ui(request: Request) -> HTMLResponse | RedirectResponse:
    try:
        require_authenticated(request)
    except HTTPException as exc:
        if exc.status_code == 401:
            return RedirectResponse("/login", status_code=303)
        raise
    index = STATIC_DIR / "index.html"
    return HTMLResponse(content=index.read_text(), status_code=200)
