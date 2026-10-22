"""Durable OFFLINE submission contract; no SDK, route or execution authority.

The journal owns short sessionmaker transactions. A committed handoff precedes
any injected call, and an unresolved handoff is never automatically repeated.
Injected transport is admitted only on a positively marked local test database.
Its implementation belongs in tests. Ordinary/default dispatch always denies.
Read consent is rechecked as an account binding safeguard, never as write consent.
"""

import os
import re
import hmac
import math
import uuid
from typing import Literal, Protocol
import asyncio
from decimal import Decimal, localcontext
import inspect
from pathlib import Path
from threading import Lock

from pydantic import Field, BaseModel, ConfigDict, field_validator, model_validator
from sqlalchemy import Text, cast, func, text, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.db.models import BrokerObservation
from src.execution.policy import PolicyDenied, digest
from src.execution.external import external_write_denied
from src.execution.broker_review import review_observations
from src.execution.broker_observations import READ_PAYLOAD_BUDGET, selected_account
from src.execution.broker_submission_models import BrokerSubmissionEvent, BrokerSubmissionIntent

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "0020_broker_submission"
MAX_OBSERVATIONS = 1000
MAX_OFFLINE_HANDOFFS = 4  # Technical resource bound, never a financial mandate.
_admissions = set()
_admission_lock = Lock()


def _admit():
    with _admission_lock:
        if len(_admissions) >= MAX_OFFLINE_HANDOFFS:
            raise PolicyDenied("OFFLINE_HANDOFF_CAPACITY")
        token = object()
        _admissions.add(token)
        return token


def _release(token):
    with _admission_lock:
        _admissions.discard(token)


class SubmissionRequest(BaseModel):
    """Frozen contract details, not a quote, risk decision or approval grant."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    environment: Literal["paper"]
    session_id: str = Field(min_length=1, max_length=128)
    correlation_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.:-]+$")
    con_id: int = Field(gt=0, strict=True, le=2**63 - 1)
    client_id: int = Field(gt=0, strict=True, le=2**31 - 1)
    order_id: int = Field(ge=0, strict=True, le=2**31 - 1)
    security_type: Literal["STK"]
    exchange: str = Field(min_length=1, max_length=32, pattern=r"^[A-Z0-9_.-]+$")
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    side: Literal["buy", "sell"]
    order_type: Literal["LMT"]
    quantity: Decimal
    limit_price: Decimal
    tick: Decimal
    lot: Decimal
    multiplier: Decimal

    @field_validator("quantity", "limit_price", "tick", "lot", "multiplier", mode="before")
    @classmethod
    def exact_input(cls, value):
        if type(value) not in (str, int, Decimal) or (isinstance(value, str) and len(value) > 128):
            raise ValueError("Use exact decimal text, Decimal or integer; float/bool is not accepted")
        return value

    @field_validator("quantity", "limit_price", "tick", "lot", "multiplier")
    @classmethod
    def bounded_decimal(cls, value):
        if not value.is_finite() or not 0 < value < Decimal("1e18"):
            raise ValueError("Finite positive decimal required")
        with localcontext() as context:
            context.prec = 80
            if value != value.quantize(Decimal("1e-10")):
                raise ValueError("Unsupported decimal precision")
            return value.normalize()

    @model_validator(mode="after")
    def precision(self):
        with localcontext() as context:
            context.prec = 80
            if self.quantity % self.lot or self.limit_price % self.tick:
                raise ValueError("Lot or tick mismatch")
        return self


class TransportReceipt(BaseModel):
    """Synthetic handoff acknowledgement/rejection, never a fill."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    status: Literal["acknowledged", "rejected"]
    client_id: int = Field(gt=0, strict=True, le=2**31 - 1)
    order_id: int = Field(ge=0, strict=True, le=2**31 - 1)
    permanent_id: int | None = Field(default=None, gt=0, strict=True, le=2**63 - 1)

    @model_validator(mode="after")
    def acknowledgement_identity(self):
        if (self.status == "acknowledged") != (self.permanent_id is not None):
            raise ValueError("Acknowledgement requires a permanent identity; rejection must not supply one")
        return self


class OfflineTransport(Protocol):
    async def submit(self, request: SubmissionRequest, *, intent_id: str, attempt_id: str) -> TransportReceipt:
        """Tests inject finite synthetic behavior. No runtime implementation exists."""


