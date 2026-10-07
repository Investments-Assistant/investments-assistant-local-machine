"""UI-only bank controls: intercepted responses, no provider requests or consent."""

from datetime import UTC, datetime, timedelta

from playwright.sync_api import expect


def verify_bank_controls(page):
    connection = {
        "id": "synthetic-connection",
        "provider": "gocardless",
        "status": "awaiting_consent",
        "last_received_at": None,
        "provider_last_success_at": None,
    }
    calls = []
    exists = False
    fail_selection = True
    fail_history = True
    history_start = (datetime.now(UTC).date() - timedelta(days=365)).isoformat()

    def handle(route):
        nonlocal exists, fail_selection, fail_history
        request = route.request
        path = request.url.split("/api/banks", 1)[1]
        calls.append((request.method, path))
        if request.method != "GET":
            assert request.headers.get("x-csrf-token")
        response = {}
        if path == "" and request.method == "GET":
            response = dict(
                external_access_enabled=True,
                consent_setup_available=True,
                connections=[connection] if exists else [],
            )
        elif path in ("/consent", "/synthetic-connection/reconnect"):
            assert request.post_data_json == {"institution": "FIXTURE_BANK"}
            exists = True
            response = {
                "connection_id": connection["id"],
                "status": "awaiting_consent",
                "consent_url": "https://ob.gocardless.com/psd2/start/fixture",
            }
        elif path == "/synthetic-connection/accounts":
            response = {"accounts": [{"handle": "a" * 64, "label": "Consented account 1"}]}
        elif path == "/synthetic-connection/account":
            assert request.post_data_json == {"account_handle": "a" * 64}
            if fail_selection:
                fail_selection = False
                route.fulfill(status=409, json={"detail": {"reason_code": "ACCOUNT_NOT_CONSENTED"}})
                return
            connection["status"] = "connected"
            response = {"status": "connected"}
        elif path == "/synthetic-connection/history":
            assert request.post_data_json == {"date_from": history_start}
            if fail_history:
                fail_history = False
                response = {"status": "retry_wait", "error_code": "PROVIDER_RATE_LIMIT"}
            else:
                connection["last_history_retrieval"] = dict(
                    requested_from=history_start,
                    completed_at=datetime.now(UTC).isoformat(),
                    records=3,
                    coverage_verified=False,
                )
                response = {"status": "complete", "records": 3}
        elif path == "/synthetic-connection" and request.method == "DELETE":
            connection["status"] = "disconnected"
            response = {"status": "disconnected"}
        else:
            raise AssertionError(f"Unexpected bank UI fixture request: {request.method} {path}")
        route.fulfill(json=response)

    page.route("**/api/banks**", handle)
    try:
        page.evaluate("loadBankConnections()")
        expect(page.locator("#bank-consent")).to_be_enabled()
        page.locator("#bank-institution").fill("FIXTURE_BANK")
        page.locator("#bank-consent").click()
        expect(page.locator("#bank-action-status a")).to_have_attribute(
            "href", "https://ob.gocardless.com/psd2/start/fixture"
        )
        # Never navigate to the external link.
        page.get_by_role("button", name="Choose consented account", exact=True).click()
        page.get_by_role("button", name="Use selected account", exact=True).click()
        expect(page.locator("#bank-action-status")).to_have_text("ACCOUNT_NOT_CONSENTED")
        page.get_by_role("button", name="Use selected account", exact=True).click()
        expect(page.locator("#bank-action-status")).to_contain_text("Account selected")
        expect(page.locator("#bank-connections")).to_contain_text("gocardless: connected")
        history_button = page.get_by_role("button", name="Retrieve older history", exact=True)
        history_button.click()
        expect(page.locator("#bank-action-status")).to_contain_text("Choose a valid start date")
        page.get_by_label("Bank history start date", exact=True).fill(history_start)
        history_button.click()
        expect(page.locator("#bank-action-status")).to_have_text("PROVIDER_RATE_LIMIT")
        page.get_by_label("Bank history start date", exact=True).fill(history_start)
        with page.expect_response(lambda response: "/api/expenses?" in response.url
                                  and response.request.method == "GET", timeout=10000):
            history_button.click()
        expect(page.locator("#bank-action-status")).to_contain_text("missing transactions were not deleted")
        expect(page.locator("#bank-connections")).to_contain_text("Complete coverage is not verified")
        page.get_by_role("button", name="Renew bank consent", exact=True).click()
        expect(page.locator("#bank-action-status a")).to_be_visible()
        page.get_by_role("button", name="Stop local synchronization", exact=True).click()
        expect(page.locator("#bank-action-status")).to_contain_text("Revoke provider consent")
        expect(page.get_by_role("button", name="Stop local synchronization", exact=True)).to_be_disabled()
        expect(page.get_by_role("button", name="Retrieve older history", exact=True)).to_be_disabled()
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        page.set_viewport_size({"width": 1440, "height": 1000})
        assert ("POST", "/consent") in calls and ("DELETE", "/synthetic-connection") in calls
    finally:
        page.unroute("**/api/banks**", handle)
        page.evaluate("loadBankConnections()")
    expect(page.locator("#bank-access-status")).to_contain_text("Bank access is disabled")

    # Real API request context bypasses the browser-only fixture interception.
    csrf = next(cookie["value"] for cookie in page.context.cookies() if cookie["name"] == "ia_csrf")
    endpoint = page.url.split("/", 3)[:3]
    endpoint = "/".join(endpoint) + "/api/banks/synthetic-connection/history"
    assert page.request.post(endpoint, data={"date_from": history_start}).status == 403
    denied = page.request.post(endpoint, data={"date_from": history_start}, headers={"X-CSRF-Token": csrf})
    assert denied.status == 409 and denied.json()["detail"]["reason_code"] == "BANK_ACCESS_NOT_AUTHORIZED"
