"""Existing workspace and vault controls through Chromium; no broker connection."""

import json

from playwright.sync_api import expect


def verify_workspace_controls(page, context, base, screenshots):
    expect(page.locator("#profile-status")).to_have_text("Profile loaded")
    page.locator("#profile-display-name").fill("Synthetic workspace owner")
    page.locator("#profile-description").fill("Fixture goals only; no trading permission.")
    page.locator("#profile-preferences").fill('{"base_currency":"EUR","monitoring_enabled":false}')
    page.get_by_role("button", name="Save profile", exact=True).click()
    expect(page.locator("#profile-status")).to_contain_text("saved")
    profile = context.request.get(base + "/api/profile").json()
    assert profile["display_name"] == "Synthetic workspace owner"
    assert profile["preferences"]["monitoring_enabled"] is False

    page.once("dialog", lambda dialog: dialog.accept("Synthetic project"))
    page.get_by_role("button", name="Create project", exact=True).click()
    expect(page.locator("#conversation-projects")).to_contain_text("Synthetic project")
    projects = context.request.get(base + "/api/projects").json()["projects"]
    project = next(row for row in projects if row["name"] == "Synthetic project")
    page.locator("#conversation-project").select_option(project["id"])
    expect(page.locator(f"#project-chats-{project['id']} .conversation-row")).to_have_count(1)

    expect(page.locator("#broker-status")).to_have_text("Encrypted account settings ready")
    page.locator("#broker-provider").select_option("ibkr")
    page.locator("#broker-display-name").fill("Disabled synthetic configuration")
    page.locator("#broker-field-host").fill("127.0.0.1")
    page.locator("#broker-field-environment").fill("unverified")
    page.locator("#broker-field-broker_account_id").fill("SYNTHETIC-WORKSPACE-ONLY")
    expect(page.locator("#broker-field-enabled")).not_to_be_checked()
    expect(page.locator("#broker-field-read_authorized")).not_to_be_checked()
    page.get_by_role("button", name="Save account", exact=True).click()
    expect(page.locator("#broker-accounts-list")).to_contain_text("Disabled synthetic configuration")
    accounts = context.request.get(base + "/api/broker-accounts").json()["accounts"]
    account = next(row for row in accounts if row["display_name"] == "Disabled synthetic configuration")
    assert "SYNTHETIC-WORKSPACE-ONLY" not in json.dumps(account)
    assert account["configured_fields"]["broker_account_id"] is True
    assert account["masked_fields"]["read_authorized"] is False
    assert account["masked_fields"]["enabled"] is False
    page.locator(f'[data-edit-account="{account["id"]}"]').click()
    expect(page.locator("#broker-provider")).to_be_disabled()
    expect(page.locator("#broker-field-broker_account_id")).to_have_value("")
    page.locator("#broker-display-name").fill("Renamed synthetic configuration")
    page.get_by_role("button", name="Save account", exact=True).click()
    expect(page.locator("#broker-accounts-list")).to_contain_text("Renamed synthetic configuration")
    page.reload()
    expect(page.locator("#profile-display-name")).to_have_value("Synthetic workspace owner")
    expect(page.locator("#conversation-project")).to_have_value(project["id"])
    expect(page.locator("#broker-accounts-list")).to_contain_text("Renamed synthetic configuration")
    saved = context.request.get(base + "/api/broker-accounts").json()["accounts"]
    assert next(row for row in saved if row["id"] == account["id"])["configured_fields"]["broker_account_id"] is True
    page.locator("#broker-accounts-list").scroll_into_view_if_needed()
    assert page.locator(".broker-account-actions").evaluate_all("""rows => rows.every(row => {
      const card = row.closest('.broker-account').getBoundingClientRect();
      return [...row.querySelectorAll('button')].every(button => {
        const box = button.getBoundingClientRect();
        return box.left >= card.left && box.right <= card.right;
      });
    })"""), "Broker controls overflow their account card"
    page.screenshot(path=str(screenshots / "workspace-settings-desktop.png"))
    page.once("dialog", lambda dialog: dialog.accept())
    page.locator(f'[data-delete-account="{account["id"]}"]').click()
    expect(page.locator("#broker-accounts-list")).not_to_contain_text("Renamed synthetic configuration")
    remaining = context.request.get(base + "/api/broker-accounts").json()["accounts"]
    assert all(row["id"] != account["id"] for row in remaining)
    return project["id"], account["id"]
