
import os
import requests
import pandas as pd
import streamlit as st
from google.cloud import bigquery
from datetime import datetime

# Configuration
PROJECT_ID = "gen-lang-client-0045947309"
CACHE_TABLE = "gen-lang-client-0045947309.rnic.cache_pappers"

def get_pappers_api_key():
    if "PAPPERS_API_KEY" in st.secrets:
        return st.secrets["PAPPERS_API_KEY"]
    return os.environ.get("PAPPERS_API_KEY", None)

def get_bigquery_client():
    if "GOOGLE_SERVICE_ACCOUNT_JSON" in st.secrets:
        info = dict(st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"])
        return bigquery.Client.from_service_account_info(info)
    return bigquery.Client(project=PROJECT_ID)

def init_cache_table():
    """Creates the cache table if it doesn't exist or adds missing columns."""
    client = get_bigquery_client()
    
    # 1. Ensure Table Exists
    query = f"""
        CREATE TABLE IF NOT EXISTS `{CACHE_TABLE}` (
            siret STRING,
            denomination STRING,
            nom_dirigeant STRING,
            prenom_dirigeant STRING,
            code_ape STRING,
            ca_annuel FLOAT64,
            derniere_maj_pappers TIMESTAMP
        )
    """
    try:
        client.query(query).result()
        
        # 2. Migration: Add new columns if they don't exist
        new_cols = {
            "sites_internet": "STRING",
            "telephone": "STRING",
            "email": "STRING",
            "lien_linkedin": "STRING",
            "categorie_entreprise": "STRING"
        }
        
        # Get existing columns
        table = client.get_table(CACHE_TABLE)
        existing_cols = [schema.name for schema in table.schema]
        
        for col, col_type in new_cols.items():
            if col not in existing_cols:
                alter_query = f"ALTER TABLE `{CACHE_TABLE}` ADD COLUMN {col} {col_type}"
                client.query(alter_query).result()
                print(f"Migration: Added column {col}")
                
    except Exception as e:
        st.error(f"Error initializing/migrating cache table: {e}")

def get_syndic_info(siret):
    """
    Retrieves syndic information using a 'Cache-Aside' strategy.
    1. Checks the BigQuery cache table (rnic.cache_pappers).
    2. If missing or incomplete (e.g., missing phone/email), calls the Pappers API.
    3. Updates the cache with the fresh API data.
    
    Args:
        siret (str): The French SIRET number of the syndic.
    Returns:
        dict: A dictionary containing legal info (dirigeant, CA, contact details).
    """
    if not siret:
        return None
        
    # Cleaning: remove spaces or non-digits
    clean_siret = "".join(filter(str.isdigit, str(siret))).strip()
    if not clean_siret or len(clean_siret) < 9:
        return None

    client = get_bigquery_client()
    
    # 1. Check Cache
    try:
        query = f"SELECT * FROM `{CACHE_TABLE}` WHERE siret = '{clean_siret}' LIMIT 1"
        df = client.query(query).to_dataframe()
        if not df.empty:
            res = df.iloc[0].to_dict()
            # If crucial new fields are missing (None or empty), we might want to re-fetch or just return
            # Let's check if 'telephone' is present and not None. If it is None, it means it's an old cache entry
            if res.get('telephone') is not None or res.get('email') is not None:
                return res
            # Otherwise, we continue to API to "refresh" this entry
    except Exception as e:
        st.warning(f"⚠️ Cache lookup error: {e}")

    # 2. Call API (if Key exists)
    api_key = get_pappers_api_key()
    if not api_key:
        return {"nom_dirigeant": "Clé Manquante", "ca_annuel": None}

    try:
        # Pappers API v2
        url = "https://api.pappers.fr/v2/entreprise/"
        params = {"siret": clean_siret, "api_token": api_key}
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            # Extract relevant fields
            result = {
                "siret": clean_siret,
                "denomination": data.get("denomination", ""),
                "nom_dirigeant": "",
                "prenom_dirigeant": "",
                "code_ape": data.get("code_naf", ""),
                "ca_annuel": 0.0,
                "derniere_maj_pappers": datetime.now().isoformat(),
                # NEW FIELDS
                "sites_internet": ", ".join(data.get("sites_internet", [])) if isinstance(data.get("sites_internet"), list) else (data.get("siege", {}).get("site_internet", "")),
                "telephone": data.get("telephone", "") or data.get("siege", {}).get("telephone", ""),
                "email": data.get("email", "") or data.get("siege", {}).get("email", ""),
                "lien_linkedin": data.get("lien_linkedin", ""),
                "categorie_entreprise": data.get("categorie_entreprise", "")
            }
            
            # Extract Leader
            representants = data.get("representants", [])
            if representants:
                first_rep = representants[0]
                result["nom_dirigeant"] = first_rep.get("nom", "") or first_rep.get("nom_complet", "")
                result["prenom_dirigeant"] = first_rep.get("prenom", "")
            
            # Extract Financials
            finances = data.get("finances", [])
            if finances:
                result["ca_annuel"] = float(finances[0].get("chiffre_affaires") or 0)

            # 3. Update Cache
            try:
                client.insert_rows_json(CACHE_TABLE, [result])
            except Exception as e:
                st.info(f"💡 Info: Cache update failed ({e})")
                
            return result
            
        elif response.status_code == 404:
            return {"nom_dirigeant": "Non trouvé", "ca_annuel": 0}
        else:
            st.error(f"❌ Erreur API Pappers: {response.status_code} - {response.text}")
            
    except Exception as e:
        st.error(f"❌ Erreur de connexion API: {e}")
        
    return None
