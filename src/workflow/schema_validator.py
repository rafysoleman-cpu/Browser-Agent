import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class SchemaValidator:
    def __init__(self, ask_human_callback=None):
        self.ask_human_callback = ask_human_callback

    def validate(self, schema: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("=" * 60)
        logger.info("📋 SCHEMA VALIDATION")
        logger.info("=" * 60)
        fields = schema.get("fields", {})
        missing_fields = []
        for field_name, field_def in fields.items():
            required = field_def.get("required", False)
            value = data.get(field_name)
            if required and (value is None or value == ""):
                missing_fields.append({"name": field_name, "definition": field_def})
        derived = schema.get("derived_fields", {})
        for field_name, field_def in derived.items():
            deps = field_def.get("depends_on", [])
            all_deps_present = all(dep in data for dep in deps)
            if all_deps_present:
                data[field_name] = f"__derived__{field_name}__"
                logger.info(f"   → Derived field '{field_name}' marked for computation")
        if missing_fields:
            logger.warning(f"⚠️ Missing {len(missing_fields)} required field(s)")
            for mf in missing_fields:
                logger.warning(f"   - {mf['name']}: {mf['definition'].get('description', 'No description')}")
            if self.ask_human_callback:
                self._ask_for_missing(missing_fields, data)
            else:
                raise ValueError(f"Missing required fields: {[m['name'] for m in missing_fields]}")
        else:
            logger.info("✅ All required fields present")
        logger.info("=" * 60)
        return data

    def _ask_for_missing(self, missing_fields: List[Dict], data: Dict[str, Any]):
        import asyncio
        for mf in missing_fields:
            name = mf["name"]
            definition = mf["definition"]
            question = (
                f"⚠️ Missing required field: **{name}**\n"
                f"Description: {definition.get('description', 'N/A')}\n"
                f"Type: {definition.get('type', 'string')}\n"
                f"Please provide the value for '{name}':"
            )
            logger.info(f"🤔 Asking human for missing field: {name}")
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    response = None
                    if self.ask_human_callback:
                        coro = self.ask_human_callback(question)
                        try:
                            import asyncio
                            future = asyncio.run_coroutine_threadsafe(coro, loop)
                            response = future.result(timeout=120)
                        except Exception as e:
                            logger.error(f"Failed to get human response for {name}: {e}")
                    if response and response.get("response", "").strip():
                        data[name] = response["response"].strip()
                        logger.info(f"   ✅ Got value for '{name}' from human")
                    else:
                        data[name] = ""
                        logger.warning(f"   ⚠️ No value provided for '{name}', leaving empty")
                else:
                    value = input(f"  Enter value for '{name}' ({definition.get('description', '')}): ")
                    data[name] = value.strip()
            except Exception as e:
                logger.error(f"Error asking for missing field '{name}': {e}")
                data[name] = ""

    def get_field_descriptions(self, schema: Dict[str, Any]) -> str:
        fields = schema.get("fields", {})
        lines = ["Available fields:"]
        for name, field_def in fields.items():
            req = "🔴 REQUIRED" if field_def.get("required") else "🟢 optional"
            desc = field_def.get("description", "No description")
            ftype = field_def.get("type", "string")
            enum_vals = field_def.get("values")
            enum_str = f" ({', '.join(enum_vals)})" if enum_vals else ""
            lines.append(f"  - {name} [{ftype}{enum_str}] {req}: {desc}")
        return "\n".join(lines)

    def is_valid(self, schema: Dict[str, Any], data: Dict[str, Any]) -> bool:
        try:
            self.validate(schema, data)
            return True
        except (ValueError, Exception) as e:
            logger.error(f"Validation failed: {e}")
            return False
