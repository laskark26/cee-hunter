# 🎯 CEE Hunter v1 - Prospecting Dashboard

**CEE Hunter** is a B2B Lead Generation and Intelligence application designed to identify and qualify real estate syndics for Energy Efficiency Certificate (CEE) projects.

## 🤖 AI Agent Integration Guide

This application is designed with a clear separation of concerns, making it easy for an AI agent to navigate, debug, and extend.

### 🏗️ Global Architecture

The app follows a 3-layer architecture:
1.  **Presentation Layer (`app.py`)**: A Streamlit-based dashboard handling user interactions, theme management, and visualization.
2.  **Core Intelligence Layer (`core/`)**:
    *   **`data_manager.py`**: Handles BigQuery queries for the main building registry (600k+ rows).
    *   **`pappers_connector.py`**: Fetches legal and financial data (Turnover, Dirigeant) from Pappers.fr and manages a BQ cache.
    *   **`enrichment_manager.py`**: Executes complex discovery flows (DuckDuckGo + Apollo.io) to find websites and decision-makers (emails, LinkedIn).
3.  **Data Layer (Google BigQuery)**:
    *   `rnic.copro`: Raw building data.
    *   `rnic.cache_pappers`: Cache for legal data.
    *   `rnic.cache_enrichissement`: Cache for Apollo/contact data.

### 📊 Data Flow

1.  **Search**: User filters by Climate Zone (H1/H2/H3) and Building Metrics.
2.  **Aggregate**: `data_manager` returns a list of unique Syndics (Legal Representatives) matching the criteria.
3.  **Enrich (Legal)**: When a syndic is selected, `pappers_connector` fetches legal data (uses BQ cache first).
4.  **Enrich (Sales)**: `enrichment_manager` discovers the website via DuckDuckGo, validates it, and then queries Apollo.io for contacts.
5.  **Output**: Displays a detailed sheet with contacts and an AI-ready email icebreaker.

### 🛠️ Key Technical Modules

#### `core/data_manager.py`
-   **Function `fetch_aggregated_syndics`**: Main entry for searching. Uses `build_filter_clause` to generate raw SQL.
-   **Important**: Climate zones are mapped derived from department codes (e.g., Paris `75` is `H1`).

#### `core/pappers_connector.py`
-   **Function `get_syndic_info(siret)`**: Central point for legal data. It automatically migrates the BQ schema if new columns are added.

#### `core/enrichment_manager.py`
-   **Class `EnrichmentManager`**: Implements a fuzzy-matching logic (`rapidfuzz`) to ensure the discovered website actually belongs to the syndic.
-   **Apollo Strategy**: Tries searching by domain first, then falls back to organization name.

### 🔐 Configuration & Secrets

The app uses Streamlit's `secrets.toml` (located in `.streamlit/`) for:
-   `APOLLO_API_KEY`
-   `PAPPERS_API_KEY`
-   `GOOGLE_SERVICE_ACCOUNT_JSON` (BigQuery access)

### 🎨 UI & UX Features (v1 Pro)

- **Full-Width SaaS Workspace**: Layout optimized for large screens, removing the sidebar for maximum focus.
- **Smart Theme Engine**: Automatic detection of system theme (Dark/Light) with manual override in the header.
- **Precise Range Filters**: Synchronized slider + numeric inputs for professional-grade data filtering.
- **High-Density Logic**: Compressed padding and micro-stepper to minimize scrolling on laptop screens.

### 🚀 Running the App

```bash
python3 -m streamlit run streamlit_app.py
```

---
*Developed with ❤️ by Antigravity for high-performance real estate prospecting.*
