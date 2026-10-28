import asyncio
import logging
import os
import json
from typing import Optional

logger = logging.getLogger(__name__)


class StepExecutor:
    def __init__(self, browser_context, selector_resolver, template_engine, context: dict):
        self.browser_context = browser_context
        self.selector_resolver = selector_resolver
        self.template_engine = template_engine
        self.context = context
        self._step_results = {}

    async def execute_step(self, step: dict) -> dict:
        action = step.get("action", "")
        logger.info(f"▶️ Executing step [{step.get('id', '?')}]: {action} - {step.get('description', '')}")
        handler = getattr(self, f"_action_{action}", None)
        if not handler:
            error_msg = f"Unknown action type: {action}"
            logger.error(error_msg)
            return {"step_id": step.get("id"), "status": "error", "error": error_msg}
        try:
            result = await handler(step)
            if step.get("store_in"):
                self.context["extracted"] = self.context.get("extracted", {})
                self.context["extracted"][step["store_in"]] = result.get("value")
            log_msg = f"✅ Step [{step.get('id', '?')}] {action} -> {result.get('status', 'ok')}"
            if result.get("value"):
                log_msg += f" | value: {str(result['value'])[:80]}"
            logger.info(log_msg)
            return result
        except Exception as e:
            logger.error(f"❌ Step [{step.get('id', '?')}] {action} failed: {e}")
            return {"step_id": step.get("id"), "status": "error", "error": str(e)}

    async def _get_page(self):
        if hasattr(self.browser_context, 'get_current_page'):
            return await self.browser_context.get_current_page()
        return self.browser_context.page

    async def _action_goto(self, step: dict) -> dict:
        page = await self._get_page()
        url = self.template_engine.resolve(step["url"], self.context)
        logger.info(f"   → Navigating to: {url}")
        await page.goto(url, wait_until="domcontentloaded")
        await self._wait_after(step)
        return {"status": "ok", "value": url}

    async def _action_click(self, step: dict) -> dict:
        page = await self._get_page()
        element, source = await self.selector_resolver.resolve_element(
            step.get("selectors", {}), step.get("description", "click element")
        )
        if element:
            await element.click()
            await self._wait_after(step)
            return {"status": "ok", "source": source}
        if step.get("optional"):
            logger.warning(f"   ⚠️ Optional click skipped (element not found)")
            return {"status": "skipped", "reason": "element not found"}
        raise Exception(f"Could not find element to click")

    async def _action_fill(self, step: dict) -> dict:
        page = await self._get_page()
        value = self.template_engine.resolve(step["value"], self.context)
        element, source = await self.selector_resolver.resolve_element(
            step.get("selectors", {}), step.get("description", "fill input")
        )
        if element:
            await element.fill("")
            await element.fill(value)
            if step.get("trigger_events", False):
                await element.evaluate("""el => {
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                    el.dispatchEvent(new Event('blur', { bubbles: true }));
                    el.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, key: (el.value || ' ').slice(-1) }));
                }""")
            await self._wait_after(step)
            return {"status": "ok", "source": source, "value": value}
        raise Exception(f"Could not find input to fill")

    async def _action_select_option(self, step: dict) -> dict:
        page = await self._get_page()
        value = self.template_engine.resolve(step["value"], self.context)
        element, source = await self.selector_resolver.resolve_element(
            step.get("selectors", {}), step.get("description", "select option")
        )
        if element:
            await element.select_option(value)
            await self._wait_after(step)
            return {"status": "ok", "source": source, "value": value}
        raise Exception(f"Could not find select element")

    async def _action_extract(self, step: dict) -> dict:
        page = await self._get_page()
        element, source = await self.selector_resolver.resolve_element(
            step.get("selectors", {}), step.get("description", "extract text"),
            try_human=not step.get("optional", False)
        )
        if element:
            text = await element.inner_text()
            text = text.strip()
            logger.info(f"   → Extracted text: {text[:100]}")
            return {"status": "ok", "value": text}
        if step.get("optional"):
            logger.warning(f"   ⚠️ Optional extract skipped (element not found)")
            return {"status": "skipped", "reason": "element not found"}
        raise Exception(f"Could not find element to extract from")

    async def _action_extract_attribute(self, step: dict) -> dict:
        page = await self._get_page()
        attr = step.get("attribute", "innerText")
        element, source = await self.selector_resolver.resolve_element(
            step.get("selectors", {}), step.get("description", "extract attribute"),
            try_human=not step.get("optional", False)
        )
        if element:
            text = await element.get_attribute(attr) or await element.inner_text()
            text = text.strip()
            logger.info(f"   → Extracted {attr}: {text[:100]}")
            return {"status": "ok", "value": text}
        if step.get("optional"):
            logger.warning(f"   ⚠️ Optional extract_attribute skipped (element not found)")
            return {"status": "skipped", "reason": "element not found"}
        raise Exception(f"Could not find element to extract attribute from")

    async def _action_check_exists(self, step: dict) -> dict:
        page = await self._get_page()
        element, source = await self.selector_resolver.resolve_element(
            step.get("selectors", {}), step.get("description", "check if exists"),
            try_human=not step.get("optional", False)
        )
        exists = element is not None
        logger.info(f"   → Element exists: {exists}")
        return {"status": "ok", "value": exists}

    async def _action_fill_otp(self, step: dict) -> dict:
        page = await self._get_page()
        value = self.template_engine.resolve(step["value"], self.context)
        element, source = await self.selector_resolver.resolve_element(
            step.get("selectors", {}), step.get("description", "fill OTP")
        )
        if not element:
            raise Exception(f"Could not find OTP container element")
        inputs = await element.query_selector_all("input")
        if not inputs:
            raise Exception(f"No input elements found inside OTP container")
        for i, input_el in enumerate(inputs):
            if i < len(value):
                await input_el.fill(value[i])
        await self._wait_after(step)
        return {"status": "ok", "source": source, "value": value}

    async def _action_wait(self, step: dict) -> dict:
        ms = step.get("ms", 1000)
        logger.info(f"   → Waiting {ms}ms")
        await asyncio.sleep(ms / 1000)
        return {"status": "ok"}

    async def _action_wait_timer(self, step: dict) -> dict:
        import re
        timer_var = step.get("timer_var", "")
        safety_margin = step.get("safety_margin", 5)
        default_wait = step.get("default_wait_ms", 120000)
        timer_text = self.context.get("extracted", {}).get(timer_var, "")
        if not timer_text:
            logger.warning(f"   ⚠️ Timer variable '{timer_var}' not found, using default {default_wait}ms")
            wait_ms = default_wait
        else:
            match = re.search(r'(\d+):(\d+)', timer_text)
            if match:
                minutes = int(match.group(1))
                seconds = int(match.group(2))
                total_seconds = minutes * 60 + seconds + safety_margin
                wait_ms = total_seconds * 1000
                logger.info(f"   → Parsed timer: {minutes}m {seconds}s + {safety_margin}s safety = {total_seconds}s ({wait_ms}ms)")
            else:
                logger.warning(f"   ⚠️ Could not parse timer text: '{timer_text}', using default {default_wait}ms")
                wait_ms = default_wait
        await asyncio.sleep(wait_ms / 1000)
        return {"status": "ok", "value": wait_ms}

    async def _action_conditional(self, step: dict) -> dict:
        condition_var = step.get("condition_var", "")
        expected = step.get("condition_value", True)
        condition_type = step.get("condition_type", "exact")
        steps_if_true = step.get("steps_if_true", [])
        steps_if_false = step.get("steps_if_false", [])
        actual_value = self.context.get("extracted", {}).get(condition_var)
        if actual_value is None:
            actual_value = self.context.get(condition_var)
        actual_str = str(actual_value) if actual_value is not None else ""
        if condition_type == "startswith":
            match = actual_str.startswith(str(expected))
        elif condition_type == "contains":
            match = str(expected) in actual_str
        else:
            match = actual_value == expected
        logger.info(f"   → Conditional: {condition_var}={actual_value} | type={condition_type} | expected={expected}? {match}")
        steps_to_run = steps_if_true if match else steps_if_false
        for sub_step in steps_to_run:
            await self.execute_step(sub_step)
        return {"status": "ok", "branch": "true" if match else "false"}

    async def _action_custom_logic(self, step: dict) -> dict:
        func_name = step.get("function", "")
        params_raw = step.get("params", {})
        params = self.template_engine.resolve_all(params_raw, self.context)
        logic = self.context.get("_logic_functions", {}).get(func_name)
        if logic:
            logger.info(f"   → Running custom logic: {func_name}")
            result = await logic(**params) if asyncio.iscoroutinefunction(logic) else logic(**params)
            self.context["calculated"] = self.context.get("calculated", {})
            self.context["calculated"][step.get("store_in", func_name)] = result
            return {"status": "ok", "value": result}
        logger.warning(f"   ⚠️ Custom function '{func_name}' not found, skipping")
        return {"status": "skipped"}

    async def _action_ask_human(self, step: dict) -> dict:
        question = self.template_engine.resolve(step.get("question", "Please assist"), self.context)
        timeout = step.get("timeout", 300)
        logger.info(f"🤔 Asking human: {question}")
        if self.selector_resolver.ask_human_callback:
            try:
                while True:
                    response = await asyncio.wait_for(
                        self.selector_resolver.ask_human_callback(question),
                        timeout=timeout
                    )
                    user_response = response.get("response", "").strip()
                    if user_response:
                        break
                    logger.info("   ⚠️ Empty response, asking again...")
                store_key = step.get("store_in", "human_response")
                self._step_results[store_key] = user_response
                self.context["extracted"] = self.context.get("extracted", {})
                self.context["extracted"][store_key] = user_response
                return {"status": "ok", "value": user_response}
            except asyncio.TimeoutError:
                logger.error(f"   ⏰ Timeout after {timeout}s waiting for human response")
                return {"status": "timeout", "error": f"No response within {timeout}s"}
        logger.warning("   ⚠️ No human callback available, skipping")
        return {"status": "skipped"}

    async def _action_screenshot(self, step: dict) -> dict:
        page = await self._get_page()
        save_path = step.get("save_path", "./tmp/screenshots")
        os.makedirs(save_path, exist_ok=True)
        filename = f"step_{step.get('id', 'screenshot')}.png"
        filepath = os.path.join(save_path, filename)
        await page.screenshot(path=filepath, full_page=True)
        logger.info(f"   → Screenshot saved: {filepath}")
        return {"status": "ok", "value": filepath}

    async def _action_run_agent(self, step: dict) -> dict:
        prompt = self.template_engine.resolve(step.get("prompt", ""), self.context)
        logger.info(f"   → Running agent sub-task: {prompt[:80]}...")
        controller_ref = self.context.get("_controller")
        llm = self.context.get("_llm")
        agent_class = self.context.get("_agent_class")
        if not all([controller_ref, llm, agent_class]):
            logger.warning("   ⚠️ Missing agent dependencies, falling back to AI detection")
            return {"status": "skipped"}
        from src.agent.browser_use.browser_use_agent import BrowserUseAgent
        agent = BrowserUseAgent(
            task=prompt,
            llm=llm,
            browser=self.context.get("_browser"),
            browser_context=self.browser_context,
            controller=controller_ref,
            use_vision=step.get("use_vision", False),
            source="webui",
        )
        history = await agent.run(max_steps=step.get("max_steps", 20))
        result = history.final_result()
        logger.info(f"   → Agent sub-task result: {result}")
        return {"status": "ok", "value": result}

    async def _wait_after(self, step: dict):
        ms = step.get("wait_after", 500)
        if ms:
            await asyncio.sleep(ms / 1000)
