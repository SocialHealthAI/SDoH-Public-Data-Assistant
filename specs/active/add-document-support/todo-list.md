# Implementation Todo List: add-document-support

## Overview
Wire Core Streamlit document chrome and `propose_data_inventory_assessment_update` so practitioners can attach public-data findings to an AI Solution Requirements Definition. Pin Poetry `sdoh-core` to GitHub `refactor-use-core` for testing.

## Todo Items

### Phase 1: Document binding
- [x] **T1**: Add `framework_sections.py`, `data_document.py`, `file_baseline.py`; unit-test heading resolve and propose-does-not-write.

### Phase 2: Agent
- [x] **T2**: Add `build_data_agent.py` (Core `ReActAgent` + public-data tools + propose tool). Slim `react_agent.py` to tool assembly.

### Phase 3: Streamlit
- [x] **T3**: `welcome_message.py` + `run_assistant_app` + `AfterTurnHook` for charts/maps; `default_doc_path="sdoh_documents/"`.

### Phase 4: Pin, prompt, Docker, tests, docs
- [x] **T4**: Poetry `branch = "refactor-use-core"`; merge document prompt; `DOCUMENTS_ROOT` + shared volume; rewrite boundary test; update architecture/usage/installation/README.

### Phase 5: Verify
- [x] **T5**: Run `tests/unit` (70 passed, 1 skipped on host; `test_analysis_tools.py` ignored — needs scipy in the container).

## Progress Tracking

| Item | Status | Notes |
|------|--------|-------|
| T1 | done | Heading resolve, propose-does-not-write, file_baseline |
| T2 | done | `DataConversationAgent` on Core `ReActAgent` |
| T3 | done | Core shell + AfterTurnHook + welcome |
| T4 | done | GitHub pin `refactor-use-core`; docs + volume |
| T5 | done | 70 passed, 1 skipped |

## Definition of Done
- [x] All todo items completed
- [x] Exploration works with folder-only path (welcome + Core unspecified-path)
- [x] Propose does not write until Confirm
- [x] Docs match Core Streamlit + testing pin
- [ ] Live Docker rebuild against Core `refactor-use-core` (not run in this pass)

---
**Created:** 2026-10-02  
**Source:** `specs/active/add-document-support/feature-brief.md` (no `plan.md`; brief is the approved plan)
