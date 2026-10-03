import pytest
from pages.checkout_page import CheckoutPage

@pytest.mark.checkout
def test_assert_login_flow(page):
    checkout_page = CheckoutPage(page)
    page.goto("https://demo.playwright.dev/todomvc/")
    checkout_page.assert_login_prompt()
