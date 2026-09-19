"""Explicit report removal in a real browser with one owned aged synthetic PDF."""

import os
import asyncio
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import text
from playwright.sync_api import expect
from sqlalchemy.ext.asyncio import create_async_engine


async def age_fixture(username, report_id):
    assert username.startswith("fixture-browser-a-")
    engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
    try:
        async with engine.begin() as connection:
            assert (await connection.scalar(text("SELECT current_database()"))).startswith("test_")
            assert await connection.scalar(text("SELECT token FROM public.ia_disposable_marker")) == os.environ[
                "TEST_DATABASE_DISPOSABLE_TOKEN"
            ]
            result = await connection.execute(text("""
                UPDATE reports SET created_at = now() - interval '60 days'
                WHERE id = :id AND user_id IN (SELECT id FROM users WHERE username = :username)
            """), {"id": report_id, "username": username})
            assert result.rowcount == 1
    finally:
        await engine.dispose()


def verify_report_retention(page, context, other, base, csrf, username, report_id):
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(lambda: asyncio.run(age_fixture(username, report_id))).result(timeout=15)
    page.locator("#report-retention-controls summary").click()
    expect(page.locator("#report-retention-apply")).to_be_disabled()
    page.locator("#report-retain-days").fill("30")
    page.locator("#report-retention-preview").click()
    expect(page.locator("#report-retention-status")).to_contain_text("1 reports in this batch")
    plan = context.request.post(
        base + "/api/reports/retention/preview", headers={"X-CSRF-Token": csrf}, data={"retain_days": 30}
    ).json()
    other_csrf = next(cookie["value"] for cookie in other.cookies() if cookie["name"] == "ia_csrf")
    body = {"policy": plan["policy"], "plan_sha256": plan["plan_sha256"], "confirm_report_content_removal": True}
    assert other.request.post(
        base + "/api/reports/retention/apply", headers={"X-CSRF-Token": other_csrf}, data=body
    ).status == 409
    assert context.request.post(base + "/api/reports/retention/apply", data=body).status == 403
    assert context.request.post(
        base + "/api/reports/retention/apply", headers={"X-CSRF-Token": csrf},
        data=dict(body, confirm_report_content_removal=False),
    ).status == 422
    page.locator("#report-retention-confirm").check()
    page.locator("#report-retention-apply").click()
    expect(page.locator("#report-retention-status")).to_contain_text("0 PDF cleanups pending")
    assert context.request.get(base + f"/api/reports/{report_id}/pdf").status == 410
    assert other.request.get(base + f"/api/reports/{report_id}/pdf").status == 404
    page.reload()
    expect(page.locator("#reports-list")).to_contain_text("Content removed by owner")
    page.locator("#report-retention-controls summary").click()
    page.locator("#report-retain-days").fill("30")
    page.locator("#report-retention-preview").click()
    expect(page.locator("#report-retention-status")).to_contain_text("No reports match this age")
