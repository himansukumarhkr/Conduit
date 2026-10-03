import pytest
from pages.alert_page import AlertPage

@pytest.mark.smoke
@pytest.mark.failed
def test_assert_success_message(page):
    alert_page = AlertPage(page)
    alert_page.trigger_alert()
    alert_page.assert_banner_visible()
