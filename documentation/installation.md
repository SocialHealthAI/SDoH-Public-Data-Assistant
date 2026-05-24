## Installation

This project uses Docker Compose to run two services on a shared network:

- **public-data-assistant** — Streamlit chat UI and LangChain agent (tools for search, observations, statistics, charts, and maps).
- **data-commons-mcp** — Local [Data Commons MCP](https://docs.datacommons.org/mcp/) server used for indicator search and as a fallback for observations.

CMS and CDC PLACES data are accessed over the public internet from the assistant container; no extra containers are required for those sources.

##### Prerequisites

Before getting started, ensure you have the following:

- Docker Engine and the Docker Compose plugin
- Git (for cloning this repository)
- At least 8 GB of RAM and 10 GB of free disk space

Platform install guides:


| Platform | Guide                                                                                         |
| -------- | --------------------------------------------------------------------------------------------- |
| Windows  | [Install Docker Desktop on Windows](https://docs.docker.com/desktop/install/windows-install/) |
| macOS    | [Install Docker Desktop on Mac](https://docs.docker.com/desktop/install/mac-install/)         |
| Linux    | [Install Docker Engine on Linux](https://docs.docker.com/engine/install/)                     |


##### Configure environment

Copy `.env.example` to `.env` and edit the values.

Required variables:


| Variable                     | Purpose                                                                                                                                        |
| ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `OPENAI_API_KEY`             | Powers the reasoning and audit LLMs                                                                                                            |
| `DC_API_KEY`                 | Data Commons API key for batched observations, place expansion, and map boundaries. See [Data Commons API](https://docs.datacommons.org/api/). |
| `DATACOMMONS_URI`            | MCP endpoint for the assistant container. Use `http://data-commons-mcp:3000/mcp` with the default compose setup.                               |
| `DATACOMMONS_CONTAINER_PORT` | Port for the MCP server (default `3000`). Must match the port in `DATACOMMONS_URI`.                                                            |


Optional:


| Variable                | Purpose                                                                          |
| ----------------------- | -------------------------------------------------------------------------------- |
| `ASSISTANT_IMAGE`       | Docker image for the assistant service (see below)                               |
| `DATACOMMONS_MCP_IMAGE` | Docker image for the MCP service (see below)                                     |
| `CDC_PLACES_APP_TOKEN`  | Socrata app token for CDC PLACES (higher rate limits)                            |
| `ASSISTANT_HOST_PORT`   | Host port for the Streamlit UI (default `8052`)                                  |
| `ASSISTANT_BIND`        | Bind address for the UI (default `127.0.0.1`; use `0.0.0.0` to allow LAN access) |


##### Docker images: local build or Docker Hub

You can run the stack in two ways. Both are configured in `.env` by setting `ASSISTANT_IMAGE` and `DATACOMMONS_MCP_IMAGE`. **Use different tags for each mode** so local builds do not overwrite images pulled from Hub.


| Mode            | When to use                                                                     | Image tags in `.env`                                                                  |
| --------------- | ------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| **Local build** | Developing this repo, changing Dockerfiles, requirements, or working offline    | `public-data-assistant:local`, `data-commons-mcp:local`                               |
| **Docker Hub**  | Quick start without building, or running a published release on another machine | `jeffgunderson/public-data-assistant:latest`, `jeffgunderson/data-commons-mcp:latest` |


`.env.example` shows both pairs. Comment one pair and uncomment the other:

```env
# Docker Hub — pull/run
# ASSISTANT_IMAGE=jeffgunderson/public-data-assistant:latest
# DATACOMMONS_MCP_IMAGE=jeffgunderson/data-commons-mcp:latest

# Local build — default in .env.example
ASSISTANT_IMAGE=public-data-assistant:local
DATACOMMONS_MCP_IMAGE=data-commons-mcp:local
```

**Why this matters:** `docker-compose.yaml` includes both `image:` and `build:` for each service. The `image:` value is the tag Compose applies after a build *or* the name it uses when pulling. If local builds and Hub images share the same tag (for example `jeffgunderson/...:latest`), Compose cannot tell them apart and `docker compose up --build` will rebuild locally even when you intended to run from Hub.

**Development note:** The assistant service mounts `./agents` into the container at `/myapps`. When that volume is present, the running app uses your host copy of the agent code regardless of whether the image was built locally or pulled from Hub. The MCP service has no source mount; it runs entirely from the image.

#### Option A — Local build (default)

From the repository root:

```
docker compose up --build
```

On first run, Compose builds both images and tags them with the `:local` names from `.env`. Subsequent starts are faster if the images are already built. To rebuild without starting:

```
docker compose build
```

To rebuild a single service:

```
docker compose build public-data-assistant
docker compose build data-commons-mcp
```

#### Option B — Docker Hub images

Published images:

- [jeffgunderson/public-data-assistant](https://hub.docker.com/r/jeffgunderson/public-data-assistant)
- [jeffgunderson/data-commons-mcp](https://hub.docker.com/r/jeffgunderson/data-commons-mcp)

1. In `.env`, comment the `:local` lines and uncomment the `jeffgunderson/...` lines.
2. Pull and start **without** building:

```
docker login
docker compose pull
docker compose up --no-build
```

Use `--no-build` so Compose does not rebuild from the Dockerfiles in this repo. If a stale local image with the same tag already exists, `docker compose pull` refreshes it from Hub.

To switch back to local development, reverse the comments in `.env` and run `docker compose up --build`.

##### Open the assistant

```
http://localhost:8052
```

Replace the port if you changed `ASSISTANT_HOST_PORT`.

See [usage.md](./usage.md) for example prompts and tips on keeping requests within model limits.