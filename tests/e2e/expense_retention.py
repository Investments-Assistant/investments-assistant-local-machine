"""Age one known synthetic row, then exercise real browser retention controls."""

import os
import asyncio
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import text
from playwright.sync_api import expect
from sqlalchemy.ext.asyncio import create_async_engine


async def age_fixture(username):
    assert username.startswith("fixture-browser-a-")
    engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
    try:
        async with engine.begin() as connection:
            assert (await connection.scalar(text("SELECT current_database()"))).startswith("test_")
            assert (
                await connection.scalar(text("SELECT token FROM public.ia_disposable_marker"))
                == os.environ["TEST_DATABASE_DISPOSABLE_TOKEN"]
            )
            row = (
                await connection.execute(
                    text("""
                SELECT e.id FROM expense_transactions e JOIN users u ON e.user_id = u.id
                WHERE u.username = :username AND e.provider = 'manual'
                ORDER BY e.id LIMIT 1
            """),
                    {"username": username},
                )
            ).scalar_one()
            await connection.execute(
                text("""
                UPDATE expense_transactions SET synced_at = now() - interval '60 days'
                WHERE id = :id
            """),
                {"id": row},
            )
            return row
    finally:
        await engine.dispose()


def verify_retention(page, context, base, username):
    # Playwright's synchronous facade already owns an event loop on this thread.
    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(lambda: asyncio.run(age_fixture(username))).result(timeout=10)
    page.locator("#expense-retention-controls summary").click()
    expect(page.locator("#expense-retention-apply")).to_be_disabled()
    page.locator("#expense-retain-days").fill("30")
    page.locator("#expense-retention-preview").click()
    expect(page.locator("#expense-retention-status")).to_contain_text("1 raw copies in this batch")
    expect(page.locator("#expense-retention-apply")).to_be_disabled()
    page.locator("#expense-retention-confirm").check()
    page.locator("#expense-retention-apply").click()
    expect(page.locator("#expense-retention-status")).to_contain_text("Removed 1 raw copies")
    expect(page.locator("#expenses-transactions-body tr")).to_have_count(200)
    page.locator("#expense-retention-preview").click()
    expect(page.locator("#expense-retention-status")).to_contain_text("No raw copies match this age")
    expect(page.locator("#expense-retention-apply")).to_be_disabled()
    denied = context.request.post(base + "/api/expenses/retention/preview", data={"retain_days": 30})
    assert denied.status == 403