def _id(value):
    try:
        return str(uuid.UUID(value))
    except (TypeError, ValueError, AttributeError):
        raise PolicyDenied("INVALID_SUBMISSION_ID") from None


def _request(value):
    try:
        return SubmissionRequest.model_validate(value)
    except (TypeError, ValueError):
        raise PolicyDenied("INVALID_SUBMISSION_REQUEST") from None


def _view(intent):
    return {
        "intent_id": intent.id,
        "request_sha256": intent.request_sha256,
        "state": "uncertain" if intent.state == "handoff_started" else intent.state,
        "journal_state": intent.state,
        "attempt_id": intent.attempt_id,
        "retry_allowed": False,
        "scope": "offline_contract",
        "environment_declared": "paper",
        "environment_verified": None,
        "execution_authority": "none",
        "complete_reconciliation": False,
        "broker_identity_resolution": ("permanent_id_bound" if intent.permanent_id is not None
                                       else "permanent_id_unknown_no_callback_association"),
    }


def _compare_request(request, observations, review):
    """Compare retained broker facts with this intent without hiding outliers.

    The existing reducer owns execution-version/correction interpretation. This
    adds only comparison against the frozen request, never a current-state claim.
    """
    reasons, executions, units_match = set(), {}, True
    with localcontext() as context:
        context.prec = 160
        for row in observations:
            payload = row["payload"]
            if row["kind"] != "execution" or digest(payload) != row["payload_sha256"]:
                continue
            executions[row["identity_sha256"]] = payload
            if payload.get("security_type") is None or payload.get("multiplier") is None:
                reasons.add("SUBMISSION_CONTRACT_EVIDENCE_INCOMPLETE")
                units_match = False
            try:
                multiplier = Decimal(payload["multiplier"]) if payload.get("multiplier") is not None else None
                mismatch = (payload.get("con_id") != request.con_id or payload.get("currency") != request.currency
                            or payload.get("side") != ("BOT" if request.side == "buy" else "SLD")
                            or (payload.get("security_type") is not None
                                and payload["security_type"] != request.security_type)
                            or (multiplier is not None and multiplier != request.multiplier))
                if mismatch:
                    reasons.add("SUBMISSION_EXECUTION_CONTRACT_MISMATCH")
                    units_match = False
                price = Decimal(payload["price"])
                if not price.is_finite():
                    raise ValueError("Invalid observed price")
                if payload.get("currency") == request.currency and (
                    (request.side == "buy" and price > request.limit_price)
                    or (request.side == "sell" and price < request.limit_price)
                ):
                    reasons.add("SUBMISSION_LIMIT_PRICE_BREACH")
            except (KeyError, TypeError, ValueError, ArithmeticError):
                reasons.add("SUBMISSION_EXECUTION_EVIDENCE_INVALID")
                units_match = False
        counts = review["counts"]
        ambiguous = any(counts[key] for key in (
            "conflicting_execution_identities", "execution_correction_families", "invalid_evidence_hashes"))
        quantity = None
        if ambiguous:
            reasons.add("SUBMISSION_EXECUTION_QUANTITY_UNRESOLVED")
        elif executions and units_match:
            try:
                quantities = [Decimal(row["quantity"]) for row in executions.values()]
                if any(not value.is_finite() or value <= 0 for value in quantities):
                    raise ValueError("Invalid observed quantity")
                quantity = sum(quantities, Decimal(0))
                if quantity > request.quantity:
                    reasons.add("SUBMISSION_QUANTITY_EXCEEDED")
            except (KeyError, TypeError, ValueError, ArithmeticError):
                reasons.add("SUBMISSION_EXECUTION_EVIDENCE_INVALID")
        for order in review["order_lifecycle"].get("orders", []):
            if (order["maximum_reported_filled"] is not None
                    and Decimal(order["maximum_reported_filled"]) > request.quantity):
                reasons.add("SUBMISSION_QUANTITY_EXCEEDED")
    return {"status": "needs_review" if reasons else "unverified", "reason_codes": sorted(reasons),
            "observed_execution_quantity": str(quantity) if quantity is not None else None,
            "scope": "retained_linked_facts_against_frozen_request_not_complete_reconciliation"}


