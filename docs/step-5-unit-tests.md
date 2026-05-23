# Step 5: Unit test expansion (high + medium priority)

Expand **fast, offline unit tests** for the multi-source SDoH tools added in Steps 2–4. This step is **test-only**—do not add features, refactor production code, or implement slow live-API regression (that is a later step).

**Prerequisite:** Step 4 (CDC PLACES) is complete and committed. Baseline: **19 tests** under `tests/unit/` (~1–2s with `pytest`).

---

## Goal

Lock in behavior that Step 4 and earlier steps rely on, especially:

- Multi-source **search** (interleaving, per-source caps, unsupported sources)
- **Place key** conventions (`geoId/*`, `zip/*`, tract 11-digit)
- **Observations** normalization and **wide join** on `(place_key, year)`
- Thin **output contract** so tool payloads stay stable for maps/stats

All new tests should use **mocks or fixtures**—no network in the default `pytest` run.

---

## Do not regress

| Area | Must keep passing |
|------|-------------------|
| Existing 19 unit tests | No removals without replacement |
| Step 4 PLACES helpers / discovery / merge / ZIP normalize | Extend, do not break |
| Production behavior | Change code only when a test exposes a real bug (minimal fix + test) |
| Supported sources | `datacommons`, `cms`, `cdcplaces` only (IHME removed—not tested) |

---

## How to run

### Canonical: running `dc-assistant` container (recommended)

The assistant image uses **LangChain 0.3.x** at `/opt/venv`. You can run pytest **while Streamlit is up** — `docker compose exec` does not stop the app.

`docker-compose.yaml` mounts host `./tests` → `/app/tests` so new test files are visible without rebuilding the image. Application code still comes from `./agents` → `/myapps` (run pytest with `cd /myapps` so `tools.*` imports resolve).

```bash
# From repo root, with dc-assistant running:
docker compose exec dc-assistant bash -lc \
  "/opt/venv/bin/pip install -q pytest && cd /myapps && /opt/venv/bin/python -m pytest /app/tests/unit/ -q"
```

Windows helper:

```powershell
.\scripts\run-unit-tests-in-container.ps1
.\scripts\run-unit-tests-in-container.ps1 -v   # passes -v to pytest
```

After changing the `tests/` volume mount, recreate the container once: `docker compose up -d dc-assistant`.

**Cursor:** Run Task → **Unit tests (dc-assistant container)** (`.vscode/tasks.json`, default test task). That is the source-of-truth run; local Windows Python may still show only 19 tests if LangChain 1.x is installed globally.

Optional: **Dev Containers: Attach to Running Container** → `dc-assistant`, interpreter `/opt/venv/bin/python`, pytest cwd `/myapps`, args `/app/tests/unit` — enables the Testing sidebar inside the container.

### Local (Cursor / host Python only)

From the `agents/` directory (so `tools.*` imports resolve):

```bash
cd agents
python -m pytest ../tests/unit/ -q
```

Requires LangChain **0.3.x** on that interpreter; otherwise H1/H2 modules are skipped (19 tests only).

Optional integration (network):

```bash
python -m pytest ../tests/unit/ -q -m integration
```

Mark live/network tests with `@pytest.mark.integration` and skip by default in `pytest.ini` or `pyproject` if you add a marker config.

---

## Current coverage (baseline)

| File | Tests | Covers |
|------|-------|--------|
| `test_cdc_places_helpers.py` | 9 | PLACES id/value-type parsing, `place_key`/`locationid`, mocked `search_catalog` |
| `test_cdc_places_dataset_discovery.py` | 5 | Catalog title parsing, dataset discovery, fallback; optional live `get_places_datasets` |
| `test_sdoh_search_merge.py` | 2 | `per_source_cap`, `interleave_search_results` |
| `test_dc_place_expand_zip.py` | 3 | `normalize_place_key` for ZIP vs county |
| `test_sdoh_cdcplaces_mocked.py` | 2 | One mocked PLACES observation row; cdcplaces-only search (requires LangChain) |

### Gaps (why Step 5 exists)

| Area | Module | Gap |
|------|--------|-----|
| Unified search facade | `sdoh_search_tool.py` | No mocked DC+CMS+PLACES `_run`; no unsupported-source warning |
| Observations facade | `sdoh_observations_tool.py` | CMS row→`place_key`, tract PLACES, wide join largely untested |
| CMS search | `sdoh_search_tool.py` | Catalog scoring / UUID extract untested |
| DC payload shaping | `sdoh_search_tool.py` | `_normalize_dc_results` untested |
| Place resolution | `resolve_places_tool.py`, `dc_place_expand.py` | Tract level; `resolve_places_for_map` untested |
| Output contract | observations/search return shape | No schema/keys guard test |

---

## Implementation principles

