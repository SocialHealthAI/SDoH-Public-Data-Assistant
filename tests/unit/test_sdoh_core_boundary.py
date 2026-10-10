"""Product must consume sdoh_core from GitHub (no local path)."""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECTS = [
    REPO_ROOT / "analytic_assistant_build" / "pyproject.openai.toml",
    REPO_ROOT / "analytic_assistant_build" / "pyproject.local.toml",
]
COMPOSE = REPO_ROOT / "docker-compose.yaml"


def test_poetry_uses_github_sdoh_core_not_local_path():
    for path in PYPROJECTS:
        text = path.read_text(encoding="utf-8")
        assert "sdoh-core" in text, f"{path.name} must depend on sdoh-core"
        assert "github.com/SocialHealthAI/SDoH-Core-Assistant" in text, (
            f"{path.name} must use the GitHub Git URL"
        )
        assert 'branch = "main"' in text, (
            f"{path.name} must pin Core main after the Core merge"
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
    assert "DOCUMENTS_ROOT" in text
    assert "sdoh_documents" in text
    for raw in text.splitlines():
        code = raw.split("#", 1)[0].strip()
        if not code:
            continue
        assert "SDoH-Core-Assistant" not in code
        assert "../SDoH-Core" not in code
