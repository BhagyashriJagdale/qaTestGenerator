"""Unit tests for FormatterAgent._strip_imports."""

import pytest
from agents.formatter_agent import FormatterAgent


@pytest.fixture
def formatter():
    return FormatterAgent()


def test_strip_removes_import_line(formatter):
    code = "import { test } from '@playwright/test';\n\ntest('x', () => {});"
    result = formatter._strip_imports(code)
    assert "import" not in result
    assert "test('x'" in result


def test_strip_removes_multiple_imports(formatter):
    code = (
        "import { test, expect } from '@playwright/test';\n"
        "import { Page } from '@playwright/test';\n"
        "\n"
        "test('x', async ({ page }) => { await expect(page).toBeTruthy(); });"
    )
    result = formatter._strip_imports(code)
    assert "import" not in result
    assert "test('x'" in result


def test_strip_preserves_non_import_lines(formatter):
    code = "const BASE_URL = 'http://localhost';\ntest('x', () => {});"
    result = formatter._strip_imports(code)
    assert "const BASE_URL" in result
    assert "test('x'" in result


def test_strip_drops_leading_blank_lines(formatter):
    code = "import { x } from 'y';\n\n\ntest('x', () => {});"
    result = formatter._strip_imports(code)
    assert not result.startswith("\n")


def test_strip_empty_code(formatter):
    assert formatter._strip_imports("") == ""


def test_strip_code_without_imports_unchanged(formatter):
    code = "describe('suite', () => { test('x', () => {}); });"
    result = formatter._strip_imports(code)
    assert result == code


def test_format_api_section_no_duplicate_imports(formatter):
    from core.models import AutomationTestCase, ScenarioType, TestCaseType, Priority
    tests = [
        AutomationTestCase(
            test_case_id="ATC-001",
            title="Test A",
            test_type=TestCaseType.API_AUTOMATION,
            scenario_type=ScenarioType.HAPPY_PATH,
            priority=Priority.HIGH,
            code="import { test } from '@playwright/test';\ntest('A', () => {});",
            file_name="auth.api.spec.ts",
            manual_test_refs=["MTC-001"],
        ),
        AutomationTestCase(
            test_case_id="ATC-002",
            title="Test B",
            test_type=TestCaseType.API_AUTOMATION,
            scenario_type=ScenarioType.NEGATIVE,
            priority=Priority.HIGH,
            code="import { test } from '@playwright/test';\ntest('B', () => {});",
            file_name="auth.api.spec.ts",
            manual_test_refs=["MTC-002"],
        ),
    ]
    output = formatter.format_api_section(tests)
    # Only one import block should appear — not two
    assert output.count("import { test }") == 1
