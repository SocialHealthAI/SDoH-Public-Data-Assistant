# Implementation Todo List: refactor-use-core

## Overview
Lock the Public Data Assistant onto `sdoh_core` from GitHub. Core on disk is review-only. Do not adopt Core’s document-section workflow.

## Todo Items

### Phase 1: Consume path
- [x] **T1**: Confirm Docker/Poetry install `sdoh-core` from GitHub (`git` in builder; no Core bind-mount; no `PYTHONPATH` to a local checkout).

### Phase 2: Product boundary
- [x] **T2**: Remove leftover unused product files (orphan `agents/.py`). Confirm no remaining copies of Core APIs in product Python.
- [x] **T3**: Add a unit test that product code does not import `document_section_tool`, `RequirementsFileHelper`, Core `react_agent`, or `run_assistant_app`, and Poetry does not use a local path dep.

### Phase 3: Docs
- [x] **T4**: Document GitHub consume and Core vs product split in README, architecture, and installation.

### Phase 4: Verify
- [x] **T5**: Run `tests/unit`. Host: 56 passed; `test_analysis_tools.py` collection error without `scipy` (container suite).

## Progress Tracking

| Item | Status | Notes |
|------|--------|-------|
| T1 | done | Git in Docker builder; Poetry GitHub URL; no Core volume or PYTHONPATH |
| T2 | done | Removed unused `agents/.py`; no leftover Core API copies in product Python |
| T3 | done | `tests/unit/test_sdoh_core_boundary.py` |
| T4 | done | README, architecture, installation |
| T5 | done | 56 passed on host; analysis tests need scipy in the assistant container |

## Definition of Done
- [x] All todo items completed
- [x] Boundary test in place
- [x] User-facing docs match GitHub consume story
- [ ] Live chat/audit smoke in running containers (not run; compose was down)

---
**Created:** 2026-09-28  
**Source:** `specs/active/refactor-use-core/feature-brief.md` (no `plan.md`; brief is the approved plan)
