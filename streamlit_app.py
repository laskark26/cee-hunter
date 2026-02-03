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
# --- SECURITY: LOGIN ---
def check_password():
    """Returns `True` if the user had the correct password."""
    def password_entered():
        """Checks whether a password entered by the user is correct."""
        if st.session_state["password"] == st.secrets.get("APP_PASSWORD", "antigravity2026"):
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # don't store password
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        # First run, show input for password.
        st.text_input(
            "Mot de passe requis", type="password", on_change=password_entered, key="password"
        )
        st.info("💡 L'accès à cet outil est restreint.")
        return False
    elif not st.session_state["password_correct"]:
        # Password incorrect, show input + error.
        st.text_input(
            "Mot de passe requis", type="password", on_change=password_entered, key="password"
        )
        st.error("😕 Mot de passe incorrect")
        return False
    else:
        # Password correct.
        return True

if not check_password():
    st.stop()  # Do not run the rest of the app

# --- SESSION STATE MANAGEMENT ---
if 'theme' not in st.session_state:
    st.session_state['theme'] = 'Dark'
if 'current_step' not in st.session_state:
    st.session_state['current_step'] = 1
if 'syndic_list' not in st.session_state:
    st.session_state['syndic_list'] = pd.DataFrame()
if 'selected_syndic_data' not in st.session_state:
    st.session_state['selected_syndic_data'] = pd.DataFrame()
if 'current_syndic_name' not in st.session_state:
    st.session_state['current_syndic_name'] = None

# --- NAVIGATION HELPERS ---
def go_to_step(step_number):
    st.session_state['current_step'] = step_number
    st.rerun()

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
        "btn_text": "#FFFFFF",
        "accent": "#10B981"
    },
    "Light": {
        "bg_color": "#F8FAFC",
        "sidebar_bg": "#FFFFFF",
        "card_bg": "#FFFFFF",
        "card_border": "#E2E8F0",
        "text_color": "#1E293B",
        "sub_text": "#64748B",
        "sep_color": "#E2E8F0",
        "btn_text": "#1E293B",
        "accent": "#059669"
    }
}

c = theme_config[st.session_state['theme']]

st.markdown(f"""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;800&display=swap');
        html, body, [class*="css"] {{ font-family: 'Inter', sans-serif; }}
        .stApp {{ background-color: {c['bg_color']}; color: {c['text_color']}; }}
        [data-testid="stSidebar"] {{ background-color: {c['sidebar_bg']}; border-right: 1px solid {c['sep_color']}; }}
        
        /* Premium Card Style */
        .premium-card {{
            background-color: {c['card_bg']};
            padding: 2rem;
            border-radius: 16px;
            border: 1px solid {c['card_border']};
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
            margin-bottom: 1.5rem;
        }}
        
        /* Metric Styling */
        [data-testid="stMetric"] {{ background-color: {c['card_bg']}; padding: 15px 20px; border-radius: 12px; border: 1px solid {c['card_border']}; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }}
        [data-testid="stMetricLabel"] {{ color: {c['sub_text']}; font-size: 0.9rem; }}
        [data-testid="stMetricValue"] {{ color: {c['text_color']}; font-weight: 600; }}
        
        h1, h2, h3, h4, h5, h6 {{ color: {c['text_color']}; font-weight: 800; tracking: -0.025em; }}
        .stMarkdown {{ color: {c['text_color']}; }}
        
        /* Stepper UI */
        .step-indicator {{
            display: flex;
            justify-content: space-between;
            margin-bottom: 3rem;
            max-width: 600px;
            margin-left: auto;
            margin-right: auto;
        }}
        .step-item {{
            text-align: center;
            flex: 1;
            position: relative;
        }}
        .step-number {{
            width: 32px;
            height: 32px;
            line-height: 32px;
            border-radius: 50%;
            background: {c['card_border']};
            color: {c['sub_text']};
            display: inline-block;
            margin-bottom: 8px;
            font-weight: 600;
        }}
        .step-active .step-number {{
            background: {c['accent']};
            color: white;
        }}
        .step-label {{
            font-size: 0.8rem;
            color: {c['sub_text']};
            text-transform: uppercase;
            letter-spacing: 0.1em;
            font-weight: 600;
        }}
        .step-active .step-label {{
            color: {c['text_color']};
        }}
    </style>
    """, unsafe_allow_html=True)

