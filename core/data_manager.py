import logging
import os

import pandas as pd
import streamlit as st
from google.cloud import bigquery

# Configuration
PROJECT_ID = "gen-lang-client-0045947309"
DATASET_TABLE = "gen-lang-client-0045947309.rnic.copro"

logger = logging.getLogger(__name__)

# Climate Zones Mapping
H1_DEPARTMENTS = [
    "01", "02", "03", "05", "08", "10", "14", "15", "19", "21", "23", "25", "27", "28", "38", "39", "42", "43", "45", "51", "52", "54", "55", "57", "58", "59", "60", "61", "62", "63", "67", "68", "69", "70", "71", "73", "74", "75", "76", "77", "78", "80", "87", "88", "89", "90", "91", "92", "93", "94", "95"
]

# Departments Names (code -> label lisible)
DEPARTMENTS_NAMES = {
    "01": "01 - Ain", "02": "02 - Aisne", "03": "03 - Allier",
    "04": "04 - Alpes-de-Haute-Provence", "05": "05 - Hautes-Alpes", "06": "06 - Alpes-Maritimes",
    "07": "07 - Ardèche", "08": "08 - Ardennes", "09": "09 - Ariège",
    "10": "10 - Aube", "11": "11 - Aude", "12": "12 - Aveyron",
    "13": "13 - Bouches-du-Rhône", "14": "14 - Calvados", "15": "15 - Cantal",
    "16": "16 - Charente", "17": "17 - Charente-Maritime", "18": "18 - Cher",
    "19": "19 - Corrèze", "2A": "2A - Corse-du-Sud", "2B": "2B - Haute-Corse",
    "21": "21 - Côte-d'Or", "22": "22 - Côtes-d'Armor", "23": "23 - Creuse",
    "24": "24 - Dordogne", "25": "25 - Doubs", "26": "26 - Drôme",
    "27": "27 - Eure", "28": "28 - Eure-et-Loir", "29": "29 - Finistère",
    "30": "30 - Gard", "31": "31 - Haute-Garonne", "32": "32 - Gers",
    "33": "33 - Gironde", "34": "34 - Hérault", "35": "35 - Ille-et-Vilaine",
    "36": "36 - Indre", "37": "37 - Indre-et-Loire", "38": "38 - Isère",
    "39": "39 - Jura", "40": "40 - Landes", "41": "41 - Loir-et-Cher",
    "42": "42 - Loire", "43": "43 - Haute-Loire", "44": "44 - Loire-Atlantique",
    "45": "45 - Loiret", "46": "46 - Lot", "47": "47 - Lot-et-Garonne",
    "48": "48 - Lozère", "49": "49 - Maine-et-Loire", "50": "50 - Manche",
    "51": "51 - Marne", "52": "52 - Haute-Marne", "53": "53 - Mayenne",
    "54": "54 - Meurthe-et-Moselle", "55": "55 - Meuse", "56": "56 - Morbihan",
    "57": "57 - Moselle", "58": "58 - Nièvre", "59": "59 - Nord",
    "60": "60 - Oise", "61": "61 - Orne", "62": "62 - Pas-de-Calais",
    "63": "63 - Puy-de-Dôme", "64": "64 - Pyrénées-Atlantiques", "65": "65 - Hautes-Pyrénées",
    "66": "66 - Pyrénées-Orientales", "67": "67 - Bas-Rhin", "68": "68 - Haut-Rhin",
    "69": "69 - Rhône", "70": "70 - Haute-Saône", "71": "71 - Saône-et-Loire",
    "72": "72 - Sarthe", "73": "73 - Savoie", "74": "74 - Haute-Savoie",
    "75": "75 - Paris", "76": "76 - Seine-Maritime", "77": "77 - Seine-et-Marne",
    "78": "78 - Yvelines", "79": "79 - Deux-Sèvres", "80": "80 - Somme",
    "81": "81 - Tarn", "82": "82 - Tarn-et-Garonne", "83": "83 - Var",
    "84": "84 - Vaucluse", "85": "85 - Vendée", "86": "86 - Vienne",
    "87": "87 - Haute-Vienne", "88": "88 - Vosges", "89": "89 - Yonne",
    "90": "90 - Territoire de Belfort", "91": "91 - Essonne", "92": "92 - Hauts-de-Seine",
    "93": "93 - Seine-Saint-Denis", "94": "94 - Val-de-Marne", "95": "95 - Val-d'Oise",
}

