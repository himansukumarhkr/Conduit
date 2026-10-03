import pytest
from pages.catalog_page import CatalogPage
from pages.cart_page import CartPage

@pytest.mark.smoke
@pytest.mark.checkout
def test_add_item_to_cart_checkout(page):
    catalog_page = CatalogPage(page)
    cart_page = CartPage(page)
    page.goto("https://demo.playwright.dev/todomvc/")
    catalog_page.click_add_to_cart()
    cart_page.assert_counter("1")
