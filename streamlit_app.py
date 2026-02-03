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

# --- SESSION STATE MANAGEMENT ---
if 'theme' not in st.session_state:
    st.session_state['theme'] = 'Dark' # Initial fallback
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
        .block-container {{ padding-top: 0.5rem !important; padding-bottom: 0rem !important; max-width: 1200px !important; }}
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
            selected_periods = st.multiselect(
                "Périodes de construction",
                options=['Avant 1949', '1949-1974', '1975-1993', '1994-2000', '2001-2010', 'Après 2011'],
                default=['Avant 1949', '1949-1974'],
                placeholder="Choisir périodes..."
            )

    with col2:
        with st.container(border=True):
            st.markdown("#### 🏘️ Taille & Cible")
            selected_lots = st.slider(
                "Nombre de lots (Habitation)",
                min_value=0, max_value=1000, value=(20, 500)
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
            periods=filters.get('periods'), exclude_big_syndics=filters.get('exclude_big', True), qpv_only=filters.get('qpv', False)
        )
        st.session_state['current_syndic_name'] = syndic_name
        
    tab_intel, tab_parc = st.tabs(["🕵️ Intelligence", "🏢 Parc Immobilier"])
    
    with tab_intel:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"""
                <div class="premium-card">
                    <p style="font-size:0.8rem; margin:0;"><b>Dirigeant :</b> {pappers_info.get('prenom_dirigeant', '')} {pappers_info.get('nom_dirigeant', '')}</p>
                    <p style="font-size:0.8rem; margin:0;"><b>CA :</b> {f"{pappers_info.get('ca_annuel', 0)/1000000:.1f} M€" if pappers_info.get('ca_annuel') else 'N/A'}</p>
                    <p style="font-size:0.75rem; color:{c['sub_text']}; margin:0;">{pappers_info.get('telephone', 'N/A')} • {pappers_info.get('email', 'N/A')}</p>
                </div>
            """, unsafe_allow_html=True)

        with c2:
            from core.enrichment_manager import EnrichmentManager
            import json
            enricher = EnrichmentManager()
            enrich_key = f"enrich_data_{syndic_siret}"
            if enrich_key not in st.session_state:
                cached = enricher.get_cached_data(syndic_siret)
                if cached: st.session_state[enrich_key] = cached
            
            data_enrich = st.session_state.get(enrich_key)
            if not data_enrich:
                if st.button("🚀 Lancer l'IA", type="primary", use_container_width=True):
                    with st.spinner("..."):
                        city = st.session_state['selected_syndic_data'].iloc[0]['commune'] if not st.session_state['selected_syndic_data'].empty else ""
                        fresh = enricher.enrich_syndic(syndic_siret, syndic_name, city, pappers_data=pappers_info)
                        if fresh: st.session_state[enrich_key] = fresh; st.rerun()
            else:
                contacts = data_enrich.get('contacts_json', [])
                if isinstance(contacts, str):
                    try: contacts = json.loads(contacts)
                    except: contacts = []
                
                for idx, ct in enumerate(contacts[:2]):
                    with st.container(border=True):
                        col_ct, col_act = st.columns([3, 1])
                        col_ct.markdown(f"**{ct.get('first_name')}** ({ct.get('title') or 'Lead'})")
                        if col_act.button("🎯", key=f"sel_{idx}"):
                            st.session_state['selected_contact'] = ct
                            go_to_step(4)

    with tab_parc:
        st.dataframe(st.session_state['selected_syndic_data'], use_container_width=True, hide_index=True, height=300)

# --- STEP 4: PROSPECTING PACK ---
elif st.session_state['current_step'] == 4:
    col_back, col_new = st.columns([1, 4])
    with col_back:
        if st.button("⬅️ Contacts"): go_to_step(3)
    with col_new:
        if st.button("🔄 Nouvelle recherche"):
            st.session_state['syndic_list'] = pd.DataFrame()
            go_to_step(1)
        
    contact, syndic_row = st.session_state.get('selected_contact', {}), st.session_state.get('selected_syndic_row', {})
    
    c1, c2 = st.columns([2, 1])
    with c1:
        with st.container(border=True):
            st.markdown("#### ✉️ Email Icebreaker")
            first_name = contact.get('first_name', 'Bonjour')
            ice = f"Objet : {syndic_row.get('Syndic')}\n\nBonjour {first_name},\n\nJ'ai identifié {int(syndic_row.get('nb_copros', 0))} de vos immeubles à fort potentiel CEE..."
            st.text_area("Template", value=ice, height=150, label_visibility="collapsed")
            if st.button("📋 Copier le Pack"): st.toast("Copié !")

    with c2:
        with st.container(border=True):
            st.markdown("#### 📦 Détails")
            st.caption(f"**{contact.get('first_name')} {contact.get('last_name')}**")
            st.caption(f"`{contact.get('email', 'N/A')}`")
            st.metric("Cibles", f"{int(syndic_row.get('nb_copros', 0))} bat.", delta=f"{int(syndic_row.get('total_lots', 0))} lots")
