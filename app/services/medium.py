import asyncio
import os
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)


class MediumPublisher:
    """
    Playwright-based Medium publisher.
    Uses saved auth.json session (logged in via login.js script)
    to publish articles headlessly — no API token needed.
    """

    def __init__(self):
        self.auth_path = settings.MEDIUM_AUTH_JSON_PATH

    def publish(self, title: str, body: str, publish_status: str = "draft") -> dict:
        """
        Synchronous wrapper around async Playwright publish.
        publish_status: 'draft' (default) or 'public'
        """
        try:
            loop = asyncio.get_running_loop()
            # If already in an async context, run in a new thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, self._publish_async(title, body, publish_status))
                return future.result(timeout=60)
        except RuntimeError:
            # No running loop — run directly
            return asyncio.run(self._publish_async(title, body, publish_status))

    async def _publish_async(self, title: str, body: str, publish_status: str = "draft") -> dict:
        """
        Uses Playwright to:
        1. Open Medium new-story page with saved session
        2. Fill title + body
        3. Click Publish (if publish_status == 'public')
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("Playwright not installed. Run: pip install playwright && python -m playwright install --with-deps")
            return {"error": "Playwright not installed"}

        if not os.path.exists(self.auth_path):
            logger.error(f"Medium auth session not found at {self.auth_path}. Run login.js first.")
            return {"error": f"Auth file not found: {self.auth_path}"}

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(storage_state=self.auth_path)
            page = await context.new_page()

            try:
                # Navigate to new story editor
                await page.goto("https://medium.com/new-story", wait_until="networkidle", timeout=30000)

                # Wait for editor to load
                await page.wait_for_selector('div[role="textbox"], textarea, [data-testid="title"]', timeout=15000)

                # Try multiple selectors for title (Medium changes DOM occasionally)
                title_selectors = [
                    'textarea[placeholder="Title"]',
                    'h3[data-contents="true"]',
                    'div[data-testid="title"]',
                    'div[role="textbox"]:first-of-type',
                ]

                title_filled = False
                for sel in title_selectors:
                    try:
                        el = await page.wait_for_selector(sel, timeout=3000)
                        if el:
                            await el.click()
                            await page.keyboard.type(title, delay=20)
                            title_filled = True
                            break
                    except Exception:
                        continue

                if not title_filled:
                    logger.error("Could not find title field in Medium editor")
                    await browser.close()
                    return {"error": "Title field not found"}

                # Move to body
                await page.keyboard.press("Enter")
                await page.keyboard.press("Enter")

                # Type body content (Medium accepts markdown-ish formatting)
                # Split into paragraphs for natural typing
                paragraphs = body.split("\n\n")
                for i, para in enumerate(paragraphs):
                    await page.keyboard.type(para, delay=5)
                    if i < len(paragraphs) - 1:
                        await page.keyboard.press("Enter")
                        await page.keyboard.press("Enter")

                if publish_status == "public":
                    # Click publish button
                    await page.wait_for_timeout(2000)

                    publish_btn = await page.query_selector('button:has-text("Publish")')
                    if publish_btn:
                        await publish_btn.click()
                        await page.wait_for_timeout(2000)

                        # Handle Medium's 2-step publish confirmation
                        confirm_btns = await page.query_selector_all('button')
                        for btn in confirm_btns:
                            text = await btn.inner_text()
                            if "publish" in text.lower():
                                await btn.click()
                                break

                        await page.wait_for_timeout(3000)
                        final_url = page.url
                        logger.info(f"Published to Medium: {final_url}")
                        await browser.close()
                        return {"data": {"url": final_url}, "status": "published"}
                    else:
                        logger.warning("Publish button not found, saving as draft")

                # If draft mode or publish button not found — just save
                final_url = page.url
                logger.info(f"Draft saved at: {final_url}")
                await browser.close()
                return {"data": {"url": final_url}, "status": "draft"}

            except Exception as e:
                logger.error(f"Playwright publish failed: {e}")
                await browser.close()
                return {"error": str(e)}
