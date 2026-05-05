## SDoH GeoSpatial Data Retrieval and Rendering Challenges
[cursor produced from my outline]

SDoH mapping depends on joining place-based statistical data to the correct geographic boundaries. In practice, this is difficult because place identifiers and geometry sources rarely align cleanly. Place records may use different ID schemes and formatting (e.g., DCIDs vs GEOIDs, `geoId/...` vs bare numeric IDs), while boundary datasets may define different levels of geography or boundary versions. Even when identifiers are “conceptually the same,” small normalization issues (whitespace, prefixes, leading zeros) can cause merges to succeed while leaving most regions with missing values—producing misleading maps.

SDoH datasets further increase complexity through heterogeneous schemas: indicator naming, temporal semantics (e.g., “past 12 months” vs annual), units, and missing-data conventions vary across measures and years. Agents must not only fetch the right metric but also ensure it is keyed and rendered consistently with the associated geography.

Geometry payload size is another major constraint. Polygon boundaries can be large enough to exceed LLM context windows or dramatically increase token cost when serialized into prompts. This repo’s approach avoids embedding GeoJSON in the LLM context by using Data Commons for geometry retrieval and a server-side cache keyed by a small `geojson_ref`. The remaining risk is correctness of reference threading and join-key logic across tool calls.

Finally, map requests often require overlays (e.g., cities colored by an SDoH metric with a county or state outline for context). Multi-layer rendering introduces multiple geometry fetches, additional injected variables, and separate join/plot logic for “primary” vs “outline” layers. Without strict rules, agents may merge metrics into outline layers, omit outline geometry, or redefine injected variables, leading to runtime failures or incomplete visualizations.

When integrating external place and boundary sources (instead of Data Commons), these challenges typically worsen: inconsistent identifiers, CRS mismatches, boundary quality/topology issues, and differing schema expectations can require additional pre-processing that is hard to reliably express through generated code under safety constraints.

### Design implications / mitigations (tailored to this repo)

This repo’s architecture mitigates key failure modes by:

* Keeping large geometry out of LLM context: `GeoJsonTool` stores full GeoJSON server-side in Streamlit session state and returns only a `geojson_ref`.
* Enforcing reference-based injection: the renderer resolves refs to injected read-only variables (e.g., `GEOJSON_DATA`, and optionally `GEOJSON_OUTLINE`), preventing accidental prompt bloat and reducing serialization errors.
* Strengthening join robustness: the toolchain and prompts emphasize normalized join keys (e.g., `dcid_norm`) so merges work even when ID formats differ.
* Using prompt and runtime sanitization safeguards: map generation instructions discourage redefining injected geometry variables, while the renderer strips imports and blocks unsafe operations and rewrites geometry construction patterns to the injected collections.

However, the approach still requires careful tool chaining:

* refs must be threaded correctly between tool calls,
* join keys must match across layers,
* and overlay-specific variables must be present at render time (otherwise outlines fail even if the primary layer renders correctly).
