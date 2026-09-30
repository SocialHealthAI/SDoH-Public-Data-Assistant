# Feature Brief: Consume SDoH Core via GitHub

**Task ID:** refactor-use-core  
**Created:** 2026-09-28  
**Status:** Ready for Development

---

## Problem Statement

The Public Data Assistant and other SDoH products share LLM construction, the tool-calling loop, and audit invocation. That shared code belongs in the `sdoh_core` package (`SDoH-Core-Assistant`), not in each product. Public Data must depend on Core **from GitHub**, keep product-owned tools and UI, and **not** take on Core’s requirements-document workflow (`document_section_tool`).

The Core checkout is mounted in this workspace **for review only**. Runtime and Docker builds must not use a local path dependency.

## Target Users

- **Maintainers** of the Public Data Assistant who change agent, audit, or Streamlit wiring.
- **Operators** who build the Docker image and expect `sdoh-core` to resolve from GitHub.
- **Core library authors** who need a stable product consume pattern (Git URL, not a sibling path).

## Core Requirements

### Must Have
- [x] Public Data depends on Poetry package `sdoh-core` (import `sdoh_core`) from `https://github.com/SocialHealthAI/SDoH-Core-Assistant.git` in both `analytic_assistant_build/pyproject.openai.toml` and `pyproject.local.toml`.
- [x] Product uses Core for: LLM factory (`llm_config`), tool-calling loop (`agent_types` / `build_tool_calling_agent`), audit LLM runner (`AuditAgent`), and Streamlit helpers (`escape_markdown`, `logic_step_*`).
- [x] Product keeps: public-data tools, chart/map renderers, `agent_system_prompt.txt`, audit criteria, and the custom Streamlit chat + viz shell.
- [x] `document_section_tool` is not imported or wired. Do not use Core `run_assistant_app` / `AssistantAppConfig` (requirements-file UX).
- [x] Product `ReActAgent` stays product-owned (tool list + prompt). Do not replace it with Core `sdoh_core.react_agent.ReActAgent` (that shell is for optional document writes).
- [x] No local `path = "../SDoH-Core-Assistant"` dependency in Poetry or Docker. Core on disk is review-only.
- [x] User-facing docs stay accurate: `documentation/architecture.md` (boundary), `documentation/installation.md` (LLM env via Core).
- [x] Anthropic is testable: `.env` / `.env.example` expose `LLM_PROVIDER`, `LLM_MODEL`, and `ANTHROPIC_API_KEY`; Compose passes `ANTHROPIC_API_KEY`; product agent and audit follow `sdoh_core` provider/model (no hardcoded `gpt-5.2` / `gpt-4o`).

### Nice to Have
- [ ] Pin Core to a version tag (`v0.1.0`) once Core publishes tags; until then `branch = "main"` is acceptable.
- [x] Remove leftover product files that are unused after the split (for example orphan `agents/.py` if still unwired).
- [x] Note in README that shared agent cores come from `sdoh_core` (optional; architecture.md already states it).

## Technical Approach

Compose Core **building blocks**, do not adopt Core’s full requirements-assistant orchestrator.

**From Core:** `build_chat_model`, `build_tool_calling_agent`, `ToolCallingAgent._default_system_prompt`, `AuditAgent`, `llm_content_to_text`, Streamlit step/markdown helpers.

**In Public Data:** `agents/react_agent.py` builds the public-data tool list (MCP, CMS, PLACES, stats, chart/map, geo) and merges Core’s loop prompt with `agent_system_prompt.txt`. `agents/audit_agent.py` subclasses Core `AuditAgent` with product review criteria. `agents/streamlit_assistant.py` remains a custom shell so charts and maps can persist in session state.

**Patterns to Follow:**
- Poetry Git dependency already declared: `sdoh-core = { git = "https://github.com/SocialHealthAI/SDoH-Core-Assistant.git", branch = "main" }`.
- Product `ReActAgent` docstring: LLM factory and loop from Core; tools and prompt stay here.
- Architecture.md already documents the split and unused `document_section_tool`.

