import streamlit as st
import pandas as pd
import json
from core.data_manager import (
    fetch_aggregated_syndics, fetch_data_by_syndic, fetch_all_data_by_syndic,
    count_matching_syndics, REGIONS_DEPARTMENTS, DEPARTMENTS_NAMES,
    init_saved_searches_table, get_saved_searches, save_search, delete_saved_search,
)
from styles import generate_css, get_theme, score_color, PALETTE
from components import (
    render_header, render_stepper, render_kpi_card, render_score_gauge,
    render_info_card, render_contact_card_html, render_copro_card,
    render_empty_state, render_skeleton, render_chips, render_section_label,
    render_divider, score_tag_html, maturite_tag_html, PERIOD_LABELS,
)

# ── Page Config ───────────────────────────────────────────────

st.set_page_config(
    page_title="CEE Hunter PRO",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Security: Login ───────────────────────────────────────────

def check_password():
    def password_entered():
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

# ── Session State ─────────────────────────────────────────────

defaults = {
    "theme": "Light",
    "theme_manually_set": False,
    "current_step": 1,
    "syndic_list": pd.DataFrame(),
    "selected_syndic_data": pd.DataFrame(),
    "current_syndic_name": None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── System Theme Detection ────────────────────────────────────

if not st.session_state.get("theme_manually_set") and not st.session_state.get("system_theme_detected"):
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
    detected = st.query_params.get("sys_theme")
    if detected:
        st.session_state["theme"] = detected
        st.session_state["system_theme_detected"] = True
        st.rerun()

# ── Navigation ────────────────────────────────────────────────

def go_to_step(n):
    st.session_state["current_step"] = n
    st.rerun()

THEME = st.session_state["theme"]
t = get_theme(THEME)

# ── Inject CSS ────────────────────────────────────────────────

st.markdown(generate_css(THEME), unsafe_allow_html=True)

# ── Header + Stepper ──────────────────────────────────────────

render_header(THEME)
render_stepper(st.session_state["current_step"])

# ── Synchronized Range Filter (utility) ───────────────────────

def synchronized_range_filter(label, key_prefix, min_val, max_val, default_val):
    slider_key = f"{key_prefix}_slider"
    min_input_key = f"{key_prefix}_min_input"
    max_input_key = f"{key_prefix}_max_input"

    if slider_key not in st.session_state:
        st.session_state[slider_key] = default_val
        st.session_state[min_input_key] = default_val[0]
        st.session_state[max_input_key] = default_val[1]

    render_section_label(f"🏘️ {label}")

    def sync_slider():
        v_min = st.session_state[min_input_key]
        v_max = st.session_state[max_input_key]
        if v_min > v_max:
            st.session_state[max_input_key] = v_min
            v_max = v_min
        st.session_state[slider_key] = (v_min, v_max)

    def sync_inputs():
        v_min, v_max = st.session_state[slider_key]
        st.session_state[min_input_key] = v_min
        st.session_state[max_input_key] = v_max

    c_min, c_max = st.columns(2)
    with c_min:
        st.number_input("Min", min_value=min_val, max_value=max_val, key=min_input_key, on_change=sync_slider, label_visibility="collapsed")
    with c_max:
        st.number_input("Max", min_value=min_val, max_value=max_val, key=max_input_key, on_change=sync_slider, label_visibility="collapsed")
    st.slider(label, min_value=min_val, max_value=max_val, key=slider_key, on_change=sync_inputs, label_visibility="collapsed")
    return st.session_state[slider_key]


# ══════════════════════════════════════════════════════════════
# STEP 1 — CRITÈRES
# ══════════════════════════════════════════════════════════════

if st.session_state["current_step"] == 1:

    # ── Presets ───────────────────────────────────────────────
    render_section_label("Recherche rapide")

    if "saved_searches_init" not in st.session_state:
        init_saved_searches_table()
        st.session_state["saved_searches_init"] = True

    if "saved_searches_cache" not in st.session_state:
        st.session_state["saved_searches_cache"] = get_saved_searches()
    saved_searches = st.session_state["saved_searches_cache"]

    builtin_presets = [
        ("🔥 Passoires IDF", {"zones": ["H1"], "regions": ["Île-de-France"], "periods": ["Avant 1949", "1949-1974"], "lots": [20, 500], "qpv": False, "exclude_big": True, "departments": []}),
        ("🏢 Grands parcs H1", {"zones": ["H1"], "regions": [], "periods": ["Avant 1949", "1949-1974", "1975-1993"], "lots": [100, 1000], "qpv": False, "exclude_big": True, "departments": []}),
        ("📍 QPV prioritaires", {"zones": ["H1", "H2"], "regions": [], "periods": ["Avant 1949", "1949-1974"], "lots": [20, 500], "qpv": True, "exclude_big": True, "departments": []}),
    ]

    all_presets = builtin_presets + [(f"💾 {s['name']}", s["filters_json"], s["id"]) for s in saved_searches]

    nb_cols = min(len(all_presets) + 1, 6)
    cols = st.columns(nb_cols)

    for i, preset_data in enumerate(all_presets):
        if len(preset_data) == 3:
            label, filters, search_id = preset_data
        else:
            label, filters = preset_data
            search_id = None

        with cols[i % nb_cols]:
            if st.button(label, use_container_width=True, key=f"preset_{i}"):
                st.session_state["preset_zones"] = filters.get("zones", ["H1"])
                st.session_state["preset_regions"] = filters.get("regions", [])
                st.session_state["preset_periods"] = filters.get("periods", ["Avant 1949", "1949-1974"])
                lots = filters.get("lots", [20, 500])
                st.session_state["preset_lots"] = tuple(lots) if isinstance(lots, list) else lots
                if filters.get("qpv"):
                    st.session_state["preset_qpv"] = True
                if filters.get("departments"):
                    st.session_state["preset_departments"] = filters["departments"]
                st.rerun()

    # Save / Delete controls
    with st.expander("💾 Gérer mes recherches", expanded=False):
        save_col, del_col = st.columns(2)
        with save_col:
            search_name = st.text_input("Nom de la recherche", placeholder="Ex: Mon ciblage Alsace", key="save_search_name", label_visibility="collapsed")
            if st.button("💾 Sauvegarder la recherche actuelle", use_container_width=True, key="btn_save_search"):
                if search_name.strip():
                    current_filters = st.session_state.get("filters", {})
                    save_search(search_name.strip(), current_filters)
                    st.session_state.pop("saved_searches_cache", None)
                    st.success(f"Recherche « {search_name} » sauvegardée !")
                    st.rerun()
                else:
                    st.warning("Donnez un nom à votre recherche.")
        with del_col:
            if saved_searches:
                search_names_map = {s["name"]: s["id"] for s in saved_searches}
                to_delete = st.selectbox("Supprimer une recherche", options=[""] + list(search_names_map.keys()), key="del_search_select", label_visibility="collapsed")
                if to_delete and st.button("🗑️ Supprimer", use_container_width=True, key="btn_del_search"):
                    delete_saved_search(search_names_map[to_delete])
                    st.session_state.pop("saved_searches_cache", None)
                    st.success(f"Recherche « {to_delete} » supprimée.")
                    st.rerun()
            else:
                st.markdown(f'<p style="font-size:12px;color:{t["text_secondary"]};">Aucune recherche sauvegardée</p>', unsafe_allow_html=True)

    preset_zones = st.session_state.pop("preset_zones", None)
    preset_regions = st.session_state.pop("preset_regions", None)
    preset_periods = st.session_state.pop("preset_periods", None)
    preset_lots = st.session_state.pop("preset_lots", None)
    preset_qpv = st.session_state.pop("preset_qpv", None)
    preset_departments = st.session_state.pop("preset_departments", None)

    render_divider()

    col_geo, col_build = st.columns(2)

    # ── Geography ─────────────────────────────────────────────
    with col_geo:
        with st.container(border=True):
            render_section_label("🌍 Géographie")

            selected_zones = st.multiselect(
                "Zones Climatiques",
                options=["H1", "H2", "H3"],
                default=preset_zones or ["H1"],
                placeholder="Choisir zones...",
            )
            selected_regions = st.multiselect(
                "Régions",
                options=sorted(REGIONS_DEPARTMENTS.keys()),
                default=preset_regions if preset_regions is not None else [],
                placeholder="Toutes les régions...",
            )
            if selected_regions:
                available_depts = []
                for r in selected_regions:
                    available_depts.extend(REGIONS_DEPARTMENTS.get(r, []))
            else:
                available_depts = sorted(DEPARTMENTS_NAMES.keys())
            dept_options = [DEPARTMENTS_NAMES[d] for d in available_depts if d in DEPARTMENTS_NAMES]
            dept_default = []
            if preset_departments:
                dept_default = [DEPARTMENTS_NAMES[d] for d in preset_departments if d in DEPARTMENTS_NAMES and DEPARTMENTS_NAMES[d] in dept_options]
            selected_dept_labels = st.multiselect(
                "Départements",
                options=dept_options,
                default=dept_default,
                placeholder="Tous les départements...",
            )
            selected_departments = [lbl.split(" - ")[0] for lbl in selected_dept_labels]

    # ── Building Characteristics ──────────────────────────────
    with col_build:
        with st.container(border=True):
            render_section_label("🏗️ Caractéristiques")

            selected_periods = st.multiselect(
                "Périodes de construction",
                options=["Avant 1949", "1949-1974", "1975-1993", "1994-2000", "2001-2010", "Après 2011"],
                default=preset_periods or ["Avant 1949", "1949-1974"],
                placeholder="Choisir périodes...",
            )

            if preset_lots:
                st.session_state["lots_filter_slider"] = preset_lots
                st.session_state["lots_filter_min_input"] = preset_lots[0]
                st.session_state["lots_filter_max_input"] = preset_lots[1]

            selected_lots = synchronized_range_filter("Nombre de lots (Habitation)", "lots_filter", 0, 1000, (20, 500))

            render_divider()
            render_section_label("⚙️ Options avancées")
            c_opt1, c_opt2 = st.columns(2)
            with c_opt1:
                exclude_big = st.checkbox("Exclure majors (Foncia, Nexity...)", value=True)
            with c_opt2:
                qpv_only = st.checkbox("QPV uniquement", value=preset_qpv or False)

    # ── Active Filters Chips ──────────────────────────────────
    chips = []
    for z in selected_zones:
        chips.append(f"Zone {z}")
    for r in selected_regions:
        chips.append(r)
    for p in selected_periods:
        chips.append(p)
    if selected_departments:
        chips.append(f"{len(selected_departments)} dép.")
    chips.append(f"{selected_lots[0]}-{selected_lots[1]} lots")
    if exclude_big:
        chips.append("Sans majors")
    if qpv_only:
        chips.append("QPV")
    render_chips(chips)

    # ── Live Count ────────────────────────────────────────────
    live_count = count_matching_syndics(
        climate_zones=selected_zones,
        min_lots=selected_lots[0],
        max_lots=selected_lots[1],
        periods=selected_periods,
        exclude_big_syndics=exclude_big,
        qpv_only=qpv_only,
        regions=selected_regions,
        departments=selected_departments,
    )
    if live_count >= 0:
        st.markdown(
            f'<div class="cee-live-count"><span class="dot"></span> ~{live_count:,} syndics correspondent à vos critères</div>'.replace(",", " "),
            unsafe_allow_html=True,
        )

    # Keep current filters in session for save feature
    st.session_state["filters"] = {
        "zones": selected_zones,
        "regions": selected_regions,
        "departments": selected_departments,
        "lots": list(selected_lots),
        "periods": selected_periods,
        "exclude_big": exclude_big,
        "qpv": qpv_only,
    }

    # ── CTA ───────────────────────────────────────────────────
    if st.button("TROUVER LES SYNDICS", type="primary", use_container_width=True):
        with st.spinner("Analyse du gisement en cours..."):
            st.session_state["syndic_list"] = fetch_aggregated_syndics(
                climate_zones=selected_zones,
                min_lots=selected_lots[0],
                max_lots=selected_lots[1],
                periods=selected_periods,
                exclude_big_syndics=exclude_big,
                qpv_only=qpv_only,
                regions=selected_regions,
                departments=selected_departments,
            )
            go_to_step(2)


# ══════════════════════════════════════════════════════════════
# STEP 2 — RÉSULTATS
# ══════════════════════════════════════════════════════════════

elif st.session_state["current_step"] == 2:
    col_back, _ = st.columns([1, 5])
    with col_back:
        if st.button("← Modifier les critères", key="back_to_1"):
            go_to_step(1)

    df_agg = st.session_state["syndic_list"]

    if df_agg.empty:
        render_empty_state("Aucun résultat", "Modifiez vos critères et relancez la recherche.", "🔍")
    else:
        # ── KPI Bar ───────────────────────────────────────────
        k1, k2, k3 = st.columns(3)
        with k1:
            render_kpi_card("Syndics", f"{len(df_agg):,}".replace(",", " "), primary=True)
        with k2:
            render_kpi_card("Immeubles", f"{int(df_agg['nb_copros'].sum()):,}".replace(",", " "))
        with k3:
            render_kpi_card("Lots", f"{int(df_agg['total_lots'].sum()):,}".replace(",", " "))

        st.markdown('<div style="height:12px"></div>', unsafe_allow_html=True)

        # ── Search Bar ────────────────────────────────────────
        search_query = st.text_input("🔍 Rechercher un syndic...", placeholder="Nom du syndic...", label_visibility="collapsed")

        df_display = df_agg[["Syndic", "Siret", "nb_copros", "total_lots"]].rename(
            columns={"nb_copros": "Immeubles", "total_lots": "Lots"}
        )

        if search_query:
            mask = df_display["Syndic"].str.contains(search_query, case=False, na=False)
            df_display = df_display[mask]
            st.caption(f"{len(df_display)} résultat(s) pour « {search_query} »")

        # ── Results Table ─────────────────────────────────────
        event = st.dataframe(
            df_display,
            use_container_width=True,
            column_config={
                "Syndic": st.column_config.TextColumn("Nom du Syndic", width="large"),
                "Siret": st.column_config.TextColumn("SIRET", width="small"),
                "Immeubles": st.column_config.NumberColumn("Immeubles", format="%d"),
                "Lots": st.column_config.ProgressColumn(
                    "Lots", format="%d", min_value=0,
                    max_value=int(df_agg["total_lots"].max()) if not df_agg.empty else 100,
                ),
            },
            selection_mode="single-row",
            on_select="rerun",
            hide_index=True,
            height=450,
        )

        # ── Pagination Info ───────────────────────────────────
        st.caption(f"Affichage de {len(df_display)} syndics sur {len(df_agg)} résultats")

        if len(event.selection["rows"]) > 0:
            selected_index = event.selection["rows"][0]
            if search_query:
                selected_row = df_agg[df_agg["Syndic"].str.contains(search_query, case=False, na=False)].iloc[selected_index]
            else:
                selected_row = df_agg.iloc[selected_index]
            st.session_state["selected_syndic_row"] = selected_row
            go_to_step(3)


# ══════════════════════════════════════════════════════════════
# STEP 3 — INTEL
# ══════════════════════════════════════════════════════════════

elif st.session_state["current_step"] == 3:
    syndic_row = st.session_state.get("selected_syndic_row")
    if syndic_row is None:
        go_to_step(2)

    syndic_name = syndic_row["Syndic"]
    syndic_siret = syndic_row["Siret"]

    col_back, col_title = st.columns([1, 6])
    with col_back:
        if st.button("← Liste", key="back_to_2"):
            go_to_step(2)
    with col_title:
        st.markdown(f"### {syndic_name}")

    from core.pappers_connector import get_syndic_info
    pappers_info = get_syndic_info(syndic_siret)

    filters = st.session_state.get("filters", {})
    if st.session_state["current_syndic_name"] != syndic_name:
        st.session_state["selected_syndic_data"] = fetch_data_by_syndic(
            syndic_name,
            filters.get("zones", ["H1"]),
            filters.get("lots", (0, 1000))[0],
            filters.get("lots", (0, 1000))[1],
            periods=filters.get("periods"),
            exclude_big_syndics=filters.get("exclude_big", True),
            qpv_only=filters.get("qpv", False),
            regions=filters.get("regions"),
            departments=filters.get("departments"),
        )
        st.session_state["current_syndic_name"] = syndic_name

    tab_intel, tab_contacts, tab_parc_cible, tab_parc_all = st.tabs([
        "🕵️ Intelligence", "👥 Contacts", "🎯 Parc ciblé", "🏢 Tout le parc"
    ])

    # ──────────────────────────────────────────────────────────
    # TAB: Intelligence
    # ──────────────────────────────────────────────────────────

    with tab_intel:
        from core.syndic_intel import SyndicIntelligence, init_enrichment_tables
        from core.enrichment_manager import EnrichmentManager

        if "enrichment_tables_initialized" not in st.session_state:
            init_enrichment_tables()
            st.session_state["enrichment_tables_initialized"] = True

        intel_engine = SyndicIntelligence()
        enricher = EnrichmentManager()

        # ── Company Card (Pappers) ────────────────────────────
        dirigeant = f"{pappers_info.get('prenom_dirigeant', '')} {pappers_info.get('nom_dirigeant', '')}".strip()
        ca = pappers_info.get("ca_annuel")
        ca_str = f"{ca / 1_000_000:.1f} M€" if ca else "—"
        cat = pappers_info.get("categorie_entreprise") or "—"
        ape = pappers_info.get("code_ape") or "—"
        tel_p = pappers_info.get("telephone") or "—"
        email_p = pappers_info.get("email") or "—"
        web_p = pappers_info.get("sites_internet") or "—"

        render_info_card(
            "Fiche entreprise",
            f'<p style="margin:0 0 4px 0;"><strong>Dirigeant</strong> : {dirigeant or "—"}</p>'
            f'<p style="margin:0 0 4px 0;"><strong>CA</strong> : {ca_str} · <strong>Catégorie</strong> : {cat} · <strong>APE</strong> : {ape}</p>'
            f'<p style="margin:0;font-size:12px;color:{t["text_secondary"]};">📞 {tel_p} · 📧 {email_p} · 🌐 {web_p}</p>',
            icon="🏛️",
        )

        # ── Intelligence Data ─────────────────────────────────
        intel_key = f"intel_data_{syndic_siret}"
        if intel_key not in st.session_state:
            cached_intel = intel_engine.get_cached_intel(syndic_siret)
            if cached_intel:
                st.session_state[intel_key] = cached_intel

        intel_data = st.session_state.get(intel_key)

        if not intel_data:
            render_divider()
            if st.button("🔬 Lancer l'Intelligence", type="primary", use_container_width=True):
                status_box = st.empty()
                progress_logs = []

                def on_status(msg):
                    progress_logs.append(msg)
                    log_html = "".join(
                        f'<p style="margin:2px 0;font-size:12px;color:{t["text_secondary"]};">{m}</p>'
                        for m in progress_logs[-10:]
                    )
                    status_box.markdown(
                        f'<div class="cee-card" style="padding:12px;max-height:250px;overflow-y:auto;">'
                        f'<p class="cee-card-title" style="margin-bottom:6px;">🔄 Progression du scraping</p>'
                        f'{log_html}</div>',
                        unsafe_allow_html=True,
                    )

                with st.spinner("Analyse en cours... Scraping, réseaux sociaux, IA..."):
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
                            candidate = sites.split(",")[0].strip().replace("https://", "").replace("http://", "").replace("www.", "").strip("/")
                            from core.syndic_intel import URL_BLACKLIST
                            if candidate and not any(bl in candidate.lower() for bl in URL_BLACKLIST):
                                domain = candidate

                    city = st.session_state["selected_syndic_data"].iloc[0]["commune"] if not st.session_state["selected_syndic_data"].empty else ""
                    result = intel_engine.run_intelligence(
                        siret=syndic_siret, name=syndic_name, city=city, domain=domain,
                        pappers_data=pappers_info,
                        nb_copros=int(syndic_row.get("nb_copros", 0)),
                        total_lots=int(syndic_row.get("total_lots", 0)),
                        status_callback=on_status,
                    )
                    if result:
                        st.session_state[intel_key] = result
                        st.rerun()
            else:
                render_empty_state("Intelligence non lancée", "Cliquez sur le bouton ci-dessus pour analyser ce syndic.", "🔬")
        else:
            analysis = intel_data.get("llm_analysis_json", {})
            if isinstance(analysis, str):
                try:
                    analysis = json.loads(analysis)
                except Exception:
                    analysis = {}

            # ── Score + KPIs Row ──────────────────────────────
            score = analysis.get("score_prospection", "?")
            maturite = (analysis.get("maturite_digitale") or "").strip() or "—"
            taille = (analysis.get("taille_estimee") or "").strip() or "—"

            col_gauge, col_kpis = st.columns([1, 2])
            with col_gauge:
                render_score_gauge(score)
                st.markdown(
                    '<p class="cee-gauge-hint">Basé sur : taille du parc, maturité digitale, présence web, accessibilité contacts</p>',
                    unsafe_allow_html=True,
                )
            with col_kpis:
                kc1, kc2 = st.columns(2)
                with kc1:
                    st.markdown(
                        f'<div class="cee-card" style="text-align:center;">'
                        f'<p class="cee-card-title">Maturité digitale</p>'
                        f'<div style="margin-top:4px;">{maturite_tag_html(maturite)}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                with kc2:
                    st.markdown(
                        f'<div class="cee-card" style="text-align:center;">'
                        f'<p class="cee-card-title">Taille estimée</p>'
                        f'<p style="font-size:16px;font-weight:700;margin:4px 0 0 0;">{taille}</p>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                # Contact info from scraping
                tel_principal = analysis.get("telephone_principal", "") or ""
                email_principal = analysis.get("email_principal", "") or ""
                scraped_phones = intel_data.get("scraped_phones", [])
                scraped_emails = intel_data.get("scraped_emails", [])
                if isinstance(scraped_phones, str):
                    try: scraped_phones = json.loads(scraped_phones)
                    except Exception: scraped_phones = []
                if isinstance(scraped_emails, str):
                    try: scraped_emails = json.loads(scraped_emails)
                    except Exception: scraped_emails = []

                has_contact = tel_principal or email_principal or scraped_phones or scraped_emails
                if has_contact:
                    parts = []
                    if tel_principal:
                        parts.append(f"📞 <strong>{tel_principal}</strong>")
                    for p in (scraped_phones or [])[:1]:
                        if p and p != (tel_principal or "").replace(" ", "").replace(".", ""):
                            parts.append(f"📞 {p} <small>(site)</small>")
                    if email_principal:
                        parts.append(f"📧 <strong>{email_principal}</strong>")
                    for e in (scraped_emails or [])[:1]:
                        if e and e != (email_principal or "").lower():
                            parts.append(f"📧 {e} <small>(site)</small>")
                    render_info_card("Coordonnées vérifiées", " · ".join(parts), icon="📇")

            # ── Identified Domain ────────────────────────────
            id_domain = intel_data.get("identified_domain", "")
            if id_domain:
                domain_url = f"https://{id_domain}"
                accent_color = t["accent"]
                render_info_card(
                    "Site internet identifié",
                    f'🌐 <a href="{domain_url}" target="_blank" style="color:{accent_color};text-decoration:none;font-weight:600;">'
                    f'{id_domain}</a>'
                    f' <span style="font-size:11px;color:{t["text_secondary"]};">(source: {intel_data.get("domain_source", "?")})</span>',
                    icon="🔗",
                )

            # ── Summary + Approach ────────────────────────────
            resume = (analysis.get("resume_activite") or "").strip()
            angle = (analysis.get("angle_approche_recommande") or "").strip()
            if resume:
                render_info_card("Résumé", resume, icon="📝")
            if angle:
                render_info_card("Angle d'approche recommandé", angle, accent_border=True, icon="🎯")

            # ── Strengths / Weaknesses ────────────────────────
            points_forts = [x for x in (analysis.get("points_forts") or []) if isinstance(x, str) and x.strip()]
            points_faibles = [x for x in (analysis.get("points_faibles") or []) if isinstance(x, str) and x.strip() and "LLM indisponible" not in x]
            if points_forts or points_faibles:
                col_pf, col_pw = st.columns(2)
                with col_pf:
                    if points_forts:
                        items = "".join(f'<p style="font-size:13px;margin:3px 0;">✅ {pf}</p>' for pf in points_forts)
                        render_info_card("Points forts", items, icon="💪")
                with col_pw:
                    if points_faibles:
                        items = "".join(f'<p style="font-size:13px;margin:3px 0;">⚠️ {pw}</p>' for pw in points_faibles)
                        render_info_card("Points faibles", items, icon="🔻")

            # ── Web Presence ──────────────────────────────────
            socials = analysis.get("reseaux_sociaux") or {}
            has_social = any(isinstance(v, dict) and v.get("url") for v in socials.values())
            if has_social:
                social_parts = []
                for platform, info in socials.items():
                    if not isinstance(info, dict) or not info.get("url"):
                        continue
                    url = info["url"]
                    label = platform.replace("_", " ").title()
                    actif = info.get("actif", False)
                    dot = "🟢" if actif else "⚪"
                    social_parts.append(
                        f'<p style="font-size:13px;margin:3px 0;">{dot} <strong>{label}</strong> '
                        f'<a href="{url}" target="_blank" style="color:{t["accent"]};text-decoration:none;">'
                        f'{url[:50]}{"…" if len(url) > 50 else ""}</a></p>'
                    )
                render_info_card("Présence web", "".join(social_parts), icon="🌐")

            # ── Reputation ────────────────────────────────────
            reputation = (analysis.get("reputation_en_ligne") or "").strip()
            if reputation and reputation.lower() not in ("non analysée", "aucun avis trouvé"):
                render_info_card("Réputation en ligne", reputation, icon="⭐")

            # ── Key Contacts from LLM ─────────────────────────
            contacts_cles = [x for x in (analysis.get("contacts_cles") or []) if isinstance(x, dict) and (x.get("nom") or x.get("email"))]
            if contacts_cles:
                ck_parts = []
                for ck in contacts_cles[:5]:
                    nom = (ck.get("nom") or "").strip() or "—"
                    poste = (ck.get("poste") or "").strip()
                    ck_email = (ck.get("email") or "").strip()
                    ck_tel = (ck.get("telephone") or "").strip()
                    ck_li = (ck.get("linkedin") or "").strip()
                    line = f'<strong>{nom}</strong>'
                    if poste:
                        line += f' — {poste}'
                    details = []
                    if ck_email:
                        details.append(f"📧 {ck_email}")
                    if ck_tel:
                        details.append(f"📞 {ck_tel}")
                    if ck_li:
                        details.append(f'<a href="{ck_li}" target="_blank" style="color:{t["accent"]};">LinkedIn</a>')
                    if details:
                        line += f'<br><span style="font-size:12px;color:{t["text_secondary"]};">{" · ".join(details)}</span>'
                    pertinence = (ck.get("pertinence_cee") or "").strip()
                    if pertinence:
                        line += f'<br><span style="font-size:11px;color:{t["text_tertiary"]};font-style:italic;">{pertinence}</span>'
                    ck_parts.append(f'<div style="padding:8px 0;border-top:1px solid {t["separator"]};">{line}</div>')
                render_info_card("Contacts clés (prospection CEE)", "".join(ck_parts), icon="👥")

            # ── Services & Zones ──────────────────────────────
            services = [s for s in (analysis.get("services_proposes") or []) if isinstance(s, str) and s.strip()]
            zones = [z for z in (analysis.get("zones_geographiques") or []) if isinstance(z, str) and z.strip()]
            if services or zones:
                row_s, row_z = st.columns(2)
                with row_s:
                    if services:
                        render_info_card("Services", " · ".join(services[:8]), icon="🔧")
                with row_z:
                    if zones:
                        render_info_card("Zones géographiques", " · ".join(zones[:8]), icon="📍")

            # ── Google Maps Data ──────────────────────────────
            maps_json = intel_data.get("google_maps_json")
            if isinstance(maps_json, str):
                try:
                    maps_json = json.loads(maps_json)
                except Exception:
                    maps_json = None
            if maps_json and isinstance(maps_json, dict):
                maps_parts = []
                maps_name = maps_json.get("name", "")
                maps_stars = maps_json.get("stars")
                maps_ratings = maps_json.get("ratings", 0)
                maps_address = maps_json.get("address", "")
                maps_phone = maps_json.get("phone", "")
                maps_url = maps_json.get("url", "")

                if maps_name:
                    star_display = ""
                    if maps_stars is not None:
                        star_display = f" — ⭐ {maps_stars}/5 ({maps_ratings} avis)"
                    maps_parts.append(f"<strong>{maps_name}</strong>{star_display}")
                if maps_address:
                    maps_parts.append(f"📍 {maps_address}")
                if maps_phone:
                    maps_parts.append(f"📞 {maps_phone}")
                if maps_url:
                    accent = t["accent"]
                    maps_parts.append(
                        f'🌐 <a href="{maps_url}" target="_blank" style="color:{accent};text-decoration:none;">'
                        f'{maps_url[:60]}{"…" if len(maps_url) > 60 else ""}</a>'
                    )
                render_info_card("Google Maps", "<br>".join(maps_parts), icon="🗺️", accent_border=True)

            # ── Raw Scraping Data (Debug) ─────────────────────
            with st.expander("🔍 Données brutes du scraping (debug)", expanded=False):
                serp_json = intel_data.get("serp_results_json")
                if isinstance(serp_json, str):
                    try:
                        serp_json = json.loads(serp_json)
                    except Exception:
                        serp_json = None

                identified_domain = intel_data.get("identified_domain", "")
                domain_source = intel_data.get("domain_source", "")

                st.markdown(f"**Domaine identifié :** `{identified_domain or 'Aucun'}` (source: `{domain_source}`)")

                serp_queries = intel_data.get("serp_queries", [])
                if serp_queries:
                    queries_str = " · ".join(f'`{q}`' for q in serp_queries)
                    st.markdown(f"**Requêtes SERP :** {queries_str}")

                if serp_json:
                    st.markdown("**Résultats Google SERP :**")
                    for idx_s, sr in enumerate(serp_json, 1):
                        sr_title = sr.get("title", "Sans titre")
                        sr_link = sr.get("link", "")
                        sr_snippet = sr.get("snippet", "")[:150]
                        st.markdown(
                            f"{idx_s}. **{sr_title}**  \n"
                            f"   [{sr_link}]({sr_link})  \n"
                            f"   _{sr_snippet}_"
                        )
                else:
                    st.markdown("**Résultats Google SERP :** Aucun")

                if maps_json:
                    st.markdown("**Données Google Maps (JSON brut) :**")
                    st.json(maps_json)
                else:
                    st.markdown("**Données Google Maps :** Aucune")

                raw_phones = intel_data.get("scraped_phones", [])
                raw_emails = intel_data.get("scraped_emails", [])
                if isinstance(raw_phones, str):
                    try:
                        raw_phones = json.loads(raw_phones)
                    except Exception:
                        raw_phones = []
                if isinstance(raw_emails, str):
                    try:
                        raw_emails = json.loads(raw_emails)
                    except Exception:
                        raw_emails = []

                st.markdown(f"**Téléphones scrapés :** {', '.join(raw_phones) if raw_phones else 'Aucun'}")
                st.markdown(f"**Emails scrapés :** {', '.join(raw_emails) if raw_emails else 'Aucun'}")

                # Scraped contacts from LLM extraction
                scraped_contacts_raw = intel_data.get("scraped_contacts_json", [])
                if isinstance(scraped_contacts_raw, str):
                    try:
                        scraped_contacts_raw = json.loads(scraped_contacts_raw)
                    except Exception:
                        scraped_contacts_raw = []
                if scraped_contacts_raw:
                    st.markdown(f"**Contacts extraits du site web (LLM) : {len(scraped_contacts_raw)} contact(s)**")
                    for sc_idx, sc in enumerate(scraped_contacts_raw, 1):
                        sc_nom = sc.get("nom", "—")
                        sc_poste = sc.get("poste", "—")
                        sc_email = sc.get("email", "")
                        sc_tel = sc.get("telephone", "")
                        sc_details = []
                        if sc_email:
                            sc_details.append(f"📧 {sc_email}")
                        if sc_tel:
                            sc_details.append(f"📞 {sc_tel}")
                        detail_str = f" — {' · '.join(sc_details)}" if sc_details else ""
                        st.markdown(f"{sc_idx}. **{sc_nom}** — _{sc_poste}_{detail_str}")
                else:
                    st.markdown("**Contacts extraits du site web (LLM) :** Aucun")

                raw_content = intel_data.get("raw_website_content", "")
                if raw_content:
                    st.markdown(f"**Contenu brut du site** ({len(raw_content)} caractères) :")
                    st.text_area("Contenu brut", raw_content[:5000], height=200, disabled=True, label_visibility="collapsed")

            # ── Refresh Button ────────────────────────────────
            st.markdown('<div style="height:8px;"></div>', unsafe_allow_html=True)
            if st.button("🔄 Réactualiser l'analyse", key="refresh_intel"):
                refresh_status_box = st.empty()
                refresh_logs = []

                def on_refresh_status(msg):
                    refresh_logs.append(msg)
                    log_html = "".join(
                        f'<p style="margin:2px 0;font-size:12px;color:{t["text_secondary"]};">{m}</p>'
                        for m in refresh_logs[-10:]
                    )
                    refresh_status_box.markdown(
                        f'<div class="cee-card" style="padding:12px;max-height:250px;overflow-y:auto;">'
                        f'<p class="cee-card-title" style="margin-bottom:6px;">🔄 Progression du scraping</p>'
                        f'{log_html}</div>',
                        unsafe_allow_html=True,
                    )

                with st.spinner("Réactualisation..."):
                    enrich_key = f"enrich_data_{syndic_siret}"
                    if enrich_key not in st.session_state:
                        cached_enrich = enricher.get_cached_data(syndic_siret)
                        if cached_enrich:
                            st.session_state[enrich_key] = cached_enrich
                    domain = None
                    enrich_data_r = st.session_state.get(enrich_key)
                    if enrich_data_r:
                        domain = enrich_data_r.get("domain")
                    city = st.session_state["selected_syndic_data"].iloc[0]["commune"] if not st.session_state["selected_syndic_data"].empty else ""
                    result = intel_engine.run_intelligence(
                        siret=syndic_siret, name=syndic_name, city=city,
                        domain=domain, pappers_data=pappers_info,
                        nb_copros=int(syndic_row.get("nb_copros", 0)),
                        total_lots=int(syndic_row.get("total_lots", 0)),
                        force_refresh=True,
                        status_callback=on_refresh_status,
                    )
                    if result:
                        st.session_state[intel_key] = result
                        st.rerun()

    # ──────────────────────────────────────────────────────────
    # TAB: Contacts
    # ──────────────────────────────────────────────────────────

    with tab_contacts:
        from core.enrichment_manager import EnrichmentManager as EM2

        all_contacts = []
        seen_keys = set()

        def _dedup_key(c):
            email = (c.get("email") or "").strip().lower()
            if email:
                return f"email:{email}"
            nom = (c.get("nom") or "").strip().lower()
            if not nom:
                first = (c.get("first_name") or "")
                last = (c.get("last_name") or "")
                nom = f"{first} {last}".strip().lower()
            return f"nom:{nom}" if nom else None

        def _add_contacts(contacts_list):
            for c in contacts_list:
                key = _dedup_key(c)
                if key and key not in seen_keys:
                    seen_keys.add(key)
                    all_contacts.append(c)

        # Source 1: Persistent enrichment contacts (syndic_contacts table)
        persistent_contacts = intel_engine.get_contacts(syndic_siret)
        if persistent_contacts:
            _add_contacts(persistent_contacts)

        # Source 2: Apollo contacts from intelligence pipeline
        intel_contacts_raw = (intel_data or {}).get("apollo_contacts_json", []) if intel_data else []
        if isinstance(intel_contacts_raw, str):
            try:
                intel_contacts_raw = json.loads(intel_contacts_raw)
            except Exception:
                intel_contacts_raw = []
        if intel_contacts_raw:
            _add_contacts(intel_contacts_raw)

        # Source 3: Enrichment manager contacts (legacy)
        enricher2 = EM2()
        enrich_key = f"enrich_data_{syndic_siret}"
        if enrich_key not in st.session_state:
            cached = enricher2.get_cached_data(syndic_siret)
            if cached:
                st.session_state[enrich_key] = cached

        data_enrich = st.session_state.get(enrich_key)
        if data_enrich:
            enrich_contacts = data_enrich.get("contacts_json", [])
            if isinstance(enrich_contacts, str):
                try:
                    enrich_contacts = json.loads(enrich_contacts)
                except Exception:
                    enrich_contacts = []
            _add_contacts(enrich_contacts)

        if not all_contacts and not data_enrich:
            if st.button("🚀 Rechercher les contacts", type="primary", use_container_width=True):
                with st.spinner("Recherche de contacts (Apollo)..."):
                    city = st.session_state["selected_syndic_data"].iloc[0]["commune"] if not st.session_state["selected_syndic_data"].empty else ""
                    fresh = enricher2.enrich_syndic(syndic_siret, syndic_name, city, pappers_data=pappers_info)
                    if fresh:
                        st.session_state[enrich_key] = fresh
                        st.rerun()
        elif not all_contacts:
            render_empty_state("Aucun contact trouvé", "Aucun contact n'a été identifié pour ce syndic.", "👤")
        else:
            st.markdown(f'<p style="font-size:13px;color:{t["text_secondary"]};margin-bottom:12px;">{len(all_contacts)} contact(s) trouvé(s)</p>', unsafe_allow_html=True)

            if "selected_contacts" not in st.session_state:
                st.session_state["selected_contacts"] = set()

            select_all = st.checkbox("Tout sélectionner", key="select_all_contacts")

            for idx, ct in enumerate(all_contacts[:20]):
                col_check, col_card, col_action = st.columns([0.5, 4, 1])
                with col_check:
                    checked = st.checkbox("", key=f"ct_check_{idx}", value=select_all, label_visibility="collapsed")
                    if checked:
                        st.session_state["selected_contacts"].add(idx)
                    elif idx in st.session_state.get("selected_contacts", set()):
                        st.session_state["selected_contacts"].discard(idx)
                with col_card:
                    st.markdown(render_contact_card_html(ct, THEME), unsafe_allow_html=True)
                with col_action:
                    st.markdown('<div style="height:16px;"></div>', unsafe_allow_html=True)
                    if st.button("🎯 Prospecter", key=f"sel_{idx}"):
                        st.session_state["selected_contact"] = ct
                        go_to_step(4)

            selected_set = st.session_state.get("selected_contacts", set())
            if len(selected_set) > 1:
                st.markdown(f'<div style="height:8px;"></div>', unsafe_allow_html=True)
                if st.button(f"🎯 Prospecter la sélection ({len(selected_set)} contacts)", type="primary"):
                    first_idx = min(selected_set)
                    st.session_state["selected_contact"] = all_contacts[first_idx]
                    go_to_step(4)

    # ──────────────────────────────────────────────────────────
    # TAB: Parc ciblé
    # ──────────────────────────────────────────────────────────

    with tab_parc_cible:
        df_parc = st.session_state["selected_syndic_data"]

        if df_parc.empty:
            render_empty_state("Aucune copropriété ciblée", "Les filtres actuels ne retournent aucun résultat pour ce syndic.", "🏢")
        else:
            # Stats summary
            nb_copros = len(df_parc)
            communes_uniques = df_parc["commune"].nunique() if "commune" in df_parc.columns else 0
            lots_col = "nombre_de_lots_a_usage_d_habitation"
            lots_moy = int(df_parc[lots_col].mean()) if lots_col in df_parc.columns else 0

            s1, s2, s3 = st.columns(3)
            with s1:
                render_kpi_card("Bâtiments ciblés", nb_copros, primary=True)
            with s2:
                render_kpi_card("Communes", communes_uniques)
            with s3:
                render_kpi_card("Lots moyens", lots_moy)

            st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)

            # Cards grid
            cols_per_row = 3
            for i in range(0, len(df_parc), cols_per_row):
                cols = st.columns(cols_per_row)
                for j, col in enumerate(cols):
                    if i + j < len(df_parc):
                        row = df_parc.iloc[i + j]
                        copro_name = row.get("nom_copropriete", "") or row.get("numero_immatriculation_copropriete", f"Copro #{i+j+1}")
                        address = f"{row.get('adresse_de_reference', '')} {row.get('commune', '')}".strip()
                        lots = int(row.get(lots_col, 0))
                        period = row.get("periode_de_construction", "")
                        with col:
                            render_copro_card(str(copro_name), address, lots, str(period))

    # ──────────────────────────────────────────────────────────
    # TAB: Tout le parc
    # ──────────────────────────────────────────────────────────

    with tab_parc_all:
        all_parc_key = f"all_parc_{syndic_name}"
        if all_parc_key not in st.session_state:
            with st.spinner("Chargement du parc complet..."):
                st.session_state[all_parc_key] = fetch_all_data_by_syndic(syndic_name)

        df_all = st.session_state[all_parc_key]

        if df_all.empty:
            render_empty_state("Aucune donnée", "Aucune copropriété trouvée pour ce syndic.", "🏢")
        else:
            lots_col = "nombre_de_lots_a_usage_d_habitation"
            nb_all = len(df_all)
            communes_all = df_all["commune"].nunique() if "commune" in df_all.columns else 0
            lots_total_all = int(df_all[lots_col].sum()) if lots_col in df_all.columns else 0

            s1, s2, s3 = st.columns(3)
            with s1:
                render_kpi_card("Total bâtiments", nb_all, primary=True)
            with s2:
                render_kpi_card("Communes", communes_all)
            with s3:
                render_kpi_card("Total lots", f"{lots_total_all:,}".replace(",", " "))

            st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)

            # Column selection for readability
            display_cols = []
            col_mapping = {}
            desired = {
                "numero_immatriculation_copropriete": "N° Immat.",
                "nom_copropriete": "Nom",
                "adresse_de_reference": "Adresse",
                "commune": "Commune",
                "code_officiel_departement": "Dép.",
                "nombre_de_lots_a_usage_d_habitation": "Lots hab.",
                "nombre_total_de_lots": "Lots total",
                "periode_de_construction": "Période",
            }
            for col_name, label in desired.items():
                if col_name in df_all.columns:
                    display_cols.append(col_name)
                    col_mapping[col_name] = label

            if display_cols:
                df_show = df_all[display_cols].rename(columns=col_mapping)
            else:
                df_show = df_all

            # Filter by commune
            if "commune" in df_all.columns:
                commune_filter = st.text_input("Filtrer par commune...", key="commune_filter_all", placeholder="Nom de commune...", label_visibility="collapsed")
                if commune_filter:
                    mask = df_show["Commune"].str.contains(commune_filter, case=False, na=False) if "Commune" in df_show.columns else pd.Series([True] * len(df_show))
                    df_show = df_show[mask]

            st.dataframe(df_show, use_container_width=True, hide_index=True, height=400)


# ══════════════════════════════════════════════════════════════
# STEP 4 — PACK
# ══════════════════════════════════════════════════════════════

elif st.session_state["current_step"] == 4:
    col_back, col_new = st.columns([1, 4])
    with col_back:
        if st.button("← Contacts"):
            go_to_step(3)
    with col_new:
        if st.button("🔄 Nouvelle recherche"):
            st.session_state["syndic_list"] = pd.DataFrame()
            go_to_step(1)

    contact = st.session_state.get("selected_contact", {})
    syndic_row = st.session_state.get("selected_syndic_row", {})
    syndic_siret_pack = syndic_row.get("Siret", "")

    # Get intel data
    intel_key_pack = f"intel_data_{syndic_siret_pack}"
    intel_pack = st.session_state.get(intel_key_pack, {})
    analysis_pack = intel_pack.get("llm_analysis_json", {})
    if isinstance(analysis_pack, str):
        try:
            analysis_pack = json.loads(analysis_pack)
        except Exception:
            analysis_pack = {}

    llm_icebreaker = analysis_pack.get("email_icebreaker", "")
    score_pack = analysis_pack.get("score_prospection", "?")
    angle_pack = analysis_pack.get("angle_approche_recommande", "")

    first_name = contact.get("first_name", "Bonjour")
    fallback_ice = f"Objet : {syndic_row.get('Syndic', '')}\n\nBonjour {first_name},\n\nJ'ai identifié {int(syndic_row.get('nb_copros', 0))} de vos immeubles à fort potentiel CEE..."
    ice = llm_icebreaker if llm_icebreaker else fallback_ice

    c1, c2 = st.columns([2, 1])

    with c1:
        # ── Email Preview ─────────────────────────────────────
        st.markdown("### ✉️ Email de prospection")

        if llm_icebreaker:
            st.markdown(
                f'<span class="cee-tag cee-tag-green" style="margin-bottom:8px;">✨ Personnalisé par IA</span>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<span class="cee-tag cee-tag-gray" style="margin-bottom:8px;">📝 Template standard</span>',
                unsafe_allow_html=True,
            )

        contact_email = contact.get("email", "")
        contact_name = f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip()

        st.markdown(
            f'<div class="cee-email-preview">'
            f'<div class="cee-email-header">'
            f'<strong>À :</strong> {contact_email or "—"}<br>'
            f'<strong>De :</strong> Votre nom<br>'
            f'<strong>Objet :</strong> Rénovation énergétique — {syndic_row.get("Syndic", "")}'
            f'</div>'
            f'<div class="cee-email-body">{ice}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        st.markdown('<div style="height:8px;"></div>', unsafe_allow_html=True)

        # ── Action Buttons ────────────────────────────────────
        btn1, btn2, btn3 = st.columns(3)
        with btn1:
            if st.button("📋 Copier", use_container_width=True):
                st.toast("Contenu copié !")
        with btn2:
            mailto = f"mailto:{contact_email}?subject=Rénovation%20énergétique%20—%20{syndic_row.get('Syndic', '')}"
            st.markdown(
                f'<a href="{mailto}" target="_blank" style="display:block;text-align:center;padding:8px;'
                f'background:{t["card_bg"]};border:1px solid {t["card_border"]};border-radius:8px;'
                f'text-decoration:none;color:{t["text"]};font-size:13px;font-weight:500;">📨 Ouvrir mail</a>',
                unsafe_allow_html=True,
            )
        with btn3:
            tone = st.selectbox("Ton", ["Professionnel", "Décontracté", "Technique"], label_visibility="collapsed", key="tone_select")
            if st.button("🔄 Régénérer", use_container_width=True, key="regen_email"):
                st.toast(f"Régénération en ton {tone.lower()} — fonctionnalité à venir")

        # ── Approach Angle ────────────────────────────────────
        if angle_pack:
            render_info_card("Angle d'approche", angle_pack, accent_border=True, icon="🎯")

        # ── Data Points Used ──────────────────────────────────
        with st.expander("📊 Données utilisées pour la personnalisation"):
            data_points = []
            if analysis_pack.get("resume_activite"):
                data_points.append(f"**Résumé activité** : {analysis_pack['resume_activite'][:100]}...")
            if analysis_pack.get("taille_estimee"):
                data_points.append(f"**Taille** : {analysis_pack['taille_estimee']}")
            if analysis_pack.get("maturite_digitale"):
                data_points.append(f"**Maturité digitale** : {analysis_pack['maturite_digitale']}")
            data_points.append(f"**Copropriétés** : {syndic_row.get('nb_copros', 0)}")
            data_points.append(f"**Lots** : {syndic_row.get('total_lots', 0)}")
            if analysis_pack.get("points_forts"):
                data_points.append(f"**Points forts** : {', '.join(analysis_pack['points_forts'][:3])}")
            for dp in data_points:
                st.markdown(f"- {dp}")

    with c2:
        # ── Contact Details ───────────────────────────────────
        st.markdown("### 📦 Contact")
        render_info_card(
            "Destinataire",
            f'<p style="font-size:15px;font-weight:600;margin:0;">{contact_name or "—"}</p>'
            f'<p style="font-size:12px;color:{t["text_secondary"]};margin:4px 0 0 0;">{contact.get("title", "Contact")}</p>'
            f'<p style="font-size:12px;margin:4px 0 0 0;">📧 {contact_email or "—"}</p>'
            + (f'<p style="font-size:12px;margin:2px 0 0 0;"><a href="{contact.get("linkedin_url")}" target="_blank" style="color:{t["accent"]};">🔗 LinkedIn</a></p>' if contact.get("linkedin_url") else ""),
            icon="👤",
        )

        # ── Target Stats ─────────────────────────────────────
        render_kpi_card("Bâtiments cibles", f'{int(syndic_row.get("nb_copros", 0))}', subtitle=f'{int(syndic_row.get("total_lots", 0))} lots')

        # ── Score ─────────────────────────────────────────────
        if isinstance(score_pack, (int, float)):
            render_score_gauge(score_pack, size=100)
