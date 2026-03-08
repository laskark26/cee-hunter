"""
CEE Hunter — Design System
Tokens (colors, spacing, typography) + CSS generation for Light/Dark themes.
"""

# ── Color Palette ─────────────────────────────────────────────

PALETTE = {
    "primary": "#10B981",
    "primary_dark": "#059669",
    "primary_light": "#D1FAE5",
    "warning": "#F59E0B",
    "warning_light": "#FEF3C7",
    "error": "#EF4444",
    "error_light": "#FEE2E2",
    "info": "#3B82F6",
    "info_light": "#DBEAFE",
}

THEMES = {
    "Light": {
        "bg": "#F9FAFB",
        "bg_secondary": "#F3F4F6",
        "card_bg": "#FFFFFF",
        "card_border": "#E5E7EB",
        "card_shadow": "0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04)",
        "text": "#111827",
        "text_secondary": "#6B7280",
        "text_tertiary": "#9CA3AF",
        "separator": "#E5E7EB",
        "hover_bg": "#F9FAFB",
        "input_bg": "#FFFFFF",
        "input_border": "#D1D5DB",
        "badge_bg": "#F3F4F6",
        "accent": PALETTE["primary"],
        "accent_dark": PALETTE["primary_dark"],
    },
    "Dark": {
        "bg": "#0F1117",
        "bg_secondary": "#1A1D29",
        "card_bg": "#1E2130",
        "card_border": "#2D3348",
        "card_shadow": "0 1px 3px rgba(0,0,0,0.3), 0 1px 2px rgba(0,0,0,0.2)",
        "text": "#F3F4F6",
        "text_secondary": "#9CA3AF",
        "text_tertiary": "#6B7280",
        "separator": "#2D3348",
        "hover_bg": "#252836",
        "input_bg": "#1A1D29",
        "input_border": "#2D3348",
        "badge_bg": "#252836",
        "accent": PALETTE["primary"],
        "accent_dark": PALETTE["primary_dark"],
    },
}

# ── Spacing (8px grid) ────────────────────────────────────────

SP = {
    "xs": "4px",
    "sm": "8px",
    "md": "16px",
    "lg": "24px",
    "xl": "32px",
    "2xl": "48px",
}

# ── Typography ────────────────────────────────────────────────

FONT_FAMILY = "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"

TYPO = {
    "h1": {"size": "24px", "weight": "700", "line_height": "32px"},
    "h2": {"size": "18px", "weight": "600", "line_height": "24px"},
    "h3": {"size": "14px", "weight": "600", "line_height": "20px"},
    "body": {"size": "14px", "weight": "400", "line_height": "20px"},
    "caption": {"size": "12px", "weight": "400", "line_height": "16px"},
    "overline": {"size": "11px", "weight": "600", "line_height": "16px"},
}

# ── Border Radius ─────────────────────────────────────────────

RADIUS = {
    "sm": "6px",
    "md": "8px",
    "lg": "12px",
    "xl": "16px",
    "full": "9999px",
}


def get_theme(theme_name: str) -> dict:
    return THEMES.get(theme_name, THEMES["Light"])


def score_color(score, fallback="#6B7280"):
    """Return color based on prospection score (0-10)."""
    if not isinstance(score, (int, float)):
        return fallback
    if score >= 7:
        return PALETTE["primary"]
    if score >= 4:
        return PALETTE["warning"]
    return PALETTE["error"]


