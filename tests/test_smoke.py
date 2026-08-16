"""Smoke tests for JARVIS Foundation (Phase 0).

Smoke tests are high-level, lightweight tests to verify that
the basic environment, core packages, and project structure
are functioning properly without runtime crashes.
"""

import sys
from pathlib import Path
import importlib


def test_python_version() -> None:
    """Verify that Python version meets the minimum requirement (>= 3.10)."""
    assert sys.version_info >= (3, 10), f"Python version too low: {sys.version}"


def test_core_dependencies_import() -> None:
    """Verify that essential foundation dependencies can be imported successfully."""
    dependencies = [
        "pydantic",
        "dotenv",
        "langchain_core",
    ]
    for dep in dependencies:
        module = importlib.import_module(dep)
        assert module is not None, f"Failed to import dependency: {dep}"


def test_app_package_import() -> None:
    """Verify that the JARVIS app package can be imported and has version info."""
    import app

    assert hasattr(app, "__version__"), "app package is missing __version__ attribute"
    assert app.__version__ == "0.1.0", f"Unexpected version: {app.__version__}"


def test_project_spec_exists() -> None:
    """Verify that the project specification document exists and is readable."""
    project_root = Path(__file__).resolve().parent.parent
    spec_file = project_root / "docs" / "PROJECT_SPEC.md"
    assert spec_file.exists(), f"PROJECT_SPEC.md not found at {spec_file}"
    assert spec_file.stat().st_size > 0, "PROJECT_SPEC.md is empty"


def test_agents_rule_exists() -> None:
    """Verify that the AI rules document AGENTS.md exists and is readable."""
    project_root = Path(__file__).resolve().parent.parent
    agents_file = project_root / "AGENTS.md"
    assert agents_file.exists(), f"AGENTS.md not found at {agents_file}"
    assert agents_file.stat().st_size > 0, "AGENTS.md is empty"


def test_readme_exists() -> None:
    """Verify that README.md exists and is non-empty."""
    project_root = Path(__file__).resolve().parent.parent
    readme_file = project_root / "README.md"
    assert readme_file.exists(), f"README.md not found at {readme_file}"
    assert readme_file.stat().st_size > 0, "README.md is empty"


def test_pyproject_toml_exists() -> None:
    """Verify that pyproject.toml exists and contains project configuration."""
    project_root = Path(__file__).resolve().parent.parent
    pyproject_file = project_root / "pyproject.toml"
    assert pyproject_file.exists(), f"pyproject.toml not found at {pyproject_file}"
    content = pyproject_file.read_text(encoding="utf-8")
    assert "[project]" in content, "pyproject.toml missing [project] section"
    assert "[tool.pytest.ini_options]" in content, "pyproject.toml missing pytest configuration"
