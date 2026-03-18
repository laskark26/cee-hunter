"""
Page Administration — Référentiel Syndics & Enrichissement SIRENE.
"""

import time
import streamlit as st

from core.log_config import setup_logging
setup_logging()

from core.data_manager import (
    init_syndics_table, populate_syndics_from_copro,
    get_syndics_to_enrich, update_syndic_sirene_data,
    count_total_syndics, count_enriched_syndics,
    fetch_syndics_table,
)
from core.sirene_connector import init_cache_table as init_sirene_cache, enrich_siren
from styles import generate_css, PALETTE

# ── Page Config ──────────────────────────────────────────────

st.set_page_config(
    page_title="Admin — CEE Hunter PRO",
    page_icon="🔧",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CSS ──────────────────────────────────────────────────────

st.markdown(f"<style>{generate_css('Light')}</style>", unsafe_allow_html=True)

# ── Auth ─────────────────────────────────────────────────────

def check_password():
    def password_entered():
        if "password" not in st.session_state:
            return
        if st.session_state["password"] == st.secrets.get("APP_PASSWORD", "antigravity2026"):
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("Mot de passe requis", type="password", on_change=password_entered, key="password")
        st.info("L'accès à cet outil est restreint.")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("Mot de passe requis", type="password", on_change=password_entered, key="password")
        st.error("Mot de passe incorrect")
        return False
    return True

if not check_password():
    st.stop()

# ── Init tables ──────────────────────────────────────────────

init_syndics_table()
init_sirene_cache()

# ── Header ───────────────────────────────────────────────────

st.markdown(
    f"""
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:24px;">
        <span style="font-size:32px;">🔧</span>
        <div>
            <h1 style="margin:0;font-size:28px;font-weight:700;">Administration</h1>
            <p style="margin:0;color:#6B7280;font-size:14px;">Référentiel Syndics & Enrichissement SIRENE INSEE</p>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ── KPIs ─────────────────────────────────────────────────────

total = count_total_syndics()
enriched = count_enriched_syndics()
taux = round(enriched / total * 100, 1) if total > 0 else 0

col1, col2, col3 = st.columns(3)
col1.metric("Total syndics", f"{total:,}".replace(",", " "))
col2.metric("Enrichis SIRENE", f"{enriched:,}".replace(",", " "))
col3.metric("Taux d'enrichissement", f"{taux}%")

st.divider()

# ── Section 1 : Actualiser le référentiel ────────────────────

st.subheader("1. Actualiser le référentiel depuis copro")
st.caption("Agrège la table copro (~600k lignes) par SIREN pour créer/mettre à jour le référentiel syndics dédupliqué.")

if st.button("Actualiser le référentiel", type="primary", use_container_width=False):
    with st.spinner("Agrégation copro → syndics en cours..."):
        n = populate_syndics_from_copro()
    if n > 0:
        st.success(f"{n:,} syndics référencés avec succès.".replace(",", " "))
        st.rerun()
    else:
        st.error("Erreur lors de l'agrégation. Vérifiez les logs.")

st.divider()

# ── Section 2 : Enrichissement SIRENE ────────────────────────

st.subheader("2. Enrichissement SIRENE INSEE")
st.caption("Appelle l'API SIRENE pour chaque syndic non enrichi. Rate limit : 30 req/min → ~2s entre chaque appel.")

col_batch, col_btn = st.columns([1, 2])
with col_batch:
    batch_size = st.number_input(
        "Taille du batch",
        min_value=1,
        max_value=500,
        value=50,
        step=10,
        help="Nombre de syndics à enrichir en une fois.",
    )

non_enrichis = total - enriched
st.info(f"{non_enrichis:,} syndics restants à enrichir.".replace(",", " "))

if st.button("Lancer l'enrichissement SIRENE", type="primary", use_container_width=False):
    syndics = get_syndics_to_enrich(limit=batch_size)
    if not syndics:
        st.warning("Aucun syndic à enrichir. Le référentiel est complet ou vide.")
    else:
        progress = st.progress(0, text="Démarrage...")
        status_container = st.empty()
        errors = 0
        enriched_count = 0

        for i, (siren, siret) in enumerate(syndics):
            progress.progress(
                (i + 1) / len(syndics),
                text=f"[{i + 1}/{len(syndics)}] SIREN {siren}",
            )

            data = enrich_siren(siren, siret=siret)
            if data:
                update_syndic_sirene_data(siren, data)
                enriched_count += 1
            else:
                errors += 1

            # Rate limit : 30 req/min ≈ 2s entre chaque appel
            # On fait 2 appels par syndic (siren + siret), donc 4s
            time.sleep(2)

        progress.progress(1.0, text="Terminé !")
        st.success(
            f"Enrichissement terminé : {enriched_count} enrichis, {errors} erreurs sur {len(syndics)} syndics."
        )
        st.rerun()

st.divider()

# ── Section 3 : Aperçu du référentiel ────────────────────────

st.subheader("3. Aperçu du référentiel")

filtre = st.radio(
    "Filtre",
    ["Tous", "Enrichis", "Non enrichis"],
    horizontal=True,
    label_visibility="collapsed",
)
filtre_map = {"Tous": None, "Enrichis": "enrichi", "Non enrichis": "non_enrichi"}

df = fetch_syndics_table(limit=200, filtre=filtre_map[filtre])

if df.empty:
    st.info("Aucun syndic dans le référentiel. Cliquez sur 'Actualiser le référentiel' pour commencer.")
else:
    # Renommer les colonnes pour l'affichage
    display_cols = {
        "raison_sociale": "Raison sociale",
        "siren": "SIREN",
        "nb_copros": "Copros",
        "total_lots": "Lots total",
        "denomination_officielle": "Dénomination INSEE",
        "code_ape": "Code APE",
        "libelle_ape": "Activité",
        "tranche_effectifs": "Effectifs",
        "etat_administratif": "État",
        "commune_siege": "Commune siège",
        "sirene_enriched_at": "Enrichi le",
    }
    # Ne garder que les colonnes existantes
    available = [c for c in display_cols if c in df.columns]
    df_display = df[available].rename(columns=display_cols)

    st.dataframe(
        df_display,
        use_container_width=True,
        hide_index=True,
        height=500,
    )
    st.caption(f"Affichage limité à 200 lignes. Total dans le filtre : voir KPIs ci-dessus.")
