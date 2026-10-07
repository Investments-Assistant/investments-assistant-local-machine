"""Operator-supplied source permissions; publisher text cannot grant these rights."""

from typing import Literal
from datetime import UTC, datetime
from urllib.parse import urlsplit

from pydantic import Field, BaseModel, ConfigDict, field_validator, model_validator

from src.execution.policy import PolicyDenied, digest


class SourcePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    policy_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    permission_basis: Literal["operator_reviewed_permission"]
    terms_url: str = Field(max_length=2048)
    reviewed_at: datetime
    review_due_at: datetime
    transport: Literal["public_https", "private_newsletter"] = "public_https"
    article_hosts: list[str] = Field(default_factory=list, max_length=30)
    content_scope: Literal["headline", "summary", "full_text"]
    retention_days: int = Field(ge=1, le=36525, strict=True)
    maximum_content_characters: int = Field(default=20000, ge=1, le=100000, strict=True)

    @model_validator(mode="after")
    def transport_scope(self):
        if (self.transport == "public_https") != bool(self.article_hosts):
            raise ValueError("Public policies require article hosts; private newsletter policies must omit them")
        return self

    @field_validator("terms_url")
    @classmethod
    def public_terms_reference(cls, value):
        parts = urlsplit(value)
        if (
            parts.scheme != "https" or not parts.hostname or parts.username or parts.password
            or any(ord(char) < 33 for char in value)
        ):
            raise ValueError("Terms reference must be an HTTPS URL without credentials")
        return value

    @field_validator("article_hosts")
    @classmethod
    def exact_hosts(cls, values):
        normalized = []
        for value in values:
            host = value.encode("idna").decode("ascii").lower()
            if not host or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789.-" for char in host):
                raise ValueError("Exact article hostnames required")
            if host.startswith(".") or host.endswith(".") or ".." in host:
                raise ValueError("Invalid article hostname")
            normalized.append(host)
        return sorted(set(normalized))

    def validate_current(self, now=None):
        now = now or datetime.now(UTC)
        if self.reviewed_at.tzinfo is None or self.review_due_at.tzinfo is None:
            raise PolicyDenied("SOURCE_POLICY_TIME_INVALID")
        if not self.reviewed_at <= now < self.review_due_at:
            raise PolicyDenied("SOURCE_POLICY_REVIEW_REQUIRED")
        return self

    @property
    def fingerprint(self):
        return digest(self.model_dump(mode="json"))


def source_policy(settings, identity, *, now=None):
    registry = settings.news_source_policies
    if not isinstance(registry, dict) or identity not in registry:
        raise PolicyDenied("SOURCE_PERMISSION_REQUIRED")
    return SourcePolicy.model_validate(registry[identity]).validate_current(now)


def newsletter_identity(settings):
    """Bind private permission to the configured owner/mailbox/server/filter, never its password."""
    return "newsletter:" + digest({
        "owner": settings.newsletter_owner_user_id, "server": settings.newsletter_imap_server,
        "port": settings.newsletter_imap_port, "mailbox": settings.newsletter_email_user,
        "sender_filter": settings.newsletter_sender_filter,
    })


def permitted_articles(articles, policy, *, identity):
    """Project only the operator-permitted text, retaining truthful omission metadata."""
    policy.validate_current()
    if len(articles) > 200:
        raise PolicyDenied("SOURCE_POLICY_BATCH_LIMIT")
    result = []
    for original in articles:
        url = urlsplit(original.get("url", ""))
        private = policy.transport == "private_newsletter"
        valid_private = (
            url.scheme == "newsletter" and not url.path and not url.query and not url.fragment and len(url.netloc) == 64
            and all(char in "0123456789abcdef" for char in url.netloc)
        )
        valid_public = (
            url.scheme == "https" and not url.username and not url.password and url.hostname in policy.article_hosts
        )
        if not (valid_private if private else valid_public):
            raise PolicyDenied("SOURCE_ARTICLE_HOST_NOT_PERMITTED")
        row = dict(original)
        omitted = []
        for field in ("summary", "content"):
            allowed = policy.content_scope == "full_text" or field == "summary" and policy.content_scope == "summary"
            if not allowed:
                if row.get(field):
                    omitted.append(field)
                row[field] = "" if field == "summary" else None
            elif row.get(field) is not None:
                value = str(row[field])
                row[field] = value[:policy.maximum_content_characters]
                if len(value) > policy.maximum_content_characters:
                    omitted.append(field + "_truncated")
        if omitted:
            from src.news.sources import _sentiment, _extract_tags

            permitted_text = f"{row.get('title') or ''} {row.get('summary') or ''} {row.get('content') or ''}"
            row["tags"] = _extract_tags(permitted_text)
            row["sentiment_label"], row["sentiment_score"] = _sentiment(permitted_text)
            row.pop("sentiment", None)
            omitted.append("derived_observations_recomputed")
        row["source_policy"] = {
            "identity": identity, "sha256": policy.fingerprint, "policy": policy.model_dump(mode="json"),
            "authority": "operator_attestation_not_independent_license_verification", "omitted": omitted,
        }
        result.append(row)
    return result
