import pandas as pd
from google.cloud import bigquery
import streamlit as st
import os

# Configuration
PROJECT_ID = "gen-lang-client-0045947309"
DATASET_TABLE = "gen-lang-client-0045947309.rnic.copro"

# Climate Zones Mapping
H1_DEPARTMENTS = [
    "01", "02", "03", "05", "08", "10", "14", "15", "19", "21", "23", "25", "26", "27", "28", "38", "39", "42", "43", "45", "51", "52", "54", "55", "57", "58", "59", "60", "61", "62", "63", "67", "68", "69", "70", "71", "73", "74", "75", "76", "77", "78", "80", "87", "88", "89", "90", "91", "92", "93", "94", "95"
]

def get_climate_zone(code_dept):
    """
    Categorizes a French department into a specific climatic zone (H1, H2, H3).
    H1: Cold/Continental, H2: Temperate/Atlantic, H3: Mediterranean.
    """
    if code_dept in H1_DEPARTMENTS:
        return "H1"
    if code_dept in ["11", "13", "30", "34", "66", "83", "2A", "2B", "06"]:
        return "H3"
    return "H2"

def get_bigquery_client():
    """
    Initializes the BigQuery client using Streamlit secrets for authentication.
    Falls back to environment credentials if secrets are missing.
    """
    if "GOOGLE_SERVICE_ACCOUNT_JSON" in st.secrets:
        info = dict(st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"])
        return bigquery.Client.from_service_account_info(info)
    return bigquery.Client(project=PROJECT_ID)

def build_filter_clause(climate_zones, min_lots, max_lots, periods=None, exclude_big_syndics=False, qpv_only=False):
    """
    Constructs a SQL WHERE clause based on UI filters.
    Includes custom logic for construction periods and syndic exclusions.
    Returns: (str, str) -> (Where clause, Zone CASE SQL expression)
    """
    conditions = []
    
    # 1. Habitation Lots
    conditions.append(f"CAST(nombre_de_lots_a_usage_d_habitation AS INT64) BETWEEN {min_lots} AND {max_lots}")
    
    # 2. Construction Periods
    if periods:
        # Mapping UI labels to DB values
        period_mapping = {
            'Avant 1949': ['AVANT_1949'],
            '1949-1974': ['DE_1949_A_1960', 'DE_1961_A_1974'],
            '1975-1993': ['DE_1975_A_1993'],
            '1994-2000': ['DE_1994_A_2000'],
            '2001-2010': ['DE_2001_A_2010'],
            'Après 2011': ['A_COMPTER_DE_2011']
        }
        
        db_periods = []
        for p in periods:
            db_periods.extend(period_mapping.get(p, []))
            
        if db_periods:
            periods_str = "', '".join(db_periods)
            conditions.append(f"periode_de_construction IN ('{periods_str}')")

    # 3. Exclusions (Big Syndics & Invalid Data)
    if exclude_big_syndics:
        exclusions = [
            "FONCIA", "LAMY", "NEXITY", "CITYA", 
            "IDENTITE NON PARTAGEE EN OPEN DATA", "IDENTITÉ NON PARTAGÉE EN OPEN DATA", "NON CONNU", 
            "SYNDIC BENEVOLE", "EN COURS", "AUCUN"
        ]
        regex_pattern = "|".join(exclusions)
        conditions.append(f"NOT REGEXP_CONTAINS(UPPER(raison_sociale_du_representant_legal), r'{regex_pattern}')")

    # 4. QPV Filter
    if qpv_only:
        conditions.append("(code_qp_2024 != '' OR nom_qp_2024 != '')")

    # 5. Climate Zones 
    h1_str = "', '".join(H1_DEPARTMENTS)
    h3_str = "', '".join(["11", "13", "30", "34", "66", "83", "2A", "2B", "06"])
    
    # Dynamic SQL Zone Logic
    zone_case = f"""
        CASE 
            WHEN code_officiel_departement IN ('{h1_str}') THEN 'H1'
            WHEN code_officiel_departement IN ('{h3_str}') THEN 'H3'
            ELSE 'H2'
        END
    """
    
    if climate_zones:
        selected_zones_str = "', '".join(climate_zones)
        conditions.append(f"({zone_case}) IN ('{selected_zones_str}')")
        
    return " AND ".join(conditions) if conditions else "1=1", zone_case

def fetch_aggregated_syndics(climate_zones, min_lots, max_lots, periods=None, exclude_big_syndics=False, qpv_only=False):
    """
    Step 2: Aggregated View.
    Returns list of filtered syndics with their total stats.
    """
    client = get_bigquery_client()
    where_clause, zone_case = build_filter_clause(climate_zones, min_lots, max_lots, periods, exclude_big_syndics, qpv_only)
    
    query = f"""
        SELECT 
            raison_sociale_du_representant_legal as Syndic,
            COUNT(*) as nb_copros,
            SUM(CAST(nombre_total_de_lots AS INT64)) as total_lots,
            ANY_VALUE(siret_du_representant_legal) as Siret
        FROM `{DATASET_TABLE}`
        WHERE 
            raison_sociale_du_representant_legal IS NOT NULL
            AND {where_clause}
        GROUP BY 1
        ORDER BY 2 DESC
        LIMIT 1000
    """
    
    try:
        df = client.query(query).to_dataframe()
        return df
    except Exception as e:
        st.error(f"Error fetching aggregations: {e}")
        return pd.DataFrame()

def fetch_data_by_syndic(syndic_name, climate_zones, min_lots, max_lots, periods=None, exclude_big_syndics=False, qpv_only=False):
    """
    Step 3: Detailed View.
    Fetches rows for a specific syndic matching filters.
    """
    client = get_bigquery_client()
    where_clause, zone_case = build_filter_clause(climate_zones, min_lots, max_lots, periods, exclude_big_syndics, qpv_only)
    
    # Escape syndic name for SQL safely
    safe_syndic = syndic_name.replace("'", "\\'")
    
    query = f"""
        SELECT 
            *,
            ({zone_case}) as climate_zone,
            CASE 
                WHEN (code_qp_2024 IS NOT NULL AND code_qp_2024 != '') 
                     OR (nom_qp_2024 IS NOT NULL AND nom_qp_2024 != '') 
                THEN 'Oui' ELSE 'Non' 
            END as in_qpv
        FROM `{DATASET_TABLE}`
        WHERE 
            raison_sociale_du_representant_legal = '{safe_syndic}'
            AND {where_clause}
        ORDER BY CAST(nombre_de_lots_a_usage_d_habitation AS INT64) DESC
    """
    
    try:
        df = client.query(query).to_dataframe()
        
        if not df.empty:
            # Basic cleaning
            df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
            df['long'] = pd.to_numeric(df['long'], errors='coerce')
            df['nombre_de_lots_a_usage_d_habitation'] = pd.to_numeric(df['nombre_de_lots_a_usage_d_habitation'], errors='coerce').fillna(0)
            df = df.dropna(subset=['lat', 'long'])
            
        return df
    except Exception as e:
        st.error(f"Error fetching details for syndic: {e}")
        return pd.DataFrame()

def dry_run():
    client = get_bigquery_client()
    try:
        client.query(f"SELECT 1 FROM `{DATASET_TABLE}` LIMIT 1").result()
        return True
    except Exception as e:
        print(f"Dry-run failed: {e}")
        return False
