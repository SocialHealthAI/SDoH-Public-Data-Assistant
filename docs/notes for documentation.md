#### unit tests
C:\Users\jeff> cd c:\installs\Data-Analytic-Assistant\agents
C:\installs\Data-Analytic-Assistant\agents> python -m pytest ..\tests\unit\ -q


#### architecture:

how we use commons for polygons

how we use commons for geo children

our assumption of SDoH place and time.  simplification but could constrain

#### problems of standards:
this points to a recurring problem we might have, that CMS does not have a good naming standard.

Agreed — and we should assume this will keep happening across CMS datasets.

How to make it robust (without guessing)

* Schema-by-observation (already doing): treat the CMS dataset as “unknown schema”, then infer likely fields from:

  * normalized key names (we already normalize)
  * value types (numeric vs string)
  * _paired fields_ patterns (e.g., `*_geo_lvl` + `*_geo_cd` + `*_geo_desc`)

* Pattern rules instead of hard-coded field names

  * Geo: detect any trio like:

    * `(<prefix>_geo_lvl, <prefix>_geo_cd, <prefix>_geo_desc)`

    * then map by `geo_lvl`:

      * `County` + 5-digit code → `geoId/<code>`
      * `State` + 2-digit code → `geoId/<code>`
      * (else warn/not supported)

  * Year: accept strict `YYYY` from any field whose normalized name contains `year`

  * Value: prefer numeric fields whose normalized name contains `rate/count/percent/value`, but allow explicit override later

* Fail loudly but helpfully

  * When we can’t map deterministically, return a warning that includes:

    * the inferred “best candidate” geo/year fields we saw
    * a short sample of keys

  * That keeps us from silently producing wrong joins/maps.

If you want, I can implement the prefix-based geo detector next, so datasets like Part D don’t require adding one-off field names like `prscrbr_geo_cd`.

#### Sources
Assistant uses API access but could be extended for other sources.


| Source | What It Adds Beyond Data Commons | Age-Adjusted Metrics? | Public API? |
|---|---|---|---|
| **CDC PLACES** | HRSN social needs measures (loneliness, food insecurity, housing insecurity) not yet ingested by Data Commons; disability sub-measures (cognitive, ambulatory); most current release without Data Commons lag | **Yes** — both crude and age-adjusted prevalence rates published for every measure at the county level; age-adjusted rates are the recommended form for cross-county comparison | **Yes** — Socrata REST API, filter by FIPS, returns JSON |
| **County Health Rankings & Roadmaps (CHR&R)** | Provider-to-population ratios, mental health provider shortage, income inequality (80/20 ratio), social capital proxies, rural/urban classification, residential segregation | **Partial** — key outcome measures are age-adjusted (Premature Death/YPLL, Premature Age-Adjusted Mortality, Life Expectancy, physical inactivity, smoking); most behavioral and social factor measures are crude rates | **No** — annual CSV download from Zenodo only; no queryable endpoint |
| **AHRQ SDOH Database** | Five structured SDOH domains (social context, economic context, education, physical infrastructure, healthcare context) designed explicitly for linkage with Medicare/Medicaid claims; county, ZIP, and census tract levels | **No** — measures are predominantly counts and percentages from ACS; not age-adjusted | **No** — flat CSV download; designed as a pre-loaded reference dataset |
---
#### Searching Multiple Repos

This section documents how multi-source indicator discovery works in the assistant, why results can look “off topic,” and how to write searches that surface CDC PLACES (and other repos) reliably. Implementation: `agents/tools/sdoh_search_tool.py`, `agents/tools/sdoh_search_merge.py`, `agents/tools/cdc_places_helpers.py`; agent rules in `agents/agent_system_prompt.txt`.

### How searches are performed

**Entry point:** `search_sdoh_indicators(query, sources?, max_results?, place_scope?, …)`.

