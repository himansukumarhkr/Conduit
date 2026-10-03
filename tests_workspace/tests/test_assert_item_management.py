import pytest
from pages.admin_page import AdminPage

@pytest.mark.smoke
@pytest.mark.checkout
def test_assert_item_management(page):
    admin_page = AdminPage(page)
    page.goto("https://demo.playwright.dev/todomvc/")
    admin_page.assert_items_table_visible()
    admin_page.click_filter_active()
