## Architecture

The **SDoH Public Data Assistant** runs as two Docker Compose services on a shared network. The chat UI and agent live in **public-data-assistant**; a local **data-commons-mcp** server provides Data Commons indicator search and an observations fallback. CMS and CDC PLACES are reached over the public internet from **public-data-assistant**—no additional containers are required for those repositories.

A planned capability connects **your own database** alongside public data (not implemented yet).

### Deployment

```mermaid
flowchart LR
  subgraph Docker_Compose["Docker Compose"]
    DC["public-data-assistant<br/>Streamlit + agent"]
    MCP["data-commons-mcp<br/>Data Commons MCP"]
  end

  Browser((Browser))
  LLM["LLM API<br/>OpenAI or Anthropic"]
  DCAPI["Data Commons API<br/>v2 REST"]
  CMS["data.cms.gov"]
  PLACES["data.cdc.gov<br/>CDC PLACES"]

  Browser -- "HTTP :8052" --> DC
  DC -- "MCP streamable HTTP<br/>/mcp" --> MCP
  DC -- "HTTPS" --> LLM
  DC -- "HTTPS<br/>DC_API_KEY" --> DCAPI
  DC -- "HTTPS" --> CMS
  DC -- "HTTPS" --> PLACES
  MCP -- "HTTPS<br/>DC_API_KEY" --> DCAPI
```

