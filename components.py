"""
CEE Hunter — Reusable UI Components
All rendering functions output HTML via st.markdown(unsafe_allow_html=True).
"""

import math
import streamlit as st
from styles import PALETTE, get_theme, score_color, RADIUS


# ── Header ────────────────────────────────────────────────────

def render_header(theme_name: str):
    """Top bar: logo + subtitle + theme toggle."""
    t = get_theme(theme_name)
    h1, h2, h3 = st.columns([3, 5, 1])
    with h1:
        st.markdown(
            f'<div class="cee-header-logo">CEE HUNTER <span>PRO</span></div>',
            unsafe_allow_html=True,
        )
    with h2:
        st.markdown(
            '<div class="cee-header-subtitle">Prospection intelligente — Syndics de copropriété</div>',
            unsafe_allow_html=True,
        )
    with h3:
        icon = "☀️" if theme_name == "Dark" else "🌙"
        if st.button(icon, key="theme_toggle", help="Changer le thème"):
            st.session_state["theme"] = "Light" if theme_name == "Dark" else "Dark"
            st.session_state["theme_manually_set"] = True
            st.rerun()
    st.markdown(f'<div style="border-bottom:1px solid {t["separator"]};margin-bottom:16px;"></div>', unsafe_allow_html=True)


# ── Stepper ───────────────────────────────────────────────────

STEP_LABELS = ["CRITÈRES", "RÉSULTATS", "INTEL", "PACK"]

def render_stepper(current_step: int):
    """4-step progress bar with numbered circles and connectors."""
    parts = []
    for i, label in enumerate(STEP_LABELS, start=1):
        if i < current_step:
            cls = "done"
            num_html = "✓"
        elif i == current_step:
            cls = "active"
            num_html = str(i)
        else:
            cls = "pending"
            num_html = str(i)
        parts.append(
            f'<div class="cee-step">'
            f'<div class="cee-step-number {cls}">{num_html}</div>'
            f'<div class="cee-step-label {cls}">{label}</div>'
            f'</div>'
        )
        if i < len(STEP_LABELS):
            conn_cls = "done" if i < current_step else "pending"
            parts.append(f'<div class="cee-step-connector {conn_cls}"></div>')
    st.markdown(f'<div class="cee-stepper">{"".join(parts)}</div>', unsafe_allow_html=True)


# ── KPI Card ──────────────────────────────────────────────────

def render_kpi_card(label: str, value, subtitle: str = "", primary: bool = False):
    """Single KPI metric card."""
    cls_extra = " cee-kpi-primary" if primary else ""
    val_cls = " primary" if primary else ""
    sub_html = f'<p class="cee-kpi-sub">{subtitle}</p>' if subtitle else ""
    st.markdown(
        f'<div class="cee-kpi{cls_extra}">'
        f'<p class="cee-kpi-label">{label}</p>'
        f'<p class="cee-kpi-value{val_cls}">{value}</p>'
        f'{sub_html}'
        f'</div>',
        unsafe_allow_html=True,
    )


# ── Score Gauge (SVG arc) ────────────────────────────────────

def render_score_gauge(score, max_score: int = 10, size: int = 120):
    """Circular arc gauge for prospection score."""
    if not isinstance(score, (int, float)):
        score_val = 0
    else:
        score_val = max(0, min(score, max_score))

    color = score_color(score_val)
    pct = score_val / max_score
    r = (size - 12) / 2
    cx = size / 2
    cy = size / 2

    # Arc from -210° to +30° (240° sweep)
    start_angle = -210
    sweep = 240
    end_angle_actual = start_angle + sweep * pct

    def polar_to_cart(angle_deg):
        rad = math.radians(angle_deg)
        return cx + r * math.cos(rad), cy - r * math.sin(rad)

    # Background arc
    bg_start = polar_to_cart(start_angle)
    bg_end = polar_to_cart(start_angle + sweep)
    large_bg = 1 if sweep > 180 else 0
    bg_path = f"M {bg_start[0]:.1f} {bg_start[1]:.1f} A {r:.1f} {r:.1f} 0 {large_bg} 1 {bg_end[0]:.1f} {bg_end[1]:.1f}"

    # Value arc
    val_start = polar_to_cart(start_angle)
    val_end = polar_to_cart(end_angle_actual)
    actual_sweep = sweep * pct
    large_val = 1 if actual_sweep > 180 else 0
    val_path = f"M {val_start[0]:.1f} {val_start[1]:.1f} A {r:.1f} {r:.1f} 0 {large_val} 1 {val_end[0]:.1f} {val_end[1]:.1f}"

    svg = f"""
    <div class="cee-gauge-container">
        <svg width="{size}" height="{size}" viewBox="0 0 {size} {size}">
            <path d="{bg_path}" fill="none" stroke="#E5E7EB" stroke-width="8" stroke-linecap="round"/>
            {'<path d="' + val_path + '" fill="none" stroke="' + color + '" stroke-width="8" stroke-linecap="round"/>' if pct > 0.01 else ''}
            <text x="{cx}" y="{cy - 2}" text-anchor="middle" dominant-baseline="central"
                  font-size="24" font-weight="800" fill="{color}" font-family="Inter, sans-serif">
                {score_val if isinstance(score, (int, float)) else '?'}
            </text>
            <text x="{cx}" y="{cy + 16}" text-anchor="middle"
                  font-size="10" fill="#9CA3AF" font-family="Inter, sans-serif">
                / {max_score}
            </text>
        </svg>
        <p class="cee-gauge-label">Score Prospection</p>
    </div>
    """
    st.markdown(svg, unsafe_allow_html=True)