# Regions Mapping (département -> région administrative)
REGIONS_DEPARTMENTS = {
    "Auvergne-Rhône-Alpes": ["01", "03", "07", "15", "26", "38", "42", "43", "63", "69", "73", "74"],
    "Bourgogne-Franche-Comté": ["21", "25", "39", "58", "70", "71", "89", "90"],
    "Bretagne": ["22", "29", "35", "56"],
    "Centre-Val de Loire": ["18", "28", "36", "37", "41", "45"],
    "Corse": ["2A", "2B"],
    "Grand Est": ["08", "10", "51", "52", "54", "55", "57", "67", "68", "88"],
    "Hauts-de-France": ["02", "59", "60", "62", "80"],
    "Île-de-France": ["75", "77", "78", "91", "92", "93", "94", "95"],
    "Normandie": ["14", "27", "50", "61", "76"],
    "Nouvelle-Aquitaine": ["16", "17", "19", "23", "24", "33", "40", "47", "64", "79", "86", "87"],
    "Occitanie": ["09", "11", "12", "30", "31", "32", "34", "46", "48", "65", "66", "81", "82"],
    "Pays de la Loire": ["44", "49", "53", "72", "85"],
    "Provence-Alpes-Côte d'Azur": ["04", "05", "06", "13", "83", "84"],
}

# Reverse mapping: département -> région
DEPT_TO_REGION = {
    dept: region
    for region, depts in REGIONS_DEPARTMENTS.items()
    for dept in depts
}

@st.cache_data(ttl=3600)
def fetch_communes(departments_key=None, regions_key=None):
    """Retourne la liste triée et dédupliquée des communes, filtrée par depts/régions."""
    conditions = ["nom_officiel_commune IS NOT NULL", "TRIM(nom_officiel_commune) != ''"]
    if departments_key:
        dept_str = "', '".join(departments_key)
        conditions.append(f"code_officiel_departement IN ('{dept_str}')")
    elif regions_key:
        dept_list = []
        for r in regions_key:
            dept_list.extend(REGIONS_DEPARTMENTS.get(r, []))
        if dept_list:
            dept_str = "', '".join(dept_list)
            conditions.append(f"code_officiel_departement IN ('{dept_str}')")
    where = " AND ".join(conditions)
    query = f"""
        SELECT UPPER(TRIM(nom_officiel_commune)) AS nom
        FROM `{DATASET_TABLE}`
        WHERE {where}
        LIMIT 50000
    """
    client = get_bigquery_client()
    try:
        df = client.query(query).to_dataframe()
        # Déduplication Python insensible à la casse et aux espaces
        seen = set()
        result = []
        for name in df["nom"].dropna():
            key = name.strip().upper()
            if key and key not in seen:
                seen.add(key)
                result.append(key)
        return sorted(result)
    except Exception:
        logger.exception("Erreur fetch_communes")
        return []


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

def build_filter_clause(climate_zones, min_lots, max_lots, periods=None, exclude_big_syndics=False, qpv_only=False, regions=None, departments=None, communes=None):
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

    # 6. Region / Department Filter (departments take priority over regions)
    if departments:
        dept_str = "', '".join(departments)
        conditions.append(f"code_officiel_departement IN ('{dept_str}')")
    elif regions:
        dept_list = []
        for region in regions:
            dept_list.extend(REGIONS_DEPARTMENTS.get(region, []))
        if dept_list:
            dept_str = "', '".join(dept_list)
            conditions.append(f"code_officiel_departement IN ('{dept_str}')")

    # 7. Filtre commune (comparaison insensible à la casse)
    if communes:
        communes_upper = [c.upper().replace("'", "\\'") for c in communes]
        communes_str = "', '".join(communes_upper)
        conditions.append(f"UPPER(nom_officiel_commune) IN ('{communes_str}')")

    return " AND ".join(conditions) if conditions else "1=1", zone_case