**public-data-assistant** (`analytic_assistant_build/dockerfile.openai`) mounts `./agents` at `/myapps` for development and the shared host folder `sdoh_documents/` at `/documents` (`DOCUMENTS_ROOT`). It exposes the Streamlit UI on `ASSISTANT_HOST_PORT` (default `8052`). Environment variables include `LLM_PROVIDER`, `LLM_MODEL`, `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`, `DC_API_KEY`, `DATACOMMONS_URI` (default `http://data-commons-mcp:3000/mcp` on the compose network), and `DOCUMENTS_ROOT`. The image installs [`sdoh_core`](https://github.com/SocialHealthAI/SDoH-Core-Assistant) from GitHub at build time (`analytic_assistant_build/pyproject.openai.toml`, `branch = "main"`); do not bind-mount a local Core checkout for runtime.

**data-commons-mcp** (`datacommons_server_build/dockerfile`) runs the published `datacommons-mcp` HTTP server. It exposes `DATACOMMONS_CONTAINER_PORT` (default `3000`) and uses the same `DC_API_KEY` as the assistant.

### Application stack

The assistant is a Streamlit chat app (`streamlit_assistant.py`) using Core’s `run_assistant_app` for confirm-before-write document chrome. `build_data_agent.py` constructs Core `ReActAgent` with public-data tools plus **`propose_data_inventory_assessment_update`**. Shared LLM factory, tool-calling loop, document helper, and audit runner come from [`sdoh_core`](https://github.com/SocialHealthAI/SDoH-Core-Assistant). Product-owned code wires public-data tools, chart/map rendering (`AfterTurnHook`), welcome copy, and framework headings. The sidebar starts at `sdoh_documents/` with no filename; exploration works until the practitioner names a file. An optional **audit** agent (`audit_agent.py`) uses the same `LLM_PROVIDER` and reviews the user prompt, tool steps, and final answer when the user clicks **Run Audit**.

```mermaid
%%{init: {
  "themeVariables": {
    "fontSize": "14px",
    "nodeSpacing": 28,
    "rankSpacing": 50
  }
}}%%
graph TB

AssistantLLM["Assistant LLM<br/>LLM_PROVIDER"]
App["Streamlit app<br/>Core shell + data agent"]
AuditLLM["Audit LLM<br/>same provider"]

AssistantLLM <--> App
App -.->|"on demand"| AuditLLM

User(["User"])
User <--> App

subgraph Tools["Agent tools"]
  direction TB
  SearchObs["search_sdoh_indicators<br/>get_sdoh_observations<br/>get_observations"]
  PlacesGeo["resolve_places_for_map<br/>get_geojson_for_places"]
  Stats["calculate_correlation<br/>regression_analysis<br/>descriptive_stats<br/>time_series_forecast"]
  Viz["generate_chart<br/>generate_map"]
  Doc["propose_data_inventory_assessment_update"]
end

App <--> SearchObs
App <--> PlacesGeo
App <--> Stats
App <--> Viz
App <--> Doc

subgraph Local["Compose network"]
  MCPNode["data-commons-mcp"]
end

subgraph External["Public APIs"]
  DCAPI2["Data Commons v2"]
  CMSAPI["CMS data.json + datasets"]
  PLACESAPI["CDC PLACES Socrata"]
end

SearchObs <--> MCPNode
SearchObs <--> CMSAPI
SearchObs <--> PLACESAPI
SearchObs <--> DCAPI2
PlacesGeo <--> DCAPI2
SearchObs --> PlacesGeo
Viz --> PlacesGeo

MCPNode <--> DCAPI2

classDef user fill:#E0E0E0,stroke:#555,stroke-width:1px;
classDef app fill:#E8F0FE,stroke:#5B7BD5,stroke-width:1px;
classDef llm fill:#CFE2FF,stroke:#2457A6,stroke-width:2px;
classDef tools fill:#DFF2E1,stroke:#2F7D4C,stroke-width:1px;
classDef data fill:#FFE0B2,stroke:#C77700,stroke-width:1px;

class User user;
class App app;
class AssistantLLM,AuditLLM llm;
class SearchObs,PlacesGeo,Stats,Viz,Doc tools;
class MCPNode,DCAPI2,CMSAPI,PLACESAPI data;
```

Charts and maps are generated as Python code in the agent run; **ChartRenderer** and **MapRenderer** execute that code in the Streamlit process and display results below the chat. Map geometry is not passed through the LLM context: `get_geojson_for_places` stores GeoJSON in the Streamlit session under a `geojson_ref` key that `generate_map` references at render time. State GeoJSON from Data Commons includes Alaska rings at +179° longitude; the renderer unwraps those rings and crops national maps to the contiguous US so the lower 48 fills the pane.

### Request flow

A typical analysis follows this pattern:

1. **Discover** — `search_sdoh_indicators` queries allowed sources (default: Data Commons, then CMS, then CDC PLACES) and returns ranked candidates with `indicator_id`, repository, and optional `metric_source`.
2. **Fetch** — `get_sdoh_observations` pulls values for one or more indicators, places, and years. Data Commons uses batched v2 API calls when `DC_API_KEY` is set; otherwise it falls back to MCP `get_observations` per place. CMS and CDC PLACES use their respective HTTP APIs inside the tool implementation.
3. **Shape** — The agent builds **wide** markdown tables (one numeric column per variable, one row per place) for multi-variable work.
4. **Analyze or visualize** — Statistics tools parse those tables; chart and map tools consume table data or structured payloads. Maps call `resolve_places_for_map` and `get_geojson_for_places` first when boundaries are needed.
5. **Review** — The user may expand logic steps or run the audit LLM on the completed turn.
6. **Document (optional)** — With a named file that has Problem Definition, the agent may propose Data Inventory or Data Assessment updates. Disk does not change until **Confirm write**.

### Data sources

| Source | Discovery | Observations | Maps / places |
|--------|-----------|--------------|---------------|
| **Google Data Commons** | MCP `search_indicators` via `search_sdoh_indicators` (place-scoped; default United States; parses Agent API `variableCandidates` tables and `variables` + `dcidNameMappings`) | v2 batch API (preferred) or MCP `get_observations` | `geoJsonCoordinates` via v2; place expansion via `datacommons-client` |
| **Centers for Medicare & Medicaid Services (CMS)** | data.cms.gov `data.json` catalog search | Per-dataset API inside `get_sdoh_observations` | Schema inferred per dataset; geo fields vary by program. If the requested year is missing, the tool returns the latest year plus a warning. Rural/Urban breakouts are filtered to Overall rows. |
| **CDC PLACES** | Socrata measure index on data.cdc.gov | Socrata query API | County, place, ZCTA, tract levels per release |

All sources normalize to a shared **`place_key`** (usually a Data Commons DCID such as `geoId/39061` or `zip/45202`) so observations, correlation tables, and map layers can be joined.

### Agent tools

The assistant LLM can call the tools below. Rules for when to use each tool and how to format tables are defined in `agents/agent_system_prompt.txt`.

#### Search and observations

| Tool | Role |
|------|------|
| **search_sdoh_indicators** | Unified search across Data Commons, CMS, and CDC PLACES; interleaves results per source. Data Commons search is place-scoped (default United States). |
| **get_sdoh_observations** | Preferred fetch for all repositories; returns long or wide tables. CMS year misses fall back to the latest available year; geography breakouts keep Overall only. |
| **get_observations** | MCP fallback for a single Data Commons variable when `get_sdoh_observations` is unsuitable. |

Implementation: `agents/tools/sdoh_search_tool.py`, `agents/tools/sdoh_observations_tool.py`, `agents/tools/sdoh_search_merge.py`, `agents/tools/cdc_places_helpers.py`, `agents/tools/dc_v2_helpers.py`.

#### Places and geometry

| Tool | Role |
|------|------|
| **resolve_places_for_map** | Resolve names or ids to DCIDs and `place_key` values; expand parent→children via Data Commons v2 (requires `DC_API_KEY`). |
| **get_geojson_for_places** | Fetch boundaries for choropleth maps; stores geometry server-side by reference. |

Implementation: `agents/tools/resolve_places_tool.py`, `agents/tools/dc_place_expand.py`, `agents/tools/geojson_tool.py`.

#### Statistics

| Tool | Role |
|------|------|
| **calculate_correlation** | Pearson correlation and *p*-value between two numeric columns in a wide table. |
| **regression_analysis** | OLS regression with a named target column. |
| **descriptive_stats** | Mean, median, standard deviation, etc. |
| **time_series_forecast** | Simple exponential smoothing over a year column. |

Implementation: `agents/tools/correlation_tool.py`, `regression_tool.py`, `descriptive_stats_tool.py`, `time_series_tool.py`, `analysis_base_tool.py`.

#### Visualization

| Tool | Role |
|------|------|
| **generate_chart** | Emits matplotlib code; Streamlit renders it after the turn. |
| **generate_map** | Emits pydeck/Folium-style map code using `geojson_ref` and optional tabular `data`. |

Implementation: `agents/tools/chart_tool.py`, `map_tool.py`, `chart_renderer.py`, `map_renderer.py`.

#### Requirements document

| Tool | Role |
|------|------|
| **propose_data_inventory_assessment_update** | Propose one `##` section (default Problem Definition). Does not write. Practitioner Confirm write / Cancel in Core Streamlit. |

Implementation: `agents/data_document.py`, `agents/framework_sections.py`, `agents/file_baseline.py`, `agents/build_data_agent.py`.

### Shared library (`sdoh_core`)

Product code imports Core LLM factory (`llm_config`), tool-calling loop, Core `ReActAgent`, `RequirementsFileHelper`, `DocumentSectionTool`, `run_assistant_app` / `AssistantAppConfig` / `AfterTurnHook`, and `AuditAgent`.

Public-data tools, chart/map renderers, welcome copy, and framework headings stay in this repository. Charts/maps persist through `AfterTurnHook.collect` / `render`. The image installs Core from GitHub `main`.

### Key files

| Path | Purpose |
|------|---------|
| `agents/streamlit_assistant.py` | Core `run_assistant_app` + AfterTurnHook for charts/maps |
| `agents/build_data_agent.py` | Core `ReActAgent` + public-data tools + propose tool |
| `agents/react_agent.py` | Public-data tool assembly |
| `agents/welcome_message.py` | Opening greeting (no LLM; no default filename) |
| `agents/data_document.py` | Framework heading binding for `DocumentSectionTool` |
| `agents/agent_system_prompt.txt` | Agent instructions (search, maps, document propose/confirm) |
| `agents/audit_agent.py` | Product audit criteria + Streamlit `audit()` adapter |
| `analytic_assistant_build/pyproject.openai.toml` | Runtime deps, including `sdoh-core` from GitHub `main` |
| `docker-compose.yaml` | Service definitions and port wiring |
| `.env.example` | Required and optional environment variables |

### Planned: local database integration

Future work will let you attach a private database so the agent can query local tables and relate them to public indicators. That path is not part of the current compose stack or tool surface.
