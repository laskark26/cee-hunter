import os
from datetime import datetime

import requests
import streamlit as st
from google.cloud import bigquery

PROJECT_ID = "gen-lang-client-0045947309"
URBS_BASE_URL = "https://api.urbs.fr"
URBS_ATTRIBUTES = "chauffageurbs,energieurbs,jannatmin,dpeurbs"
URBS_TABLE = "gen-lang-client-0045947309.rnic.urbs_building_data"


def _get_bq_client():
    if "GOOGLE_SERVICE_ACCOUNT_JSON" in st.secrets:
        info = dict(st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"])
        return bigquery.Client.from_service_account_info(info)
    return bigquery.Client(project=PROJECT_ID)


def _get_urbs_key():
    return st.secrets.get("URBS_API_KEY", os.environ.get("URBS_API_KEY", ""))


# ── BigQuery persistence ─────────────────────────────────────


def init_urbs_table():
    client = _get_bq_client()
    try:
        client.query(f"""
            CREATE TABLE IF NOT EXISTS `{URBS_TABLE}` (
                numero_immatriculation STRING,
                address STRING,
                imope_id STRING,
                chauffage STRING,
                energie STRING,
                annee INT64,
                dpe STRING,
                ges STRING,
                fetched_at TIMESTAMP
            )
        """).result()
    except Exception as e:
        print(f"Error creating URBS table: {e}")


def get_urbs_from_db(numero_immat):
    """Load cached URBS data for a copro from BigQuery."""
    if not numero_immat:
        return None
    client = _get_bq_client()
    try:
        safe = numero_immat.replace("'", "\\'")
        df = client.query(
            f"SELECT * FROM `{URBS_TABLE}` WHERE numero_immatriculation = '{safe}' LIMIT 1"
        ).to_dataframe()
        if df.empty:
            return None
        row = df.iloc[0]
        return {
            "chauffage": row.get("chauffage", "") or "",
            "energie": row.get("energie", "") or "",
            "annee": int(row["annee"]) if row.get("annee") is not None and str(row.get("annee", "")) != "" else None,
            "dpe": row.get("dpe", "") or "",
            "ges": row.get("ges", "") or "",
        }
    except Exception as e:
        print(f"URBS DB read error: {e}")
        return None


def save_urbs_to_db(numero_immat, address, imope_id, data):
    """Persist URBS data in BigQuery (upsert via DELETE + INSERT)."""
    if not numero_immat or not data:
        return
    client = _get_bq_client()
    try:
        safe = numero_immat.replace("'", "\\'")
        client.query(
            f"DELETE FROM `{URBS_TABLE}` WHERE numero_immatriculation = '{safe}'"
        ).result()

        row = {
            "numero_immatriculation": numero_immat,
            "address": address or "",
            "imope_id": imope_id or "",
            "chauffage": data.get("chauffage", ""),
            "energie": data.get("energie", ""),
            "annee": data.get("annee"),
            "dpe": data.get("dpe", ""),
            "ges": data.get("ges", ""),
            "fetched_at": datetime.utcnow().isoformat(),
        }
        client.insert_rows_json(URBS_TABLE, [row])
    except Exception as e:
        print(f"URBS DB save error: {e}")


# ── API calls ─────────────────────────────────────────────────


def urbs_geocode(address):
    """Geocode an address via URBS and return the best IMOPE id, or None."""
    key = _get_urbs_key()
    if not key:
        return None
    try:
        resp = requests.get(
            f"{URBS_BASE_URL}/geocoder/search",
            params={"key": key, "value": address},
            timeout=10,
        )
        if resp.status_code == 200:
            results = resp.json()
            if isinstance(results, list) and results:
                return results[0].get("id")
    except Exception as e:
        print(f"URBS geocode error: {e}")
    return None


def urbs_get_attributes(imope_id):
    """Fetch building attributes from URBS dashboard for a given IMOPE id."""
    key = _get_urbs_key()
    if not key or not imope_id:
        return None
    try:
        resp = requests.get(
            f"{URBS_BASE_URL}/dashboard",
            params={"key": key, "id": imope_id, "attributes": URBS_ATTRIBUTES},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            entry = data.get(imope_id, {})
            attrs = entry.get("attributes", {})

            chauffage = (attrs.get("chauffageurbs") or {}).get("value", "")
            energie = (attrs.get("energieurbs") or {}).get("value", "")
            annee = (attrs.get("jannatmin") or {}).get("value", "")

            dpe_raw = (attrs.get("dpeurbs") or {}).get("value", {})
            if isinstance(dpe_raw, dict):
                dpe = dpe_raw.get("dpe", "")
                ges = dpe_raw.get("ges", "")
            else:
                dpe = str(dpe_raw) if dpe_raw else ""
                ges = ""

            return {
                "chauffage": chauffage or "",
                "energie": energie or "",
                "annee": int(annee) if annee else None,
                "dpe": dpe,
                "ges": ges,
            }
    except Exception as e:
        print(f"URBS dashboard error: {e}")
    return None


# ── Main enrichment pipeline ─────────────────────────────────


def urbs_enrich_address(address, numero_immat=None):
    """Full pipeline: session cache -> BigQuery -> API. Persists to BQ."""
    cache_key = f"urbs_{address}"

    # 1. Session cache (fastest)
    if cache_key in st.session_state:
        return st.session_state[cache_key]

    # 2. BigQuery lookup
    if numero_immat:
        db_result = get_urbs_from_db(numero_immat)
        if db_result is not None:
            st.session_state[cache_key] = db_result
            return db_result

    # 3. API call
    imope_id = urbs_geocode(address)
    if not imope_id:
        st.session_state[cache_key] = None
        return None

    result = urbs_get_attributes(imope_id)
    st.session_state[cache_key] = result

    # 4. Persist to BigQuery
    if result and numero_immat:
        save_urbs_to_db(numero_immat, address, imope_id, result)

    return result