**Default `sources`:** `datacommons`, `cms`, `cdcplaces`. The agent may pass a narrower allowlist; if `cdcplaces` is omitted, no PLACES candidates are returned.

**Discovery order (fetch, then merge):**

| Order | Source | Mechanism | What gets matched |
|-------|--------|-----------|-------------------|
| 1 | Data Commons | MCP `search_indicators` (semantic / topic expansion when enabled) | Statistical variable DCIDs, names, descriptions |
| 2 | CMS | Project Open Data `data.json` catalog; token overlap on title, description, keywords, themes | Dataset UUIDs (`cms:<uuid>`) |
| 3 | CDC PLACES | Socrata measure index; keyword scoring on measure id, title, category | `cdcplaces:<geo>/<measureid>/<datavaluetypeid>` |

Each source produces candidates in a **unified schema** (`indicator_id`, `name`, `source`, `repository`, `native_id`, `metric_source`, …).

**Multi-source `max_results` (important):** When more than one real source runs, the tool does **not** let the first source consume the entire budget. It:

1. Computes a **per-source cap:** `per_source_cap ≈ ceil(max_results / number_of_sources)` (minimum 3 per source when splitting).
2. Fetches up to that many candidates from Data Commons, CMS, and CDC PLACES separately.
3. **Interleaves** results round-robin (DC, CMS, PLACES, DC, CMS, PLACES, …) until `max_results` total rows.

This avoids the failure mode where 10 Data Commons + 10 CMS hits fill `max_results=20` and **zero PLACES rows** appear even though PLACES matched the query. The tool adds a warning when interleaving is active.

**CDC PLACES search specifics (v1):**

- County release dataset id is configured (`swc5-untb` for 2025 county).
- Search runs against a **curated HRSN-oriented catalog**, not a live Socrata full-text scan of every PLACES measure (planned for a later phase).
- Query tokens (length ≥ 3 after splitting on non-alphanumerics) are scored against measure names and keywords.
- If the query mentions age-adjusted wording, **`AgeAdjPrv` is ranked above `CrdPrv`**; both may be returned when relevant.
- Legacy measure ids in docs (e.g. `LONELY`) are aliased to current Socrata ids (e.g. `LONELINESS`) when parsing `native_id`, not when searching the catalog entry list.

**Observations are separate:** `get_sdoh_observations` can fetch any valid `cdcplaces:*` id via Socrata even if that measure was not in the curated search catalog—search only affects **discovery**, not whether the API has the series.

### Tangential matches (why titles do not mention your topic)

All three catalogs can return **plausible but loosely related** candidates when the query is vague or noisy.

| Source | Typical tangential-match behavior |
|--------|-----------------------------------|
| **Data Commons** | Broad semantic recall; optional topic expansion increases recall. Related health/SDoH variables (e.g. general BRFSS, social determinants) may rank without containing your exact word. |
| **CMS** | Keyword overlap on **dataset titles/descriptions** in `data.json`. A phrase like “data items for loneliness” may match datasets that mention health, Medicare, or geographic data but not “loneliness” in the title. |
| **CDC PLACES** | Requires at least one query token (≥ 3 chars) to match measure text or catalog keywords. Stopwords and filler (“are”, “there”, “items”) do not help. Unrelated HRSN measures are suppressed unless their keywords overlap your tokens. |

**Symptoms users notice:**

- “I asked about loneliness but nothing in the table says loneliness” — often **CMS/DC** tangential hits, or the agent used a **generic paraphrase** instead of the topic token `loneliness`.
- “PLACES returned nothing” — before interleaving fix: budget exhaustion; or `cdcplaces` not in `sources`; or query tokens never matched the curated catalog (no token ≥ 3 chars matching measure/keywords).

**Mitigation in product behavior:** Re-run search with a **simplified, topic-first query**; increase `max_results`; include `cdcplaces` for HRSN; inspect `sources_checked` and `warnings` on the tool response.

