# Feature Brief: Add AI Solution Requirements Document Support

**Task ID:** add-document-support  
**Created:** 2026-10-01  
**Status:** Ready for Development

---

## Problem Statement

The Public Data Assistant can search, fetch, analyze, and map public SDoH data, but it cannot attach those findings to an **AI Solution Requirements Definition**. Practitioners need the same confirm-before-write document workflow other SDoH assistants use: specify a requirements file, use public-data tools to test availability, and propose updates to **Data Inventory** and **Data Assessment** without the model writing the file itself.

This **reverses** the `refactor-use-core` decision that left Core’s document UX unused. GitHub consume of `sdoh_core` (no local path dependency) still stands. **For testing this feature**, Poetry pins Core’s `refactor-use-core` branch (not `main`) so `AfterTurnHook` and folder-only `sdoh_documents/` are available. After Core merges, switch the pin back to `main` or a version tag.

## Target Users

- **Practitioners** who already have (or are starting) an AI Solution Requirements Definition and need public-data evidence in the Data Inventory and Data Assessment sections.
- **Practitioners** who only want data exploration — chat, charts, and maps must still work when no file is specified.
- **Maintainers** wiring this product to Core Streamlit, `RequirementsFileHelper`, and `DocumentSectionTool`.

## Core Requirements

### Must Have
- [x] Use **SDoH-Core-Assistant Streamlit support** for the document chrome: sidebar file path, Reload from disk, Confirm write / Cancel, chat paused while a write is pending, welcome via `intro_builder` / `opening_assistant_message`. Do not invent a second confirm/write stack.
- [ ] Add `agents/data_document.py` (structure from `SDoH-Public-Data-Assistant-files/problem_definition_document_tool.py`) binding Core `DocumentSectionTool` + `RequirementsFileHelper`. The LangChain tool name is **`propose_data_inventory_assessment_update`**.
- [ ] Add `agents/build_data_agent.py` (structure from `SDoH-Public-Data-Assistant-files/build_pd_agent.py`) that builds a Core `sdoh_core.react_agent.ReActAgent` (or a thin subclass) with existing public-data tools **plus** the propose tool. Research/knowledge tools from the PD sample are **out of scope**.
- [ ] Section headings come from `framework_sections.py` (sample in the files folder): `1. Problem Definition`, `2. Data Inventory`, `3. Data Assessment`, `4. AI Approach Recommendation`, `5. Operational Requirements`. The file **must** have Problem Definition. This assistant creates/updates **Data Inventory** and **Data Assessment**; it may propose other headings only when the practitioner asks or a dependent update requires it.
- [ ] `propose_data_inventory_assessment_update` requires `section_body` (markdown without the top-level `##` heading). Optional `section_heading` is one of the five framework headings. Default heading: `1. Problem Definition` (same as the sample tool contract). One section per call. Does **not** write the file. Chat must include the proposed markdown, then tell the practitioner to Confirm write or Cancel.
- [ ] Adopt `file_baseline.py` (or Core’s fingerprint on the helper) so Confirm refuses if the file changed on disk after the proposal.
- [ ] Welcome is product-owned (sample `welcome.txt`). Pass Core `default_doc_path="sdoh_documents/"` so the sidebar shows the shared folder with **no filename**. Chat, tools, charts, and maps work with that folder-only path. Document propose/write stays blocked until the practitioner names a file. If a file exists, follow Core `docs/contract.md` (continuing with that path + a short recap). Do not call an LLM for the greeting.
- [ ] Merge sample `agent_system_prompt.txt` document workflows into `agents/agent_system_prompt.txt` (keep current public-data tool rules). When a file is specified, the agent reviews the whole document, tests availability with existing tools, and proposes Inventory/Assessment updates. Never claim a write until Confirm.
- [ ] Charts and maps still render after analysis turns via Core `AfterTurnHook` (`collect` extras onto `last_result`, `render` with existing `ChartRenderer` / `MapRenderer` + `geojson_ref` session store). Do not fork a second Streamlit shell for viz.
- [ ] Docker: `DOCUMENTS_ROOT` + a **shared** host volume `sdoh_documents/` (same folder other SDoH assistants use), not a product-local documents directory. Poetry installs `sdoh-core` from GitHub with `branch = "refactor-use-core"` for testing (both `pyproject.openai.toml` and `pyproject.local.toml`). No Core path dependency or bind-mount. Revert to `branch = "main"` (or a tag) when Core lands those APIs on `main`.
- [ ] Keep Core’s **Save current draft** control visible. Do not hide it even though the last assistant bubble is often analysis output rather than a section body.
- [ ] Replace `tests/unit/test_sdoh_core_boundary.py` “no document imports” with “GitHub consume only”; add tests for propose-does-not-write, heading resolve, and welcome builder.
- [ ] Update `documentation/architecture.md`, `documentation/usage.md`, and `documentation/installation.md` (and README if the one-line description changes).

### Nice to Have
- [ ] Shared default filename `ai-solution-requirements-definition.md` as a *placeholder hint* only (still no auto-selected working file).
- [ ] Consistency pass across sections 4–5 when geography/population/time disagree (called out in the sample prompt; implement if cheap).

## Technical Approach

Treat the files folder as **structure samples**, not drop-in code. Product names: `build_data_agent.py`, `data_document.py`, tool **`propose_data_inventory_assessment_update`**.