1. **Mock at boundaries:** `urllib.request`, `fetch_places_observations_batched`, `fetch_measure_index`, `_call_dc_search`, `_search_cms`, `fetch_property_values_map`, `expand_places_for_parent_and_level`—not full HTTP servers.
2. **Fixtures on disk:** Small JSON under `tests/fixtures/` (e.g. `cms_data.json` fragment, Socrata `$group` row, MCP `variables` payload).
3. **Deterministic:** No sleeps; no reliance on catalog release year changing.
4. **LangChain:** Tests that import `SdohSearchTool` / `SdohObservationsTool` may use `pytest.importorskip("langchain")` (see `test_sdoh_cdcplaces_mocked.py`) or mock `StructuredTool` at import time—prefer importorskip for clarity.
5. **One concern per test:** Small tests; descriptive names (`test_interleave_preserves_cdcplaces_when_dc_and_cms_fill_budget`).

---

## High priority (implement in Step 5)

### H1 — Unified search (`sdoh_search_tool._run`)

**File:** `tests/unit/test_sdoh_search_tool.py` (new)

| Test | Intent |
|------|--------|
| `test_run_interleaves_dc_cms_cdcplaces` | Mock DC (10), CMS (10), PLACES (5) candidates; `max_results=20`; assert round-robin includes `cdcplaces` in first 20 |
| `test_run_per_source_cap_warning` | Multi-source run; assert warning mentions interleaving / per-source cap |
| `test_run_unsupported_source_warning` | `sources=["datacommons","ihme"]`; assert warning lists supported sources; no crash |
| `test_run_cdcplaces_only` | Extend pattern from `test_sdoh_cdcplaces_mocked.py` with mocked catalog search |

**Mocks:** Assign `tool._call_dc_search`, `tool._normalize_dc_results`, `tool._search_cms`, patch `search_cdc_places_catalog`.

---

### H2 — Observations facade (`sdoh_observations_tool._run`)

**File:** `tests/unit/test_sdoh_observations_tool.py` (new)

| Test | Intent |
|------|--------|
| `test_cms_county_place_key` | Fixture CMS row with `Prscrbr_Geo_Cd` / county fields → `place_key=geoId/<5-digit>`, `source=cms` |
| `test_cms_zip_place_key` | ZIP-style row → `place_key=zip/45202` |
| `test_cdcplaces_tract_row` | Mock `fetch_places_observations_batched` with 11-digit `locationid`; `place.level=tract`; assert `geoId/39061000200` |
| `test_cdcplaces_year_filter` | Rows with wrong year excluded when `time.year=2023` |
| `test_wide_join_two_indicators` | Two indicators, overlapping `(place_key, year)`; `output.format=wide`; assert join columns and one combined row |

**Mocks:** `fetch_places_observations_batched`, `fetch_observations_by_entity_batch` / `_call_dc_get_observations` as needed; avoid paging real CMS API.

---

### H3 — PLACES dataset / measure parsing (fixtures)

**File:** extend `test_cdc_places_dataset_discovery.py` or `tests/unit/test_cdc_places_measure_index.py` (new)

| Test | Intent |
|------|--------|
| `test_parse_socrata_group_payload` | Fixture list of Socrata rows → `fetch_measure_index` parsing logic (patch `_socrata_get_json`) |
| `test_discover_sets_city_zcta_aliases` | Mock catalog with place + zip → `datasets["city"]`, `datasets["zcta"]` share ids |
| `test_gis_friendly_title_excluded` | Catalog hit with “GIS Friendly Format” does not map to geo level |

---

### H4 — Place keys: tract + ZIP edge cases

**File:** extend `test_dc_place_expand_zip.py` → `test_dc_place_expand.py` or `test_place_key_normalize.py`

| Test | Intent |
|------|--------|
| `test_normalize_tract_eleven_digit` | `39025040800` + `level=tract` → `geoId/39025040800` |
| `test_normalize_zip_rejects_geoid_on_county` | `zip/01001` ignored when `level=county` (existing behavior) |
| `test_search_scoring_no_false_positive_age_in_among` | `search_catalog("loneliness among adults county")` ranks LONELINESS above unrelated HRSN when index mocked (regression for “age” in “among”) |

---

## Medium priority (implement in Step 5)

### M1 — Indicator id / allowlist

**File:** `tests/unit/test_indicator_id_parse.py` (new) or inside `test_sdoh_observations_tool.py`

| Test | Intent |
|------|--------|
| `test_parse_indicator_id_prefixes` | `datacommons:Count_Person`, `cms:<uuid>`, `cdcplaces:county/X/Y` |
| `test_skip_indicator_not_in_allowlist` | `sources=["cdcplaces"]` + DC indicator → skipped with warning |

---

### M2 — CMS catalog helpers

**File:** `tests/unit/test_sdoh_search_cms.py` (new)