def generate_css(theme_name: str) -> str:
    """Generate the full CSS string for the given theme."""
    t = get_theme(theme_name)
    return f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

    /* ── Reset & Base ──────────────────────────────── */
    html, body, [class*="css"] {{
        font-family: {FONT_FAMILY};
    }}
    .stApp {{
        background-color: {t['bg']};
        color: {t['text']};
    }}
    .block-container {{
        padding-top: 56px !important;
        padding-bottom: 1rem !important;
        max-width: 1200px !important;
    }}
    [data-testid="stVerticalBlock"] {{
        gap: 0.35rem !important;
    }}

    /* Hide default sidebar */
    [data-testid="stSidebar"],
    [data-testid="stSidebarCollapsedControl"] {{
        display: none !important;
    }}

    /* ── Headings ──────────────────────────────────── */
    h1 {{ font-size: {TYPO['h1']['size']} !important; font-weight: {TYPO['h1']['weight']} !important; margin: 0 0 {SP['sm']} 0 !important; color: {t['text']}; }}
    h2 {{ font-size: {TYPO['h2']['size']} !important; font-weight: {TYPO['h2']['weight']} !important; margin: 0 0 {SP['xs']} 0 !important; color: {t['text']}; }}
    h3 {{ font-size: {TYPO['h3']['size']} !important; font-weight: {TYPO['h3']['weight']} !important; margin: 0 !important; color: {t['text']}; }}

    /* ── Header ────────────────────────────────────── */
    .cee-header {{
        display: flex;
        align-items: center;
        padding: {SP['sm']} 0 {SP['md']} 0;
        border-bottom: 1px solid {t['separator']};
        margin-bottom: {SP['md']};
    }}
    .cee-header-logo {{
        font-size: 18px;
        font-weight: 800;
        color: {t['accent']};
        letter-spacing: -0.02em;
    }}
    .cee-header-logo span {{
        font-weight: 400;
        font-size: 12px;
        color: {t['text_secondary']};
        margin-left: 6px;
    }}
    .cee-header-subtitle {{
        font-size: 13px;
        color: {t['text_secondary']};
        margin-left: 16px;
        flex-grow: 1;
    }}

    /* ── Stepper ───────────────────────────────────── */
    .cee-stepper {{
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 0;
        padding: {SP['sm']} {SP['lg']};
        background: {t['card_bg']};
        border: 1px solid {t['card_border']};
        border-radius: {RADIUS['lg']};
        margin-bottom: {SP['lg']};
    }}
    .cee-step {{
        display: flex;
        align-items: center;
        gap: 8px;
    }}
    .cee-step-number {{
        width: 24px;
        height: 24px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 11px;
        font-weight: 700;
        flex-shrink: 0;
    }}
    .cee-step-number.done {{
        background: {t['accent']};
        color: #FFFFFF;
    }}
    .cee-step-number.active {{
        background: {t['accent']};
        color: #FFFFFF;
        box-shadow: 0 0 0 3px {t['accent']}33;
    }}
    .cee-step-number.pending {{
        background: {t['badge_bg']};
        color: {t['text_tertiary']};
        border: 1px solid {t['card_border']};
    }}
    .cee-step-label {{
        font-size: 12px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }}
    .cee-step-label.done {{ color: {t['accent']}; }}
    .cee-step-label.active {{ color: {t['accent']}; }}
    .cee-step-label.pending {{ color: {t['text_tertiary']}; }}
    .cee-step-connector {{
        width: 40px;
        height: 2px;
        margin: 0 8px;
        border-radius: 1px;
    }}
    .cee-step-connector.done {{ background: {t['accent']}; }}
    .cee-step-connector.pending {{ background: {t['card_border']}; }}

    /* ── Cards ─────────────────────────────────────── */
    .cee-card {{
        background: {t['card_bg']};
        border: 1px solid {t['card_border']};
        border-radius: {RADIUS['lg']};
        padding: {SP['md']};
        box-shadow: {t['card_shadow']};
        margin-bottom: {SP['sm']};
    }}
    .cee-card-accent {{
        border-left: 3px solid {t['accent']};
    }}
    .cee-card-title {{
        font-size: 12px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        color: {t['text_secondary']};
        margin: 0 0 {SP['sm']} 0;
    }}
    .cee-card-body {{
        font-size: 14px;
        color: {t['text']};
        line-height: 1.5;
        margin: 0;
    }}

    /* ── KPI Cards ─────────────────────────────────── */
    .cee-kpi {{
        background: {t['card_bg']};
        border: 1px solid {t['card_border']};
        border-radius: {RADIUS['lg']};
        padding: {SP['md']} {SP['lg']};
        text-align: center;
        box-shadow: {t['card_shadow']};
    }}
    .cee-kpi-primary {{
        border-bottom: 3px solid {t['accent']};
    }}
    .cee-kpi-label {{
        font-size: 11px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: {t['text_secondary']};
        margin: 0 0 4px 0;
    }}
    .cee-kpi-value {{
        font-size: 28px;
        font-weight: 800;
        color: {t['text']};
        margin: 0;
        line-height: 1.1;
    }}
    .cee-kpi-value.primary {{
        font-size: 36px;
        color: {t['accent']};
    }}
    .cee-kpi-sub {{
        font-size: 12px;
        color: {t['text_tertiary']};
        margin: 4px 0 0 0;
    }}

    /* ── Copro Card (Parc ciblé) ───────────────────── */
    .cee-copro-card {{
        background: {t['card_bg']};
        border: 1px solid {t['card_border']};
        border-radius: {RADIUS['md']};
        padding: {SP['md']};
        box-shadow: {t['card_shadow']};
        margin-bottom: {SP['sm']};
        transition: border-color 0.15s ease;
    }}
    .cee-copro-card:hover {{
        border-color: {t['accent']};
    }}
    .cee-copro-card h4 {{
        font-size: 13px !important;
        font-weight: 600 !important;
        color: {t['text']} !important;
        margin: 0 0 8px 0 !important;
        line-height: 1.3 !important;
    }}
    .cee-copro-meta {{
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin-top: 8px;
    }}
    .cee-copro-badge {{
        display: inline-flex;
        align-items: center;
        gap: 4px;
        font-size: 11px;
        font-weight: 500;
        color: {t['text_secondary']};
        background: {t['badge_bg']};
        padding: 3px 8px;
        border-radius: {RADIUS['full']};
    }}

    /* ── Contact Card ──────────────────────────────── */
    .cee-contact-card {{
        background: {t['card_bg']};
        border: 1px solid {t['card_border']};
        border-radius: {RADIUS['lg']};
        padding: {SP['md']};
        box-shadow: {t['card_shadow']};
        display: flex;
        align-items: flex-start;
        gap: {SP['md']};
        margin-bottom: {SP['sm']};
        transition: border-color 0.15s ease;
    }}
    .cee-contact-card:hover {{
        border-color: {t['accent']};
    }}
    .cee-contact-avatar {{
        width: 40px;
        height: 40px;
        border-radius: 50%;
        background: {PALETTE['primary_light']};
        color: {PALETTE['primary_dark']};
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 14px;
        font-weight: 700;
        flex-shrink: 0;
    }}
    .cee-contact-info {{
        flex-grow: 1;
        min-width: 0;
    }}
    .cee-contact-name {{
        font-size: 14px;
        font-weight: 600;
        color: {t['text']};
        margin: 0;
    }}
    .cee-contact-role {{
        font-size: 12px;
        color: {t['text_secondary']};
        margin: 2px 0 0 0;
    }}
    .cee-contact-channels {{
        display: flex;
        gap: 12px;
        margin-top: 8px;
        flex-wrap: wrap;
    }}
    .cee-contact-channel {{
        font-size: 12px;
        color: {t['text_secondary']};
        text-decoration: none;
        display: inline-flex;
        align-items: center;
        gap: 4px;
    }}
    .cee-contact-channel:hover {{
        color: {t['accent']};
    }}

    /* ── Score Gauge ───────────────────────────────── */
    .cee-gauge-container {{
        text-align: center;
        padding: {SP['md']};
    }}
    .cee-gauge-label {{
        font-size: 11px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: {t['text_secondary']};
        margin-top: 8px;
    }}
    .cee-gauge-hint {{
        font-size: 11px;
        color: {t['text_tertiary']};
        margin-top: 4px;
        line-height: 1.4;
    }}

    /* ── Chips ─────────────────────────────────────── */
    .cee-chips {{
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        margin: {SP['sm']} 0;
    }}
    .cee-chip {{
        display: inline-flex;
        align-items: center;
        gap: 4px;
        font-size: 12px;
        font-weight: 500;
        color: {t['accent']};
        background: {PALETTE['primary_light']}40;
        border: 1px solid {t['accent']}30;
        padding: 4px 10px;
        border-radius: {RADIUS['full']};
    }}

    /* ── Empty State ───────────────────────────────── */
    .cee-empty {{
        text-align: center;
        padding: {SP['2xl']} {SP['lg']};
        color: {t['text_tertiary']};
    }}
    .cee-empty-icon {{
        font-size: 32px;
        margin-bottom: {SP['sm']};
        opacity: 0.5;
    }}
    .cee-empty-text {{
        font-size: 14px;
        font-weight: 500;
        margin: 0;
    }}
    .cee-empty-sub {{
        font-size: 12px;
        margin: 4px 0 0 0;
        color: {t['text_tertiary']};
    }}

    /* ── Preset Buttons ────────────────────────────── */
    .cee-presets {{
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
        margin-bottom: {SP['md']};
    }}

    /* ── Section Divider ───────────────────────────── */
    .cee-divider {{
        height: 1px;
        background: {t['separator']};
        margin: {SP['md']} 0;
    }}
    .cee-section-label {{
        font-size: 11px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: {t['text_tertiary']};
        margin: {SP['md']} 0 {SP['sm']} 0;
    }}

    /* ── Table Overrides ───────────────────────────── */
    [data-testid="stDataFrame"] {{
        border: 1px solid {t['card_border']};
        border-radius: {RADIUS['lg']};
        overflow: hidden;
    }}
    [data-testid="stDataFrame"] [data-testid="glideDataEditor"] {{
        border-radius: {RADIUS['lg']};
    }}

    /* ── Metric Overrides ──────────────────────────── */
    [data-testid="stMetric"] {{
        background: transparent;
        padding: 0 !important;
    }}

    /* ── Button Overrides ──────────────────────────── */
    .stButton > button[kind="primary"] {{
        background-color: {t['accent']};
        border-color: {t['accent']};
        color: #FFFFFF;
        font-weight: 600;
        border-radius: {RADIUS['md']};
        transition: background-color 0.15s ease;
    }}
    .stButton > button[kind="primary"]:hover {{
        background-color: {t['accent_dark']};
        border-color: {t['accent_dark']};
    }}
    .stButton > button[kind="secondary"] {{
        background: {t['card_bg']};
        border: 1px solid {t['card_border']};
        color: {t['text']};
        font-weight: 500;
        border-radius: {RADIUS['md']};
    }}
    .stButton > button[kind="secondary"]:hover {{
        background: {t['hover_bg']};
        border-color: {t['text_tertiary']};
    }}

    /* ── Tabs Overrides ────────────────────────────── */
    .stTabs [data-baseweb="tab-list"] {{
        gap: 0;
        background: {t['card_bg']};
        border: 1px solid {t['card_border']};
        border-radius: {RADIUS['lg']};
        padding: 4px;
    }}
    .stTabs [data-baseweb="tab"] {{
        border-radius: {RADIUS['md']};
        padding: 8px 16px;
        font-size: 13px;
        font-weight: 500;
        color: {t['text_secondary']};
    }}
    .stTabs [aria-selected="true"] {{
        background: {t['accent']} !important;
        color: #FFFFFF !important;
        font-weight: 600;
    }}
    .stTabs [data-baseweb="tab-highlight"] {{
        display: none;
    }}
    .stTabs [data-baseweb="tab-border"] {{
        display: none;
    }}

    /* ── Multiselect / Input Overrides ──────────────── */
    [data-baseweb="select"] {{
        border-radius: {RADIUS['md']} !important;
    }}
    .stTextInput > div > div > input {{
        border-radius: {RADIUS['md']} !important;
        border-color: {t['input_border']} !important;
        background: {t['input_bg']} !important;
    }}
    .stMultiSelect > div {{
        border-radius: {RADIUS['md']} !important;
    }}

    /* ── Skeleton Loader ───────────────────────────── */
    @keyframes cee-shimmer {{
        0% {{ background-position: -200px 0; }}
        100% {{ background-position: 200px 0; }}
    }}
    .cee-skeleton {{
        background: linear-gradient(90deg, {t['badge_bg']} 25%, {t['card_border']} 50%, {t['badge_bg']} 75%);
        background-size: 400px 100%;
        animation: cee-shimmer 1.5s ease-in-out infinite;
        border-radius: {RADIUS['md']};
    }}

    /* ── Live Count Badge ──────────────────────────── */
    .cee-live-count {{
        display: inline-flex;
        align-items: center;
        gap: 6px;
        font-size: 14px;
        font-weight: 600;
        color: {t['accent']};
        background: {PALETTE['primary_light']}30;
        border: 1px solid {t['accent']}25;
        padding: 8px 16px;
        border-radius: {RADIUS['md']};
        margin-bottom: {SP['sm']};
    }}
    .cee-live-count .dot {{
        width: 8px;
        height: 8px;
        background: {t['accent']};
        border-radius: 50%;
        animation: cee-pulse 2s ease-in-out infinite;
    }}
    @keyframes cee-pulse {{
        0%, 100% {{ opacity: 1; }}
        50% {{ opacity: 0.4; }}
    }}

    /* ── Email Preview ─────────────────────────────── */
    .cee-email-preview {{
        background: {t['card_bg']};
        border: 1px solid {t['card_border']};
        border-radius: {RADIUS['lg']};
        padding: {SP['lg']};
        box-shadow: {t['card_shadow']};
        font-family: {FONT_FAMILY};
    }}
    .cee-email-header {{
        font-size: 12px;
        color: {t['text_tertiary']};
        padding-bottom: {SP['sm']};
        border-bottom: 1px solid {t['separator']};
        margin-bottom: {SP['md']};
    }}
    .cee-email-body {{
        font-size: 14px;
        color: {t['text']};
        line-height: 1.6;
        white-space: pre-wrap;
    }}

    /* ── Misc ──────────────────────────────────────── */
    .cee-tag {{
        display: inline-block;
        font-size: 11px;
        font-weight: 600;
        padding: 2px 8px;
        border-radius: {RADIUS['full']};
    }}
    .cee-tag-green {{
        background: {PALETTE['primary_light']};
        color: {PALETTE['primary_dark']};
    }}
    .cee-tag-orange {{
        background: {PALETTE['warning_light']};
        color: #92400E;
    }}
    .cee-tag-red {{
        background: {PALETTE['error_light']};
        color: #991B1B;
    }}
    .cee-tag-gray {{
        background: {t['badge_bg']};
        color: {t['text_secondary']};
    }}
</style>
"""