**From Core:** `RequirementsFileHelper`, `DocumentSectionTool`, Core `ReActAgent` (`document_path`, `chat_history`, `pending_write`, `apply_pending_write`), Streamlit `AssistantAppConfig` / `run_assistant_app` / `AfterTurnHook`, `opening_assistant_message`, confirm-gated `write`.

**In Public Data:** public-data tool list, chart/map renderers, `agent_system_prompt.txt`, welcome copy, `framework_sections.py`, `data_document.py` heading binding, `build_data_agent.py`, Docker documents volume. Product `agents/react_agent.py` becomes tool assembly and/or is replaced by the Core agent built in `build_data_agent.py` — do not keep two `ReActAgent` classes with the same import name.

Use `run_assistant_app` as the shell. Persist chart/map extras with `AfterTurnHook.collect` and redraw them with `AfterTurnHook.render` so Streamlit reruns keep the figures.

**Patterns to Follow:**
- Sibling PD assistant: `build_pd_agent.py` + document tool binding + Core `ReActAgent` + `file_baseline` + `intro_builder` (`SDoH-Public-Data-Assistant-files/`).
- Core contract: product-owned welcome; helper is not a LangChain tool; Confirm is UI, not a model tool (`SDoH-Core-Assistant/docs/contract.md`).
- GitHub `sdoh-core` consume (keep `test_poetry_uses_github_sdoh_core_not_local_path`). Testing pin: `branch = "refactor-use-core"`.

**Key Decisions:**
- **Supersede unused-document-UX:** `refactor-use-core` forbade `document_section_tool` / `run_assistant_app`. This brief authorizes those imports for document support only.
- **Core Streamlit, product viz:** Document chrome from Core `run_assistant_app`. Charts/maps stay product-owned and plug in through `AfterTurnHook` — not a second product shell.
- **No default file:** Start with `default_doc_path="sdoh_documents/"`. Core treats folder-only/empty as unspecified. Document workflows run only after the practitioner names a file.
- **Core `ReActAgent` for this product:** Needed for `document_path` / pending write. Public-data tools are injected; do not import Core’s class under the same name as the old product class.
- **Audit adapter:** Core shell calls `audit(user_prompt, conversation, final_answer)`. Product `AuditAgent.audit_turn` must be adapted or wrapped so logic-steps/audit still work.
- **Shared `sdoh_documents/`:** Persist requirements files in the host folder other SDoH assistants use, so the same AI Solution Requirements Definition can be opened across products.
- **Save current draft stays:** Leave the Core sidebar button as-is. Do not hide or special-case it for this product.
- **Testing pin on Core `refactor-use-core`:** Image/Poetry must clone that GitHub branch so `AfterTurnHook` and unspecified-path behavior exist. Still not a sibling `path =` dependency. Switch back to `main` or a tag after Core merges.

## Next Actions

1. [ ] Add `framework_sections.py`, `data_document.py`, `file_baseline.py` (adapt samples); unit-test heading resolve and propose-does-not-write.
2. [ ] Add `build_data_agent.py`: Core `ReActAgent` + public-data tools + `propose_data_inventory_assessment_update`; retire or slim product `agents/react_agent.py`.
3. [ ] Wire Streamlit: `run_assistant_app` + welcome from `welcome.txt` / `welcome_message.py` + `AfterTurnHook` for charts/maps; block chat while pending.
4. [ ] Set Poetry `sdoh-core` `branch = "refactor-use-core"` in both pyproject files; merge sample document prompt into `agent_system_prompt.txt`; add `DOCUMENTS_ROOT` + shared `sdoh_documents/` volume; rewrite boundary test; update architecture/usage/installation (note the temporary Core branch pin).

## Success Criteria

- [ ] With `default_doc_path="sdoh_documents/"` (no filename), data exploration, charts, and maps still work.
- [ ] With a path to a file that has Problem Definition, the agent can propose Data Inventory / Data Assessment updates; disk does not change until Confirm write.
- [ ] Cancel discards the proposal; Confirm after an out-of-band file change is rejected.
- [ ] Welcome matches product copy and does not invent a default filename.
- [ ] Image still installs `sdoh-core` from GitHub (`refactor-use-core` while testing); documents persist in shared host `sdoh_documents/`.
- [ ] Save current draft remains visible in the sidebar.

## Open Questions

- None.

---

## Changelog

| Date | Change |
|------|--------|
| 2026-10-01 | Brief from `SDoH-Public-Data-Assistant-files/add-document-support.txt` and sibling samples. |
| 2026-10-02 | Documents use shared host `sdoh_documents/` with other SDoH assistants. Keep Core “Save current draft” visible. |
| 2026-10-02 | Chose Core `AfterTurnHook` (`collect` + `render`) instead of a product Streamlit wrapper. |
| 2026-10-02 | Public Data starts at `default_doc_path="sdoh_documents/"`; Core treats folder-only as no file and still runs chat. |
| 2026-10-02 | Testing pin: Poetry `sdoh-core` Git branch `refactor-use-core` (not `main`, not a local path). Revert after Core merge. |
| 2026-10-10 | Core `refactor-use-core` merged to `main`; Poetry pin reverted to `branch = "main"`. |

---

*Brief created with SDD 6.0 - Ready to code!*
