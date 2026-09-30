"""Product must consume sdoh_core from GitHub and not import Core document UX."""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = REPO_ROOT / "agents"
PYPROJECTS = [
    REPO_ROOT / "analytic_assistant_build" / "pyproject.openai.toml",
    REPO_ROOT / "analytic_assistant_build" / "pyproject.local.toml",
]
COMPOSE = REPO_ROOT / "docker-compose.yaml"

FORBIDDEN_IMPORT_MARKERS = (
    "sdoh_core.document_section_tool",
    "sdoh_core.requirements_file",
    "sdoh_core.react_agent",
    "run_assistant_app",
    "AssistantAppConfig",
    "RequirementsFileHelper",
    "DocumentSectionTool",
)


def _import_lines(path: Path) -> list[str]:
    lines = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        code = raw.split("#", 1)[0].strip()
        if code.startswith(("import ", "from ")):
            lines.append(code)
    return lines


def test_product_python_does_not_import_core_document_workflow():
    py_files = list(AGENTS_DIR.rglob("*.py"))
    assert py_files, f"no Python files under {AGENTS_DIR}"
    offenders = []
    for path in py_files:
        for line in _import_lines(path):
            if any(marker in line for marker in FORBIDDEN_IMPORT_MARKERS):
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {line}")
    assert not offenders, "forbidden Core document-workflow imports:\n" + "\n".join(
        offenders
    )


def test_poetry_uses_github_sdoh_core_not_local_path():
    for path in PYPROJECTS:
        text = path.read_text(encoding="utf-8")
        assert "sdoh-core" in text, f"{path.name} must depend on sdoh-core"
        assert "github.com/SocialHealthAI/SDoH-Core-Assistant" in text, (
            f"{path.name} must use the GitHub Git URL"
        )
        for raw in text.splitlines():
            code = raw.split("#", 1)[0]
            if "sdoh-core" not in code:
                continue
            lowered = code.lower()
            assert "path" not in lowered, f"{path.name} must not use a path dependency"
            assert "github.com/socialhealthai/sdoh-core-assistant" in lowered


def test_compose_does_not_bind_mount_core_or_set_core_pythonpath():
    text = COMPOSE.read_text(encoding="utf-8")
    assert "PYTHONPATH" not in text
    for raw in text.splitlines():
        code = raw.split("#", 1)[0].strip()
        if not code:
            continue
        assert "SDoH-Core-Assistant" not in code
        assert "../SDoH-Core" not in code
