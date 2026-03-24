"""
Connecteur API SIRENE INSEE — Enrichissement des données légales des syndics.

Utilise l'API SIRENE V3.11 de l'INSEE avec authentification par clé API.
Cache-aside sur BigQuery (rnic.cache_sirene).
"""

import json
import logging
import os
from datetime import datetime

import requests
import streamlit as st
from google.cloud import bigquery

# ── Configuration ────────────────────────────────────────────
PROJECT_ID = "gen-lang-client-0045947309"
CACHE_TABLE = "gen-lang-client-0045947309.rnic.cache_sirene"
INSEE_SIRENE_BASE = "https://api.insee.fr/api-sirene/3.11"

logger = logging.getLogger(__name__)


# ── Clients & credentials ────────────────────────────────────

def _get_bq_client():
    if "GOOGLE_SERVICE_ACCOUNT_JSON" in st.secrets:
        info = dict(st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"])
        return bigquery.Client.from_service_account_info(info)
    return bigquery.Client(project=PROJECT_ID)


def _get_insee_api_key():
    """Retourne la clé API INSEE depuis secrets ou env."""
    return st.secrets.get("INSEE_API_KEY", os.environ.get("INSEE_API_KEY", ""))


# ── BigQuery cache ───────────────────────────────────────────

def init_cache_table():
    """Crée la table cache_sirene si elle n'existe pas."""
    client = _get_bq_client()
    try:
        client.query(f"""
            CREATE TABLE IF NOT EXISTS `{CACHE_TABLE}` (
                siren STRING,
                siret_siege STRING,
                denomination STRING,
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
                raw_json STRING,
                fetched_at TIMESTAMP
            )
        """).result()
    except Exception:
        logger.exception("Erreur création table cache_sirene")


def get_cached_sirene(siren):
    """Lookup cache BQ par SIREN. Retourne dict ou None."""
    if not siren:
        return None
    client = _get_bq_client()
    try:
        safe = siren.replace("'", "\\'")
        df = client.query(
            f"SELECT * FROM `{CACHE_TABLE}` WHERE siren = '{safe}' LIMIT 1"
        ).to_dataframe()
        if df.empty:
            return None
        row = df.iloc[0].to_dict()
        # Convertir NaN/NaT en None
        return {k: (None if str(v) in ("NaT", "nan", "") else v) for k, v in row.items()}
    except Exception:
        logger.exception("Erreur lecture cache SIRENE")
        return None


def _save_to_cache(data):
    """Persiste une entrée dans cache_sirene (upsert via DELETE + INSERT)."""
    if not data or not data.get("siren"):
        return
    client = _get_bq_client()
    try:
        safe_siren = data["siren"].replace("'", "\\'")
        client.query(
            f"DELETE FROM `{CACHE_TABLE}` WHERE siren = '{safe_siren}'"
        ).result()

        row = {
            "siren": data.get("siren", ""),
            "siret_siege": data.get("siret_siege", ""),
            "denomination": data.get("denomination", ""),
            "sigle": data.get("sigle", ""),
            "code_ape": data.get("code_ape", ""),
            "libelle_ape": data.get("libelle_ape", ""),
            "categorie_juridique": data.get("categorie_juridique", ""),
            "tranche_effectifs": data.get("tranche_effectifs", ""),
            "date_creation": data.get("date_creation", ""),
            "etat_administratif": data.get("etat_administratif", ""),
            "adresse_siege": data.get("adresse_siege", ""),
            "code_postal_siege": data.get("code_postal_siege", ""),
            "commune_siege": data.get("commune_siege", ""),
            "raw_json": data.get("raw_json", ""),
            "fetched_at": datetime.utcnow().isoformat(),
        }
        errors = client.insert_rows_json(CACHE_TABLE, [row])
        if errors:
            logger.warning("Erreurs insert cache SIRENE: %s", errors)
    except Exception:
        logger.exception("Erreur sauvegarde cache SIRENE")


# ── API calls ────────────────────────────────────────────────

def _make_insee_request(url):
    """Requête GET authentifiée vers l'API INSEE via clé API."""
    api_key = _get_insee_api_key()
    if not api_key:
        logger.warning("Clé API INSEE manquante")
        return None

    resp = requests.get(
        url,
        headers={
            "X-INSEE-Api-Key-Integration": api_key,
            "Accept": "application/json",
        },
        timeout=10,
    )
    return resp


def _decode_tranche_effectifs(code):
    """Convertit le code tranche effectifs INSEE en libellé lisible."""
    tranches = {
        "NN": "Non employeur",
        "00": "0 salarié",
        "01": "1 ou 2 salariés",
        "02": "3 à 5 salariés",
        "03": "6 à 9 salariés",
        "11": "10 à 19 salariés",
        "12": "20 à 49 salariés",
        "21": "50 à 99 salariés",
        "22": "100 à 199 salariés",
        "31": "200 à 249 salariés",
        "32": "250 à 499 salariés",
        "41": "500 à 999 salariés",
        "42": "1 000 à 1 999 salariés",
        "51": "2 000 à 4 999 salariés",
        "52": "5 000 à 9 999 salariés",
        "53": "10 000 salariés et plus",
    }
    return tranches.get(str(code), str(code) if code else "")


def fetch_sirene_api(siren):
    """
    Appelle GET /siren/{siren} pour les infos de l'unité légale.
    Retourne un dict parsé ou None.
    """
    try:
        url = f"{INSEE_SIRENE_BASE}/siren/{siren}"
        resp = _make_insee_request(url)
        if resp is None:
            return None

        if resp.status_code == 200:
            data = resp.json()
            ul = data.get("uniteLegale", {})

            # La dénomination peut être dans les periodes (historique)
            denomination = ul.get("denominationUniteLegale", "")
            if not denomination:
                periodes = ul.get("periodesUniteLegale", [])
                if periodes:
                    denomination = periodes[0].get("denominationUniteLegale", "")

            tranche_code = ul.get("trancheEffectifsUniteLegale", "")

            return {
                "siren": ul.get("siren", siren),
                "denomination": denomination,
                "sigle": ul.get("sigleUniteLegale", "") or "",
                "code_ape": ul.get("activitePrincipaleUniteLegale", "") or "",
                "categorie_juridique": ul.get("categorieJuridiqueUniteLegale", "") or "",
                "tranche_effectifs": _decode_tranche_effectifs(tranche_code),
                "date_creation": ul.get("dateCreationUniteLegale", "") or "",
                "etat_administratif": ul.get("etatAdministratifUniteLegale", "") or "",
                "raw_json": json.dumps(data, ensure_ascii=False)[:50000],
            }

        elif resp.status_code == 404:
            logger.info("SIREN %s non trouvé dans SIRENE", siren)
            return None
        elif resp.status_code == 429:
            logger.warning("Rate limit INSEE atteint pour SIREN %s", siren)
            return None
        else:
            logger.error("Erreur API SIRENE /siren: %s - %s", resp.status_code, resp.text[:300])
            return None

    except Exception:
        logger.exception("Erreur appel API SIRENE /siren/%s", siren)
        return None


def fetch_siret_api(siret):
    """
    Appelle GET /siret/{siret} pour l'adresse de l'établissement.
    Retourne un dict avec les champs adresse ou None.
    """
    try:
        url = f"{INSEE_SIRENE_BASE}/siret/{siret}"
        resp = _make_insee_request(url)
        if resp is None:
            return None

        if resp.status_code == 200:
            data = resp.json()
            etab = data.get("etablissement", {})
            adresse = etab.get("adresseEtablissement", {})

            # Construire l'adresse complète
            parts = [
                adresse.get("numeroVoieEtablissement", "") or "",
                adresse.get("typeVoieEtablissement", "") or "",
                adresse.get("libelleVoieEtablissement", "") or "",
            ]
            adresse_str = " ".join(p for p in parts if p).strip()

            return {
                "siret_siege": siret,
                "adresse_siege": adresse_str,
                "code_postal_siege": adresse.get("codePostalEtablissement", "") or "",
                "commune_siege": adresse.get("libelleCommuneEtablissement", "") or "",
            }

        elif resp.status_code == 404:
            logger.info("SIRET %s non trouvé dans SIRENE", siret)
        elif resp.status_code == 429:
            logger.warning("Rate limit INSEE atteint pour SIRET %s", siret)
        else:
            logger.error("Erreur API SIRENE /siret: %s - %s", resp.status_code, resp.text[:300])

    except Exception:
        logger.exception("Erreur appel API SIRENE /siret/%s", siret)

    return None


# ── Libellé APE ──────────────────────────────────────────────

def _get_libelle_ape(code_ape):
    """Retourne le libellé APE pour les codes courants dans l'immobilier."""
    ape_labels = {
        "68.32A": "Administration d'immeubles et autres biens immobiliers",
        "68.32B": "Supports juridiques de gestion de patrimoine immobilier",
        "68.31Z": "Agences immobilières",
        "68.20A": "Location de logements",
        "68.20B": "Location de terrains et d'autres biens immobiliers",
        "68.10Z": "Activités des marchands de biens immobiliers",
    }
    if not code_ape:
        return ""
    # Normaliser le code (parfois sans le point)
    normalized = code_ape.replace(".", "")
    for key, label in ape_labels.items():
        if key.replace(".", "") == normalized:
            return label
    return ""


# ── Entry point ──────────────────────────────────────────────

def enrich_siren(siren, siret=None):
    """
    Point d'entrée principal — cache-aside :
    1. Vérifie le cache BQ
    2. Appelle l'API /siren/{siren}
    3. Appelle l'API /siret/{siret} pour l'adresse du siège
    4. Sauvegarde en cache
    5. Retourne le dict enrichi

    Args:
        siren: Le numéro SIREN (9 chiffres)
        siret: Le SIRET principal (optionnel, pour récupérer l'adresse)

    Returns:
        dict avec les données SIRENE ou None
    """
    if not siren or len(siren.strip()) < 9:
        return None

    siren = siren.strip()[:9]

    # 1. Cache
    cached = get_cached_sirene(siren)
    if cached:
        return cached

    # 2. API /siren
    result = fetch_sirene_api(siren)
    if not result:
        return None

    # 3. Libellé APE
    result["libelle_ape"] = _get_libelle_ape(result.get("code_ape", ""))

    # 4. API /siret pour l'adresse du siège
    if siret:
        adresse_data = fetch_siret_api(siret)
        if adresse_data:
            result.update(adresse_data)

    # 5. Sauvegarder en cache
    _save_to_cache(result)

    return result
