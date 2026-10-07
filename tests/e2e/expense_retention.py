"""Age one known synthetic row, then exercise real browser retention controls."""

import os
import asyncio
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import text
from playwright.sync_api import expect
from sqlalchemy.ext.asyncio import create_async_engine


async def age_fixture(username, history=False):
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
            if history:
                await connection.execute(
                    text("UPDATE expense_transactions SET occurred_at = now() - interval '60 days' WHERE id=:id"),
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


def verify_history_retention(page, context, other, base, csrf, username, transactions, screenshots):
    import json
    from pathlib import Path

    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(lambda: asyncio.run(age_fixture(username, history=True))).result(timeout=10)
    page.locator("#expense-history-controls summary").click()
    page.locator("#expense-history-days").fill("1")
    expect(page.locator("#expense-history-apply")).to_be_disabled()
    with page.expect_download() as exported:
        page.locator("#expense-history-preview").click()
    evidence = json.loads(Path(exported.value.path()).read_text())
    assert evidence["count"] == 1 and evidence["status"] == "complete_batch"
    assert "raw_data" not in evidence["records"][0]
    expect(page.locator("#expense-history-status")).to_contain_text("1 transactions in this batch")
    expect(page.locator("#expense-history-apply")).to_be_disabled()
    plan = page.evaluate("expenseHistoryPlan")
    denied = context.request.post(base + "/api/expenses/retention/history/preview", data={"retain_days": 1})
    assert denied.status == 403
    other_csrf = next(c["value"] for c in other.cookies() if c["name"] == "ia_csrf")
    cross = other.request.post(
        base + "/api/expenses/retention/history/apply",
        headers={"X-CSRF-Token": other_csrf},
        data={
            "policy": plan["policy"],
            "plan_sha256": plan["plan_sha256"],
            "export_sha256": plan["export_sha256"],
            "confirm_history_removal": True,
            "confirm_export_saved": True,
        },
    )
    assert cross.status == 409
    page.locator("#expense-history-confirm").check()
    page.locator("#expense-history-apply").click()
    expect(page.locator("#expense-history-status")).to_contain_text("Removed 1 transactions")
    page.locator("#expense-import-file").set_input_files(
        dict(
            name="synthetic-reimport.json",
            mimeType="application/json",
            buffer=json.dumps(dict(provider="manual", transactions=transactions)).encode(),
        )
    )
    page.locator("#expense-import-submit").click()
    expect(page.locator("#expense-import-status")).to_contain_text("updated 201; skipped retired 1")
    page.locator("#expense-history-controls").scroll_into_view_if_needed()
    page.screenshot(path=str(screenshots / "expense-history-desktop.png"))
    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_function("document.getElementById('sidebar').getBoundingClientRect().right <= 1")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.locator("#expense-history-controls").scroll_into_view_if_needed()
    page.screenshot(path=str(screenshots / "expense-history-mobile.png"))
    page.set_viewport_size({"width": 1440, "height": 1000})
