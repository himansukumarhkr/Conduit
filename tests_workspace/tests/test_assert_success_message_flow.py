import pytest
from pages.feedback_page import FeedbackPage

@pytest.mark.regression
def test_assert_success_message_flow(page):
    feedback_page = FeedbackPage(page)
    feedback_page.fill_feedback("Great platform!")
    feedback_page.click_submit()
    feedback_page.assert_toast("Success")
