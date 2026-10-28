import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

from src.workflow.template_engine import TemplateEngine
from src.workflow.selector_resolver import SelectorResolver
from src.workflow.step_executors import StepExecutor
from src.workflow.schema_validator import SchemaValidator
from src.workflow.data_parser import DataParser

logger = logging.getLogger(__name__)


class WorkflowEngine:
    WORKFLOWS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "workflows")

    def __init__(self, browser_context, llm=None, ask_human_callback=None, controller=None):
        self.browser_context = browser_context
        self.llm = llm
        self.ask_human_callback = ask_human_callback
        self.controller = controller
        self.template_engine = TemplateEngine()
        self.selector_resolver = SelectorResolver(browser_context, llm, ask_human_callback)
        self.schema_validator = SchemaValidator(ask_human_callback)
        self.data_parser = DataParser()
        self.executor = None
        self._stop_requested = False
        self._last_result = None

    def request_stop(self):
        self._stop_requested = True
        logger.info("⏹️ Stop requested for workflow engine")

    async def run_workflow(
        self,
        site_name: str,
        app_name: str,
        user_prompt: str = "",
        user_data: Optional[Dict[str, Any]] = None,
        browser=None,
        agent_class=None,
    ) -> Dict[str, Any]:
        self._stop_requested = False
        start_time = datetime.now()
        logger.info("")
        logger.info("█" * 70)
        logger.info("██  WORKFLOW ENGINE STARTED")
        logger.info(f"██  Site: {site_name} | App: {app_name}")
        logger.info(f"██  Start Time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("█" * 70)

        site_config = self._load_json("site", site_name, None)
        app_config = self._load_json("app", site_name, app_name)
        workflow_config = self._load_json("workflow", site_name, app_name)
        schema_config = self._load_json("schema", site_name, app_name)
        selectors_config = self._load_json("selectors", site_name, app_name)

        context = {
            "site": site_config or {},
            "app": app_config or {},
            "data": {},
            "extracted": {},
            "calculated": {},
            "auth": {},
            "_controller": self.controller,
            "_llm": self.llm,
            "_browser": browser,
            "_agent_class": agent_class,
        }

        if app_config and os.path.exists(self._get_logic_path(site_name, app_name)):
            logic = self._load_logic(site_name, app_name)
            if logic:
                context["_logic_functions"] = logic
                logger.info(f"🧠 Loaded {len(logic)} custom logic function(s)")

        user_data = user_data or {}
        if user_prompt:
            parsed = self.data_parser.parse_task_prompt(user_prompt)
            context["data"].update(parsed)
            logger.info(f"📝 Parsed {len(parsed)} field(s) from task prompt")
        context["data"].update(user_data)

        if schema_config:
            logger.info("🔍 Running schema validation...")
            try:
                context["data"] = self.schema_validator.validate(schema_config, context["data"])
            except ValueError as e:
                logger.error(f"❌ Schema validation failed: {e}")
                return self._result("failed", start_time, error=str(e))

        if self._stop_requested:
            return self._result("stopped", start_time)

        self.executor = StepExecutor(self.browser_context, self.selector_resolver, self.template_engine, context)

        steps = workflow_config.get("steps", []) if workflow_config else []
        if not steps and os.path.exists(self._get_flow_txt_path(site_name, app_name)):
            logger.info("📄 No workflow.json steps found, checking flow.txt...")
            steps = self._parse_flow_txt(site_name, app_name, selectors_config or {})

        if not steps:
            error_msg = f"No workflow steps found for {site_name}/{app_name}"
            logger.error(f"❌ {error_msg}")
            return self._result("failed", start_time, error=error_msg)

        logger.info(f"📋 Loaded {len(steps)} workflow step(s)")
        logger.info("─" * 70)

        step_results = []
        failed_step = None
        for i, step in enumerate(steps):
            if self._stop_requested:
                logger.warning("⏹️ Workflow stopped by user")
                break
            step_id = step.get("id", f"step_{i+1}")
            step_desc = step.get("description", step.get("action", "unknown"))
            logger.info(f"[{i+1}/{len(steps)}] Step: {step_id} - {step_desc}")
            result = await self.executor.execute_step(step)
            step_results.append({"step_id": step_id, "result": result})
            if result.get("status") in ("error", "timeout"):
                failed_step = {"step_id": step_id, "error": result.get("error") or "Timeout waiting for user input"}
                logger.error(f"❌ Step '{step_id}' failed: {result.get('error')}")
                break
            logger.info("─" * 70)

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        status = "completed" if not failed_step and not self._stop_requested else (
            "stopped" if self._stop_requested else "failed"
        )

        logger.info("█" * 70)
        logger.info(f"██  WORKFLOW {status.upper()}")
        logger.info(f"██  Duration: {duration:.2f}s")
        logger.info(f"██  Steps: {len(step_results)} executed, "
                     f"CSS={self.selector_resolver.stats['css_hits']}, "
                     f"AI={self.selector_resolver.stats['ai_hits']}, "
                     f"Human={self.selector_resolver.stats['human']}")
        if failed_step:
            logger.info(f"██  Failed at: {failed_step['step_id']} - {failed_step['error']}")
        if context.get("extracted"):
            for k, v in context["extracted"].items():
                logger.info(f"██  Extracted [{k}]: {str(v)[:100]}")
        logger.info("█" * 70)

        self._last_result = {
            "status": status,
            "duration_seconds": duration,
            "steps_executed": len(step_results),
            "step_results": step_results,
            "extracted_data": context.get("extracted", {}),
            "calculated_data": context.get("calculated", {}),
            "selector_stats": self.selector_resolver.stats,
            "failed_step": failed_step,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
        }
        return self._last_result

    def _result(self, status: str, start_time: datetime, error: str = ""):
        duration = (datetime.now() - start_time).total_seconds()
        return {
            "status": status,
            "duration_seconds": duration,
            "steps_executed": 0,
            "step_results": [],
            "extracted_data": {},
            "calculated_data": {},
            "selector_stats": self.selector_resolver.stats,
            "failed_step": {"error": error} if error else None,
            "start_time": start_time.isoformat(),
            "end_time": datetime.now().isoformat(),
        }

    def _load_json(self, file_type: str, site_name: str, app_name: Optional[str]) -> Optional[Dict]:
        if app_name:
            path = os.path.join(self.WORKFLOWS_DIR, site_name, "applications", app_name, f"{file_type}.json")
        else:
            path = os.path.join(self.WORKFLOWS_DIR, site_name, f"{file_type}.json")
        if os.path.exists(path) and os.path.getsize(path) > 0:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load {path}: {e}")
        else:
            logger.debug(f"File not found or empty: {path}")
        return None

    def _get_logic_path(self, site_name: str, app_name: str) -> str:
        return os.path.join(self.WORKFLOWS_DIR, site_name, "applications", app_name, "logic.py")

    def _get_flow_txt_path(self, site_name: str, app_name: str) -> str:
        return os.path.join(self.WORKFLOWS_DIR, site_name, "applications", app_name, "flow.txt")

    def _load_logic(self, site_name: str, app_name: str) -> Optional[Dict]:
        import importlib.util
        path = self._get_logic_path(site_name, app_name)
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            return None
        try:
            spec = importlib.util.spec_from_file_location(f"{site_name}_{app_name}_logic", path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                funcs = {}
                for name in dir(module):
                    if callable(getattr(module, name)) and not name.startswith("_"):
                        funcs[name] = getattr(module, name)
                return funcs
        except Exception as e:
            logger.error(f"Failed to load logic.py: {e}")
        return None

    def _parse_flow_txt(self, site_name: str, app_name: str, selectors: Dict) -> list:
        path = self._get_flow_txt_path(site_name, app_name)
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            lines = [l.strip() for l in content.split("\n") if l.strip()]
            steps = []
            for i, line in enumerate(lines):
                step_id = f"flow_step_{i+1}"
                step = self._parse_flow_line(line, step_id, selectors)
                if step:
                    steps.append(step)
            return steps
        except Exception as e:
            logger.error(f"Failed to parse flow.txt: {e}")
            return []

    def _parse_flow_line(self, line: str, step_id: str, selectors: Dict) -> Optional[Dict]:
        line_lower = line.lower()
        step = {"id": step_id, "description": line}

        if line.startswith("Step") and ":" in line:
            line = line.split(":", 1)[1].strip()

        if "navigate" in line_lower or "go to" in line_lower or "goto" in line_lower:
            step["action"] = "goto"
            import re
            urls = re.findall(r'https?://[^\s]+', line)
            step["url"] = urls[0] if urls else selectors.get("startPageUrl", "")

        elif "click" in line_lower:
            step["action"] = "click"
            for sel_name in selectors:
                if sel_name.lower() in line_lower:
                    step["selectors"] = selectors[sel_name] if isinstance(selectors[sel_name], dict) else {"css": selectors[sel_name]}
                    break

        elif "fill" in line_lower or "input" in line_lower or "type" in line_lower:
            step["action"] = "fill"
            for sel_name in selectors:
                if sel_name.lower() in line_lower:
                    step["selectors"] = selectors[sel_name] if isinstance(selectors[sel_name], dict) else {"css": selectors[sel_name]}
                    break

        elif "wait" in line_lower:
            step["action"] = "wait"
            import re
            nums = re.findall(r'\d+', line)
            step["ms"] = int(nums[0]) if nums else 1000

        elif "extract" in line_lower or "read" in line_lower or "captcha" in line_lower:
            step["action"] = "extract"
            for sel_name in selectors:
                if sel_name.lower() in line_lower:
                    step["selectors"] = selectors[sel_name] if isinstance(selectors[sel_name], dict) else {"css": selectors[sel_name]}
                    break

        elif "check" in line_lower or "if" in line_lower or "exist" in line_lower:
            step["action"] = "check_exists"
            for sel_name in selectors:
                if sel_name.lower() in line_lower:
                    step["selectors"] = selectors[sel_name] if isinstance(selectors[sel_name], dict) else {"css": selectors[sel_name]}
                    break

        else:
            logger.warning(f"   ⚠️ Could not parse flow line: {line}")
            return None

        step["wait_after"] = 500
        return step if "action" in step else None
