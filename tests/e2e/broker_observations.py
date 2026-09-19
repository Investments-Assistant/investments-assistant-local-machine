"""Real browser approval and persistence; external callback source is synthetic."""

from playwright.sync_api import expect


def verify_broker_observations(page, context, other, base, csrf):
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