# --- ONBOARDING BANNER ---
st.container().markdown(f"""
    <div style="text-align: center; padding: 2rem 0;">
        <h1 style="font-size: 3rem; margin-bottom: 0.5rem;">🎯 CEE Hunter</h1>
        <p style="color: {c['sub_text']}; font-size: 1.2rem; max-width: 800px; margin: 0 auto;">
            Trouvez les meilleurs syndics à contacter pour des projets de rénovation CEE en 4 étapes simples.
        </p>
    </div>
""", unsafe_allow_html=True)

# --- PROGRESS STEPPER ---
steps = ["Critères", "Résultats", "Intelligence", "Prospecter"]
step_cols = st.columns(len(steps))
st.markdown('<div class="step-indicator">', unsafe_allow_html=True)
cols = st.columns(len(steps))
for i, label in enumerate(steps):
    is_active = st.session_state['current_step'] >= (i + 1)
    status_class = "step-active" if is_active else ""
    with cols[i]:
        st.markdown(f"""
            <div class="step-item {status_class}">
                <div class="step-number">{i+1}</div>
                <div class="step-label">{label}</div>
            </div>
        """, unsafe_allow_html=True)
st.markdown("<br>", unsafe_allow_html=True)

# --- STEP 1: GUIDED CRITERIA ---
if st.session_state['current_step'] == 1:
    st.markdown("### 🥇 Étape 1 : Quels types d'immeubles cherchez-vous ?")
    
    with st.container(border=True):
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### 🌍 Zone Climatique")
            st.caption("Les zones H1 sont les plus froides et génèrent souvent plus de certificats CEE.")
            selected_zones = st.multiselect(
                "Sélectionnez les zones",
                options=["H1", "H2", "H3"],
                default=["H1"],
                label_visibility="collapsed"
            )
            
            st.markdown("#### 🏗️ Période de construction")
            st.caption("Les bâtiments construits avant 1975 sont les cibles prioritaires.")
            selected_periods = st.multiselect(
                "Sélectionnez les périodes",
                options=['Avant 1949', '1949-1974', '1975-1993', '1994-2000', '2001-2010', 'Après 2011'],
                default=['Avant 1949', '1949-1974'],
                label_visibility="collapsed"
            )

        with col2:
            st.markdown("#### 🏘️ Taille de la copropriété")
            st.caption("Nombre de lots d'habitation. Les copros de 20 à 200 lots sont idéales.")
            selected_lots = st.slider(
                "Nombre de lots",
                min_value=0,
                max_value=1000,
                value=(20, 500),
                label_visibility="collapsed"
            )
            
            st.markdown("#### 🏠 Options avancées")
            exclude_big = st.checkbox("🚫 Exclure les géants (Foncia, Nexity, etc.)", value=True)
            qpv_only = st.checkbox("📍 Uniquement Quartiers Prioritaires (QPV)", value=False)

    st.markdown("<br>", unsafe_allow_html=True)
    
    if st.button("🚀 Trouver les meilleurs syndics", type="primary", use_container_width=True):
        with st.spinner("Analyse du gisement en cours..."):
            st.session_state['syndic_list'] = fetch_aggregated_syndics(
                climate_zones=selected_zones,
                min_lots=selected_lots[0],
                max_lots=selected_lots[1],
                periods=selected_periods,
                exclude_big_syndics=exclude_big,
                qpv_only=qpv_only
            )
            # Store filters for reuse in step 2
            st.session_state['filters'] = {
                'zones': selected_zones,
                'lots': selected_lots,
                'periods': selected_periods,
                'exclude_big': exclude_big,
                'qpv': qpv_only
            }
            go_to_step(2)
# --- STEP 2: RESULTS TABLE ---
elif st.session_state['current_step'] == 2:
    st.markdown("### 🥈 Étape 2 : Voici les syndics correspondants")
    st.caption("Sélectionnez un syndic pour lancer l'enrichissement et voir les contacts.")
    
    if st.button("⬅️ Modifier les critères", key="back_to_1"):
        go_to_step(1)

    df_agg = st.session_state['syndic_list']
    
    if df_agg.empty:
        st.warning("⚠️ Aucun résultat trouvé. Essayez d'élargir vos critères (ex: inclure plus de périodes de construction).")
    else:
        # Mini KPIs
        k1, k2, k3 = st.columns(3)
        k1.metric("Syndics", f"{len(df_agg)}")
        k2.metric("Copropriétés", f"{int(df_agg['nb_copros'].sum())}")
        k3.metric("Total Lots", f"{int(df_agg['total_lots'].sum())}")
        
        # Table configuration
        df_display = df_agg[[
            "Syndic", "Siret", "nb_copros", "total_lots"
        ]].rename(columns={
            "nb_copros": "Copropriétés", 
            "total_lots": "Volume Lots"
        })

        event = st.dataframe(
            df_display,
            use_container_width=True,
            column_config={
                "Syndic": st.column_config.TextColumn("📋 Nom du Syndic", width="large"),
                "Siret": st.column_config.TextColumn("SIRET", width="small"),
                "Copropriétés": st.column_config.NumberColumn("🏢 Immeubles", format="%d"),
                "Volume Lots": st.column_config.ProgressColumn("🏠 Lots Totaux", format="%d", min_value=0, max_value=int(df_agg['total_lots'].max())),
            },
            selection_mode="single-row",
            on_select="rerun",  
            hide_index=True,
            height=500
        )
        
        if len(event.selection['rows']) > 0:
            selected_index = event.selection['rows'][0]
            selected_row = df_agg.iloc[selected_index]
            st.session_state['selected_syndic_row'] = selected_row
            go_to_step(3)

