import streamlit as st
import pandas as pd
import pydeck as pdk
from core.data_manager import fetch_aggregated_syndics, fetch_data_by_syndic
import base64

# Page Configuration
st.set_page_config(
    page_title="CEE Hunter v1 - Prospecting Dashboard",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- SESSION STATE MANAGEMENT ---
if 'theme' not in st.session_state:
    st.session_state['theme'] = 'Dark'
if 'syndic_list' not in st.session_state:
    st.session_state['syndic_list'] = pd.DataFrame()
if 'selected_syndic_data' not in st.session_state:
    st.session_state['selected_syndic_data'] = pd.DataFrame()
if 'current_syndic_name' not in st.session_state:
    st.session_state['current_syndic_name'] = None

# --- THEME SELECTOR ---
st.sidebar.markdown("## 🎨 Apparence")
theme = st.sidebar.radio("Choisir le thème", ["Dark", "Light"], index=0 if st.session_state['theme'] == 'Dark' else 1, label_visibility="collapsed")
if theme != st.session_state['theme']:
    st.session_state['theme'] = theme
    st.rerun()

# --- PREMIUM CSS STYLING ---
theme_config = {
    "Dark": {
        "bg_color": "#0E1117",
        "sidebar_bg": "#161B22",
        "card_bg": "#1E232F",
        "card_border": "#2D333F",
        "text_color": "#F3F4F6",
        "sub_text": "#9CA3AF",
        "sep_color": "#262730",
        "btn_text": "#FFFFFF"
    },
    "Light": {
        "bg_color": "#F8FAFC",
        "sidebar_bg": "#FFFFFF",
        "card_bg": "#FFFFFF",
        "card_border": "#E2E8F0",
        "text_color": "#1E293B",
        "sub_text": "#64748B",
        "sep_color": "#E2E8F0",
        "btn_text": "#1E293B"
    }
}

c = theme_config[st.session_state['theme']]

st.markdown(f"""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600&display=swap');
        html, body, [class*="css"] {{ font-family: 'Inter', sans-serif; }}
        .stApp {{ background-color: {c['bg_color']}; color: {c['text_color']}; }}
        [data-testid="stSidebar"] {{ background-color: {c['sidebar_bg']}; border-right: 1px solid {c['sep_color']}; }}
        [data-testid="stMetric"] {{ background-color: {c['card_bg']}; padding: 15px 20px; border-radius: 12px; border: 1px solid {c['card_border']}; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }}
        [data-testid="stMetricLabel"] {{ color: {c['sub_text']}; font-size: 0.9rem; }}
        [data-testid="stMetricValue"] {{ color: {c['text_color']}; font-weight: 600; }}
        h1, h2, h3, h4, h5, h6 {{ color: {c['text_color']}; font-weight: 600; }}
        .stMarkdown {{ color: {c['text_color']}; }}
        div.stButton > button {{ width: 100%; border-radius: 6px; font-weight: 600; padding: 0.5rem 1rem; }}
        /* Dataframe styling adjustment for theme */
        [data-testid="stDataFrame"] {{ border: 1px solid {c['card_border']}; border-radius: 8px; }}
    </style>
    """, unsafe_allow_html=True)

# --- HEADER ---
col_logo, col_title = st.columns([1, 6])
with col_title:
    st.title("🎯 CEE Hunter v1")
    st.markdown("POWERED BY **ANTIGRAVITY** | *Lead Generation Intelligence*")
st.markdown("---")

# --- STEP 1: GLOBAL FILTERS (SIDEBAR) ---
st.sidebar.markdown("## 1. Critères de Recherche")

# Climate Zone
selected_zones = st.sidebar.multiselect(
    "🌍 Zone Climatique",
    options=["H1", "H2", "H3"],
    default=["H1"]
)

# Habitation Lots
selected_lots = st.sidebar.slider(
    "🏘️ Lots d'habitation (Min/Max)",
    min_value=0,
    max_value=1000,
    value=(20, 500)
)

# Construction Period
selected_periods = st.sidebar.multiselect(
    "🏗️ Période de construction",
    options=['Avant 1949', '1949-1974', '1975-1993', '1994-2000', '2001-2010', 'Après 2011'],
    default=['Avant 1949', '1949-1974', '1975-1993', '1994-2000', '2001-2010', 'Après 2011']
)

# Exclusions
exclude_big = st.sidebar.checkbox("🚫 Exclure Gros Syndics & Non-Valides", value=True, help="Exclut Foncia, Lamy, Nexity, Citya, et les données 'Non partagées'.")

# QPV Filter
qpv_filter = st.sidebar.checkbox("🏠 Uniquement QPV", value=False, help="Ne montrer que les copropriétés en Quartier Prioritaire de la Ville.")

st.sidebar.markdown("---")


# --- STEP 2: SEARCH & AGGREGATE ---
st.sidebar.markdown("## 2. Lancer la Recherche")
if st.sidebar.button("🔍 Rechercher les Syndics", type="primary"):
    with st.spinner("Analyse de la base BigQuery (600k+ lignes)..."):
        st.session_state['syndic_list'] = fetch_aggregated_syndics(
            climate_zones=selected_zones,
            min_lots=selected_lots[0],
            max_lots=selected_lots[1],
            periods=selected_periods,
            exclude_big_syndics=exclude_big,
            qpv_only=qpv_filter
        )
        # Reset detail view on new search
        st.session_state['selected_syndic_data'] = pd.DataFrame()
        st.session_state['current_syndic_name'] = None

# Display Aggregated Results
if not st.session_state['syndic_list'].empty:
    df_agg = st.session_state['syndic_list']
    
    # KPIs Global to Selection
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Syndics Trouvés", f"{len(df_agg):,}".replace(",", " "))
    with col2:
        st.metric("Total Copropriétés", f"{df_agg['nb_copros'].sum():,}".replace(",", " "))
    with col3:
        st.metric("Total Lots (Est.)", f"{df_agg['total_lots'].sum():,}".replace(",", " "))

    st.markdown("### 🏆 Top Syndics Correspondants")
    st.info("Sélectionnez un syndic ci-dessous pour voir le détail et la carte.")
    
    # Renaming for display
    df_display = df_agg[[
        "Syndic", "Siret", "nb_copros", "total_lots"
    ]].rename(columns={
        "nb_copros": "Copropriétés", 
        "total_lots": "Total Lots"
    })

    # Interactive Table with Selection
    event = st.dataframe(
        df_display,
        use_container_width=True,
        column_config={
            "Syndic": st.column_config.TextColumn("Syndic Principal", width="medium"),
            "Siret": st.column_config.TextColumn("SIRET", width="small"),
            "Copropriétés": st.column_config.NumberColumn("NB Copros", format="%d"),
            "Total Lots": st.column_config.ProgressColumn("Volume Lots", format="%d", min_value=0, max_value=int(df_agg['total_lots'].max())),
        },
        selection_mode="single-row",
        on_select="rerun",  
        hide_index=True,
        height=400
    )
    
    # --- STEP 3: DRILL DOWN (DETAIL) ---
    if len(event.selection['rows']) > 0:
        selected_index = event.selection['rows'][0]
        syndic_row = df_agg.iloc[selected_index]
        syndic_name = syndic_row['Syndic']
        syndic_siret = syndic_row['Siret']
        
        # Pappers Enrichment for the SELECTED syndic ONLY
        from core.pappers_connector import get_syndic_info
        with st.spinner(f"Enrichissement Pappers pour {syndic_name}..."):
            pappers_info = get_syndic_info(syndic_siret)

        # Fetch details if not already loaded for this syndic
        if st.session_state['current_syndic_name'] != syndic_name:
            with st.spinner(f"Chargement des copropriétés pour {syndic_name}..."):
                st.session_state['selected_syndic_data'] = fetch_data_by_syndic(
                    syndic_name, 
                    selected_zones, 
                    selected_lots[0], 
                    selected_lots[1],
                    periods=selected_periods,
                    exclude_big_syndics=exclude_big,
                    qpv_only=qpv_filter
                )
                st.session_state['current_syndic_name'] = syndic_name
        
        # Display Detail View
        detail_data = st.session_state['selected_syndic_data']

        if not detail_data.empty:
            st.markdown("---")
            st.header(f"🏢 Détail : {syndic_name}")
            
            # Pappers Info Header
            if pappers_info:
                with st.expander("📊 Informations Légales & Contact Pappers", expanded=True):
                    # Top Row: Dirigeant, CA, Siret
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        dirigeant = f"{pappers_info.get('prenom_dirigeant', '')} {pappers_info.get('nom_dirigeant', '')}".strip()
                        st.subheader("👤 Dirigeant")
                        st.write(f"{dirigeant or 'Non renseigné'}")
                    with c2:
                        ca = pappers_info.get('ca_annuel', 0)
                        ca_str = f"{ca/1000000:.1f} M€" if ca and ca > 0 else "N/A"
                        st.subheader("💰 Chiffre d'Affaires")
                        st.write(f"{ca_str}")
                    with c3:
                        st.subheader("🔢 SIRET")
                        st.write(f"`{syndic_siret}`")
                    
                    st.divider()
                    
                    # Bottom Row: Contact Info
                    c4, c5, c6 = st.columns(3)
                    with c4:
                        site = pappers_info.get('sites_internet', '')
                        st.write(f"**🌐 Site :** {site or 'N/A'}")
                    with c5:
                        tel = pappers_info.get('telephone', '')
                        st.write(f"**📞 Tel :** {tel or 'N/A'}")
                    with c6:
                        email = pappers_info.get('email', '')
                        st.write(f"**📧 Email :** {email or 'N/A'}")
                    
                    # Additional: LinkedIn & Category
                    c7, c8 = st.columns(2)
                    with c7:
                        linkedin = pappers_info.get('lien_linkedin', '')
                        st.write(f"**🔗 LinkedIn :** {linkedin or 'N/A'}")
                    with c8:
                        cat = pappers_info.get('categorie_entreprise', '')
                        st.write(f"**📂 Catégorie :** {cat or 'N/A'}")

            st.markdown("---")
            
            # --- ENRICHISSEMENT APOLLO ---
            from core.enrichment_manager import EnrichmentManager
            import json
            
            enricher = EnrichmentManager()
            
            # Add state key for enrichment data to persist across reruns
            enrich_key = f"enrich_data_{syndic_siret}"
            
            # Check for existing data in session or cache
            if enrich_key not in st.session_state:
                cached_enrich = enricher.get_cached_data(syndic_siret)
                if cached_enrich:
                    st.session_state[enrich_key] = cached_enrich
            
            st.markdown("### 🕵️‍♂️ Intelligence & Prospection (Apollo.io)")
            
            col_enrich_btn, col_enrich_status = st.columns([1, 2])
            
            data_enrich = st.session_state.get(enrich_key)
            
            with col_enrich_btn:
                if st.button("🚀 Lancer l'Enrichissement", key=f"btn_enrich_{syndic_siret}"):
                    with st.spinner("Recherche Web & Apollo en cours..."):
                        # We use the city from Pappers Address if available (Adresse de reference) from the first row of detail data
                        city_ref = detail_data.iloc[0]['commune'] if not detail_data.empty else ""
                        
                        fresh_data = enricher.enrich_syndic(syndic_siret, syndic_name, city_ref, pappers_data=pappers_info)
                        if fresh_data:
                            st.session_state[enrich_key] = fresh_data
                            st.success("Enrichissement terminé !")
                            st.rerun()
                        else:
                            st.error("Aucune correspondance trouvée.")

            # Display Results if available
            if data_enrich:
                # 1. Domain Validation
                domain = data_enrich.get('domain')
                score = data_enrich.get('confidence_score', 0)
                
                if domain:
                    st.markdown(f"**✅ Site Web Validé :** [{domain}](https://{domain}) *(Confiance: {int(score)}%)*")
                else:
                    st.warning("Domaine non identifié avec certitude.")

                # 2. Key Contacts
                contacts = data_enrich.get('contacts_json')
                # Handle stringified json from BQ
                if isinstance(contacts, str):
                    try:
                        contacts = json.loads(contacts)
                    except:
                        contacts = []
                
                if contacts:
                    st.info(f"{len(contacts)} contact(s) clé(s) identifié(s)")
                    
                    for idx, ct in enumerate(contacts):
                        with st.container(border=True):
                            c_av, c_info, c_action = st.columns([1, 4, 3]) # Slightly wider action col
                            with c_av:
                                if ct.get('photo_url'):
                                    st.image(ct.get('photo_url'), width=50)
                                else:
                                    st.write("👤")
                            
                            with c_info:
                                name_ct = f"{ct.get('first_name', '')} {ct.get('last_name', '')}"
                                st.markdown(f"**{name_ct}**")
                                st.caption(f"{ct.get('title') or 'Poste inconnu'}")
                                if ct.get('email'):
                                    st.write(f"📧 `{ct.get('email')}`")
                                if ct.get('linkedin_url'):
                                    st.markdown(f"[LinkedIn]({ct.get('linkedin_url')})")

                            with c_action:
                                # Use index to ensure unique key even if email is missing or duplicate
                                btn_id = f"ice_{syndic_siret}_{idx}"
                                if st.button("🧊 Icebreaker", key=btn_id):
                                    # Simple Logic for now
                                    first_name = ct.get('first_name', 'Bonjour')
                                    syndic_short = syndic_name.split(' ')[0].title()
                                    
                                    msg = f"""
                                    **Objet : Synergie avec {syndic_short}**
                                    
                                    Bonjour {first_name},
                                    
                                    Je vois que vous gérez un parc important de copropriétés en zone H1.
                                    
                                    En tant que partenaire CEE, nous accompagnons {syndic_short} sur la valorisation des travaux...
                                    """
                                    st.text_area("Email généré", value=msg, height=200)

                else:
                    st.write("Aucun contact pertinent trouvé via Apollo.")
            
            st.markdown("---")

            # Expanded Columns for Detail View
            display_cols = [
                'nom_d_usage_de_la_copropriete', 
                'adresse_de_reference', 
                'code_postal_adresse_de_reference', 
                'commune', 
                'nombre_total_de_lots', 
                'nombre_de_lots_a_usage_d_habitation', 
                'periode_de_construction',
                'climate_zone',
                'in_qpv'
            ]
            
            st.dataframe(
                detail_data[display_cols],
                use_container_width=True,
                column_config={
                    "nom_d_usage_de_la_copropriete": st.column_config.TextColumn("Copropriété", width="large"),
                    "adresse_de_reference": st.column_config.TextColumn("Adresse", width="medium"),
                    "code_postal_adresse_de_reference": st.column_config.TextColumn("CP", width="small"),
                    "commune": st.column_config.TextColumn("Ville", width="small"),
                    "nombre_total_de_lots": st.column_config.NumberColumn("Total Lots", format="%d"),
                    "nombre_de_lots_a_usage_d_habitation": st.column_config.NumberColumn("Lots Hab.", format="%d"),
                    "periode_de_construction": st.column_config.TextColumn("Période Constr.", width="medium"),
                    "climate_zone": st.column_config.TextColumn("Zone", width="small"),
                    "in_qpv": st.column_config.TextColumn("🏠 QPV", width="small"),
                },
                hide_index=True,
                height=600
            )
        else:
            st.warning("Aucune géolocalisation disponible pour ce syndic.")
            
else:
    st.info("👈 Configurez les filtres à gauche et cliquez sur 'Rechercher' pour commencer.")
