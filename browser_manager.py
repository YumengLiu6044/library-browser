from playwright.async_api import async_playwright
from functools import wraps


class BrowserManager:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None

        self.has_started = False

    async def start(self):
        self.playwright = await async_playwright().start()

        self.browser = await self.playwright.chromium.launch(headless=True)

        self.context = await self.browser.new_context()

        self.has_started = True
        return self

    @staticmethod
    def must_be_started(method):
        @wraps(method)
        async def wrapper(self, *args, **kwargs):
            if not self.has_started:
                raise RuntimeError("BrowserManager has not been started")

            return await method(self, *args, **kwargs)

        return wrapper

    @must_be_started
    async def stop(self):
        if not self.has_started:
            raise RuntimeError("BrowserManager has not been started")

        if self.context:
            await self.context.close()

        if self.browser:
            await self.browser.close()

        if self.playwright:
            await self.playwright.stop()

        self.has_started = False

    @must_be_started
    async def fetch_hydrated_html(
        self,
        url: str,
        wait_selector: str | None = None,
    ):
        if not self.has_started:
            raise RuntimeError("BrowserManager has not been started")

        page = await self.context.new_page()

        try:
            await page.goto(
                url,
                wait_until="domcontentloaded"
            )

            if wait_selector:
                await page.wait_for_selector(
                    wait_selector,
                    timeout=10000
                )
            else:
                await page.wait_for_load_state(
                    "networkidle"
                )

            return await page.content()

        finally:
            await page.close()
