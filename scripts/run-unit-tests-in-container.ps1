# Run fast unit tests in the running public-data-assistant container (LangChain 0.3.x venv).
# Prerequisite: docker compose up (public-data-assistant running), ./tests mounted at /app/tests.
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$pytestArgs = if ($args.Count -gt 0) { $args -join " " } else { "-q" }

docker compose exec public-data-assistant bash -lc @"
/opt/venv/bin/pip install -q pytest
cd /myapps
/opt/venv/bin/python -m pytest /app/tests/unit/ $pytestArgs
"@