def fetch_aggregated_syndics(climate_zones, min_lots, max_lots, periods=None, exclude_big_syndics=False, qpv_only=False, regions=None, departments=None, communes=None, limit=1000):
    """
    Step 2: Aggregated View.
    Returns list of filtered syndics with their total stats.
    """
    client = get_bigquery_client()
    where_clause, zone_case = build_filter_clause(climate_zones, min_lots, max_lots, periods, exclude_big_syndics, qpv_only, regions=regions, departments=departments, communes=communes)

    query = f"""
        SELECT
            raison_sociale_du_representant_legal as Syndic,
            COUNT(*) as nb_copros,
            SUM(CAST(nombre_total_de_lots AS INT64)) as total_lots,
            APPROX_TOP_COUNT(siret_du_representant_legal, 1)[OFFSET(0)].value as Siret
        FROM `{DATASET_TABLE}`
        WHERE
            raison_sociale_du_representant_legal IS NOT NULL
            AND {where_clause}
        GROUP BY 1
        ORDER BY 2 DESC
        LIMIT {int(limit)}
    """
    
    try:
        df = client.query(query).to_dataframe()
        return df
    except Exception as e:
        logger.exception("Error fetching aggregations")
        st.error(f"Error fetching aggregations: {e}")
        return pd.DataFrame()

def fetch_data_by_syndic(syndic_name, climate_zones, min_lots, max_lots, periods=None, exclude_big_syndics=False, qpv_only=False, regions=None, departments=None):
    """
    Step 3: Detailed View.
    Fetches rows for a specific syndic matching filters.
    """
    client = get_bigquery_client()
    where_clause, zone_case = build_filter_clause(climate_zones, min_lots, max_lots, periods, exclude_big_syndics, qpv_only, regions=regions, departments=departments)
    
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
        logger.exception("Error fetching details for syndic")
        st.error(f"Error fetching details for syndic: {e}")
        return pd.DataFrame()

def count_matching_syndics(climate_zones, min_lots, max_lots, periods=None, exclude_big_syndics=False, qpv_only=False, regions=None, departments=None, communes=None):
    """Lightweight COUNT query for live preview of matching syndics."""
    client = get_bigquery_client()
    where_clause, zone_case = build_filter_clause(
        climate_zones, min_lots, max_lots, periods,
        exclude_big_syndics, qpv_only, regions=regions, departments=departments, communes=communes,
    )
    query = f"""
        SELECT COUNT(DISTINCT raison_sociale_du_representant_legal) as cnt
        FROM `{DATASET_TABLE}`
        WHERE raison_sociale_du_representant_legal IS NOT NULL
          AND {where_clause}
    """
    try:
        df = client.query(query).to_dataframe()
        return int(df.iloc[0]["cnt"]) if not df.empty else 0
    except Exception:
        logger.exception("Error counting matching syndics")
        return -1


@st.cache_data(ttl=120)
def search_syndic_direct(query, limit=20):
    """Recherche un syndic par nom (sous-chaîne) ou SIRET."""
    client = get_bigquery_client()
    safe = query.strip().replace("'", "\\'")
    safe_upper = safe.upper()
    sql = f"""
        SELECT
            raison_sociale_du_representant_legal AS Syndic,
            APPROX_TOP_COUNT(siret_du_representant_legal, 1)[OFFSET(0)].value AS Siret,
            COUNT(*) AS nb_copros,
            SUM(CAST(nombre_total_de_lots AS INT64)) AS total_lots
        FROM `{DATASET_TABLE}`
        WHERE
            raison_sociale_du_representant_legal IS NOT NULL
            AND (
                UPPER(raison_sociale_du_representant_legal) LIKE '%{safe_upper}%'
                OR siret_du_representant_legal LIKE '%{safe}%'
            )
        GROUP BY 1
        ORDER BY nb_copros DESC
        LIMIT {int(limit)}
    """
    try:
        df = client.query(sql).to_dataframe()
        return df
    except Exception:
        logger.exception("Erreur search_syndic_direct")
        return pd.DataFrame()


