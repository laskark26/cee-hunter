# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**CEE Hunter PRO** is a French B2B lead generation app for prospecting syndics (property management companies) for energy efficiency projects (CEE - Certificats d'Economies d'Energie). Built with Streamlit, backed by Google BigQuery.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the app (accessible at http://localhost:8501)
streamlit run streamlit_app.py

# Run with debug logging
LOG_LEVEL=DEBUG streamlit run streamlit_app.py

# Run with file logging
LOG_LEVEL=DEBUG LOG_FILE=logs/app.log streamlit run streamlit_app.py
```

There are no tests, linters, or build steps configured.

## Architecture

Three-layer architecture: Presentation → Core Intelligence → Data (BigQuery).

### Presentation Layer
- `streamlit_app.py` — Main entry point. Multi-step workflow (Criteres → Resultats → Fiche Syndic → Pack). Manages session state, authentication, and step navigation.
- `components.py` — Reusable UI components (header, stepper, KPI cards, score gauge, copro cards, contact cards, skeletons).
- `styles.py` — Design system with Light/Dark themes. `generate_css(theme_name)` produces full CSS injection. Primary color: `#10B981`.

### Core Intelligence Layer (`core/`)
- `data_manager.py` — BigQuery queries. `build_filter_clause()` generates SQL WHERE from UI filters. `fetch_aggregated_syndics()` is the main search. Climate zones (H1/H2/H3) derived from department codes.
- `pappers_connector.py` — Pappers API with cache-aside pattern on `rnic.cache_pappers`. Entry point: `get_syndic_info(siret)`. Has automatic BQ schema migration.
- `enrichment_manager.py` — `EnrichmentManager` class. Domain discovery via DuckDuckGo, validation with rapidfuzz fuzzy matching, Apollo.io contact search. Cache: `rnic.cache_enrichissement`.
- `urbs_connector.py` — URBS API for building attributes (heating, energy, DPE, GES). `urbs_enrich_address()` with session state + BQ cache.
- `syndic_intel.py` — Largest module (~57KB). `SyndicIntelligence` class orchestrates SERP (SerpApi), Google Maps, web scraping (BeautifulSoup), social media extraction, Apollo contacts, and OpenAI LLM analysis. Produces structured JSON with prospection score, icebreaker email, key contacts. Caches in `cache_syndic_intel`, `syndic_enrichment`, `syndic_contacts`.
- `log_config.py` — `setup_logging()` called at app startup. Level via `LOG_LEVEL` env var, optional file via `LOG_FILE`.

### Data Layer (Google BigQuery)
Project: `gen-lang-client-0045947309`, dataset: `rnic`. Key tables:
- `copro` — Building registry (600k+ rows), main data source
- `cache_pappers`, `cache_enrichissement`, `cache_syndic_intel` — API response caches
- `syndic_enrichment`, `syndic_contacts` — Enriched analysis output
- `saved_searches` — User search presets
- `urbs_building_data` — Building attribute cache

## Key Patterns

**BigQuery client instantiation** (used in every core module):
```python
def get_bigquery_client():
    if "GOOGLE_SERVICE_ACCOUNT_JSON" in st.secrets:
        info = dict(st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"])
        return bigquery.Client.from_service_account_info(info)
    return bigquery.Client(project=PROJECT_ID)
```

**Cache-aside strategy**: All external API calls (Pappers, Apollo, SERP, URBS) check BQ cache first, call API on miss, then persist result.

**Logging**: Each module uses `logger = logging.getLogger(__name__)`. Use `logger.debug/info/warning/exception`. Keep `st.error/warning/info` for user-facing messages alongside technical logs.

**Session state**: Initialize with `if k not in st.session_state: st.session_state[k] = default`.

## Configuration

Secrets in `.streamlit/secrets.toml` (not versioned):
- `APP_PASSWORD` — App access password
- `GOOGLE_SERVICE_ACCOUNT_JSON` — BigQuery service account (JSON object)
- `APOLLO_API_KEY`, `PAPPERS_API_KEY`, `OPENAI_API_KEY`, `SERPAPI_KEY`, `URBS_API_KEY`

Missing keys gracefully degrade the corresponding feature. Pappers and Apollo APIs are currently disabled in code.

## Language

The codebase, UI, variable names, and comments are primarily in **French**. Follow this convention when adding code or comments.
