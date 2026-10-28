import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__))))

from src.workflow import DataParser, SchemaValidator, TemplateEngine
from src.workflow.workflow_engine import WorkflowEngine

def test_template_engine():
    t = TemplateEngine()
    assert t.resolve("Hello {{name}}", {"name": "World"}) == "Hello World"
    assert t.resolve("No template", {}) == "No template"
    assert t.resolve("{{a.b}}", {"a": {"b": "nested"}}) == "nested"
    assert t.resolve("{{missing}}", {}) == ""
    print("✅ TemplateEngine: All tests passed")

def test_data_parser():
    parser = DataParser()
    prompt = "Do a login for mutation portal.\nMobile Number: 01712345678\nPassword: mypass123\nUser Type: Citizen"
    parsed = parser.parse_task_prompt(prompt)
    assert parsed.get("mobile_number") == "01712345678"
    assert parsed.get("password") == "mypass123"
    assert parsed.get("user_type") == "Citizen"
    assert parsed.get("_app_type") == "login"
    print(f"✅ DataParser: All tests passed (parsed {len(parsed)} fields)")

def test_schema_validator():
    schema = {
        "name": "mutation_login",
        "fields": {
            "mobile_number": {"type": "string", "required": True, "description": "Mobile number"},
            "password": {"type": "string", "required": False, "description": "Password"},
            "user_type": {"type": "enum", "values": ["Citizen", "Organization"], "required": False},
        }
    }
    v = SchemaValidator()
    # Test with all fields
    result = v.validate(schema, {"mobile_number": "01712345678", "password": "mypass", "user_type": "Citizen"})
    assert result["mobile_number"] == "01712345678"
    print("✅ SchemaValidator: Validation with all fields passed")
    # Test with missing required field
    try:
        v.validate(schema, {"password": "mypass"})
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "mobile_number" in str(e)
        print("✅ SchemaValidator: Missing field detection passed")

def test_workflow_engine_loading():
    engine = WorkflowEngine(
        browser_context=None,
        llm=None,
        ask_human_callback=None,
        controller=None,
    )
    engine.WORKFLOWS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "workflows")
    # Test loading site.json
    site = engine._load_json("site", "mutation", None)
    assert site is not None
    assert site["name"] == "Mutation Portal Bangladesh"
    print(f"✅ WorkflowEngine: site.json loaded -> {site['name']}")
    # Test loading app.json
    app = engine._load_json("app", "mutation", "login")
    assert app is not None
    assert app["name"] == "Login"
    print(f"✅ WorkflowEngine: app.json loaded -> {app['name']}")
    # Test loading selectors.json
    selectors = engine._load_json("selectors", "mutation", "login")
    assert selectors is not None
    assert len(selectors) >= 10
    print(f"✅ WorkflowEngine: selectors.json loaded ({len(selectors)} entries)")
    # Test loading schema.json
    schema = engine._load_json("schema", "mutation", "login")
    assert schema is not None
    assert "fields" in schema
    print(f"✅ WorkflowEngine: schema.json loaded ({len(schema['fields'])} fields)")
    # Test loading workflow.json
    workflow = engine._load_json("workflow", "mutation", "login")
    assert workflow is not None
    assert "steps" in workflow
    print(f"✅ WorkflowEngine: workflow.json loaded ({len(workflow['steps'])} steps)")
    # Test logic.py detection
    logic_path = engine._get_logic_path("mutation", "login")
    assert "login" in logic_path and "logic.py" in logic_path
    print(f"✅ WorkflowEngine: logic.py path correct")

def test_flow_txt_parsing():
    engine = WorkflowEngine(
        browser_context=None,
        llm=None,
        ask_human_callback=None,
        controller=None,
    )
    engine.WORKFLOWS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "workflows")
    selectors = engine._load_json("selectors", "mutation", "login")
    steps = engine._parse_flow_txt("mutation", "login", selectors or {})
    if steps:
        print(f"✅ WorkflowEngine: flow.txt parsed into {len(steps)} steps")
        for s in steps[:3]:
            print(f"   - {s.get('id')}: {s.get('action')} - {s.get('description', '')[:60]}")
    else:
        print("ℹ️ WorkflowEngine: flow.txt empty or not found (workflow.json will be used instead)")

if __name__ == "__main__":
    test_template_engine()
    test_data_parser()
    test_schema_validator()
    test_workflow_engine_loading()
    test_flow_txt_parsing()
    print("\n" + "=" * 50)
    print("🎉 ALL UNIT TESTS PASSED")
    print("=" * 50)
