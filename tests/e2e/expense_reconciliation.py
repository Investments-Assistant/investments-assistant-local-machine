"""Real browser selection/export/confirmation; synthetic records and no bank calls."""

import json
from pathlib import Path
from datetime import UTC, datetime

from playwright.sync_api import expect


def verify_reconciliation(page, context, other, base, csrf, screenshots):
    page.set_viewport_size({"width": 1440, "height": 1000})
    page.get_by_role("button", name="Expenses", exact=True).click()
    page.locator("#expenses-period").select_option("year")
    day = datetime.now(UTC).date().isoformat()
    records = [
        dict(
            transactionId="reconcile-" + state,
            account_id="synthetic-reconciliation-bank",
            amount=amount,
            currency="EUR",
            date=day + "T23:00:00Z",
            lifecycle=state,
            merchant="Reconciliation " + state + " fixture",
        )
        for state, amount in (("pending", "-4.00"), ("booked", "-4.25"))
    ]
    file = dict(
        name="synthetic-reconciliation.json",
        mimeType="application/json",
        buffer=json.dumps(dict(provider="manual", transactions=records)).encode(),
    )
    page.locator("#expense-import-file").set_input_files(file)
    page.locator("#expense-import-submit").click()
    expect(page.locator("#expense-import-status")).to_contain_text("Imported 2; updated 0")

    def transactions():
        response = context.request.get(base + "/api/expenses?period=year&limit=200")
        assert response.status == 200
        return {row["external_id"]: row for row in response.json()["transactions"]}

    before = transactions()
    pending = before["reconcile-pending"]
    booked = before["reconcile-booked"]
    pending_row = page.locator("#expenses-transactions-body tr").filter(has_text="Reconciliation pending fixture")
    with page.expect_response(lambda response: response.request.method == "PATCH" and "/category" in response.url):
        pending_row.locator("select").select_option("health")
    expect(pending_row.locator("select")).to_have_value("health")
    assert transactions()["reconcile-pending"]["received_at"] == pending["received_at"]
    pending_row.get_by_role("button", name="Resolve pending", exact=True).click()
    expect(page.locator("#expense-reconciliation-apply")).to_be_disabled()
    booked_row = page.locator("#expenses-transactions-body tr").filter(has_text="Reconciliation booked fixture")
    with (
        page.expect_download() as download,
        page.expect_response(lambda response: "/reconciliation/preview" in response.url) as preview,
    ):
        booked_row.get_by_role("button", name="Review as booked match", exact=True).click()
    exported = json.loads(Path(download.value.path()).read_text())
    assert exported["pending"]["id"] == pending["id"] and exported["booked"]["id"] == booked["id"]
    assert "raw_data" not in exported["pending"]
    plan = preview.value.json()["plan"]
    expect(page.locator("#expense-reconciliation-status")).to_contain_text(
        "Your pending category override will carry over"
    )
    expect(page.locator("#expense-reconciliation-apply")).to_be_disabled()
    pair = dict(pending_id=pending["id"], booked_id=booked["id"])
    assert context.request.post(base + "/api/expenses/reconciliation/preview", data=pair).status == 403
    other_csrf = next(cookie["value"] for cookie in other.cookies() if cookie["name"] == "ia_csrf")
    denied = other.request.post(
        base + "/api/expenses/reconciliation/preview", data=pair, headers={"X-CSRF-Token": other_csrf}
    )
    assert denied.status == 409 and denied.json()["detail"]["reason_code"] == "TRANSACTIONS_NOT_OWNED"
    apply = pair | dict(
        as_of=plan["as_of"],
        plan_sha256=plan["plan_sha256"],
        export_sha256=plan["export_sha256"],
        confirm_same_transaction=True,
        confirm_export_saved=True,
    )
    assert (
        context.request.post(
            base + "/api/expenses/reconciliation/apply",
            data=apply | {"confirm_same_transaction": False},
            headers={"X-CSRF-Token": csrf},
        ).status
        == 422
    )
    assert (
        context.request.post(
            base + "/api/expenses/reconciliation/apply",
            data=apply | {"export_sha256": "0" * 64},
            headers={"X-CSRF-Token": csrf},
        ).status
        == 409
    )
    page.locator("#expense-reconciliation-controls").scroll_into_view_if_needed()
    page.screenshot(path=str(screenshots / "expense-reconciliation-desktop.png"))
    page.set_viewport_size({"width": 390, "height": 844})
    page.locator("#expense-reconciliation-controls").scroll_into_view_if_needed()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.screenshot(path=str(screenshots / "expense-reconciliation-mobile.png"))
    page.locator("#expense-reconciliation-confirm").check()
    page.locator("#expense-reconciliation-apply").click()
    expect(page.locator("#expense-reconciliation-status")).to_contain_text("Removed the reviewed pending entry")
    after = transactions()
    assert "reconcile-pending" not in after
    assert after["reconcile-booked"]["amount_exact"] == booked["amount_exact"]
    assert after["reconcile-booked"]["received_at"] == booked["received_at"]
    assert after["reconcile-booked"]["category"] == "health"
    assert (
        context.request.post(
            base + "/api/expenses/reconciliation/apply", data=apply, headers={"X-CSRF-Token": csrf}
        ).status
        == 409
    )
    page.set_viewport_size({"width": 1440, "height": 1000})
    page.locator("#expense-import-file").set_input_files(file)
    page.locator("#expense-import-submit").click()
    expect(page.locator("#expense-import-status")).to_contain_text("Imported 0; updated 1; skipped retired 1")
    assert "reconcile-pending" not in transactions()