def fetch_all_data_by_syndic(syndic_name):
    """Fetch ALL copros for a syndic without any filter (for 'Tout le parc' tab)."""
    client = get_bigquery_client()
    safe_syndic = syndic_name.replace("'", "\\'")
    query = f"""
        SELECT *
        FROM `{DATASET_TABLE}`
        WHERE raison_sociale_du_representant_legal = '{safe_syndic}'
        ORDER BY CAST(nombre_de_lots_a_usage_d_habitation AS INT64) DESC
    """
    try:
        df = client.query(query).to_dataframe()
        if not df.empty:
            df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
            df['long'] = pd.to_numeric(df['long'], errors='coerce')
            df['nombre_de_lots_a_usage_d_habitation'] = pd.to_numeric(
                df['nombre_de_lots_a_usage_d_habitation'], errors='coerce'
            ).fillna(0)
            df = df.dropna(subset=['lat', 'long'])
        return df
    except Exception as e:
        logger.exception("Error fetching full portfolio")
        st.error(f"Error fetching full portfolio: {e}")
        return pd.DataFrame()


def fetch_stats_par_departement(filters=None):
    """
    Vue Nationale : agrège nb_immeubles par département avec filtres optionnels.
    filters dict : zones, periods, lots=(0,10000), qpv_only, exclude_big_syndics
    Retourne un DataFrame avec colonnes : dept_code, nb_immeubles, region_name
    """
    if filters is None:
        filters = {}

    zones = filters.get("zones", [])
    periods = filters.get("periods", [])
    lots = filters.get("lots", (0, 10000))
    qpv_only = filters.get("qpv_only", False)
    exclude_big = filters.get("exclude_big_syndics", False)

    where_clause, _ = build_filter_clause(
        climate_zones=zones,
        min_lots=lots[0],
        max_lots=lots[1],
        periods=periods,
        exclude_big_syndics=exclude_big,
        qpv_only=qpv_only,
    )

    query = f"""
        SELECT
            code_officiel_departement AS dept_code,
            COUNT(*) AS nb_immeubles
        FROM `{DATASET_TABLE}`
        WHERE
            code_officiel_departement IS NOT NULL
            AND {where_clause}
        GROUP BY 1
        ORDER BY 1
    """

    client = get_bigquery_client()
    try:
        df = client.query(query).to_dataframe()
        df["region_name"] = df["dept_code"].map(DEPT_TO_REGION).fillna("Autres")
        return df
    except Exception as e:
        logger.exception("Erreur fetch_stats_par_departement")
        st.error(f"Erreur chargement carte : {e}")
        return pd.DataFrame(columns=["dept_code", "nb_immeubles", "region_name"])


def aggregate_stats_par_region(df_dept):
    """
    Agrège un DataFrame département → région.
    Entrée : sortie de fetch_stats_par_departement()
    Sortie : DataFrame avec region_name, nb_immeubles
    """
    if df_dept.empty:
        return pd.DataFrame(columns=["region_name", "nb_immeubles"])
    return (
        df_dept.groupby("region_name", as_index=False)["nb_immeubles"]
        .sum()
        .sort_values("nb_immeubles", ascending=False)
        .reset_index(drop=True)
    )


def fetch_syndics_par_territoire(filters=None, departments=None, regions=None):
    """
    Vue Nationale : retourne la liste des syndics d'un territoire (région ou depts),
    avec le même format que fetch_aggregated_syndics().
    """
    if filters is None:
        filters = {}

    zones = filters.get("zones", [])
    periods = filters.get("periods", [])
    lots = filters.get("lots", (0, 10000))
    qpv_only = filters.get("qpv_only", False)
    exclude_big = filters.get("exclude_big_syndics", False)

    where_clause, _ = build_filter_clause(
        climate_zones=zones,
        min_lots=lots[0],
        max_lots=lots[1],
        periods=periods,
        exclude_big_syndics=exclude_big,
        qpv_only=qpv_only,
        regions=regions,
        departments=departments,
    )

    query = f"""
        SELECT
            raison_sociale_du_representant_legal AS Syndic,
            COUNT(*) AS nb_copros,
            SUM(CAST(nombre_total_de_lots AS INT64)) AS total_lots,
            APPROX_TOP_COUNT(siret_du_representant_legal, 1)[OFFSET(0)].value AS Siret
        FROM `{DATASET_TABLE}`
        WHERE
            raison_sociale_du_representant_legal IS NOT NULL
            AND {where_clause}
        GROUP BY 1
        ORDER BY 2 DESC
        LIMIT 500
    """

    client = get_bigquery_client()
    try:
        return client.query(query).to_dataframe()
    except Exception as e:
        logger.exception("Erreur fetch_syndics_par_territoire")
        st.error(f"Erreur chargement syndics : {e}")
        return pd.DataFrame()


