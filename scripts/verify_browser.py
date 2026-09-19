"""Real Chromium + isolated application routes; deterministic inference tier."""

import os
import sys
import json
import time
import uuid
import socket
from pathlib import Path
from datetime import UTC, datetime
import subprocess
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    if not os.environ.get("TEST_DATABASE_URL") or not os.environ.get("TEST_DATABASE_DISPOSABLE_TOKEN"):
        raise SystemExit("Explicit disposable database URL and marker are required")
    run_id = uuid.uuid4().hex[:12]
    user_a, user_b = f"fixture-browser-a-{run_id}", f"fixture-browser-b-{run_id}"
    os.environ["BROWSER_FIXTURE_USERS"] = f"{user_a},{user_b}"
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    screenshots = Path("/tmp/ia-browser-evidence")
    screenshots.mkdir(exist_ok=True)
    with (screenshots / "server.log").open("w") as log:
        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "tests.e2e.fixture_server:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            stdout=log,
            stderr=log,
        )
        try:
            for _ in range(100):
                if server.poll() is not None:
                    raise RuntimeError("Fixture server exited; inspect /tmp/ia-browser-evidence/server.log")
                try:
                    with urlopen(base + "/api/health", timeout=1) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(0.1)
            else:
                raise RuntimeError("Fixture server did not become available")
            with sync_playwright() as p:
                browser = p.chromium.launch()
                try:
                    context = browser.new_context(viewport={"width": 1440, "height": 1000})
                    page = context.new_page()
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    expected_errors = []

                    def console_message(msg):
                        if msg.type != "error":
                            return
                        if (
                            msg.location.get("url") == base + "/api/banks/synthetic-connection/account"
                            and msg.text
                            == "Failed to load resource: the server responded with a status of 409 (Conflict)"
                        ):
                            expected_errors.append(msg.text)
                        else:
                            errors.append(msg.text)

                    page.on("console", console_message)
                    page.goto(base + "/login")
                    page.locator("#username").fill(user_a)
                    page.locator("#password").fill("fixture-browser-password")
                    page.get_by_role("button", name="Sign in", exact=True).click()
                    page.wait_for_url(base + "/")
                    expect(page).to_have_title("Investment Assistant")
                    page.get_by_role("button", name="Portfolio", exact=True).click()
                    expect(page.locator("#portfolio-view")).to_be_visible()
                    page.get_by_role("button", name="Simulation", exact=True).click()
                    page.locator("#simulation-symbols").fill("FIXTURE")
                    page.locator("#simulation-capital").fill("100")
                    page.locator("#simulation-currency").select_option("EUR")
                    page.locator("#simulation-start").fill("2024-01-29")
                    page.locator("#simulation-end").fill("2024-02-03")
                    page.locator("#simulation-run-btn").click()
                    expect(page.locator("#simulation-status")).to_have_text("Complete", timeout=30000)
                    expect(page.locator("#sim-final-value")).to_contain_text("€")
                    expect(page.locator("#simulation-research-note")).to_contain_text("Synthetic source bars")
                    with page.expect_download() as replay_download:
                        page.locator("#simulation-evidence-link").click()
                    evidence = json.loads(Path(replay_download.value.path()).read_text())
                    from scripts.replay_saved_evidence import reproduce

                    assert reproduce(evidence)["status"] == "PASS"
                    assert float(evidence["result"]["fees"]) > 0
                    replay_id = context.request.get(base + "/api/simulations").json()[0]["id"]
                    page.locator("#fixture-create").click()
                    expect(page.locator("#fixture-details")).to_contain_text("Synthetic fixture only")
                    fixture = json.loads(page.locator("#fixture-details").inner_text())
                    page.locator("#fixture-propose").click()
                    expect(page.locator("#fixture-details")).to_contain_text('"status": "proposed"')
                    proposal = json.loads(page.locator("#fixture-details").inner_text())
                    page.screenshot(path=str(screenshots / "proposal-desktop.png"))
                    page.locator("#fixture-approve").click()
                    expect(page.locator("#fixture-details")).to_contain_text('"status": "submitted"')
                    page.locator("#fixture-tick").click()
                    expect(page.locator("#fixture-details")).to_contain_text('"status": "filled"')
                    account = context.request.get(base + "/api/simulator/accounts/" + fixture["account_id"]).json()
                    assert float(account["cash"]) == 899.9 and float(account["reserved"]) == 0
                    assert account["orders"][0]["status"] == "filled"
                    assert account["reconciliation"]["status"] == "consistent"
                    assert account["reconciliation"]["scope"] == "simulator_internal"
                    assert len(account["reconciliation"]["inputs_sha256"]) == 64
                    page.locator("#fixture-mandate-review").click()
                    expect(page.locator("#fixture-details")).to_contain_text('"status": "proposed"')
                    mandate = json.loads(page.locator("#fixture-details").inner_text())
                    assert mandate["details"]["specification"]["environment"] == "simulator"
                    expect(page.locator("#fixture-approve")).to_be_disabled()
                    page.locator("#fixture-mandate-approve").click()
                    expect(page.locator("#fixture-details")).to_contain_text('"status": "approved"')
                    page.locator("#fixture-halt").click()
                    expect(page.locator("#fixture-details")).to_contain_text('"halted": true')
                    expect(page.locator("#fixture-propose")).to_be_disabled()
                    expect(page.locator("#operational-alerts")).to_contain_text("Simulator stopped new orders")
                    page.locator("#operational-alerts").get_by_role("button", name="Acknowledge").last.click()
                    expect(page.locator("#operational-alerts")).to_contain_text("acknowledged")

                    page.screenshot(path=str(screenshots / "halted-desktop.png"))
                    # Same-session generic tool endpoint must not act as a human event.
                    csrf = next(c["value"] for c in context.cookies() if c["name"] == "ia_csrf")
                    denied = context.request.post(
                        base + "/api/tools/invoke",
                        headers={"X-CSRF-Token": csrf},
                        data={
                            "tool_name": "confirm_trade",
                            "tool_input": {"confirmation_id": proposal["order_id"]},
                        },
                    )
                    assert json.loads(denied.json()["result"])["reason_code"] == "HUMAN_APPROVAL_REQUIRED"
                    no_csrf = context.request.post(base + "/api/simulator/fixtures", data={})
                    assert no_csrf.status == 403
                    # Actual file input → authenticated import → bounded page controls.
                    page.get_by_role("button", name="Expenses", exact=True).click()
                    page.locator("#expenses-period").select_option("year")
                    expect(page.locator("#bank-access-status")).to_contain_text("Bank access is disabled")
                    expect(page.locator("#bank-consent")).to_be_disabled()
                    expect(page.locator("#bank-connections")).to_be_empty()
                    from tests.e2e.bank_controls import verify_bank_controls

                    verify_bank_controls(page)
                    assert len(expected_errors) == 1, expected_errors
                    day = datetime.now(UTC).date().isoformat()
                    transactions = [
                        dict(
                            transactionId=f"fixture-expense-{i}",
                            accountId="synthetic-bank",
                            amount="-1",
                            currency="EUR",
                            date=day + "T00:00:00Z",
                            merchant=f"Fixture shop {i}",
                        )
                        for i in range(200)
                    ]
                    transactions += [
                        dict(
                            transactionId="refund",
                            accountId="synthetic-bank",
                            amount="2",
                            type="refund",
                            currency="EUR",
                            date=day + "T12:00:00Z",
                            merchant="Fixture refund",
                        ),
                        dict(
                            transactionId="usd",
                            accountId="synthetic-bank",
                            amount="-3",
                            currency="USD",
                            date=day + "T11:00:00Z",
                            merchant="Fixture dollar",
                        ),
                    ]
                    page.locator("#expense-import-file").set_input_files(
                        dict(
                            name="synthetic-expenses.json",
                            mimeType="application/json",
                            buffer=json.dumps(dict(provider="manual", transactions=transactions)).encode(),
                        )
                    )
                    page.locator("#expense-import-submit").click()
                    expect(page.locator("#expense-import-status")).to_contain_text("Imported 202; updated 0")
                    expect(page.locator("#expenses-transactions-body tr")).to_have_count(200)
                    expect(page.locator("#expenses-total")).to_have_text("—")
                    expect(page.locator("#expenses-alerts")).to_contain_text("USD")
                    expect(
                        page.locator("#expenses-transactions-body tr")
                        .filter(has_text="Fixture refund")
                        .locator("td")
                        .last
                    ).to_contain_text("+")
                    page.locator("#expenses-next").click()
                    expect(page.locator("#expenses-transactions-body tr")).to_have_count(2)
                    page.locator("#expenses-prev").click()
                    expect(page.locator("#expenses-transactions-body tr")).to_have_count(200)
                    refund_category = (
                        page.locator("#expenses-transactions-body tr")
                        .filter(has_text="Fixture refund")
                        .locator("select")
                    )
                    expense_id = refund_category.get_attribute("data-transaction")
                    with page.expect_response(
                        lambda response: response.request.method == "PATCH" and "/category" in response.url
                    ) as category_response:
                        refund_category.select_option("work")
                    assert category_response.value.status == 200
                    page.locator("#expense-import-submit").click()
                    expect(page.locator("#expense-import-status")).to_contain_text("Imported 0; updated 202")

                    expect(refund_category).to_have_value("work")
                    with page.expect_download() as export_info:
                        page.locator("#expenses-export").click()
                    exported = json.loads(Path(export_info.value.path()).read_text())
                    assert exported["scope"] == "displayed_page" and len(exported["transactions"]) == 200
                    assert all("raw_data" not in row for row in exported["transactions"])
                    with page.expect_download() as period_download:
                        page.locator("#expenses-export-period").click()
                    period_lines = [
                        json.loads(line) for line in Path(period_download.value.path()).read_text().splitlines()
                    ]
                    assert period_lines[-1] == {"kind": "completion", "status": "complete", "records": 202}
                    assert len([line for line in period_lines if line["kind"] == "transaction"]) == 202
                    from tests.e2e.expense_retention import verify_retention

                    verify_retention(page, context, base, user_a)
                    expect(page.locator("#expense-import-status")).to_contain_text("Exported 202 transactions")
                    page.set_viewport_size({"width": 390, "height": 844})
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    page.set_viewport_size({"width": 1440, "height": 1000})

                    # Generate and retrieve a real PDF from the browser chat workflow.
                    page.get_by_role("button", name="Assistant", exact=True).click()
                    page.locator("#user-input").fill("Generate my report from 2026-09-01 to 2026-09-07.")
                    page.locator("#send-btn").click()
                    expect(page.locator("#messages")).to_contain_text("evidence_sha256", timeout=30000)
                    expect(page.locator(".chat-evidence-note")).to_contain_text("Saved answer")
                    evidence_link = page.locator(".chat-evidence-note a").last
                    chat_evidence_url = evidence_link.get_attribute("href")
                    with page.expect_download() as chat_download:
                        evidence_link.click()
                    chat_evidence = json.loads(Path(chat_download.value.path()).read_text())
                    assert chat_evidence["state"] == "complete"
                    assert any(item["type"] == "tool_result" for item in chat_evidence["evidence"])
                    reports = context.request.get(base + "/api/reports").json()
                    assert reports and reports[0]["pdf_available"]
                    assert reports[0]["generation_status"] == "complete"
                    assert reports[0]["generation_errors"] == []
                    report_id = reports[0]["id"]
                    pdf = context.request.get(base + f"/api/reports/{report_id}/pdf")
                    assert pdf.status == 200 and pdf.body().startswith(b"%PDF")
                    page.reload()
                    expect(page.locator(".chat-evidence-note")).to_contain_text("Saved answer")
                    expect(page.locator("#reports-list")).to_contain_text("2026-09-01")
                    expect(page.locator("#reports-list .report-status").first).to_have_text("Generation complete")
                    page.get_by_role("button", name="Simulation", exact=True).click()
                    other = browser.new_context()
                    other_page = other.new_page()
                    other_page.goto(base + "/login")
                    other_page.locator("#username").fill(user_b)
                    other_page.locator("#password").fill("fixture-browser-password")
                    other_page.get_by_role("button", name="Sign in", exact=True).click()
                    other_page.wait_for_url(base + "/")
                    cross = other.request.get(base + "/api/simulator/accounts/" + fixture["account_id"])
                    assert cross.status == 409 and cross.json()["detail"]["reason_code"] == "ACCOUNT_NOT_OWNED"
                    assert other.request.get(base + f"/api/reports/{report_id}/pdf").status == 404
                    assert other.request.get(base + chat_evidence_url).status == 404
                    other_csrf = next(c["value"] for c in other.cookies() if c["name"] == "ia_csrf")
                    denied_category = other.request.patch(
                        base + f"/api/expenses/{expense_id}/category",
                        headers={"X-CSRF-Token": other_csrf},
                        data={"category": "food"},
                    )
                    assert denied_category.status == 404
                    assert other.request.get(base + "/api/expenses?period=year").json()["transactions"] == []
                    assert other.request.get(base + f"/api/simulations/{replay_id}/evidence").status == 404
                    from tests.e2e.broker_observations import verify_broker_observations

                    verify_broker_observations(page, context, other, base, csrf)
                    from tests.e2e.report_retention import verify_report_retention

                    verify_report_retention(page, context, other, base, csrf, user_a, report_id)
                    from tests.e2e.chat_retention import verify_chat_retention

                    verify_chat_retention(page, context, other, base, csrf, user_a, chat_evidence_url)
                    other.close()
                    page.set_viewport_size({"width": 390, "height": 844})
                    expect(page.locator("#sidebar")).to_have_class("hidden")
                    page.wait_for_function("document.getElementById('sidebar').getBoundingClientRect().right <= 1")
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    page.screenshot(path=str(screenshots / "halted-mobile.png"))
                    assert not errors, errors
                    # Test revocation on an already-open socket without app reconnects.
                    guard = context.new_page()
                    guard.goto(base + "/api/health")
                    guard.evaluate("""async () => {
                      window.revokedCode = null;
                      const wsBase = location.origin.replace('http','ws');
                      const wsPath = '/ws/chat/' + crypto.randomUUID();
                      window.guardSocket = new WebSocket(wsBase + wsPath);
                      window.guardSocket.onclose = event => window.revokedCode = event.code;
                      await new Promise((resolve, reject) => {
                        window.guardSocket.onopen = resolve;
                        window.guardSocket.onerror = reject;
                      });
                    }""")
                    old_cookie = next(c["value"] for c in context.cookies() if c["name"] == "ia_session")
                    page.close()
                    response = context.request.post(base + "/api/auth/logout", headers={"X-CSRF-Token": csrf})
                    assert response.status == 200
                    guard.wait_for_function("window.revokedCode === 4001", timeout=5000)
                    replay = context.request.get(base + "/api/auth/me", headers={"Cookie": "ia_session=" + old_cookie})
                    assert replay.status == 401
                    guard.close()
                    print(
                        json.dumps(
                            {
                                "status": "PASS",
                                "tier": "real-browser-real-postgres-stub-model",
                                "url": base,
                                "viewports": ["1440x1000", "390x844"],
                                "checks": [
                                    "login",
                                    "page identity",
                                    "portfolio view",
                                    "proposal",
                                    "independent approval",
                                    "independent simulator mandate approval",
                                    "expense import, currencies, pages, category, full-period export "
                                    "and raw-payload retention",
                                    "bank disabled status; intercepted UI consent/selection/retry/disconnect",
                                    "cost-aware replay, evidence download/reproduction/isolation",
                                    "fill and fees",
                                    "broker journal, confirmed read and isolation (synthetic source)",
                                    "halt",
                                    "model self-approval denial",
                                    "CSRF denial",
                                    "cross-user denial",
                                    "in-app alert acknowledgement",
                                    "chat report PDF, confirmed retention tombstone and isolation",
                                    "durable chat evidence, confirmed retention tombstones, reload and ownership",
                                    "logout cookie replay and open-WebSocket revocation",
                                ],
                                "screenshots": str(screenshots),
                                "console_errors": errors,
                                "expected_fixture_http_errors": expected_errors,
                                "broker_connections": 0,
                                "external_orders": 0,
                            }
                        )
                    )
                finally:
                    browser.close()
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()


if __name__ == "__main__":
    main()