| Test | Intent |
|------|--------|
| `test_extract_cms_dataset_uuid` | Minimal `data.json` dataset entry → UUID from `identifier` / `distribution` |
| `test_score_cms_dataset_prefers_title_match` | Query matches one title; scored dataset ranks first |

**Fixture:** `tests/fixtures/cms_catalog_snippet.json`

---

### M3 — Resolve places for map (mocked)

**File:** `tests/unit/test_resolve_places_tool.py` (new)

| Test | Intent |
|------|--------|
| `test_resolve_zip_ids` | `places.level=zip`, `ids=["45202","45214"]` → `resolved[].dcid` is `zip/45202`, etc. |
| `test_resolve_tract_ids` | 11-digit id + `level=tract` → `geoId/...` |

**Mocks:** `fetch_property_values_map` return `{}` or simple names; no DC_API_KEY required.

---

### M4 — Observations output contract

**File:** `tests/unit/test_sdoh_output_contract.py` (new)

| Test | Intent |
|------|--------|
| `test_observations_response_shape` | Mocked minimal `_run` → top-level keys: `data`, `warnings`; `data.rows` list; row has `place_key`, `year`, `indicator_id`, `value`, `source` |
| `test_search_response_shape` | Mocked `_run` → `results`, `sources_checked`, `warnings` |

Use for audit/rubric compatibility if restored later.

---

## Out of scope (defer to “Step 6” or later)

| Item | Why defer |
|------|-----------|
| Live HTTP tests (default suite) | Slow, flaky; use `pytest.mark.integration` only |
| VCR / recorded golden files against data.cdc.gov | Regression layer |
| Streamlit / ReAct agent E2E | Heavy; separate harness |
| Map code generation / `patheffects` | Brittle string tests |
| Data Commons MCP real calls | Integration |
| Full CMS dataset paging / ZIP scan | Integration |
| IHME | Removed from product |

See `docs/Regressio test outline GPT 5.2.md` (if present) for slow regression ideas.

---

## Suggested file layout after Step 5

```text
tests/
  fixtures/
    cms_catalog_snippet.json
    socrata_measure_group_sample.json
    mcp_search_variables_sample.json
  unit/
    test_cdc_places_helpers.py          # existing + H4 scoring test
    test_cdc_places_dataset_discovery.py
    test_sdoh_search_merge.py
    test_dc_place_expand_zip.py         # or rename test_place_key_normalize.py
    test_sdoh_cdcplaces_mocked.py
    test_sdoh_search_tool.py            # new — H1
    test_sdoh_observations_tool.py      # new — H2
    test_sdoh_search_cms.py             # new — M2
    test_resolve_places_tool.py         # new — M3
    test_sdoh_output_contract.py        # new — M4
    test_indicator_id_parse.py          # new — M1 (optional split)
```

Target: **~35–45 tests** total; runtime still **under ~5s** without integration markers.

---

## Acceptance criteria

1. `python -m pytest ../tests/unit/ -q` passes from `agents/` with **no network** (integration tests skipped or pass offline).
2. High-priority table (H1–H4) has at least one test per row.
3. Medium-priority table (M1–M4) has at least one test per row.
4. No new production dependencies required for tests (pytest + existing stack).
5. PR / commit is **tests + fixtures + this doc** only (unless a one-line bugfix is required).

---

## Verify checklist (before closing Step 5)

- [ ] H1: PLACES appears when DC and CMS both return many hits (`max_results=20`)
- [ ] H1: `ihme` in `sources` → warning, no crash
- [ ] H2: CMS county/ZIP → correct `place_key`
- [ ] H2: PLACES tract → `geoId/<11-digit>`
- [ ] H2: Wide join on `(place_key, year)` for two indicators
- [ ] H3: Socrata group JSON → measure index; GIS-friendly excluded
- [ ] H4: Tract + ZIP `normalize_place_key` levels
- [ ] M2: CMS UUID extract from fixture catalog
- [ ] M3: `resolve_places_for_map` returns `zip/*` for ZIP level
- [ ] M4: Observations/search response keys stable
- [ ] Full suite green; document any `importorskip` for LangChain

---

## Notes for implementers

- **Working directory:** Run pytest from `agents/`; same as Step 4 smoke notes.
- **Step 4 doc** may still mention IHME in historical sections; product code uses three sources only.
- Prefer **extending** `test_sdoh_cdcplaces_mocked.py` into `test_sdoh_search_tool.py` rather than duplicating patterns.
- When mocking `SdohObservationsTool._run`, pass pydantic-friendly dicts for `place` and `time` (same shapes as tool schema).

---

## Relationship to Step 4

| Step 4 | Step 5 |
|--------|--------|
| CDC PLACES feature + docs | Tests that guard that feature and shared SDoH facades |
| Manual smoke (maps, correlation) | Automated fast guards |
| Optional 4c overlap hints (not done) | Not required here |

Step 5 does **not** replace manual smoke; it reduces regression risk before Step 6 live tests.
