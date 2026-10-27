"""Real browser approval and persistence; external callback source is synthetic."""

from playwright.sync_api import expect


def verify_broker_observations(page, context, other, base, csrf, expected_http_errors=None):
    verify_broker_save_consent(page, expected_http_errors)
    page.locator("#broker-provider").select_option("ibkr")
    expect(page.locator("#broker-field-read_authorized")).not_to_be_checked()
    expect(page.locator("#broker-field-enabled")).not_to_be_checked()
    page.locator("#broker-display-name").fill("Synthetic callback fixture")
    page.locator("#broker-field-broker_account_id").fill("SYNTHETIC-BROWSER-ONLY")
    page.locator("#broker-field-environment").fill("paper")
    page.locator("#broker-field-host").fill("127.0.0.1")
    page.locator("#broker-field-client_id").fill("77")
    page.locator("#broker-field-enabled").check()
    page.locator("#broker-field-read_authorized").check()
    page.get_by_role("button", name="Save account", exact=True).click()
    button = page.get_by_role("button", name="Saved execution evidence", exact=True)
    expect(button).to_be_visible()
    account_id = button.get_attribute("data-broker-evidence")
    output = page.locator(f'[data-broker-result="{account_id}"]')
    button.click()
    expect(output).to_contain_text('"observations": []')
    page.once("dialog", lambda dialog: dialog.dismiss())
    page.get_by_role("button", name="Read broker evidence", exact=True).click()
    assert context.request.get(base + f"/api/broker-accounts/{account_id}/observations").json()["observations"] == []
    page.once("dialog", lambda dialog: dialog.accept())
    page.get_by_role("button", name="Read broker evidence", exact=True).click()
    expect(output).to_contain_text('"inserted": 3')
    # Exercise the real backend's bounded paging with one fixture fact per page.
    pattern = f"**/api/broker-accounts/{account_id}/observations*"

    def one_row_page(route):
        url = route.request.url
        route.continue_(url=url + ("&" if "?" in url else "?") + "limit=1")

    page.route(pattern, one_row_page)
    button.click()
    expect(output).to_contain_text('"quantity": "0.004"')
    expect(output).to_contain_text('"environment_verified": null')
    assert "SYNTHETIC-BROWSER-ONLY" not in output.inner_text()
    page.get_by_role("button", name="Next saved evidence page", exact=True).click()
    expect(output).to_contain_text('"amount": "0.01"')
    expect(output).to_contain_text("REVIEW_WINDOW_TRUNCATED")
    page.get_by_role("button", name="Next saved evidence page", exact=True).click()
    expect(output).to_contain_text('"amount": "999.59"')
    expect(output).to_contain_text('"atomic_snapshot": false')
    expect(output).to_contain_text('"balance_reconciliation": "not_established"')
    expect(button).to_be_visible()
    page.unroute(pattern, one_row_page)
    url = base + f"/api/broker-accounts/{account_id}/observations"
    state = context.request.get(url).json()["refresh_state"]
    assert state["status"] == "observed" and state["last_success"] is not None
    assert state["native_completion"] == "returned" and state["scope"] == "broker_read_only"
    assert other.request.get(url).status == 409
    assert context.request.post(url + "/refresh", data={"confirm_broker_read": True}).status == 403
    assert (
        context.request.post(
            url + "/refresh", headers={"X-CSRF-Token": csrf}, data={"confirm_broker_read": False}
        ).status
        == 422
    )


