"""Owner chat removal uses the real browser/API and retains evidence tombstones."""

import os
import asyncio
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import text
from playwright.sync_api import expect
from sqlalchemy.ext.asyncio import create_async_engine


async def age_fixture(username, conversation_id):
    assert username.startswith("fixture-browser-a-")
    engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
    try:
        async with engine.begin() as connection:
            assert (await connection.scalar(text("SELECT current_database()"))).startswith("test_")
            assert await connection.scalar(text("SELECT token FROM public.ia_disposable_marker")) == os.environ[
                "TEST_DATABASE_DISPOSABLE_TOKEN"
            ]
            result = await connection.execute(text("""
                UPDATE conversations SET updated_at = now() - interval '60 days',
                    last_message_at = now() - interval '60 days'
                WHERE id = :id AND user_id IN (SELECT id FROM users WHERE username = :username)
            """), {"id": conversation_id, "username": username})
            assert result.rowcount == 1
    finally:
        await engine.dispose()


def verify_chat_retention(page, context, other, base, csrf, username, evidence_url):
    conversation = page.evaluate("sessionStorage.getItem('ia_active_conversation_id')")
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(lambda: asyncio.run(age_fixture(username, conversation))).result(timeout=15)
    plan = context.request.post(
        base + "/api/chat/retention/preview", headers={"X-CSRF-Token": csrf}, data={"retain_days": 30}
    ).json()
    assert plan["message_count"] > 0 and plan["active_turns_excluded"]
    other_csrf = next(cookie["value"] for cookie in other.cookies() if cookie["name"] == "ia_csrf")
    body = {"policy": plan["policy"], "plan_sha256": plan["plan_sha256"], "confirm_chat_content_removal": True}
    assert other.request.post(
        base + "/api/chat/retention/apply", headers={"X-CSRF-Token": other_csrf}, data=body
    ).status == 409
    assert context.request.post(base + "/api/chat/retention/apply", data=body).status == 403
    assert context.request.post(
        base + "/api/chat/retention/apply", headers={"X-CSRF-Token": csrf},
        data=dict(body, confirm_chat_content_removal=False),
    ).status == 422
    page.locator("#chat-retention-controls summary").click()
    page.locator("#chat-retain-days").fill("30")
    expect(page.locator("#chat-retention-apply")).to_be_disabled()
    page.locator("#chat-retention-preview").click()
    expect(page.locator("#chat-retention-status")).to_contain_text("messages in this batch")
    page.locator("#chat-retention-confirm").check()
    page.locator("#chat-retention-apply").click()
    expect(page.locator("#chat-retention-status")).to_contain_text(f'Removed {plan["message_count"]} chat messages')
    tombstone = context.request.get(base + evidence_url)
    assert tombstone.status == 200
    assert tombstone.json()["state"] == "retired" and tombstone.json()["evidence"] == []
    assert tombstone.json()["retention"]["content_sha256"]
    assert other.request.get(base + evidence_url).status == 404
    page.reload()
    expect(page.locator(".chat-evidence-note").first).to_contain_text("Content removed by owner")
    page.locator("#chat-retention-controls summary").click()
    page.locator("#chat-retain-days").fill("30")
    page.locator("#chat-retention-preview").click()
    expect(page.locator("#chat-retention-status")).to_contain_text("No inactive chats match")