class BrokerSubmissionJournal:
    def __init__(self, sessions: async_sessionmaker):
        if not isinstance(sessions, async_sessionmaker) or not isinstance(sessions.kw.get("bind"), AsyncEngine):
            raise TypeError("A bound async_sessionmaker is required; caller transactions are not accepted")
        self.sessions = sessions
        self.engine = sessions.kw["bind"]
        self._unfinished = set()

    async def _fixture(self):
        """Prove the actual bound database, not merely a caller/environment label."""
        configured = os.environ.get("TEST_DATABASE_URL")
        marker = os.environ.get("TEST_DATABASE_DISPOSABLE_TOKEN")
        if (not configured or not marker or not 16 <= len(marker) <= 256
                or self.sessions.kw.get("bind") is not self.engine):
            raise PolicyDenied("OFFLINE_DISPOSABLE_DATABASE_REQUIRED")
        try:
            url = make_url(configured)
        except Exception:
            raise PolicyDenied("OFFLINE_DISPOSABLE_DATABASE_REQUIRED") from None
        if (url != self.engine.url or url.drivername != "postgresql+asyncpg"
                or not re.fullmatch(r"test_[a-z0-9_]+", url.database or "")):
            raise PolicyDenied("OFFLINE_DISPOSABLE_DATABASE_REQUIRED")
        socket = url.query.get("host")
        local = (isinstance(socket, str) and Path(socket).is_absolute()
                 and Path(socket).resolve().is_relative_to(ROOT / ".qa")) if socket else (
                     url.host in {"127.0.0.1", "::1", "localhost"})
        if not local:
            raise PolicyDenied("OFFLINE_LOCAL_DATABASE_REQUIRED")
        try:
            async with self.engine.connect() as connection, connection.begin():
                await connection.execute(text("SET LOCAL statement_timeout = '5s'"))
                actual = await connection.scalar(text("SELECT current_database()"))
                tokens = (await connection.execute(
                    text("SELECT token FROM public.ia_disposable_marker"))).scalars().all()
                revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
                version = await connection.scalar(text("SELECT current_setting('server_version_num')::int"))
            valid = (actual == url.database and len(tokens) == 1 and isinstance(tokens[0], str)
                     and hmac.compare_digest(tokens[0].encode(), marker.encode()) and revision == SCHEMA
                     and type(version) is int and version >= 100000)
        except Exception:
            raise PolicyDenied("OFFLINE_DATABASE_IDENTITY_UNVERIFIED") from None
        if not valid:
            raise PolicyDenied("OFFLINE_DATABASE_IDENTITY_UNVERIFIED")

    async def _scope(self, session, user_id, account_id, request, *, dispatch=True):
        config, binding = await selected_account(session, user_id=user_id, account_id=account_id,
                                                require_consent=dispatch)
        if dispatch and (config.get("environment") != "paper" or type(config.get("client_id")) is not int
                or config["client_id"] != request.client_id):
            raise PolicyDenied("SUBMISSION_ACCOUNT_BINDING_MISMATCH")
        return binding, digest(config)

    @staticmethod
    def _append(session, intent, key, kind, payload, *, observation_id=None):
        payload = dict(payload, scope="offline_contract", execution_authority="none")
        session.add(BrokerSubmissionEvent(
            intent_id=intent.id, event_key=key, kind=kind, payload=payload,
            payload_sha256=digest(payload), observation_id=observation_id,
        ))

    async def _load(self, session, *, user_id, account_id, intent_id, dispatch=True):
        # Lock order matches the existing principal/account boundary before intent.
        candidate = await session.scalar(select(BrokerSubmissionIntent).where(
            BrokerSubmissionIntent.id == _id(intent_id), BrokerSubmissionIntent.user_id == user_id,
            BrokerSubmissionIntent.account_id == account_id,
        ))
        if candidate is None:
            raise PolicyDenied("SUBMISSION_NOT_OWNED")
        request = _request(candidate.request)
        binding, configuration = await self._scope(session, user_id, account_id, request, dispatch=dispatch)
        intent = await session.scalar(select(BrokerSubmissionIntent).where(
            BrokerSubmissionIntent.id == candidate.id,
        ).with_for_update().execution_options(populate_existing=True))
        if (intent.account_binding != binding or (dispatch and intent.configuration_sha256 != configuration)):
            raise PolicyDenied("SUBMISSION_ACCOUNT_CHANGED")
        if (digest(intent.request) != intent.request_sha256
                or request.model_dump(mode="json") != intent.request
                or intent.broker_order_key != digest([request.client_id, request.order_id])):
            raise PolicyDenied("SUBMISSION_REQUEST_CHANGED")
        if intent.state not in {"staged", "handoff_started", "acknowledged", "rejected", "uncertain", "blocked"}:
            raise PolicyDenied("SUBMISSION_STATE_INVALID")
        return intent, request

    async def stage_intent(self, *, user_id, account_id, idempotency_key, request):
        request = _request(request)
        if not isinstance(idempotency_key, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", idempotency_key):
            raise PolicyDenied("INVALID_SUBMISSION_KEY")
        # Even staging is currently fixture-only. It creates no real-account
        # proposal, financial policy, approval or executable capability.
        await self._fixture()
        payload = request.model_dump(mode="json")
        async with self.sessions.begin() as session:
            binding, configuration = await self._scope(session, user_id, account_id, request)
            existing = await session.scalar(select(BrokerSubmissionIntent).where(
                BrokerSubmissionIntent.account_id == account_id, BrokerSubmissionIntent.account_binding == binding,
                BrokerSubmissionIntent.idempotency_key == idempotency_key,
            ).with_for_update())
            if existing is not None:
                intent, _ = await self._load(session, user_id=user_id, account_id=account_id, intent_id=existing.id)
                if intent.request_sha256 != digest(payload):
                    raise PolicyDenied("SUBMISSION_IDEMPOTENCY_CONFLICT")
                return _view(intent)
            broker_key = digest([request.client_id, request.order_id])
            if await session.scalar(select(BrokerSubmissionIntent.id).where(
                BrokerSubmissionIntent.account_id == account_id, BrokerSubmissionIntent.account_binding == binding,
                BrokerSubmissionIntent.broker_order_key == broker_key,
            )):
                raise PolicyDenied("SUBMISSION_BROKER_ID_ALREADY_RESERVED")
            intent = BrokerSubmissionIntent(
                id=str(uuid.uuid4()), user_id=user_id, account_id=account_id, account_binding=binding,
                configuration_sha256=configuration, idempotency_key=idempotency_key, broker_order_key=broker_key,
                request=payload, request_sha256=digest(payload), state="staged",
            )
            session.add(intent)
            await session.flush()
            self._append(session, intent, "staged", "staged", {"request_sha256": intent.request_sha256})
            return _view(intent)

    async def _outcome(self, *, user_id, account_id, intent_id, attempt_id, state, reason, receipt=None):
        await self._fixture()
        async with self.sessions.begin() as session:
            intent, request = await self._load(session, user_id=user_id, account_id=account_id,
                                               intent_id=intent_id, dispatch=False)
            if intent.state != "handoff_started" or intent.attempt_id != attempt_id:
                return _view(intent)
            try:
                binding, configuration = await self._scope(session, user_id, account_id, request)
                if binding != intent.account_binding or configuration != intent.configuration_sha256:
                    raise PolicyDenied("SUBMISSION_ACCOUNT_CHANGED")
            except PolicyDenied:
                # Owned local audit may record uncertainty after consent/config
                # loss; the stale receipt never becomes an acknowledgement.
                state, reason, receipt = "uncertain", "SUBMISSION_SCOPE_LOST_DURING_HANDOFF", None
            if receipt is not None and receipt.permanent_id is not None:
                permanent = str(receipt.permanent_id)
                collision = await session.scalar(select(BrokerSubmissionIntent.id).where(
                    BrokerSubmissionIntent.account_id == account_id,
                    BrokerSubmissionIntent.account_binding == intent.account_binding,
                    BrokerSubmissionIntent.permanent_id == permanent,
                    BrokerSubmissionIntent.id != intent.id,
                ))
                if collision:
                    state, reason, receipt = "uncertain", "BROKER_PERMANENT_ID_CONFLICT", None
                else:
                    intent.permanent_id = permanent
            intent.state = state
            self._append(session, intent, "outcome:" + attempt_id, state,
                         {"attempt_id": attempt_id, "reason_code": reason,
                          "receipt_sha256": digest(receipt.model_dump(mode="json")) if receipt else None})
            return _view(intent)

    def _track(self, task, token):
        # Admission remains occupied until actual completion, including when a
        # synthetic coroutine ignores cancellation. No late result is persisted.
        self._unfinished.add(task)

        def finished(done):
            self._unfinished.discard(done)
            _release(token)
            if not done.cancelled():
                done.exception()

        task.add_done_callback(finished)

    async def dispatch_once(self, *, user_id, account_id, intent_id, transport: OfflineTransport | None = None,
                            timeout_seconds=None):
        if transport is None:
            # This path does not even connect to a database or inspect credentials.
            return dict(external_write_denied("broker submission"), state="blocked", attempt_id=None,
                        scope="offline_contract", execution_authority="none")
        if (type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds)
                or not 0 < timeout_seconds <= 30
                or not inspect.iscoroutinefunction(getattr(transport, "submit", None))):
            raise PolicyDenied("INVALID_OFFLINE_TRANSPORT")
        await self._fixture()
        token, task = _admit(), None
        try:
            async with self.sessions.begin() as session:
                intent, request = await self._load(session, user_id=user_id, account_id=account_id, intent_id=intent_id)
                if intent.state != "staged":
                    return _view(intent)
                intent.attempt_id = str(uuid.uuid4())
                intent.state = "handoff_started"
                self._append(session, intent, "handoff", "handoff_started",
                             {"attempt_id": intent.attempt_id, "request_sha256": intent.request_sha256,
                              "timeout_seconds": timeout_seconds})
                attempt = intent.attempt_id
            # Commit before final scope check and handoff. A lost process here
            # leaves durable uncertainty, never an automatically retryable intent.
            await self._fixture()
            async with self.sessions.begin() as session:
                intent, request = await self._load(session, user_id=user_id, account_id=account_id, intent_id=intent_id)
                if intent.state != "handoff_started" or intent.attempt_id != attempt:
                    return _view(intent)
            args = dict(user_id=user_id, account_id=account_id, intent_id=intent_id, attempt_id=attempt)

            async def invoke():
                return await transport.submit(request, intent_id=intent_id, attempt_id=attempt)

            task = asyncio.create_task(invoke())
            self._track(task, token)
            try:
                done, _ = await asyncio.wait({task}, timeout=timeout_seconds)
                if not done:
                    task.cancel()
                    return await self._outcome(**args, state="uncertain", reason="OFFLINE_HANDOFF_TIMEOUT")
                try:
                    receipt = task.result()
                except Exception:
                    # Only transport exceptions become uncertain outcomes. A
                    # persistence failure propagates for inspected recovery; it
                    # is not silently retried as another outcome write.
                    return await self._outcome(**args, state="uncertain", reason="OFFLINE_HANDOFF_EXCEPTION")
                if not isinstance(receipt, TransportReceipt):
                    return await self._outcome(**args, state="uncertain", reason="OFFLINE_RECEIPT_INVALID")
                try:
                    receipt = TransportReceipt.model_validate(receipt)
                except ValueError:
                    return await self._outcome(**args, state="uncertain", reason="OFFLINE_RECEIPT_INVALID")
                if receipt.client_id != request.client_id or receipt.order_id != request.order_id:
                    return await self._outcome(**args, state="uncertain", reason="OFFLINE_RECEIPT_INVALID")
                return await self._outcome(**args, state=receipt.status, reason="OFFLINE_TRANSPORT_RECEIPT",
                                           receipt=receipt)
            except asyncio.CancelledError:
                task.cancel()
                await asyncio.shield(self._outcome(**args, state="uncertain", reason="OFFLINE_HANDOFF_CANCELLED"))
                raise
        finally:
            if task is None:
                _release(token)

    async def recover_uncertain(self, *, user_id, account_id, intent_id):
        """Conservatively close a lost handoff; never grants a retry or cancels it."""
        await self._fixture()
        async with self.sessions.begin() as session:
            intent, _ = await self._load(session, user_id=user_id, account_id=account_id,
                                          intent_id=intent_id, dispatch=False)
            if intent.state == "handoff_started":
                intent.state = "uncertain"
                self._append(session, intent, "recovery:" + intent.attempt_id, "uncertain",
                             {"reason_code": "HANDOFF_RECOVERY_UNCERTAIN", "attempt_id": intent.attempt_id})
            return _view(intent)

    async def attach_observation(self, *, user_id, account_id, intent_id, observation_id):
        await self._fixture()
        async with self.sessions.begin() as session:
            intent, request = await self._load(session, user_id=user_id, account_id=account_id,
                                               intent_id=intent_id, dispatch=False)
            size = await session.scalar(select(func.octet_length(cast(BrokerObservation.payload, Text))).where(
                BrokerObservation.id == _id(observation_id), BrokerObservation.user_id == user_id,
                BrokerObservation.account_id == account_id, BrokerObservation.account_binding == intent.account_binding,
            ))
            if size is None or size > READ_PAYLOAD_BUDGET:
                raise PolicyDenied("SUBMISSION_OBSERVATION_NOT_BOUND")
            row = await session.scalar(select(BrokerObservation).where(
                BrokerObservation.id == _id(observation_id), BrokerObservation.user_id == user_id,
                BrokerObservation.account_id == account_id, BrokerObservation.account_binding == intent.account_binding,
            ))
            if row is None or digest(row.payload) != row.payload_sha256:
                raise PolicyDenied("SUBMISSION_OBSERVATION_NOT_BOUND")
            payload = row.payload
            if row.kind in {"execution", "order_status"}:
                if (intent.permanent_id is None or payload.get("permanent_id") != int(intent.permanent_id)
                        or payload.get("client_id") != request.client_id
                        or payload.get("order_id") != request.order_id):
                    raise PolicyDenied("SUBMISSION_STABLE_BROKER_ID_REQUIRED")
                # Stable identity associates the evidence, not ownership or
                # correctness. Contract/price/quantity outliers remain visible
                # and are flagged by review_intent instead of being discarded.
            elif row.kind == "commission":
                linked = await session.scalar(select(BrokerObservation.id).join(
                    BrokerSubmissionEvent, BrokerSubmissionEvent.observation_id == BrokerObservation.id,
                ).where(BrokerSubmissionEvent.intent_id == intent.id, BrokerObservation.kind == "execution",
                        BrokerObservation.identity_sha256 == row.identity_sha256))
                if linked is None:
                    raise PolicyDenied("SUBMISSION_LINKED_EXECUTION_REQUIRED")
            else:
                raise PolicyDenied("SUBMISSION_OBSERVATION_KIND_UNSUPPORTED")
            key = "observation:" + row.id
            if not await session.scalar(select(BrokerSubmissionEvent.id).where(
                BrokerSubmissionEvent.intent_id == intent.id, BrokerSubmissionEvent.event_key == key,
            )):
                self._append(session, intent, key, "observation_linked",
                             {"payload_sha256": row.payload_sha256, "identity_sha256": row.identity_sha256},
                             observation_id=row.id)
            return _view(intent)

    async def review_intent(self, *, user_id, account_id, intent_id):
        await self._fixture()
        async with self.sessions.begin() as session:
            intent, request = await self._load(session, user_id=user_id, account_id=account_id,
                                          intent_id=intent_id, dispatch=False)
            filters = (
                BrokerSubmissionEvent.intent_id == intent.id, BrokerObservation.user_id == user_id,
                BrokerObservation.account_id == account_id, BrokerObservation.account_binding == intent.account_binding,
            )
            metadata = (await session.execute(select(
                BrokerObservation.id, func.octet_length(cast(BrokerObservation.payload, Text)),
            ).join(BrokerSubmissionEvent, BrokerSubmissionEvent.observation_id == BrokerObservation.id)
                .where(*filters).order_by(BrokerObservation.recorded_at, BrokerObservation.id)
                .limit(MAX_OBSERVATIONS + 1))).all()
            chosen, size = [], 0
            for identity, count in metadata[:MAX_OBSERVATIONS]:
                if size + count > READ_PAYLOAD_BUDGET:
                    break
                chosen.append(identity)
                size += count
            rows = (await session.scalars(select(BrokerObservation).where(
                BrokerObservation.id.in_(chosen), BrokerObservation.user_id == user_id,
                BrokerObservation.account_id == account_id, BrokerObservation.account_binding == intent.account_binding,
            ).order_by(BrokerObservation.recorded_at, BrokerObservation.id))).all() if chosen else []
            observations = [{"kind": row.kind, "payload": row.payload, "identity_sha256": row.identity_sha256,
                             "payload_sha256": row.payload_sha256} for row in rows]
            review = review_observations(observations, truncated=len(chosen) < len(metadata))
            review.pop("evidence_sha256")
            comparison = _compare_request(request, observations, review)
            review["request_comparison"] = comparison
            review["reason_codes"] = sorted(set(review["reason_codes"]) | set(comparison["reason_codes"]))
            if review["reason_codes"]:
                review["status"] = "needs_review"
            review["evidence_sha256"] = digest(review)
            return dict(_view(intent), review=review, linked_observations=len(rows), payload_bytes=size,
                        strategy_order_ownership="not_established", current_broker_state="not_established")