# ── Info Card ─────────────────────────────────────────────────

def render_info_card(title: str, content: str, accent_border: bool = False, icon: str = ""):
    """Generic information card with optional accent left border."""
    cls = "cee-card cee-card-accent" if accent_border else "cee-card"
    icon_html = f'<span style="margin-right:6px;">{icon}</span>' if icon else ""
    st.markdown(
        f'<div class="{cls}">'
        f'<p class="cee-card-title">{icon_html}{title}</p>'
        f'<div class="cee-card-body">{content}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ── Contact Card ──────────────────────────────────────────────

SOURCE_BADGES = {
    "site_web": ("Site web", "#2563eb"),
    "apollo": ("Apollo", "#7c3aed"),
    "llm_analysis": ("IA", "#059669"),
    "google_maps": ("Maps", "#d97706"),
}


def render_contact_card_html(contact: dict, theme_name: str) -> str:
    """Return HTML for a single contact card (no st.markdown call).
    Supports both Apollo format (first_name/last_name) and unified format (nom)."""
    t = get_theme(theme_name)

    nom = (contact.get("nom") or "").strip()
    if not nom:
        first = contact.get("first_name", "")
        last = contact.get("last_name", "")
        nom = f"{first} {last}".strip()
    nom = nom or "Inconnu"

    parts = nom.split()
    initials = (parts[0][:1] + (parts[-1][:1] if len(parts) > 1 else "")).upper() or "?"

    role = contact.get("poste") or contact.get("title") or "Contact"

    email = (contact.get("email") or "").strip()
    telephone = (contact.get("telephone") or "").strip()
    if not telephone:
        phones = contact.get("phone_numbers", [])
        if isinstance(phones, list) and phones:
            telephone = phones[0]
        elif isinstance(phones, str):
            telephone = phones
    linkedin = (contact.get("linkedin") or contact.get("linkedin_url") or "").strip()

    channels = []
    if email:
        channels.append(f'<span class="cee-contact-channel">📧 {email}</span>')
    if telephone:
        channels.append(f'<span class="cee-contact-channel">📞 {telephone}</span>')
    if linkedin:
        channels.append(f'<a class="cee-contact-channel" href="{linkedin}" target="_blank" rel="noopener">🔗 LinkedIn</a>')

    source = (contact.get("source") or "").strip()
    badge_html = ""
    if source:
        label, color = SOURCE_BADGES.get(source, (source, "#6b7280"))
        badge_html = (
            f'<span style="display:inline-block;font-size:10px;font-weight:600;'
            f'padding:2px 6px;border-radius:4px;background:{color}20;color:{color};'
            f'margin-left:6px;vertical-align:middle;">{label}</span>'
        )

    confidence = (contact.get("confidence") or "").strip()
    conf_dot = ""
    if confidence == "high":
        conf_dot = '<span style="color:#059669;margin-left:4px;" title="Confiance haute">●</span>'
    elif confidence == "medium":
        conf_dot = '<span style="color:#d97706;margin-left:4px;" title="Confiance moyenne">●</span>'
    elif confidence == "low":
        conf_dot = '<span style="color:#dc2626;margin-left:4px;" title="Confiance basse">●</span>'

    return (
        f'<div class="cee-contact-card">'
        f'<div class="cee-contact-avatar">{initials}</div>'
        f'<div class="cee-contact-info">'
        f'<p class="cee-contact-name">{nom}{badge_html}{conf_dot}</p>'
        f'<p class="cee-contact-role">{role}</p>'
        f'<div class="cee-contact-channels">{"".join(channels)}</div>'
        f'</div>'
        f'</div>'
    )


# ── Copro Card (Parc ciblé) ──────────────────────────────────

PERIOD_LABELS = {
    "AVANT_1949": "Avant 1949",
    "DE_1949_A_1960": "1949-1960",
    "DE_1961_A_1974": "1961-1974",
    "DE_1975_A_1993": "1975-1993",
    "DE_1994_A_2000": "1994-2000",
    "DE_2001_A_2010": "2001-2010",
    "A_COMPTER_DE_2011": "Après 2011",
}

DPE_COLORS = {
    "A": "#059669", "B": "#10b981", "C": "#84cc16",
    "D": "#eab308", "E": "#f97316", "F": "#ef4444", "G": "#1f2937",
}


def _google_earth_url(address: str) -> str:
    from urllib.parse import quote_plus
    return f"https://earth.google.com/web/search/{quote_plus(address)}"


def render_copro_card(name: str, address: str, lots: int, period: str, urbs_data: dict = None, numero_immat: str = ""):
    """Card for a single copropriété in the targeted portfolio view."""
    period_display = PERIOD_LABELS.get(period, period or "—")

    immat_html = ""
    if numero_immat and numero_immat != name:
        immat_html = f'<p style="font-size:11px;color:#9CA3AF;margin:0 0 4px 0;">{numero_immat}</p>'

    earth_link = ""
    if address:
        earth_url = _google_earth_url(address)
        earth_link = (
            f' <a href="{earth_url}" target="_blank" title="Voir sur Google Earth"'
            f' style="text-decoration:none;font-size:14px;vertical-align:middle;">🌍</a>'
        )

    urbs_html = ""
    if urbs_data:
        badges = []
        dpe = urbs_data.get("dpe", "")
        if dpe:
            color = DPE_COLORS.get(dpe.upper(), "#6b7280")
            badges.append(
                f'<span style="display:inline-block;font-size:11px;font-weight:700;'
                f'padding:2px 8px;border-radius:4px;background:{color};color:#fff;">'
                f'DPE {dpe}</span>'
            )
        chauffage = urbs_data.get("chauffage", "")
        if chauffage:
            badges.append(f'<span class="cee-copro-badge">🔥 {chauffage}</span>')
        energie = urbs_data.get("energie", "")
        if energie and "individuel" not in chauffage.lower():
            badges.append(f'<span class="cee-copro-badge">⚡ {energie}</span>')
        annee = urbs_data.get("annee")
        if annee:
            badges.append(f'<span class="cee-copro-badge">📅 {annee}</span>')
        if badges:
            urbs_html = f'<div class="cee-copro-meta" style="margin-top:4px;">{"".join(badges)}</div>'

    lots_display = f"{lots:,}".replace(",", "\u202f")
    st.markdown(
        f'<div class="cee-copro-card">'
        f'<div class="cee-copro-header">'
        f'<h4>{name or "Copropriété"}</h4>'
        f'<span class="cee-copro-lots">{lots_display} lots</span>'
        f'</div>'
        f'{immat_html}'
        f'<p class="cee-copro-address">{address}{earth_link}</p>'
        f'<div class="cee-copro-meta">'
        f'<span class="cee-copro-badge">🏗️ {period_display}</span>'
        f'</div>'
        f'{urbs_html}'
        f'</div>',
        unsafe_allow_html=True,
    )


# ── Empty State ───────────────────────────────────────────────

def render_empty_state(message: str = "Analyse en attente", sub: str = "", icon: str = "📋"):
    st.markdown(
        f'<div class="cee-empty">'
        f'<div class="cee-empty-icon">{icon}</div>'
        f'<p class="cee-empty-text">{message}</p>'
        f'<p class="cee-empty-sub">{sub}</p>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ── Skeleton Loader ───────────────────────────────────────────

def render_skeleton(height: int = 60):
    st.markdown(
        f'<div class="cee-skeleton" style="height:{height}px;width:100%;margin-bottom:8px;"></div>',
        unsafe_allow_html=True,
    )


# ── Filter Chips ──────────────────────────────────────────────

def render_chips(labels: list[str]):
    """Render a row of filter chips (display only)."""
    if not labels:
        return
    chips_html = "".join(f'<span class="cee-chip">{lbl}</span>' for lbl in labels)
    st.markdown(f'<div class="cee-chips">{chips_html}</div>', unsafe_allow_html=True)


# ── Section Divider ───────────────────────────────────────────

def render_section_label(text: str):
    st.markdown(f'<p class="cee-section-label">{text}</p>', unsafe_allow_html=True)


def render_divider():
    st.markdown('<div class="cee-divider"></div>', unsafe_allow_html=True)


# ── Tag / Badge ───────────────────────────────────────────────

def score_tag_html(score) -> str:
    """Return inline HTML for a colored score tag."""
    if not isinstance(score, (int, float)):
        return '<span class="cee-tag cee-tag-gray">?</span>'
    if score >= 7:
        cls = "cee-tag-green"
    elif score >= 4:
        cls = "cee-tag-orange"
    else:
        cls = "cee-tag-red"
    return f'<span class="cee-tag {cls}">{score}/10</span>'


def maturite_tag_html(maturite: str) -> str:
    """Return inline HTML for digital maturity tag."""
    m = (maturite or "").strip().lower()
    if m == "forte":
        return '<span class="cee-tag cee-tag-green">FORTE</span>'
    if m == "moyenne":
        return '<span class="cee-tag cee-tag-orange">MOYENNE</span>'
    if m == "faible":
        return '<span class="cee-tag cee-tag-red">FAIBLE</span>'
    return '<span class="cee-tag cee-tag-gray">—</span>'
