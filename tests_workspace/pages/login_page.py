from playwright.sync_api import Page, Locator, expect

class LoginPage:
    def __init__(self, page: Page):
        self.page = page
        self.email_input: Locator = page.locator("[data-testid='email-input']")
        self.password_input: Locator = page.get_by_label("Password")
        self.submit_button: Locator = page.get_by_role("button", name="Sign In")
        self.success_message: Locator = page.locator(".toast-success")

    def fill_email(self, email: str):
        self.email_input.fill(email)

    def fill_password(self, password: str):
        self.password_input.fill(password)

    def click_submit(self):
        self.submit_button.click()

    def assert_success_message_visible(self):
        expect(self.success_message).to_be_visible()
