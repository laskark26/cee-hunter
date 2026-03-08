import streamlit as st
import pandas as pd
import pydeck as pdk
from core.data_manager import fetch_aggregated_syndics, fetch_data_by_syndic, REGIONS_DEPARTMENTS, DEPARTMENTS_NAMES
import base64

# Page Configuration
st.set_page_config(
    page_title="CEE Hunter v1 - Prospecting Dashboard",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- CSS TO HIDE SIDEBAR COMPLETELY ---
st.markdown("""
<style>
    [data-testid="stSidebar"] { display: none !important; }
    [data-testid="stSidebarCollapsedControl"] { display: none !important; }
</style>
""", unsafe_allow_html=True)
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

# --- UTILITIES: SYNCHRONIZED FILTERS ---
def synchronized_range_filter(label, key_prefix, min_val, max_val, default_val):
    """Creates a range filter with a slider synchronized with two numeric inputs."""
    slider_key = f"{key_prefix}_slider"
    min_input_key = f"{key_prefix}_min_input"
    max_input_key = f"{key_prefix}_max_input"
    
    # Initialize state if not present
    if slider_key not in st.session_state:
        st.session_state[slider_key] = default_val
        st.session_state[min_input_key] = default_val[0]
        st.session_state[max_input_key] = default_val[1]

    st.markdown(f"#### 🏘️ {label}")
    
    # Header with Numeric Inputs
    c_min, c_max = st.columns(2)
    
    # Callback to sync slider from inputs
    def sync_slider_from_inputs():
        # Auto-fix: Ensure min <= max
        v_min = st.session_state[min_input_key]
        v_max = st.session_state[max_input_key]
        if v_min > v_max:
            st.session_state[max_input_key] = v_min
            v_max = v_min
        st.session_state[slider_key] = (v_min, v_max)

    # Callback to sync inputs from slider
    def sync_inputs_from_slider():
        v_min, v_max = st.session_state[slider_key]
        st.session_state[min_input_key] = v_min
        st.session_state[max_input_key] = v_max

    with c_min:
        st.number_input(
            "Min", min_value=min_val, max_value=max_val,
            key=min_input_key, on_change=sync_slider_from_inputs,
            label_visibility="collapsed"
        )
    with c_max:
        st.number_input(
            "Max", min_value=min_val, max_value=max_val,
            key=max_input_key, on_change=sync_slider_from_inputs,
            label_visibility="collapsed"
        )

    # Slider
    st.slider(
        label, min_value=min_val, max_value=max_val,
        key=slider_key, on_change=sync_inputs_from_slider,
        label_visibility="collapsed"
    )
    
    return st.session_state[slider_key]

# --- SESSION STATE MANAGEMENT ---
if 'theme' not in st.session_state:
    st.session_state['theme'] = 'Light' # Initial fallback
if 'theme_manually_set' not in st.session_state:
    st.session_state['theme_manually_set'] = False
if 'current_step' not in st.session_state:
    st.session_state['current_step'] = 1
if 'syndic_list' not in st.session_state:
    st.session_state['syndic_list'] = pd.DataFrame()
if 'selected_syndic_data' not in st.session_state:
    st.session_state['selected_syndic_data'] = pd.DataFrame()
if 'current_syndic_name' not in st.session_state:
    st.session_state['current_syndic_name'] = None

# --- SYSTEM THEME DETECTION (One-time) ---
if not st.session_state.get('theme_manually_set') and not st.session_state.get('system_theme_detected'):
    from streamlit.components.v1 import html
    html("""
    <script>
        const theme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'Dark' : 'Light';
        const url = new URL(window.parent.location.href);
        if (url.searchParams.get('sys_theme') !== theme) {
            url.searchParams.set('sys_theme', theme);
            window.parent.location.href = url.href;
        }
    </script>
    """, height=0)
    
    detected = st.query_params.get('sys_theme')
    if detected:
        st.session_state['theme'] = detected
        st.session_state['system_theme_detected'] = True
        st.rerun()

# --- NAVIGATION HELPERS ---
def go_to_step(step_number):
    st.session_state['current_step'] = step_number
    st.rerun()

# --- PREMIUM CSS STYLING ---
theme_config = {
    "Dark": {
        "bg_color": "#0E1117",
        "sidebar_bg": "#161B22", # Still used for stepper bg
        "card_bg": "#1E232F",
        "card_border": "#2D333F",
        "text_color": "#F3F4F6",
        "sub_text": "#9CA3AF",
        "sep_color": "#262730",
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
        "accent": "#059669"
    }
}

c = theme_config[st.session_state['theme']]

# --- HIGH-DENSITY CSS STYLING ---
st.markdown(f"""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');
        html, body, [class*="css"] {{ font-family: 'Inter', sans-serif; }}
        .stApp {{ background-color: {c['bg_color']}; color: {c['text_color']}; }}
        
        /* 60% Reduction in Vertical Spacing */
        .block-container {{ padding-top: 60px !important; padding-bottom: 0rem !important; max-width: 1200px !important; }}
        [data-testid="stVerticalBlock"] {{ gap: 0.25rem !important; }}
        
        /* Compact Header */
        .header-compact {{
            display: flex;
            align-items: center;
            padding-bottom: 0.5rem;
            border-bottom: 1px solid {c['sep_color']};
            margin-bottom: 0.5rem;
        }}
        .header-logo {{ font-size: 1.1rem; font-weight: 800; color: {c['accent']}; margin-right: 1rem; }}
        .header-title {{ font-size: 0.85rem; color: {c['sub_text']}; font-weight: 400; flex-grow: 1; }}

        /* Theme Toggle Button Styling */
        .stButton>button[kind="secondary"] {{
            background: transparent;
            border: none;
            font-size: 1.2rem;
            padding: 0;
            margin: 0;
            min-height: auto;
            width: 32px;
            height: 32px;
        }}

        /* Micro Stepper */
        .micro-stepper {{
            display: flex;
            gap: 1.5rem;
            justify-content: center;
            background: {c['sidebar_bg']};
            padding: 6px 16px;
            border-radius: 8px;
            border: 1px solid {c['card_border']};
            margin-bottom: 0.75rem;
        }}
        .step-pill {{ font-size: 0.7rem; color: {c['sub_text']}; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }}
        .step-pill-active {{ color: {c['accent']}; }}
        .step-dot {{ width: 5px; height: 5px; background: {c['card_border']}; border-radius: 50%; display: inline-block; margin-right: 5px; }}
        .step-pill-active .step-dot {{ background: {c['accent']}; box-shadow: 0 0 8px {c['accent']}; }}

        /* Compact Cards */
        .premium-card {{
            background-color: {c['card_bg']};
            padding: 0.5rem 0.75rem;
            border-radius: 8px;
            border: 1px solid {c['card_border']};
            margin-bottom: 0.25rem;
        }}
        
        [data-testid="stMetric"] {{ padding: 0.25rem 0.5rem !important; }}
        h1 {{ font-size: 1.1rem !important; margin: 0 !important; }}
        h3 {{ font-size: 0.9rem !important; margin: 0.15rem 0 !important; }}
        h4 {{ font-size: 0.8rem !important; margin: 0.1rem 0 !important; color: {c['sub_text']}; }}
        .stCaption {{ font-size: 0.7rem !important; margin-bottom: 0.15rem !important; }}
    </style>
    """, unsafe_allow_html=True)

# --- COMPACT HEADER WITH THEME TOGGLE ---
h_col1, h_col2, h_col3 = st.columns([2, 5, 1])
with h_col1:
    st.markdown(f'<div class="header-logo">🎯 CEE HUNTER <span style="font-weight: 300; font-size: 0.75rem; color: {c["sub_text"]};">PRO</span></div>', unsafe_allow_html=True)
with h_col2:
    st.markdown(f'<div class="header-title" style="margin-top:4px;">Assistant de prospection intelligente</div>', unsafe_allow_html=True)
with h_col3:
    current_icon = "☀️" if st.session_state['theme'] == "Dark" else "🌙"
    if st.button(current_icon, key="theme_toggle"):
        st.session_state['theme'] = "Light" if st.session_state['theme'] == "Dark" else "Dark"
        st.session_state['theme_manually_set'] = True
        st.rerun()

st.markdown(f'<div style="border-bottom: 1px solid {c["sep_color"]}; margin-bottom: 0.5rem;"></div>', unsafe_allow_html=True)

# --- MICRO STEPPER ---
s = st.session_state['current_step']
st.markdown(f"""
    <div class="micro-stepper">
        <div class="step-pill {'step-pill-active' if s>=1 else ''}"><span class="step-dot"></span>CRITÈRES</div>
        <div class="step-pill {'step-pill-active' if s>=2 else ''}"><span class="step-dot"></span>RÉSULTATS</div>
        <div class="step-pill {'step-pill-active' if s>=3 else ''}"><span class="step-dot"></span>INTEL</div>
        <div class="step-pill {'step-pill-active' if s>=4 else ''}"><span class="step-dot"></span>PACK</div>
    </div>
""", unsafe_allow_html=True)

# --- STEP 1: GUIDED CRITERIA ---
if st.session_state['current_step'] == 1:
    col1, col2 = st.columns(2)
    
    with col1:
        with st.container(border=True):
            st.markdown("#### 🌍 Zone & Période")
            selected_zones = st.multiselect(
                "Zones Climatiques",
                options=["H1", "H2", "H3"],
                default=["H1"],
                placeholder="Choisir zones..."
            )
            selected_regions = st.multiselect(
                "Régions",
                options=sorted(REGIONS_DEPARTMENTS.keys()),
                default=[],
                placeholder="Toutes les régions..."
            )
            if selected_regions:
                available_depts = []
                for r in selected_regions:
                    available_depts.extend(REGIONS_DEPARTMENTS.get(r, []))
            else:
                available_depts = sorted(DEPARTMENTS_NAMES.keys())
            dept_options = [DEPARTMENTS_NAMES[d] for d in available_depts if d in DEPARTMENTS_NAMES]
            selected_dept_labels = st.multiselect(
                "Départements",
                options=dept_options,
                default=[],
                placeholder="Tous les départements..."
            )
            selected_departments = [lbl.split(" - ")[0] for lbl in selected_dept_labels]
            selected_periods = st.multiselect(
                "Périodes de construction",
                options=['Avant 1949', '1949-1974', '1975-1993', '1994-2000', '2001-2010', 'Après 2011'],
                default=['Avant 1949', '1949-1974'],
                placeholder="Choisir périodes..."
            )

    with col2:
        with st.container(border=True):
            selected_lots = synchronized_range_filter(
                "Nombre de lots (Habitation)",
                "lots_filter", 0, 1000, (20, 500)
            )
            c_opt1, c_opt2 = st.columns(2)
            with c_opt1:
                exclude_big = st.checkbox("🚫 Exclure majors", value=True)
            with c_opt2:
                qpv_only = st.checkbox("📍 QPV Uniq.", value=False)

    if st.button("🚀 TROUVER LES SYNDICS", type="primary", use_container_width=True):
        with st.spinner("Analyse du gisement en cours..."):
            st.session_state['syndic_list'] = fetch_aggregated_syndics(
                climate_zones=selected_zones,
                min_lots=selected_lots[0],
                max_lots=selected_lots[1],
                periods=selected_periods,
                exclude_big_syndics=exclude_big,
                qpv_only=qpv_only,
                regions=selected_regions,
                departments=selected_departments
            )
            # Store filters for reuse in step 2
            st.session_state['filters'] = {
                'zones': selected_zones,
                'regions': selected_regions,
                'departments': selected_departments,
                'lots': selected_lots,
                'periods': selected_periods,
                'exclude_big': exclude_big,
                'qpv': qpv_only
            }
            go_to_step(2)
# --- STEP 2: RESULTS TABLE ---
elif st.session_state['current_step'] == 2:
    col_back, col_kpis = st.columns([1, 4])
    with col_back:
        if st.button("⬅️ Critères", key="back_to_1"):
            go_to_step(1)
    
    df_agg = st.session_state['syndic_list']
    
    if df_agg.empty:
        st.warning("Aucun résultat.")
    else:
        with col_kpis:
            k1, k2, k3 = st.columns(3)
            k1.metric("Syndics", f"{len(df_agg)}")
            k2.metric("Immeubles", f"{int(df_agg['nb_copros'].sum())}")
            k3.metric("Lots", f"{int(df_agg['total_lots'].sum())}")
        
        df_display = df_agg[["Syndic", "Siret", "nb_copros", "total_lots"]].rename(columns={
            "nb_copros": "Immeubles", "total_lots": "Lots"
        })

        event = st.dataframe(
            df_display, use_container_width=True,
            column_config={
                "Syndic": st.column_config.TextColumn("Nom du Syndic", width="large"),
                "Siret": st.column_config.TextColumn("SIRET", width="small"),
                "Immeubles": st.column_config.NumberColumn("🏢", format="%d"),
                "Lots": st.column_config.ProgressColumn("🏠 Total", format="%d", min_value=0, max_value=int(df_agg['total_lots'].max())),
            },
            selection_mode="single-row", on_select="rerun", hide_index=True, height=400
        )
        
        if len(event.selection['rows']) > 0:
            selected_index = event.selection['rows'][0]
            selected_row = df_agg.iloc[selected_index]
            st.session_state['selected_syndic_row'] = selected_row
            go_to_step(3)

# --- STEP 3: SYNDIC DETAILS ---
elif st.session_state['current_step'] == 3:
    syndic_row = st.session_state.get('selected_syndic_row')
    if syndic_row is None: go_to_step(2)
        
    syndic_name, syndic_siret = syndic_row['Syndic'], syndic_row['Siret']
    
    col_back, col_title = st.columns([1, 6])
    with col_back:
        if st.button("⬅️ Liste", key="back_to_2"): go_to_step(2)
    with col_title:
        st.markdown(f"#### {syndic_name}")

    from core.pappers_connector import get_syndic_info
    pappers_info = get_syndic_info(syndic_siret)

    filters = st.session_state.get('filters', {})
    if st.session_state['current_syndic_name'] != syndic_name:
        st.session_state['selected_syndic_data'] = fetch_data_by_syndic(
            syndic_name, filters.get('zones', ['H1']), filters.get('lots', (0, 1000))[0], filters.get('lots', (0, 1000))[1],
            periods=filters.get('periods'), exclude_big_syndics=filters.get('exclude_big', True), qpv_only=filters.get('qpv', False),
            regions=filters.get('regions'), departments=filters.get('departments')
        )
        st.session_state['current_syndic_name'] = syndic_name
        
    tab_intel, tab_contacts, tab_parc = st.tabs(["🕵️ Intelligence", "👥 Contacts", "🏢 Parc Immobilier"])

    with tab_intel:
        from core.syndic_intel import SyndicIntelligence
        from core.enrichment_manager import EnrichmentManager
        import json

        intel_engine = SyndicIntelligence()
        enricher = EnrichmentManager()

        # Fiche entreprise (Pappers)
        st.markdown(f"""
            <div class="premium-card">
                <p style="font-size:0.8rem; margin:0;"><b>Dirigeant :</b> {pappers_info.get('prenom_dirigeant', '')} {pappers_info.get('nom_dirigeant', '')}</p>
                <p style="font-size:0.8rem; margin:0;"><b>CA :</b> {f"{pappers_info.get('ca_annuel', 0)/1000000:.1f} M€" if pappers_info.get('ca_annuel') else 'N/A'}
                    &nbsp;•&nbsp; <b>Catégorie :</b> {pappers_info.get('categorie_entreprise', 'N/A')}
                    &nbsp;•&nbsp; <b>APE :</b> {pappers_info.get('code_ape', 'N/A')}</p>
                <p style="font-size:0.75rem; color:{c['sub_text']}; margin:0;">
                    📞 {pappers_info.get('telephone', 'N/A')} &nbsp;•&nbsp; 📧 {pappers_info.get('email', 'N/A')}
                    &nbsp;•&nbsp; 🌐 {pappers_info.get('sites_internet', 'N/A')}</p>
            </div>
        """, unsafe_allow_html=True)

        # Intelligence IA
        intel_key = f"intel_data_{syndic_siret}"
        if intel_key not in st.session_state:
            cached_intel = intel_engine.get_cached_intel(syndic_siret)
            if cached_intel:
                st.session_state[intel_key] = cached_intel

        intel_data = st.session_state.get(intel_key)

        if not intel_data:
            st.markdown("")
            col_btn, col_refresh = st.columns([3, 1])
            with col_btn:
                if st.button("🔬 Lancer l'Intelligence", type="primary", use_container_width=True):
                    with st.spinner("Analyse en cours... Scraping du site, recherche réseaux sociaux, analyse IA..."):
                        # Get domain from enrichment or pappers
                        enrich_key = f"enrich_data_{syndic_siret}"
                        if enrich_key not in st.session_state:
                            cached_enrich = enricher.get_cached_data(syndic_siret)
                            if cached_enrich:
                                st.session_state[enrich_key] = cached_enrich
                        domain = None
                        enrich_data = st.session_state.get(enrich_key)
                        if enrich_data:
                            domain = enrich_data.get("domain")
                        if not domain and pappers_info:
                            sites = pappers_info.get("sites_internet", "")
                            if sites:
                                domain = sites.split(",")[0].strip().replace("https://", "").replace("http://", "").replace("www.", "").strip("/")

                        city = st.session_state['selected_syndic_data'].iloc[0]['commune'] if not st.session_state['selected_syndic_data'].empty else ""
                        result = intel_engine.run_intelligence(
                            siret=syndic_siret,
                            name=syndic_name,
                            city=city,
                            domain=domain,
                            pappers_data=pappers_info,
                            nb_copros=int(syndic_row.get('nb_copros', 0)),
                            total_lots=int(syndic_row.get('total_lots', 0)),
                        )
                        if result:
                            st.session_state[intel_key] = result
                            st.rerun()
        else:
            analysis = intel_data.get("llm_analysis_json", {})
            if isinstance(analysis, str):
                try:
                    analysis = json.loads(analysis)
                except Exception:
                    analysis = {}

            # Score de prospection
            score = analysis.get("score_prospection", "?")
            score_color = "#10B981" if isinstance(score, (int, float)) and score >= 7 else "#F59E0B" if isinstance(score, (int, float)) and score >= 4 else "#EF4444"
            maturite = analysis.get("maturite_digitale", "N/A")
            maturite_color = "#10B981" if maturite == "forte" else "#F59E0B" if maturite == "moyenne" else "#EF4444"

            col_s1, col_s2, col_s3 = st.columns(3)
            with col_s1:
                st.markdown(f"""<div class="premium-card" style="text-align:center;">
                    <p style="font-size:0.7rem; margin:0; color:{c['sub_text']};">SCORE PROSPECTION</p>
                    <p style="font-size:1.8rem; font-weight:800; margin:0; color:{score_color};">{score}/10</p>
                </div>""", unsafe_allow_html=True)
            with col_s2:
                st.markdown(f"""<div class="premium-card" style="text-align:center;">
                    <p style="font-size:0.7rem; margin:0; color:{c['sub_text']};">MATURITÉ DIGITALE</p>
                    <p style="font-size:1rem; font-weight:700; margin:0.25rem 0 0 0; color:{maturite_color};">{maturite.upper() if maturite else 'N/A'}</p>
                </div>""", unsafe_allow_html=True)
            with col_s3:
                taille = analysis.get("taille_estimee", "N/A")
                st.markdown(f"""<div class="premium-card" style="text-align:center;">
                    <p style="font-size:0.7rem; margin:0; color:{c['sub_text']};">TAILLE ESTIMÉE</p>
                    <p style="font-size:1rem; font-weight:700; margin:0.25rem 0 0 0;">{taille}</p>
                </div>""", unsafe_allow_html=True)

            # Résumé activité
            resume = analysis.get("resume_activite", "")
            if resume:
                st.markdown(f"""<div class="premium-card">
                    <p style="font-size:0.75rem; font-weight:600; margin:0 0 0.25rem 0;">📋 Résumé</p>
                    <p style="font-size:0.8rem; margin:0;">{resume}</p>
                </div>""", unsafe_allow_html=True)

            # Réseaux sociaux
            socials = analysis.get("reseaux_sociaux", {})
            if socials:
                social_html = '<div class="premium-card"><p style="font-size:0.75rem; font-weight:600; margin:0 0 0.25rem 0;">🌐 Présence Web</p>'
                for platform, info in socials.items():
                    if isinstance(info, dict):
                        url = info.get("url", "")
                        actif = info.get("actif", False)
                        icon = "🟢" if actif else "🔴"
                        label = platform.replace("_", " ").title()
                        if url:
                            social_html += f'<p style="font-size:0.75rem; margin:0;">{icon} <b>{label}</b>: <a href="{url}" target="_blank" style="color:{c["accent"]};">{url[:50]}...</a></p>'
                        else:
                            social_html += f'<p style="font-size:0.75rem; margin:0;">{icon} <b>{label}</b>: Non trouvé</p>'
                        note = info.get("note", "")
                        nb_avis = info.get("nb_avis", "")
                        if note or nb_avis:
                            social_html += f'<p style="font-size:0.7rem; margin:0; color:{c["sub_text"]};">&nbsp;&nbsp;&nbsp;Note: {note} ({nb_avis} avis)</p>'
                social_html += '</div>'
                st.markdown(social_html, unsafe_allow_html=True)

            # Points forts / faibles
            col_pf, col_pw = st.columns(2)
            with col_pf:
                points_forts = analysis.get("points_forts", [])
                if points_forts:
                    html_pf = '<div class="premium-card"><p style="font-size:0.75rem; font-weight:600; margin:0 0 0.25rem 0;">✅ Points forts</p>'
                    for pf in points_forts:
                        html_pf += f'<p style="font-size:0.75rem; margin:0;">• {pf}</p>'
                    html_pf += '</div>'
                    st.markdown(html_pf, unsafe_allow_html=True)
            with col_pw:
                points_faibles = analysis.get("points_faibles", [])
                if points_faibles:
                    html_pw = '<div class="premium-card"><p style="font-size:0.75rem; font-weight:600; margin:0 0 0.25rem 0;">⚠️ Points faibles</p>'
                    for pw in points_faibles:
                        html_pw += f'<p style="font-size:0.75rem; margin:0;">• {pw}</p>'
                    html_pw += '</div>'
                    st.markdown(html_pw, unsafe_allow_html=True)

            # Angle d'approche
            angle = analysis.get("angle_approche_recommande", "")
            if angle:
                st.markdown(f"""<div class="premium-card" style="border-left: 3px solid {c['accent']};">
                    <p style="font-size:0.75rem; font-weight:600; margin:0 0 0.25rem 0;">🎯 Angle d'approche recommandé</p>
                    <p style="font-size:0.8rem; margin:0;">{angle}</p>
                </div>""", unsafe_allow_html=True)

            # Reputation
            reputation = analysis.get("reputation_en_ligne", "")
            if reputation:
                st.markdown(f"""<div class="premium-card">
                    <p style="font-size:0.75rem; font-weight:600; margin:0 0 0.25rem 0;">💬 Réputation en ligne</p>
                    <p style="font-size:0.8rem; margin:0;">{reputation}</p>
                </div>""", unsafe_allow_html=True)

            # Telephone & Email principaux
            tel_principal = analysis.get("telephone_principal", "")
            email_principal = analysis.get("email_principal", "")
            if tel_principal or email_principal:
                contact_html = '<div class="premium-card"><p style="font-size:0.75rem; font-weight:600; margin:0 0 0.25rem 0;">📞 Contact principal</p>'
                if tel_principal:
                    contact_html += f'<p style="font-size:0.8rem; margin:0;">Tél : <b>{tel_principal}</b></p>'
                if email_principal:
                    contact_html += f'<p style="font-size:0.8rem; margin:0;">Email : <b>{email_principal}</b></p>'
                contact_html += '</div>'
                st.markdown(contact_html, unsafe_allow_html=True)

            # Contacts cles (from LLM analysis of Apollo data)
            contacts_cles = analysis.get("contacts_cles", [])
            if contacts_cles:
                ck_html = '<div class="premium-card"><p style="font-size:0.75rem; font-weight:600; margin:0 0 0.25rem 0;">👥 Contacts clés pour la prospection CEE</p>'
                for ck in contacts_cles[:5]:
                    if isinstance(ck, dict):
                        nom = ck.get("nom", "")
                        poste = ck.get("poste", "")
                        ck_email = ck.get("email", "")
                        ck_tel = ck.get("telephone", "")
                        ck_li = ck.get("linkedin", "")
                        pertinence = ck.get("pertinence_cee", "")
                        ck_html += f'<div style="border-top:1px solid {c["card_border"]}; padding:0.3rem 0; margin-top:0.2rem;">'
                        ck_html += f'<p style="font-size:0.8rem; margin:0;"><b>{nom}</b> — {poste}</p>'
                        details_parts = []
                        if ck_email:
                            details_parts.append(f'📧 {ck_email}')
                        if ck_tel:
                            details_parts.append(f'📞 {ck_tel}')
                        if ck_li:
                            details_parts.append(f'<a href="{ck_li}" target="_blank" style="color:{c["accent"]};">LinkedIn</a>')
                        if details_parts:
                            ck_html += f'<p style="font-size:0.7rem; margin:0; color:{c["sub_text"]};">{" &nbsp;•&nbsp; ".join(details_parts)}</p>'
                        if pertinence:
                            ck_html += f'<p style="font-size:0.7rem; margin:0; color:{c["sub_text"]}; font-style:italic;">→ {pertinence}</p>'
                        ck_html += '</div>'
                ck_html += '</div>'
                st.markdown(ck_html, unsafe_allow_html=True)

            # Services & Zones
            services = analysis.get("services_proposes", [])
            zones = analysis.get("zones_geographiques", [])
            if services or zones:
                col_sv, col_zn = st.columns(2)
                with col_sv:
                    if services:
                        st.markdown(f"""<div class="premium-card">
                            <p style="font-size:0.75rem; font-weight:600; margin:0 0 0.25rem 0;">🔧 Services</p>
                            <p style="font-size:0.75rem; margin:0;">{' • '.join(services)}</p>
                        </div>""", unsafe_allow_html=True)
                with col_zn:
                    if zones:
                        st.markdown(f"""<div class="premium-card">
                            <p style="font-size:0.75rem; font-weight:600; margin:0 0 0.25rem 0;">📍 Zones géographiques</p>
                            <p style="font-size:0.75rem; margin:0;">{' • '.join(zones)}</p>
                        </div>""", unsafe_allow_html=True)

            # Bouton refresh
            if st.button("🔄 Réactualiser l'analyse", key="refresh_intel"):
                with st.spinner("Réactualisation..."):
                    enrich_key = f"enrich_data_{syndic_siret}"
                    if enrich_key not in st.session_state:
                        cached_enrich = enricher.get_cached_data(syndic_siret)
                        if cached_enrich:
                            st.session_state[enrich_key] = cached_enrich
                    domain = None
                    enrich_data = st.session_state.get(enrich_key)
                    if enrich_data:
                        domain = enrich_data.get("domain")
                    city = st.session_state['selected_syndic_data'].iloc[0]['commune'] if not st.session_state['selected_syndic_data'].empty else ""
                    result = intel_engine.run_intelligence(
                        siret=syndic_siret, name=syndic_name, city=city,
                        domain=domain, pappers_data=pappers_info,
                        nb_copros=int(syndic_row.get('nb_copros', 0)),
                        total_lots=int(syndic_row.get('total_lots', 0)),
                        force_refresh=True,
                    )
                    if result:
                        st.session_state[intel_key] = result
                        st.rerun()

    with tab_contacts:
        from core.enrichment_manager import EnrichmentManager as EM2

        # Merge contacts: Apollo intel contacts + enrichment contacts
        all_contacts = []

        # Source 1: Apollo contacts from intelligence pipeline
        intel_contacts_raw = (intel_data or {}).get("apollo_contacts_json", []) if intel_data else []
        if isinstance(intel_contacts_raw, str):
            try:
                intel_contacts_raw = json.loads(intel_contacts_raw)
            except Exception:
                intel_contacts_raw = []
        if intel_contacts_raw:
            all_contacts.extend(intel_contacts_raw)

        # Source 2: Enrichment manager contacts (Apollo targeted search)
        enricher2 = EM2()
        enrich_key = f"enrich_data_{syndic_siret}"
        if enrich_key not in st.session_state:
            cached = enricher2.get_cached_data(syndic_siret)
            if cached:
                st.session_state[enrich_key] = cached

        data_enrich = st.session_state.get(enrich_key)
        if data_enrich:
            enrich_contacts = data_enrich.get('contacts_json', [])
            if isinstance(enrich_contacts, str):
                try:
                    enrich_contacts = json.loads(enrich_contacts)
                except Exception:
                    enrich_contacts = []
            # Deduplicate by email
            existing_emails = {ct.get("email", "").lower() for ct in all_contacts if ct.get("email")}
            for ec in enrich_contacts:
                if ec.get("email", "").lower() not in existing_emails:
                    all_contacts.append(ec)
                    existing_emails.add(ec.get("email", "").lower())

        if not all_contacts and not data_enrich:
            if st.button("🚀 Rechercher les contacts", type="primary", use_container_width=True):
                with st.spinner("Recherche de contacts (Apollo)..."):
                    city = st.session_state['selected_syndic_data'].iloc[0]['commune'] if not st.session_state['selected_syndic_data'].empty else ""
                    fresh = enricher2.enrich_syndic(syndic_siret, syndic_name, city, pappers_data=pappers_info)
                    if fresh:
                        st.session_state[enrich_key] = fresh
                        st.rerun()
        elif not all_contacts:
            st.info("Aucun contact trouvé pour ce syndic.")
        else:
            st.caption(f"{len(all_contacts)} contact(s) trouvé(s)")
            for idx, ct in enumerate(all_contacts[:10]):
                with st.container(border=True):
                    col_ct, col_act = st.columns([3, 1])
                    col_ct.markdown(f"**{ct.get('first_name', '')} {ct.get('last_name', '')}** — {ct.get('title') or 'Lead'}")
                    details = []
                    email_ct = ct.get('email', '')
                    if email_ct:
                        details.append(f"📧 {email_ct}")
                    phones = ct.get('phone_numbers', [])
                    if phones:
                        details.append(f"📞 {', '.join(phones) if isinstance(phones, list) else phones}")
                    linkedin_ct = ct.get('linkedin_url', '')
                    if linkedin_ct:
                        details.append(f"[LinkedIn]({linkedin_ct})")
                    if details:
                        col_ct.caption(" • ".join(details))
                    if col_act.button("🎯 Prospecter", key=f"sel_{idx}"):
                        st.session_state['selected_contact'] = ct
                        go_to_step(4)

    with tab_parc:
        st.dataframe(st.session_state['selected_syndic_data'], use_container_width=True, hide_index=True, height=300)

# --- STEP 4: PROSPECTING PACK ---
elif st.session_state['current_step'] == 4:
    import json as json4
    col_back, col_new = st.columns([1, 4])
    with col_back:
        if st.button("⬅️ Contacts"): go_to_step(3)
    with col_new:
        if st.button("🔄 Nouvelle recherche"):
            st.session_state['syndic_list'] = pd.DataFrame()
            go_to_step(1)

    contact = st.session_state.get('selected_contact', {})
    syndic_row = st.session_state.get('selected_syndic_row', {})
    syndic_siret_pack = syndic_row.get('Siret', '')

    # Try to get LLM-generated icebreaker from intel cache
    intel_key_pack = f"intel_data_{syndic_siret_pack}"
    intel_pack = st.session_state.get(intel_key_pack, {})
    analysis_pack = intel_pack.get("llm_analysis_json", {})
    if isinstance(analysis_pack, str):
        try:
            analysis_pack = json4.loads(analysis_pack)
        except Exception:
            analysis_pack = {}

    llm_icebreaker = analysis_pack.get("email_icebreaker", "")
    score_pack = analysis_pack.get("score_prospection", "?")
    angle_pack = analysis_pack.get("angle_approche_recommande", "")

    first_name = contact.get('first_name', 'Bonjour')
    fallback_ice = f"Objet : {syndic_row.get('Syndic')}\n\nBonjour {first_name},\n\nJ'ai identifié {int(syndic_row.get('nb_copros', 0))} de vos immeubles à fort potentiel CEE..."
    ice = llm_icebreaker if llm_icebreaker else fallback_ice

    c1, c2 = st.columns([2, 1])
    with c1:
        with st.container(border=True):
            st.markdown("#### ✉️ Email Icebreaker")
            if llm_icebreaker:
                st.caption("✨ Généré par IA — personnalisé à partir de l'analyse du syndic")
            else:
                st.caption("📝 Template standard — lancez l'Intelligence pour un email personnalisé")
            st.text_area("Template", value=ice, height=180, label_visibility="collapsed")
            if st.button("📋 Copier le Pack"): st.toast("Copié !")

        if angle_pack:
            st.markdown(f"""<div class="premium-card" style="border-left: 3px solid {c['accent']};">
                <p style="font-size:0.75rem; font-weight:600; margin:0 0 0.25rem 0;">🎯 Angle d'approche</p>
                <p style="font-size:0.8rem; margin:0;">{angle_pack}</p>
            </div>""", unsafe_allow_html=True)

    with c2:
        with st.container(border=True):
            st.markdown("#### 📦 Détails")
            st.caption(f"**{contact.get('first_name')} {contact.get('last_name')}**")
            st.caption(f"`{contact.get('email', 'N/A')}`")
            linkedin = contact.get('linkedin_url', '')
            if linkedin:
                st.caption(f"[LinkedIn]({linkedin})")
            st.metric("Cibles", f"{int(syndic_row.get('nb_copros', 0))} bat.", delta=f"{int(syndic_row.get('total_lots', 0))} lots")
            if isinstance(score_pack, (int, float)):
                score_color_pack = "#10B981" if score_pack >= 7 else "#F59E0B" if score_pack >= 4 else "#EF4444"
                st.markdown(f"""<div style="text-align:center; margin-top:0.5rem;">
                    <p style="font-size:0.7rem; color:{c['sub_text']}; margin:0;">SCORE</p>
                    <p style="font-size:1.5rem; font-weight:800; color:{score_color_pack}; margin:0;">{score_pack}/10</p>
                </div>""", unsafe_allow_html=True)
