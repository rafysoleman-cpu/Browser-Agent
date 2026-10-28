import logging
import re

logger = logging.getLogger(__name__)


class TemplateEngine:
    def __init__(self):
        self.pattern = re.compile(r"\{\{([^}]+)\}\}")

    def resolve(self, text: str, context: dict) -> str:
        if not text or "{{" not in text:
            return text
        def _replace(match):
            key_path = match.group(1).strip()
            parts = key_path.split(".")
            value = context
            for part in parts:
                if isinstance(value, dict):
                    value = value.get(part, "")
                else:
                    logger.warning(f"Template key '{match.group(0)}' not found in context")
                    return ""
            if value is None:
                logger.warning(f"Template key '{match.group(0)}' resolved to None")
                return ""
            return str(value)
        return self.pattern.sub(_replace, text)

    def resolve_all(self, obj, context: dict):
        if isinstance(obj, str):
            return self.resolve(obj, context)
        elif isinstance(obj, dict):
            return {k: self.resolve_all(v, context) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self.resolve_all(v, context) for v in obj]
        return obj