def verify_broker_save_consent(page, expected_http_errors=None):
    """Saved OFF/drafts/pending or failed saves never authorize a read.

    All refresh POSTs are intercepted, so this regression cannot invoke the
    provider even if the UI guard regresses. Only this new synthetic record is
    created/edited/disabled in the isolated browser fixture.
    """
    page.locator("#broker-provider").select_option("ibkr")
    page.locator("#broker-display-name").fill("Synthetic save-consent race")
    page.locator("#broker-field-broker_account_id").fill("SYNTHETIC-SAVE-RACE-ONLY")
    page.locator("#broker-field-environment").fill("paper")
    page.locator("#broker-field-host").fill("127.0.0.1")
    page.locator("#broker-field-client_id").fill("79")
    page.locator("#broker-field-enabled").uncheck()
    page.locator("#broker-field-read_authorized").uncheck()
    page.get_by_role("button", name="Save account", exact=True).click()
    card = page.locator(".broker-account").filter(has_text="Synthetic save-consent race")
    expect(card).to_be_visible()
    account_id = card.locator("[data-broker-refresh]").get_attribute("data-broker-refresh")
    refresh_pattern = f"**/api/broker-accounts/{account_id}/observations/refresh"
    save_pattern = f"**/api/broker-accounts/{account_id}"
    refreshes, dialogs, held = [], [], []

    def deny_provider(route):
        refreshes.append(route.request.post_data_json)
        route.fulfill(status=409, json={"detail": {"reason_code": "SYNTHETIC_REFRESH_MUST_NOT_RUN"}})

    def confirm(dialog):
        dialogs.append(dialog.message)
        dialog.accept()

    def hold_save(route):
        if route.request.method == "PUT":
            held.append(route)
        else:
            route.fallback()

    def assert_read_blocked():
        read = card.locator("[data-broker-refresh]")
        # Exercise an already-bound handler too: disabling a DOM button alone
        # must not let an old handler manufacture consent from an unsaved draft.
        page.evaluate(
            """async id => {
                const b = document.querySelector(`[data-broker-refresh="${id}"]`);
                await brokerExecutionEvidence(b, true);
            }""",
            account_id,
        )
        assert not refreshes, "A read POST escaped while consent was unsaved or unacknowledged"
        assert not dialogs, "Read confirmation appeared without saved acknowledged consent"
        expect(read).to_be_disabled()
        assert read.get_attribute("title") or read.get_attribute("aria-describedby"), (
            "Disabled read needs actionable guidance"
        )
        expect(card.locator("[data-broker-evidence]")).to_be_enabled()

    page.route(refresh_pattern, deny_provider)
    page.on("dialog", confirm)
    try:
        assert_read_blocked()
        card.locator("[data-edit-account]").click()
        page.locator("#broker-field-enabled").check()
        page.locator("#broker-field-read_authorized").check()
        assert_read_blocked()  # Checked draft is not saved authorization.
        page.route(save_pattern, hold_save)
        try:
            page.get_by_role("button", name="Save account", exact=True).click()
            expect(page.locator("#broker-status")).to_contain_text("Saving")
            assert len(held) == 1
            body = held[0].request.post_data_json
            assert body["config"]["enabled"] is True and body["config"]["read_authorized"] is True
            assert_read_blocked()
            held.pop().fallback()  # Only now may the isolated backend commit.
            expect(page.locator("#broker-status")).to_have_text("Encrypted account settings ready")
            expect(card.locator("[data-broker-refresh]")).to_be_enabled()
            card.locator("[data-edit-account]").click()
            expect(page.locator("#broker-field-enabled")).to_be_checked()
            expect(page.locator("#broker-field-read_authorized")).to_be_checked()
            page.locator("#broker-field-enabled").uncheck()
            page.locator("#broker-field-read_authorized").uncheck()
            page.get_by_role("button", name="Save account", exact=True).click()
            expect(page.locator("#broker-status")).to_contain_text("Saving")
            assert len(held) == 1
            failed_save = held.pop()
            if expected_http_errors is not None:
                expected_http_errors.add((
                    failed_save.request.url,
                    "Failed to load resource: the server responded with a status of 503 (Service Unavailable)",
                ))
            failed_save.fulfill(status=503, json={"detail": "Synthetic save failed; consent not acknowledged"})
            expect(page.locator("#broker-status")).to_contain_text("Synthetic save failed")
            assert_read_blocked()
            # Retry only this synthetic settings save, never a provider request.
            page.get_by_role("button", name="Save account", exact=True).click()
            expect(page.locator("#broker-status")).to_contain_text("Saving")
            assert len(held) == 1
            held.pop().fallback()
            expect(page.locator("#broker-status")).to_have_text("Encrypted account settings ready")
            assert_read_blocked()
        finally:
            for route in held:
                route.fulfill(status=503, json={"detail": "Synthetic held save cancelled"})
            page.unroute(save_pattern, hold_save)
    finally:
        page.unroute(refresh_pattern, deny_provider)
        page.remove_listener("dialog", confirm)
    page.once("dialog", lambda dialog: dialog.accept())
    card.locator("[data-delete-account]").click()
    expect(card).to_have_count(0)
