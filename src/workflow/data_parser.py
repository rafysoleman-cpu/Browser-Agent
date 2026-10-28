import json
import logging
import os
import re

logger = logging.getLogger(__name__)


class DataParser:
    def __init__(self):
        self.field_pattern = re.compile(r"^\s*(?:- )?(.+?):\s*(.+)\s*$", re.MULTILINE)

    def parse_task_prompt(self, prompt: str) -> dict:
        logger.info("=" * 60)
        logger.info("📝 PARSING TASK PROMPT")
        logger.info("=" * 60)
        data = {}
        lines = prompt.strip().split("\n")
        current_key = None
        current_value = []
        for line in lines:
            match = self.field_pattern.match(line)
            if match:
                if current_key and current_value:
                    data[current_key.lower().replace(" ", "_")] = "\n".join(current_value).strip()
                    current_value = []
                key = match.group(1).strip()
                val = match.group(2).strip()
                current_key = key
                current_value.append(val) if val else None
            elif current_key and line.strip():
                current_value.append(line.strip())
        if current_key and current_value:
            data[current_key.lower().replace(" ", "_")] = "\n".join(current_value).strip()
        app_type = self._detect_app_type(prompt, data)
        if app_type:
            data["_app_type"] = app_type
        data_file_path = self._find_data_file_in_prompt(prompt)
        if data_file_path:
            try:
                file_data = self.parse_data_file(data_file_path)
                for k, v in file_data.items():
                    if k not in data or not data[k]:
                        data[k] = v
                logger.info(f"✅ Loaded data from file: {data_file_path}")
            except Exception as e:
                logger.error(f"Failed to load data file '{data_file_path}': {e}")
        logger.info(f"📊 Parsed data keys: {list(data.keys())}")
        logger.info("=" * 60)
        return data

    def _detect_app_type(self, prompt: str, data: dict) -> str:
        known_apps = {
            "login": ["login", "log in", "sign in", "authentication"],
            "land-transfer": ["land transfer", "land mutation", "mutation", "জমি", "ভূমি"],
            "e-passport": ["passport", "e-passport", "epassport"],
            "new-voter": ["voter", "new voter", "registration", "নতুন ভোটার"],
            "correction": ["correction", "fix", "correct", "সংশোধন"],
        }
        text = (prompt + " " + json.dumps(data)).lower()
        for app_name, keywords in known_apps.items():
            for kw in keywords:
                if kw.lower() in text:
                    logger.info(f"🔍 Detected application type: {app_name}")
                    return app_name
        return ""

    def _find_data_file_in_prompt(self, prompt: str) -> str:
        patterns = [
            r"(?:file|path|from)\s*[:\s]+([^\n]+\.(?:txt|json|md))",
            r"(?:read|load|open)\s+([^\n]+\.(?:txt|json|md))",
            r"([^\s]+\.(?:txt|json|md))",
        ]
        for pattern in patterns:
            match = re.search(pattern, prompt, re.IGNORECASE)
            if match:
                path = match.group(1).strip().strip('"').strip("'")
                if os.path.exists(path):
                    return path
                alt_path = os.path.join(os.getcwd(), path)
                if os.path.exists(alt_path):
                    return alt_path
        return ""

    def parse_data_file(self, file_path: str) -> dict:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Data file not found: {file_path}")
        _, ext = os.path.splitext(file_path)
        ext = ext.lower()
        if ext == ".json":
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        elif ext == ".txt" or ext == ".md":
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            return self._parse_text_data(content)
        else:
            raise ValueError(f"Unsupported file type: {ext}")

    def _parse_text_data(self, content: str) -> dict:
        data = {}
        lines = content.strip().split("\n")
        current_key = None
        current_value = []
        for line in lines:
            match = self.field_pattern.match(line)
            if match:
                if current_key and current_value:
                    data[current_key.lower().replace(" ", "_")] = "\n".join(current_value).strip()
                    current_value = []
                key = match.group(1).strip()
                val = match.group(2).strip()
                current_key = key
                current_value.append(val) if val else None
            elif current_key and line.strip():
                current_value.append(line.strip())
        if current_key and current_value:
            data[current_key.lower().replace(" ", "_")] = "\n".join(current_value).strip()
        return data