# --- STEP 3: SYNDIC DETAILS ---
elif st.session_state['current_step'] == 3:
    syndic_row = st.session_state.get('selected_syndic_row')
    if syndic_row is None:
        go_to_step(2)
        
    syndic_name = syndic_row['Syndic']
    syndic_siret = syndic_row['Siret']
    
    col_back, col_title_detail = st.columns([1, 5])
    with col_back:
        if st.button("⬅️ Retour", key="back_to_2"):
            go_to_step(2)
    with col_title_detail:
        st.markdown(f"### 🥉 Étape 3 : Intelligence sur {syndic_name}")

    # Pappers Enrichment
    from core.pappers_connector import get_syndic_info
    with st.spinner(f"Récupération des données légales pour {syndic_name}..."):
        pappers_info = get_syndic_info(syndic_siret)

    # Fetch buildings details if needed
    filters = st.session_state.get('filters', {})
    if st.session_state['current_syndic_name'] != syndic_name:
        with st.spinner(f"Chargement du parc immobilier..."):
            st.session_state['selected_syndic_data'] = fetch_data_by_syndic(
                syndic_name, 
                filters.get('zones', ['H1']), 
                filters.get('lots', (0, 1000))[0], 
                filters.get('lots', (0, 1000))[1],
                periods=filters.get('periods'),
                exclude_big_syndics=filters.get('exclude_big', True),
                qpv_only=filters.get('qpv', False)
            )
            st.session_state['current_syndic_name'] = syndic_name
        
    # --- PREMIUM CARDS LAYOUT ---
    tab_overview, tab_buildings = st.tabs(["📊 Intelligence & Contacts", "🏢 Parc Immobilier"])
    
    with tab_overview:
        col_legal, col_sales = st.columns(2)
        
        with col_legal:
            st.markdown(f"""
                <div class="premium-card">
                    <h4>🏢 Informations Légales</h4>
                    <p style="color: {c['sub_text']}; font-size: 0.9rem;">Données Pappers.fr</p>
                    <hr style="margin: 1rem 0; border-color: {c['sep_color']};">
                    <p><b>Dirigeant :</b> {pappers_info.get('prenom_dirigeant', '')} {pappers_info.get('nom_dirigeant', '')}</p>
                    <p><b>CA Annuel :</b> {f"{pappers_info.get('ca_annuel', 0)/1000000:.1f} M€" if pappers_info.get('ca_annuel') else 'N/A'}</p>
                    <p><b>SIRET :</b> {syndic_siret}</p>
                    <p><b>Catégorie :</b> {pappers_info.get('categorie_entreprise', 'N/A')}</p>
                </div>
            """, unsafe_allow_html=True)
            
            with st.container(border=True):
                st.markdown("#### 🌍 Présence Web")
                st.write(f"**🌐 Site :** {pappers_info.get('sites_internet', 'N/A')}")
                st.write(f"**📞 Tel :** {pappers_info.get('telephone', 'N/A')}")
                st.write(f"**📧 Email :** {pappers_info.get('email', 'N/A')}")

        with col_sales:
            from core.enrichment_manager import EnrichmentManager
            import json
            enricher = EnrichmentManager()
            enrich_key = f"enrich_data_{syndic_siret}"
            
            # Check for existing data
            if enrich_key not in st.session_state:
                cached_enrich = enricher.get_cached_data(syndic_siret)
                if cached_enrich:
                    st.session_state[enrich_key] = cached_enrich
            
            data_enrich = st.session_state.get(enrich_key)
            
            st.markdown(f"""
                <div class="premium-card" style="border-left-color: {c['accent']};">
                    <h4 style="color: {c['accent']};">🕵️ Intelligence Apollo.io</h4>
                    <p style="color: {c['sub_text']}; font-size: 0.9rem;">Détection de décideurs & Emails</p>
                </div>
            """, unsafe_allow_html=True)
            
            if not data_enrich:
                if st.button("🚀 Lancer l'Intelligence Artificielle", type="primary", use_container_width=True):
                    with st.spinner("Recherche des décideurs..."):
                        city_ref = st.session_state['selected_syndic_data'].iloc[0]['commune'] if not st.session_state['selected_syndic_data'].empty else ""
                        fresh_data = enricher.enrich_syndic(syndic_siret, syndic_name, city_ref, pappers_data=pappers_info)
                        if fresh_data:
                            st.session_state[enrich_key] = fresh_data
                            st.rerun()
            else:
                domain = data_enrich.get('domain')
                score = data_enrich.get('confidence_score', 0)
                if domain:
                    st.success(f"Domaine validé : **{domain}** ({int(score)}%)")
                else:
                    st.warning("Domaine non identifié avec certitude.")
                
                contacts = data_enrich.get('contacts_json', [])
                if isinstance(contacts, str):
                    try: contacts = json.loads(contacts)
                    except: contacts = []
                
                if contacts:
                    st.info(f"{len(contacts)} contact(s) clé(s) identifié(s)")
                    for idx, ct in enumerate(contacts[:3]): # Show top 3
                        with st.container(border=True):
                            st.markdown(f"**{ct.get('first_name')} {ct.get('last_name')}**")
                            st.caption(ct.get('title') or "Decision Maker")
                            if ct.get('email'): st.code(ct.get('email'))
                            if st.button(f"Sélectionner {ct.get('first_name')}", key=f"sel_{idx}"):
                                st.session_state['selected_contact'] = ct
                                go_to_step(4)
                else:
                    st.write("Aucun contact pertinent trouvé via Apollo.")

    with tab_buildings:
        st.markdown(f"#### 🏢 Parc immobilier géré par {syndic_name}")
        if not st.session_state['selected_syndic_data'].empty:
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
                st.session_state['selected_syndic_data'][display_cols],
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

