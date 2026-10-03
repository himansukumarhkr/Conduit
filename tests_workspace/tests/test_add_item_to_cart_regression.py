import pytest
from pages.catalog_page import CatalogPage
from pages.cart_page import CartPage

@pytest.mark.smoke
@pytest.mark.regression
def test_add_item_to_cart_regression(page):
    catalog_page = CatalogPage(page)
    cart_page = CartPage(page)
    page.goto("https://demo.playwright.dev/todomvc/")
    catalog_page.select_quantity("2")
    catalog_page.click_add_to_cart()
    cart_page.assert_badge_visible()
