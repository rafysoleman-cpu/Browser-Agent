import logging
import asyncio

logger = logging.getLogger(__name__)


class SelectorResolver:
    CSS_TIMEOUT_MS = 3000
    AI_FALLBACK_TIMEOUT = 15

    def __init__(self, browser_context, llm=None, ask_human_callback=None):
        self.browser_context = browser_context
        self.llm = llm
        self.ask_human_callback = ask_human_callback
        self._stats = {"css_hits": 0, "css_misses": 0, "ai_hits": 0, "ai_misses": 0, "human": 0}

    @property
    def stats(self):
        return self._stats

    async def resolve_element(self, selectors: dict, step_description: str, try_human: bool = True) -> tuple:
        """
        Try to find and return a Playwright element.
        Returns: (element_or_None, source_string)
        """
        element = await self._try_css_selectors(selectors)
        if element:
            self._stats["css_hits"] += 1
            logger.info(f"✅ [CSS HIT] Found element via CSS: {selectors}")
            return element, "css"

        self._stats["css_misses"] += 1
        logger.warning(f"❌ [CSS MISS] No CSS selector worked: {selectors}")

        if self.llm:
            element = await self._try_ai_fallback(step_description)
            if element:
                self._stats["ai_hits"] += 1
                logger.info(f"✅ [AI HIT] Found element via AI for: {step_description}")
                return element, "ai"
            self._stats["ai_misses"] += 1
            logger.warning(f"❌ [AI MISS] AI could not find element for: {step_description}")

        if try_human and self.ask_human_callback:
            self._stats["human"] += 1
            element = await self._try_human(step_description)
            return element, "human"

        return None, "none"

    async def _try_css_selectors(self, selectors: dict) -> object:
        css_selectors = []
        if isinstance(selectors, dict):
            for key in ["css", "selector", "xpath", "Xpath"]:
                val = selectors.get(key)
                if val:
                    if isinstance(val, list):
                        css_selectors.extend(val)
                    else:
                        css_selectors.append(val)
        elif isinstance(selectors, str):
            css_selectors = [selectors]
        for css in css_selectors:
            try:
                page = await self._get_page()
                if css.startswith("//") or css.startswith("("):
                    element = await page.wait_for_selector(f"xpath={css}", timeout=self.CSS_TIMEOUT_MS)
                else:
                    element = await page.wait_for_selector(css, timeout=self.CSS_TIMEOUT_MS)
                if element:
                    return element
            except Exception:
                continue
        return None

    async def _try_ai_fallback(self, description: str) -> object:
        try:
            page = await self._get_page()
            html = await page.content()
            snippet = html[:10000]
            prompt = (
                f"On this webpage, I need to find an element that: {description}\n\n"
                f"Here is the page HTML (first 10k chars):\n{snippet}\n\n"
                f"Return ONLY a valid CSS selector or XPath that uniquely identifies this element. "
                f"Return just the selector string, nothing else."
            )
            response = await self.llm.ainvoke(prompt)
            selector = response.content.strip().strip("`").strip()
            if selector.startswith("css="):
                selector = selector[4:]
            if selector:
                element = await page.wait_for_selector(selector, timeout=self.CSS_TIMEOUT_MS)
                if element:
                    logger.info(f"AI suggested selector: {selector} -> FOUND")
                    return element
                logger.warning(f"AI suggested selector: {selector} -> NOT FOUND")
        except Exception as e:
            logger.error(f"AI fallback error: {e}")
        return None

    async def _try_human(self, description: str) -> object:
        if not self.ask_human_callback:
            return None
        try:
            logger.info(f"🤔 Asking human for help with: {description}")
            response = await self.ask_human_callback(
                f"Agent could not find this element automatically:\n{description}\n\n"
                f"Please click on the element in the browser, or provide a CSS/XPath selector:"
            )
            user_input = response.get("response", "").strip()
            if user_input:
                page = await self._get_page()
                try:
                    if user_input.startswith("//") or user_input.startswith("("):
                        element = await page.wait_for_selector(f"xpath={user_input}", timeout=5000)
                    else:
                        element = await page.wait_for_selector(user_input, timeout=5000)
                    if element:
                        logger.info(f"Human gave selector: {user_input} -> FOUND")
                        return element
                except Exception:
                    pass
                logger.info("Human provided input but selector didn't match. Waiting for manual action...")
                await asyncio.sleep(3)
                return None
        except Exception as e:
            logger.error(f"Human fallback error: {e}")
        return None

    async def _get_page(self):
        if hasattr(self.browser_context, 'get_current_page'):
            return await self.browser_context.get_current_page()
        return self.browser_context.page
