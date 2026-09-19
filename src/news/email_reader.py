"""IMAP newsletter reader.

Connects to your email account and ingests investment newsletters into the
private news memory of an explicitly selected active application user.
Email content is untrusted evidence, never authority.

Setup (Gmail example):
1. In Gmail settings → Forwarding and POP/IMAP → enable IMAP.
2. If 2-Factor Auth is on, create an App Password:
   Google Account → Security → App Passwords → "Mail" → your device.
3. Set in .env:
       NEWSLETTER_OWNER_USER_ID=<explicit application user UUID>
       NEWSLETTER_IMAP_SERVER=imap.gmail.com
       NEWSLETTER_IMAP_PORT=993
       NEWSLETTER_EMAIL_USER=your@gmail.com
       NEWSLETTER_EMAIL_PASSWORD=xxxx xxxx xxxx xxxx   # 16-char app password
       NEWSLETTER_SENDER_FILTER=newsletter@example.com  # sender to watch for
"""

from __future__ import annotations

import re
import email
from typing import Any
import asyncio
import hashlib
import imaplib
from datetime import UTC, datetime, timedelta
from contextlib import suppress
from html.parser import HTMLParser
from email.header import decode_header

from src.config import settings
from src.db.database import async_session
from src.news.ingestion import ingest_articles
from src.security.sessions import SessionInactive, assert_active
from src.agent.utils.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# HTML → plain text (no extra deps)
# ---------------------------------------------------------------------------


class _HTMLStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def get_text(self) -> str:
        return " ".join(self._parts)


def _strip_html(html: str) -> str:
    stripper = _HTMLStripper()
    stripper.feed(html)
    return re.sub(r"\s+", " ", stripper.get_text()).strip()


# ---------------------------------------------------------------------------
# Header decoding
# ---------------------------------------------------------------------------


def _decode_header_value(value: str) -> str:
    parts = decode_header(value)
    decoded = []
    for chunk, charset in parts:
        if isinstance(chunk, bytes):
            decoded.append(chunk.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(chunk)
    return "".join(decoded)


# ---------------------------------------------------------------------------
# Email body extraction
# ---------------------------------------------------------------------------


def _extract_body(msg: email.message.Message) -> str:
    """Return the plaintext body of an email (prefers text/plain over HTML)."""
    plain: list[str] = []
    html: list[str] = []

    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            charset = part.get_content_charset() or "utf-8"
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            text = (
                payload.decode(charset, errors="replace")
                if isinstance(payload, bytes)
                else str(payload)
            )
            if ct == "text/plain":
                plain.append(text)
            elif ct == "text/html":
                html.append(_strip_html(text))
    else:
        payload = msg.get_payload(decode=True)
        charset = msg.get_content_charset() or "utf-8"
        if payload:
            text = (
                payload.decode(charset, errors="replace")
                if isinstance(payload, bytes)
                else str(payload)
            )
            ct = msg.get_content_type()
            if ct == "text/html":
                html.append(_strip_html(text))
            else:
                plain.append(text)

    return "\n\n".join(plain or html)


# ---------------------------------------------------------------------------
# IMAP search + ingestion
# ---------------------------------------------------------------------------


def _imap_connect() -> imaplib.IMAP4_SSL | None:
    if not settings.newsletter_email_user or not settings.newsletter_email_password:
        logger.debug("Newsletter IMAP credentials not configured — skipping")
        return None
    try:
        conn = imaplib.IMAP4_SSL(
            settings.newsletter_imap_server, settings.newsletter_imap_port, timeout=10
        )
        conn.login(settings.newsletter_email_user, settings.newsletter_email_password)
        return conn
    except Exception as exc:
        logger.warning("IMAP login failed: %s", type(exc).__name__)
        return None


def _build_search_criteria(since_days: int) -> str:
    since_date = (datetime.now(UTC) - timedelta(days=since_days)).strftime("%d-%b-%Y")
    criteria = f'(SINCE "{since_date}")'
    if settings.newsletter_sender_filter:
        criteria = f'(FROM "{settings.newsletter_sender_filter}" SINCE "{since_date}")'
    return criteria


async def read_and_ingest_newsletters(since_days: int = 8) -> dict:
    """Fetch unseen newsletters via IMAP and ingest them.

    By default looks back 8 days so a weekly Saturday newsletter is always
    caught even if the job fires a day late.

    Returns stats dict: {"fetched": N, "inserted": M}.
    """
    owner = settings.newsletter_owner_user_id
    if not owner:
        return {
            "fetched": 0,
            "inserted": 0,
            "status": "blocked",
            "reason": "NEWSLETTER_OWNER_REQUIRED",
        }
    try:
        async with async_session() as session:
            await assert_active(session, owner)
    except SessionInactive:
        return {"fetched": 0, "inserted": 0, "status": "blocked", "reason": "PRINCIPAL_INACTIVE"}
    articles = await asyncio.to_thread(_fetch_newsletters, since_days)
    if articles is None:
        return {"fetched": 0, "inserted": 0, "status": "unavailable"}
    # Revalidate after fetching; a deactivated owner cannot persist new private data.
    inserted = await ingest_articles(articles, owner_user_id=owner)
    logger.info("Newsletter ingestion: fetched=%d new=%d", len(articles), inserted)
    return {"fetched": len(articles), "inserted": inserted, "status": "complete"}


def _fetch_newsletters(since_days: int):
    conn = _imap_connect()
    if conn is None:
        return None
    articles: list[dict[str, Any]] = []
    try:
        conn.select("INBOX", readonly=True)
        criteria = _build_search_criteria(since_days)
        _, msg_nums = conn.search(None, criteria)

        raw_nums = msg_nums[0] if msg_nums else b""
        for num in (raw_nums or b"").split()[-50:]:
            try:
                _, data = conn.fetch(num.decode("ascii"), "(BODY.PEEK[]<0.2097153>)")
                raw = data[0][1] if data and data[0] else None
                if not isinstance(raw, bytes) or len(raw) > 2 * 1024 * 1024:
                    continue
                msg = email.message_from_bytes(raw)
                subject = _decode_header_value(msg.get("Subject", "Newsletter"))
                body = _extract_body(msg)

                if not body.strip():
                    continue

                # Hash mailbox and stable message identity; never emit addresses in URLs.
                # Without Message-ID, content identity survives IMAP sequence renumbering.
                msg_id = msg.get("Message-ID") or hashlib.sha256(raw).hexdigest()
                identity = settings.newsletter_email_user + "\0" + msg_id
                url = "newsletter://" + hashlib.sha256(identity.encode()).hexdigest()
                source_name = "Newsletter"

                articles.append(
                    {
                        "title": subject[:500],
                        "summary": body[:2000],
                        "content": body[:10000],
                        "source": source_name,
                        "url": url,
                        "published_at": None,
                        "sentiment_label": "neutral",
                        "sentiment_score": 0.0,
                        "tags": [],
                    }
                )
                logger.debug("Newsletter parsed")
            except Exception as exc:
                logger.warning("Newsletter parsing failed: %s", type(exc).__name__)

    finally:
        with suppress(Exception):
            conn.logout()

    return articles