**Key Decisions:**
- **GitHub, not path:** Docker image install must clone Core from GitHub. Sibling mount is for humans reviewing Core, not for `PYTHONPATH`.
- **Partial Streamlit reuse:** Core `run_assistant_app` assumes confirm-before-write on a requirements markdown file. Analytics needs a different shell.
- **Keep product `ReActAgent` name:** Same class name as Core’s orchestrator, different constructor. Avoid importing Core’s `ReActAgent` to prevent accidental document-tool coupling.
- **Anthropic via Core, not a product LLM factory:** `LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY` are enough; Core selects `claude-sonnet-5` when `LLM_MODEL` is empty. Audit uses the same provider so Claude can be tested without an OpenAI key.

## Current state (as of brief)

Already in product code (uncommitted / in-tree):
- `agent_types.py` removed; loop imported from `sdoh_core`.
- `react_agent.py`, `audit_agent.py`, `streamlit_assistant.py` import Core as described above.
- Both pyproject files use the GitHub Git dependency.
- Architecture and installation docs mention `sdoh_core`.

Remaining work is to **lock the boundary**, confirm Docker/Git consume, and finish any leftover product duplication—not to start the split from scratch.

## Next Actions

1. [x] Anthropic env + wiring for testing (`LLM_PROVIDER` / `ANTHROPIC_API_KEY` through Compose; agent/audit use Core defaults).
2. [x] Confirm Docker build (`dockerfile.openai`) installs `sdoh-core` from GitHub with no Core bind-mount or `PYTHONPATH` to a local checkout.
3. [x] Grep product code for remaining copies of Core APIs (`ToolCallingAgent`, LLM factory, document/requirements helpers) and delete or rewire them.
4. [x] Keep `document_section_tool` / `RequirementsFileHelper` / `run_assistant_app` out of product imports; add a unit or import-linter check if useful.
5. [x] Align docs if the consume pin changes (branch vs tag).
6. [x] Run existing pytest (`tests/unit`) after the dependency settles. Host run: 56 passed; `test_analysis_tools.py` needs `scipy` (run in the assistant container).

## Success Criteria

- [x] Image build resolves `sdoh-core` from GitHub; local Core checkout is not required to run. (Dockerfile installs Git; Poetry uses the GitHub URL; Compose does not mount Core.)
- [ ] Chat, tools, charts, maps, and optional audit still work with Core providing LLM + loop + audit invoke. (Code path confirmed; live UI not exercised in this pass — containers were down.)
- [x] Switching `.env` to `LLM_PROVIDER=anthropic`, `LLM_MODEL=claude-sonnet-5`, and `ANTHROPIC_API_KEY` runs the assistant (and audit) on Claude without a hardcoded OpenAI model.
- [x] No product import of `sdoh_core.document_section_tool` or Core `run_assistant_app`.
- [x] Architecture/installation docs match the GitHub consume story and LLM provider env.

## Open Questions

- Pin `branch = "main"` until Core cuts `v0.1.0`, or wait on a tag before treating this brief as done?
- Private-repo Docker git credentials: Core is public on GitHub today; if it becomes private, the image build needs git auth (do not bake a PAT into the image).

---

## Changelog

| Date | Change |
|------|--------|
| 2026-09-28 | Added Anthropic test support: env template, Compose `ANTHROPIC_API_KEY`, product LLM/audit follow `sdoh_core` provider instead of hardcoded OpenAI models. |
| 2026-09-29 | Discovery: GitHub `ToolCallingAgent` parsed the product system prompt as an f-string; `{...}` in chart/map examples crashed Anthropic startup. Core now uses a literal `SystemMessage`; product escapes braces until that Core fix is on GitHub. |

---

*Brief created with SDD 6.0 - Ready to code!*
