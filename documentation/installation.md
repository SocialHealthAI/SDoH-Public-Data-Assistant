## Installation

This project uses Docker Compose to run two services on a shared network:

- **public-data-assistant** — Streamlit chat UI and LangChain agent.
- **data-commons-mcp** — Local [Data Commons MCP](https://docs.datacommons.org/mcp/) server.
- 
Both run modes start from a **clone of this repository**. Compose reads `docker-compose.yaml` from the repo, and the assistant mounts host `./agents` into the container, so a clone is required even when you pull images from Docker Hub.

### Prerequisites

- Docker Engine and the Docker Compose plugin
- Git (to clone this repository).
- At least 8 GB of RAM and 10 GB of free disk space
- API keys (see Configure Environment)
  - OpenAI *or* Anthropic, depending on `LLM_PROVIDER`
  - A [Data Commons API key](https://docs.datacommons.org/api/)

| Platform | Guide |
| -------- | ----- |
| Windows  | [Install Docker Desktop on Windows](https://docs.docker.com/desktop/install/windows-install/) |
| macOS    | [Install Docker Desktop on Mac](https://docs.docker.com/desktop/install/mac-install/) |
| Linux    | [Install Docker Engine on Linux](https://docs.docker.com/engine/install/) |

### 1. Clone the repository

```
git clone https://github.com/SocialHealthAI/SDoH-Public-Data-Assistant.git
cd SDoH-Public-Data-Assistant
```

### 2. Configure Environment

1. Copy the template and edit it:

```
cp .env.example .env
```
On Windows: 
```
copy .env.example .env
```

2. Set the keys for the LLM you will use, plus Data Commons (see tables below).
3. Create the shared documents folder if it does not exist (default host path `../sdoh_documents`, a sibling of this repo). 

### 3. Use DockerHub Images or Build Images

#### Option 1 — Docker Hub images (default)
Use published images and skip building:
- [jeffgunderson/public-data-assistant](https://hub.docker.com/r/jeffgunderson/public-data-assistant)
- [jeffgunderson/data-commons-mcp](https://hub.docker.com/r/jeffgunderson/data-commons-mcp)

Keep these lines active in `.env` (they are already uncommented in `.env.example`):

```
ASSISTANT_IMAGE=jeffgunderson/public-data-assistant:latest
DATACOMMONS_MCP_IMAGE=jeffgunderson/data-commons-mcp:latest
```
Pull and start **without** building:

```
docker compose pull
docker compose up -d --no-build
```

Then open:

```
http://localhost:8052
```

#### Option 2 — Local build
Build when you are changing Dockerfiles or want images produced on this machine.

In `.env`, comment the Hub tags and uncomment the local tags:

```
# Docker Hub
#ASSISTANT_IMAGE=jeffgunderson/public-data-assistant:latest
#DATACOMMONS_MCP_IMAGE=jeffgunderson/data-commons-mcp:latest

# Local build
ASSISTANT_IMAGE=public-data-assistant:local
DATACOMMONS_MCP_IMAGE=data-commons-mcp:local
```

Build and start:

```
docker compose up --build
```

On first run this builds both images and tags them `:local`. Later starts are faster. To rebuild without starting:

```
docker compose build
```

A single service:

```
docker compose build public-data-assistant
docker compose build data-commons-mcp
```

To run detached after a build: `docker compose up -d`.

Then open `http://localhost:8052` (or your `ASSISTANT_HOST_PORT`).

### Environment variables

#### Required for a working chat

| Variable | Purpose |
| -------- | ------- |
| `OPENAI_API_KEY` | Required when `LLM_PROVIDER=openai` (the default). |
| `ANTHROPIC_API_KEY` | Required when `LLM_PROVIDER=anthropic`. |
| `DC_API_KEY` | Data Commons key for batched observations, place expansion, and map boundaries. See [Data Commons API](https://docs.datacommons.org/api/). |

#### LLM selection
Set the LLM variables, LLM_PROVIDER, LLM_MODEL, and the OPENAI_API_KEY or the ANTHROPIC_API_KEY.  For example, to use Anthropic:

```
# LLM_PROVIDER=openai
# LLM_MODEL=gpt-5.2
# OPENAI_API_KEY=

LLM_PROVIDER=anthropic
LLM_MODEL=claude-sonnet-5
ANTHROPIC_API_KEY=your-anthropic-key
```

#### Usually leave as in `.env.example`

| Variable | Purpose |
| -------- | ------- |
| `ASSISTANT_IMAGE` | Assistant image tag (Hub `latest` or local `:local`). |
| `DATACOMMONS_MCP_IMAGE` | MCP image tag (Hub `latest` or local `:local`). |
| `DATACOMMONS_URI` | MCP URL inside the compose network. Default `http://data-commons-mcp:3000/mcp`. |
| `DATACOMMONS_CONTAINER_PORT` | MCP port (default `3000`). Must match the port in `DATACOMMONS_URI`. |
| `ASSISTANT_HOST_PORT` | Host port for the Streamlit UI (default `8052`). |
| `ASSISTANT_BIND` | Bind address (default `127.0.0.1`; use `0.0.0.0` to allow LAN access). |
| `SDOH_DOCUMENTS_HOST` | Host path for shared `sdoh_documents/` (default `../sdoh_documents`). Other SDoH assistants use the same folder. |
| `DOCUMENTS_ROOT` | Path inside the assistant container (default `/documents`). Compose mounts `SDOH_DOCUMENTS_HOST` there. |
| `CDC_PLACES_APP_TOKEN` | Optional Socrata app token for CDC PLACES (higher rate limits). |