def dry_run():
    client = get_bigquery_client()
    try:
        client.query(f"SELECT 1 FROM `{DATASET_TABLE}` LIMIT 1").result()
        return True
    except Exception:
        logger.exception("Dry-run failed")
        return False


# ── Saved Searches ──────────────────────────────────────────

SAVED_SEARCHES_TABLE = "gen-lang-client-0045947309.rnic.saved_searches"


def init_saved_searches_table():
    client = get_bigquery_client()
    try:
        client.query(f"""
            CREATE TABLE IF NOT EXISTS `{SAVED_SEARCHES_TABLE}` (
                id STRING,
                name STRING,
                filters_json STRING,
                created_at TIMESTAMP
            )
        """).result()
    except Exception:
        logger.exception("Error creating saved_searches table")


def get_saved_searches():
    client = get_bigquery_client()
    try:
        df = client.query(
            f"SELECT * FROM `{SAVED_SEARCHES_TABLE}` ORDER BY created_at DESC"
        ).to_dataframe()
        if df.empty:
            return []
        rows = df.to_dict("records")
        import json as _json
        for r in rows:
            if isinstance(r.get("filters_json"), str):
                try:
                    r["filters_json"] = _json.loads(r["filters_json"])
                except Exception:
                    r["filters_json"] = {}
        return rows
    except Exception:
        logger.exception("Error loading saved searches")
        return []


def save_search(name, filters):
    import json as _json
    import uuid
    client = get_bigquery_client()
    try:
        from datetime import datetime
        row = {
            "id": str(uuid.uuid4()),
            "name": name,
            "filters_json": _json.dumps(filters, ensure_ascii=False),
            "created_at": datetime.now().isoformat(),
        }
        client.insert_rows_json(SAVED_SEARCHES_TABLE, [row])
    except Exception:
        logger.exception("Error saving search")


def delete_saved_search(search_id):
    client = get_bigquery_client()
    try:
        client.query(
            f"DELETE FROM `{SAVED_SEARCHES_TABLE}` WHERE id = '{search_id}'"
        ).result()
    except Exception:
        logger.exception("Error deleting saved search")


# ── Référentiel Syndics ─────────────────────────────────────

SYNDICS_TABLE = "gen-lang-client-0045947309.rnic.syndics"


def init_syndics_table():
    """Crée la table syndics si elle n'existe pas."""
    client = get_bigquery_client()
    try:
        client.query(f"""
            CREATE TABLE IF NOT EXISTS `{SYNDICS_TABLE}` (
                siren STRING,
                siret_principal STRING,
                all_sirets STRING,
                raison_sociale STRING,
                nb_copros INT64,
                total_lots INT64,
                total_lots_habitation INT64,
                departements STRING,
                communes STRING,
                zones_climatiques STRING,
                periodes_construction STRING,
                denomination_officielle STRING,
                sigle STRING,
                code_ape STRING,
                libelle_ape STRING,
                categorie_juridique STRING,
                tranche_effectifs STRING,
                date_creation STRING,
                etat_administratif STRING,
                adresse_siege STRING,
                code_postal_siege STRING,
                commune_siege STRING,
                created_at TIMESTAMP,
                last_updated TIMESTAMP,
                sirene_enriched_at TIMESTAMP
            )
        """).result()
    except Exception:
        logger.exception("Erreur création table syndics")


