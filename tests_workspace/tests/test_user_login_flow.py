import pytest
from playwright.sync_api import Page, expect
from pages.login_page import LoginPage

@pytest.mark.smoke
@pytest.mark.regression
def test_user_login_flow(page: Page):
    login_page = LoginPage(page)
    page.goto("https://demo.playwright.dev/todomvc/")
    login_page.fill_email("admin@conduit.io")
    login_page.fill_password("SuperSecret123!")
    login_page.click_submit()
    login_page.assert_success_message_visible()