### Keyword priority (agent prompt and query shaping)

The agent is instructed to treat **search text as high-leverage**: the same user intent phrased differently can change which repository “wins” the first screen of results.

**Priority (highest first):**

1. **Topic tokens** — the measurable concept: `loneliness`, `food insecurity`, `diabetes`, `obesity`, `age-adjusted`, etc. These should appear explicitly in `query`, not only in conversational framing.
2. **Repository / subject anchors** (especially for PLACES) — `PLACES`, `BRFSS`, `HRSN` help humans and future Socrata-backed search; for v1 curated PLACES, topic tokens matter more than the word “PLACES.”
3. **Geography** — `county`, `state`, `ZCTA`, `tract`, or `place_scope.level` to pick geo level and dataset.
4. **Value-type intent** — “age-adjusted”, “crude”, “adjusted rate” map to PLACES `datavaluetypeid` `AgeAdjPrv` / `CrdPrv` (not the phrase “age adjusted” in the measure name).

**Deprioritize / drop in a retry query:**

- Filler: “are there”, “data items”, “available”, “what variables”, “show me”
- Over-broad: “health”, “social”, “data” (unless you want wide recall)
- Program names that steer CMS off-topic unless intended: “Medicare” when the topic is PLACES HRSN

**Recommended PLACES query shape (agent or power user):**

```text
<topic> + [HRSN|PLACES|BRFSS] + [county|state|ZCTA] + [age adjusted|crude]
```

Examples:

```text
loneliness county age adjusted
PLACES HRSN food insecurity county
housing insecurity PLACES county
```

**Agent prompt rules (summary):** See `agents/agent_system_prompt.txt` — multi-source searches use `max_results >= 20`; use `>= 30` when you need depth from DC, CMS, and PLACES together; always include `cdcplaces` for HRSN/loneliness/food/housing/age-adjusted asks; on weak first pass, re-run with simplified tokens and higher `max_results`.

### Practical search advice

| Situation | Suggested action |
|-----------|------------------|
| HRSN topic (loneliness, food/housing insecurity) | `sources=["datacommons","cms","cdcplaces"]`, query includes topic word, `max_results` 20–30 |
| User question is conversational | Agent should rewrite to `loneliness` / `FOODINSECU` / etc., not pass the whole sentence verbatim |
| No PLACES in results | Check `sources_checked` includes `cdcplaces`; check `warnings` for interleaving; simplify query; increase `max_results` |
| Titles lack the topic word | Likely tangential DC/CMS hits—narrow query or rank by `name` / `repository` and re-search PLACES-only: `sources=["cdcplaces"]` |
| Need age-adjusted PLACES | Prefer `.../AgeAdjPrv`; confirm `data_value_type` “Age-adjusted prevalence” in candidate description |
| Compare catalogs | Expect duplicate concepts across DC and PLACES; use `indicator_id` and `metric_source` columns, not title alone |
| After empty PLACES catalog match | Observations may still work if you know `cdcplaces:county/<measureid>/<AgeAdjPrv\|CrdPrv>` from CDC docs |

**Smoke-style search calls:**

```text
# Balanced three-way (interleaved)
search_sdoh_indicators(
  query="loneliness county",
  sources=["datacommons", "cms", "cdcplaces"],
  max_results=30
)

# PLACES-only discovery
search_sdoh_indicators(
  query="loneliness age adjusted county",
  sources=["cdcplaces"],
  max_results=10
)
```

**Future (Step 4c):** Replace or augment the curated PLACES catalog with a **cached Socrata distinct-measure index** so diabetes, obesity, and other non-HRSN PLACES measures appear without hand-maintaining ids; ranking and tangential-match guidance above still apply.

#### Searches actually test data
not just relying on Internet searche but runs queries to get sample data.