def populate_syndics_from_copro():
    """
    Agrège la table copro par SIREN pour peupler le référentiel syndics.
    TRUNCATE + INSERT via load_table_from_dataframe.
    Retourne le nombre de syndics insérés.
    """
    client = get_bigquery_client()

    h1_str = "', '".join(H1_DEPARTMENTS)
    h3_str = "', '".join(["11", "13", "30", "34", "66", "83", "2A", "2B", "06"])

    query = f"""
        SELECT
            SUBSTR(REGEXP_REPLACE(siret_du_representant_legal, r'\\s', ''), 1, 9) AS siren,
            APPROX_TOP_COUNT(siret_du_representant_legal, 1)[OFFSET(0)].value AS siret_principal,
            STRING_AGG(DISTINCT siret_du_representant_legal, ',' ORDER BY siret_du_representant_legal LIMIT 50) AS all_sirets,
            APPROX_TOP_COUNT(raison_sociale_du_representant_legal, 1)[OFFSET(0)].value AS raison_sociale,
            COUNT(*) AS nb_copros,
            SUM(SAFE_CAST(nombre_total_de_lots AS INT64)) AS total_lots,
            SUM(SAFE_CAST(nombre_de_lots_a_usage_d_habitation AS INT64)) AS total_lots_habitation,
            STRING_AGG(DISTINCT code_officiel_departement, ',' ORDER BY code_officiel_departement) AS departements,
            STRING_AGG(DISTINCT nom_officiel_commune, ',' ORDER BY nom_officiel_commune LIMIT 20) AS communes,
            STRING_AGG(DISTINCT
                CASE
                    WHEN code_officiel_departement IN ('{h1_str}') THEN 'H1'
                    WHEN code_officiel_departement IN ('{h3_str}') THEN 'H3'
                    ELSE 'H2'
                END, ','
            ) AS zones_climatiques,
            STRING_AGG(DISTINCT periode_de_construction, ',') AS periodes_construction
        FROM `{DATASET_TABLE}`
        WHERE
            siret_du_representant_legal IS NOT NULL
            AND LENGTH(TRIM(siret_du_representant_legal)) >= 9
            AND raison_sociale_du_representant_legal IS NOT NULL
            AND UPPER(raison_sociale_du_representant_legal) NOT IN
                ('IDENTITE NON PARTAGEE EN OPEN DATA', 'IDENTITÉ NON PARTAGÉE EN OPEN DATA',
                 'NON CONNU', 'EN COURS', 'AUCUN')
            AND UPPER(raison_sociale_du_representant_legal) NOT LIKE '%SYNDIC BENEVOLE%'
        GROUP BY 1
        HAVING LENGTH(siren) = 9
    """

    try:
        df = client.query(query).to_dataframe()
        if df.empty:
            return 0

        from datetime import datetime
        now = datetime.utcnow().isoformat()
        df["created_at"] = now
        df["last_updated"] = now

        # Colonnes SIRENE à NULL
        for col in ["denomination_officielle", "sigle", "code_ape", "libelle_ape",
                     "categorie_juridique", "tranche_effectifs", "date_creation",
                     "etat_administratif", "adresse_siege", "code_postal_siege",
                     "commune_siege", "sirene_enriched_at"]:
            df[col] = None

        # TRUNCATE + INSERT
        client.query(f"DELETE FROM `{SYNDICS_TABLE}` WHERE TRUE").result()

        job_config = bigquery.LoadJobConfig(write_disposition="WRITE_APPEND")
        job = client.load_table_from_dataframe(df, SYNDICS_TABLE, job_config=job_config)
        job.result()

        logger.info("Référentiel syndics peuplé : %d syndics", len(df))
        return len(df)

    except Exception:
        logger.exception("Erreur populate_syndics_from_copro")
        return 0


def get_syndics_to_enrich(limit=None):
    """Retourne la liste des (siren, siret_principal) non enrichis SIRENE."""
    client = get_bigquery_client()
    limit_clause = f"LIMIT {int(limit)}" if limit else ""
    try:
        df = client.query(f"""
            SELECT siren, siret_principal
            FROM `{SYNDICS_TABLE}`
            WHERE sirene_enriched_at IS NULL
            ORDER BY nb_copros DESC
            {limit_clause}
        """).to_dataframe()
        return list(df.itertuples(index=False, name=None))
    except Exception:
        logger.exception("Erreur get_syndics_to_enrich")
        return []