# --- STEP 4: PROSPECTING PACK ---
elif st.session_state['current_step'] == 4:
    st.markdown("### 🏅 Étape 4 : Votre Pack de Prospection")
    
    if st.button("⬅️ Retour aux contacts", key="back_to_3"):
        go_to_step(3)
        
    contact = st.session_state.get('selected_contact', {})
    syndic_row = st.session_state.get('selected_syndic_row', {})
    
    col_left, col_right = st.columns([2, 1])
    
    with col_left:
        st.markdown(f"""
            <div class="premium-card">
                <h4>✉️ Icebreaker Personnalisé</h4>
                <p style="color: {c['sub_text']};">Copiable pour votre CRM ou Outlook</p>
                <hr style="margin: 1rem 0; border-color: {c['sep_color']};">
            </div>
        """, unsafe_allow_html=True)
        
        first_name = contact.get('first_name', 'Bonjour')
        syndic_name = syndic_row.get('Syndic', 'votre cabinet')
        
        icebreaker = f"""Objet : Valorisation des travaux de rénovation énergétique - {syndic_name}

Bonjour {first_name},

Je vous contacte car vous gérez un parc immobilier significatif dans la région, notamment des bâtiments construits avant 1975 qui présentent un fort potentiel pour les certificats d'économie d'énergie (CEE).

Nous avons identifié plusieurs de vos copropriétés qui pourraient bénéficier de subventions majeures. Seriez-vous disponible pour un court échange sur la manière dont nous pouvons valoriser ces dossiers pour vos copropriétaires ?

Bien cordialement,"""
        
        st.text_area("Template d'email", value=icebreaker, height=300)
        if st.button("📋 Copier tout le pack"):
            st.toast("Copié dans le presse-papier !")

    with col_right:
        st.markdown("#### 📦 Résumé du pack")
        with st.container(border=True):
            st.write(f"**Destinataire :** {contact.get('first_name')} {contact.get('last_name')}")
            st.write(f"**Email :** `{contact.get('email')}`")
            st.write(f"**Cabinet :** {syndic_name}")
            st.divider()
            st.metric("Immeubles cibles", int(syndic_row.get('nb_copros', 0)))
            st.metric("Lots impactés", int(syndic_row.get('total_lots', 0)))

    if st.button("🔄 Nouvelle recherche", use_container_width=True):
        import pandas as pd # Ensure pandas is imported for DataFrame
        st.session_state['syndic_list'] = pd.DataFrame()
        go_to_step(1)
else:
    st.info("👈 Configurez les filtres à gauche et cliquez sur 'Rechercher' pour commencer.")
