"""UI-only bank controls: intercepted responses, no provider requests or consent."""

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

    def handle(route):
        nonlocal exists, fail_selection
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
        page.get_by_role("button", name="Renew bank consent", exact=True).click()
        expect(page.locator("#bank-action-status a")).to_be_visible()
        page.get_by_role("button", name="Stop local synchronization", exact=True).click()
        expect(page.locator("#bank-action-status")).to_contain_text("Revoke provider consent")
        expect(
            page.get_by_role("button", name="Stop local synchronization", exact=True)
        ).to_be_disabled()
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        page.set_viewport_size({"width": 1440, "height": 1000})
        assert ("POST", "/consent") in calls and ("DELETE", "/synthetic-connection") in calls
    finally:
        page.unroute("**/api/banks**", handle)
        page.evaluate("loadBankConnections()")
    expect(page.locator("#bank-access-status")).to_contain_text("Bank access is disabled")