#### Sources
Data Commons is the broadest source: demographics, economics, health, education, and environment for countries down to cities, counties, census tracts, and ZIP Code Tabulation Areas (ZCTAs), with many series drawn from Census, CDC, BLS, and other programs already harmonized in one knowledge graph. In this assistant, indicator discovery uses the Data Commons search API (via MCP `search_indicators`), which returns statistical variable DCIDs and human-readable names; optional probing can attach a factual metric\_source (for example ACS or a named import) when the API exposes it. Observations are fetched through the Data Commons v2 observation API when `DC_API_KEY` is set (batched by place and variable), otherwise through a slower per-place fallback. For places, Data Commons is also the system of record for maps: boundaries come from `geoJsonCoordinates` keyed by DCID. All sources are conformed to a shared `place_key` that is usually the Data Commons DCID itself—`geoId/<FIPS>` for states (2-digit), counties (5-digit), and tracts (11-digit); `zip/<five digits>` for ZCTA/ZIP maps (not `geoId/<zip>`). Bare numeric FIPS or ZIP codes are normalized using the requested geography level. Parent→child expansion (for example “counties in Indiana”) uses Data Commons v2 place APIs and requires the same API key.

CMS (Centers for Medicare & Medicaid Services) complements Data Commons with program and claims-oriented public datasets published on [data.cms.gov](https://data.cms.gov/)—for example Medicare utilization, providers, hospitals, and geography-specific extracts such as Part D prescriber statistics by state, county, or ZIP. Search does not use a semantic graph; it scans the CMS Project Open Data catalog (`data.json`) and returns dataset identifiers as `cms:<uuid>`. Observations are read from the CMS Data API (`data-api/v1` per dataset), which returns row-oriented JSON; the assistant infers year, geography fields, and numeric value columns from each dataset’s schema rather than assuming one national layout. Place conformance is explicit but CMS-specific: state and county rows map to `geoId/<FIPS>` from CMS geography codes or names (with county-name matching to FIPS when Data Commons names are available), while ZIP-level datasets map to `zip/<five digits>`. CMS rows are not native DCIDs, so mixing CMS with Data Commons or PLACES on a map only works when those keys align (same FIPS or ZIP). ZIP-level CMS pulls need explicit 5-digit ZIPs; open-ended national ZIP scans are not supported.

CDC PLACES (Population Level Analysis and Community Estimates) provides model-based community health estimates—including health outcomes, disability, health-related social needs (HRSN) such as loneliness and food insecurity, and many prevalence measures with both crude and age-adjusted forms—at county, census place, census tract, and ZCTA levels. Data live on [data.cdc.gov](https://data.cdc.gov/) as separate Socrata tables per geography and release; the assistant discovers dataset ids from the public catalog (by release year) and discovers measures from each table’s distinct `measureid` list. Observations are fetched with SoQL filters on `measureid`, `datavaluetypeid` (for example `AgeAdjPrv` or `CrdPrv`), `locationid`, and `year`. Indicator ids look like `cdcplaces:tract/EMOTIONSPT/CrdPrv`. For places, PLACES `locationid` values are converted to the same join keys as elsewhere: 11-digit tract GEOIDs, 5-digit county FIPS, 7-digit place FIPS, and 5-digit ZCTAs become `geoId/...` or `zip/...` respectively. The PLACES `year` field is the survey/model year in the file (for example 2023), not necessarily the title year of the CDC release. Not every census tract code appears in PLACES (missing tracts mean no published estimate, not a tool error), and there is no separate state-level PLACES table in the current release—use county-level PLACES or Data Commons for state summaries. Maps still use Data Commons geometry; tract and ZIP keys must match the DCID style above (`geoId/<tract>`, `zip/<zcta>`) so choropleths join correctly.

***

Joining across sources: combine tables only on `(place_key, year)`—same geography encoding and annual year. Do not join on place names alone. When searching multiple sources, use focused topic words and set `max_results` high enough that PLACES and CMS results are not crowded out by Data Commons hits