def update_syndic_sirene_data(siren, data):
    """Met à jour un syndic avec les données SIRENE."""
    if not siren or not data:
        return
    client = get_bigquery_client()
    safe_siren = siren.replace("'", "\\'")

    def esc(val):
        if val is None:
            return "NULL"
        return "'" + str(val).replace("'", "\\'") + "'"

    try:
        client.query(f"""
            UPDATE `{SYNDICS_TABLE}`
            SET
                denomination_officielle = {esc(data.get('denomination'))},
                sigle = {esc(data.get('sigle'))},
                code_ape = {esc(data.get('code_ape'))},
                libelle_ape = {esc(data.get('libelle_ape'))},
                categorie_juridique = {esc(data.get('categorie_juridique'))},
                tranche_effectifs = {esc(data.get('tranche_effectifs'))},
                date_creation = {esc(data.get('date_creation'))},
                etat_administratif = {esc(data.get('etat_administratif'))},
                adresse_siege = {esc(data.get('adresse_siege'))},
                code_postal_siege = {esc(data.get('code_postal_siege'))},
                commune_siege = {esc(data.get('commune_siege'))},
                sirene_enriched_at = CURRENT_TIMESTAMP(),
                last_updated = CURRENT_TIMESTAMP()
            WHERE siren = '{safe_siren}'
        """).result()
    except Exception:
        logger.exception("Erreur update_syndic_sirene_data pour SIREN %s", siren)


def get_syndic_ref(siren):
    """Lecture d'un syndic depuis le référentiel par SIREN."""
    if not siren:
        return None
    client = get_bigquery_client()
    safe = siren.replace("'", "\\'")
    try:
        df = client.query(
            f"SELECT * FROM `{SYNDICS_TABLE}` WHERE siren = '{safe}' LIMIT 1"
        ).to_dataframe()
        if df.empty:
            return None
        return df.iloc[0].to_dict()
    except Exception:
        logger.exception("Erreur get_syndic_ref")
        return None


def get_syndic_ref_by_name(raison_sociale):
    """Recherche un syndic dans le référentiel par raison sociale (match exact insensible à la casse)."""
    if not raison_sociale:
        return None
    client = get_bigquery_client()
    safe = raison_sociale.replace("'", "\\'")
    try:
        df = client.query(
            f"SELECT * FROM `{SYNDICS_TABLE}` WHERE UPPER(raison_sociale) = UPPER('{safe}') LIMIT 1"
        ).to_dataframe()
        if df.empty:
            return None
        return df.iloc[0].to_dict()
    except Exception:
        logger.exception("Erreur get_syndic_ref_by_name")
        return None


def count_total_syndics():
    """Compte le nombre total de syndics dans le référentiel."""
    client = get_bigquery_client()
    try:
        df = client.query(f"SELECT COUNT(*) as cnt FROM `{SYNDICS_TABLE}`").to_dataframe()
        return int(df.iloc[0]["cnt"]) if not df.empty else 0
    except Exception:
        logger.exception("Erreur count_total_syndics")
        return 0


def count_enriched_syndics():
    """Compte les syndics enrichis SIRENE."""
    client = get_bigquery_client()
    try:
        df = client.query(
            f"SELECT COUNT(*) as cnt FROM `{SYNDICS_TABLE}` WHERE sirene_enriched_at IS NOT NULL"
        ).to_dataframe()
        return int(df.iloc[0]["cnt"]) if not df.empty else 0
    except Exception:
        logger.exception("Erreur count_enriched_syndics")
        return 0


def fetch_syndics_table(limit=100, offset=0, filtre=None):
    """
    Lecture paginée de la table syndics pour l'affichage admin.
    filtre: 'enrichi', 'non_enrichi', ou None (tous)
    """
    client = get_bigquery_client()
    where = "WHERE TRUE"
    if filtre == "enrichi":
        where = "WHERE sirene_enriched_at IS NOT NULL"
    elif filtre == "non_enrichi":
        where = "WHERE sirene_enriched_at IS NULL"

    try:
        df = client.query(f"""
            SELECT
                raison_sociale, siren, siret_principal, nb_copros, total_lots,
                total_lots_habitation, departements, denomination_officielle,
                code_ape, libelle_ape, tranche_effectifs, etat_administratif,
                commune_siege, sirene_enriched_at
            FROM `{SYNDICS_TABLE}`
            {where}
            ORDER BY nb_copros DESC
            LIMIT {int(limit)} OFFSET {int(offset)}
        """).to_dataframe()
        return df
    except Exception:
        logger.exception("Erreur fetch_syndics_table")
        return pd.DataFrame()
