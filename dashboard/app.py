import hashlib
import json
from pathlib import Path
import sys

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analytics.cricket_metrics import calculate_player_metrics
from analytics.cricket_analyst import (
    LLMProviderError,
    SUPPORTED_QUESTION_CATEGORIES,
    analyze_question,
    generate_commentary,
    provider_from_environment,
)
from analytics.analyst_tools import CricketToolbox, analyze_with_tools


DATA = ROOT / "data" / "raw"
CURATED = ROOT / "data" / "curated"
REPORTS = ROOT / "reports"
LOGO = ROOT / "dashboard" / "assets" / "superr_intelligence_logo.png"
THEMES = {
    "IPL Theme": {
        "label": "IPL Theme",
        "background": "#071B3A",
        "sidebar": "#071B3A",
        "surface": "#0B2857",
        "surface_alt": "#123B7A",
        "primary": "#123B7A",
        "interactive": "#246BCE",
        "accent": "#C9A227",
        "accent_text": "#C9A227",
        "secondary": "#C9A227",
        "text": "#F4F7FF",
        "muted": "#B6C5DE",
        "subtle": "#91A7C9",
        "border": "rgba(36,107,206,.28)",
        "hero_gradient": "linear-gradient(110deg, #071B3A 0%, #123B7A 68%, #071B3A 100%)",
        "chart_background": "rgba(7,27,58,.28)",
        "chart_plot": "rgba(7,27,58,.12)",
        "chart_grid": "rgba(182,197,222,.18)",
        "chart_colors": ["#246BCE", "#C9A227", "#123B7A"],
        "chart_scale": ["#123B7A", "#246BCE", "#C9A227"],
    },
    "Rajasthan Royals Theme": {
        "label": "Rajasthan Royals Theme",
        "background": "#071B3A",
        "sidebar": "#071B3A",
        "surface": "#0A2D60",
        "surface_alt": "#004BA0",
        "primary": "#004BA0",
        "interactive": "#004BA0",
        "accent": "#EA1A85",
        "accent_text": "#F7F5FC",
        "secondary": "#EA1A85",
        "text": "#F7F5FC",
        "muted": "#D2C7DA",
        "subtle": "#A99DB8",
        "border": "rgba(234,26,133,.25)",
        "hero_gradient": "linear-gradient(110deg, #071B3A 0%, #004BA0 42%, #EA1A85 100%)",
        "chart_background": "rgba(7,27,58,.28)",
        "chart_plot": "rgba(7,27,58,.12)",
        "chart_grid": "rgba(210,199,218,.18)",
        "chart_colors": ["#004BA0", "#EA1A85", "#2D76C2"],
        "chart_scale": ["#071B3A", "#004BA0", "#EA1A85"],
    },
}


def theme_for_appearance(theme, appearance):
    if appearance != "Light mode":
        return theme

    light_theme = theme.copy()
    light_theme.update(
        {
            "background": "#F5F7FB",
            "sidebar": "#FFFFFF",
            "surface": "#FFFFFF",
            "surface_alt": "#EAF0F8",
            "text": "#172033",
            "muted": "#43536C",
            "subtle": "#62748B",
            "accent_text": theme["accent"] if theme["label"] == "IPL Theme" else "#172033",
            "hero_gradient": (
                "linear-gradient(110deg, #F5F7FB 0%, #E8F0FC 68%, #FFFFFF 100%)"
                if theme["label"] == "IPL Theme"
                else "linear-gradient(110deg, #F5F7FB 0%, #E8F0FC 42%, #FCEAF4 100%)"
            ),
            "chart_background": "rgba(255,255,255,.92)",
            "chart_plot": "#F8FAFC",
            "chart_grid": "rgba(7,27,58,.12)",
        }
    )
    return light_theme


st.set_page_config(
    page_title="Boundary — Cricket, in the moment",
    page_icon="🏏",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_data(show_spinner="Reading the match archive…")
def load_data():
    matches = pd.read_csv(DATA / "matches.csv")
    matches["match_date"] = pd.to_datetime(matches["match_date"], errors="coerce")
    balls = pd.read_csv(
        DATA / "ball_by_ball.csv",
        usecols=[
            "match_id",
            "innings",
            "overid",
            "innings_ball_num",
            "batting_team_id",
            "bowling_team_id",
            "striker_name",
            "bowler_name",
            "runs",
            "is_four",
            "is_six",
            "is_wicket",
            "dismissal_type",
            "extras_type",
            "extras1_runs",
            "extras_2_runs",
            "pace_or_spin",
        ],
    )
    balls["total_runs"] = balls["runs"] + balls["extras1_runs"] + balls["extras_2_runs"]
    competitions = pd.read_csv(DATA / "competitions.csv")
    roster = pd.read_csv(DATA / "competition_team_player_mapping.csv")
    return matches, balls, competitions, roster


@st.cache_data(show_spinner="Loading pressure analytics…")
def load_pressure_data():
    columns = [
        "match_id",
        "comp_id",
        "comp_name",
        "match_format",
        "season",
        "innings",
        "overid",
        "innings_ball_num",
        "batting_team_id",
        "bowling_team_id",
        "striker_id",
        "striker_name",
        "bowler_id",
        "bowler_name",
        "dismissed_player_id",
        "is_batting_pressure",
        "is_bowling_pressure",
        "pressure_batter_ball",
        "pressure_bowler_ball",
        "batter_runs",
        "is_batter_ball_faced",
        "is_four",
        "is_six",
        "is_legal_ball",
        "bowler_conceded_runs",
        "is_bowler_wicket",
        "is_dot_ball",
        "has_boundary_flag",
        "team_runs",
        "score_before",
        "wickets_before",
        "legal_balls_before",
        "balls_remaining",
        "target",
        "runs_required",
        "current_run_rate",
        "required_run_rate",
        "reference_run_rate",
        "innings_progress",
        "innings_phase",
        "batting_pressure",
        "bowling_pressure",
    ]
    return pd.read_parquet(CURATED / "pressure_deliveries.parquet", columns=columns)


@st.cache_data(show_spinner="Loading verified ranking outputs…")
def _load_rankings(file_fingerprint):
    return {
        "top_batters": pd.read_csv(REPORTS / "top_10_batters.csv"),
        "top_bowlers": pd.read_csv(REPORTS / "top_10_bowlers.csv"),
        "full_batters": pd.read_csv(REPORTS / "full_batter_ranking.csv"),
        "full_bowlers": pd.read_csv(REPORTS / "full_bowler_ranking.csv"),
    }


def load_rankings():
    files = [
        "top_10_batters.csv",
        "top_10_bowlers.csv",
        "full_batter_ranking.csv",
        "full_bowler_ranking.csv",
    ]
    fingerprint = tuple(
        (name, (REPORTS / name).stat().st_mtime_ns)
        for name in files
    )
    return _load_rankings(fingerprint)


@st.cache_data(show_spinner="Calculating filtered player metrics…")
def calculate_filtered_metrics(match_ids, team_ids):
    pressure_data = load_pressure_data()
    scoped = pressure_data[pressure_data["match_id"].isin(match_ids)]
    if team_ids:
        scoped = scoped[
            scoped["batting_team_id"].isin(team_ids)
            | scoped["bowling_team_id"].isin(team_ids)
        ]
    return calculate_player_metrics(scoped)


@st.cache_data(show_spinner=False)
def _load_methodology_text(file_mtime_ns):
    return (ROOT / "reports" / "methodology_report.md").read_text(encoding="utf-8")


def load_methodology_text():
    return _load_methodology_text(
        (REPORTS / "methodology_report.md").stat().st_mtime_ns
    )


@st.cache_data(show_spinner=False)
def _load_final_validation_artifacts(file_fingerprint):
    return {
        "validation": json.loads(
            (REPORTS / "final_validation.json").read_text(encoding="utf-8")
        ),
        "ranking_run": json.loads(
            (REPORTS / "final_rankings.json").read_text(encoding="utf-8")
        ),
        "quality": json.loads(
            (REPORTS / "data_quality_report.json").read_text(encoding="utf-8")
        ),
    }


def load_final_validation_artifacts():
    files = [
        "final_validation.json",
        "final_rankings.json",
        "data_quality_report.json",
    ]
    fingerprint = tuple(
        (name, (REPORTS / name).stat().st_mtime_ns)
        for name in files
    )
    return _load_final_validation_artifacts(fingerprint)


def chart_theme(fig, theme, height=320):
    grid = theme["chart_grid"]
    fig.update_layout(
        height=height,
        paper_bgcolor=theme["chart_background"],
        plot_bgcolor=theme["chart_plot"],
        font={"family": "Inter, sans-serif", "color": theme["text"], "size": 12},
        margin={"l": 8, "r": 8, "t": 28, "b": 8},
        legend={
            "bgcolor": "rgba(0,0,0,0)",
            "orientation": "h",
            "y": 1.14,
            "font": {"color": theme["muted"]},
        },
        hoverlabel={
            "bgcolor": theme["surface_alt"],
            "bordercolor": theme["interactive"],
            "font": {"color": theme["text"]},
        },
        xaxis={
            "gridcolor": grid,
            "zerolinecolor": grid,
            "linecolor": theme["border"],
            "tickfont": {"color": theme["muted"]},
            "title_font": {"color": theme["muted"]},
        },
        yaxis={
            "gridcolor": grid,
            "zerolinecolor": grid,
            "linecolor": theme["border"],
            "tickfont": {"color": theme["muted"]},
            "title_font": {"color": theme["muted"]},
        },
    )
    return fig


def metric(label, value, note, icon, index):
    digits = "".join(
        f'<span class="count-digit" style="--target:translateY(-{char}em)"><span class="count-strip">{"".join(f"<span>{number}</span>" for number in range(10))}</span></span>'
        if char.isdigit()
        else f'<span class="count-separator">{char}</span>'
        for char in value
    )
    st.markdown(
        f"""
        <div class="metric-card" style="--card-delay:{index * 80}ms">
          <div class="metric-top"><span>{label}</span><span class="metric-icon" aria-hidden="true">{icon}</span></div>
          <div class="metric-value" role="img" aria-label="{value}"><span class="count-display" aria-hidden="true">{digits}</span></div>
          <div class="metric-note">{note}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def hero_illustration():
    routes = [
        (0, 4, "M 205 151 Q 295 130 420 24", 420, 24),
        (1.8, 6, "M 205 151 Q 330 130 493 72", 493, 72),
        (3.6, 4, "M 205 151 Q 340 155 510 150", 510, 150),
        (5.4, 6, "M 205 151 Q 330 205 435 214", 435, 214),
        (7.2, 4, "M 205 151 Q 225 75 314 18", 314, 18),
    ]
    shots = "".join(
        f"""
        <path class="shot-trail" style="--shot-delay:{delay}s" pathLength="100" d="{path}"/>
        <circle class="shot-ripple" style="--shot-delay:{delay}s" cx="{x}" cy="{y}" r="6"/>
        <text class="shot-label" style="--shot-delay:{delay}s" x="{x}" y="{y - 11}">{runs}</text>
        <circle class="shot-ball" style="--shot-delay:{delay}s" cx="0" cy="0" r="4.5">
          <animateMotion path="{path}" dur="9s" begin="{delay}s" repeatCount="indefinite" keyPoints="0;1;1" keyTimes="0;0.14;1" calcMode="linear"/>
        </circle>
        """
        for delay, runs, path, x, y in routes
    )
    rings = "".join(
        f'<circle class="{"ground-inner" if radius == 112 else "ground-ring"}" cx="420" cy="118" r="{radius}"/>'
        for radius in (112, 145, 178, 211)
    )
    return f"""
    <svg class="hero-ground" viewBox="0 0 600 235" preserveAspectRatio="xMaxYMid meet" aria-hidden="true" focusable="false">
      {rings}
      {shots}
    </svg>
    """


def hero_scene(season, theme):
    hero_css = {
        "--hero-background": theme["hero_gradient"],
        "--hero-accent": theme["accent"],
        "--hero-accent-text": theme["accent_text"],
        "--hero-secondary": theme["secondary"],
        "--hero-primary": theme["primary"],
        "--hero-interactive": theme["interactive"],
        "--hero-text": theme["text"],
        "--hero-muted": theme["muted"],
        "--hero-border": theme["border"],
        "--hero-surface": theme["surface"],
        "--hero-subtle": theme["subtle"],
    }
    theme_variables = ";".join(
        f"{name}:{value}" for name, value in hero_css.items()
    )
    return f"""
    <style>
      @import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@400;500;600;700&display=swap');
      :root {{ {theme_variables}; }}
      html,body {{ margin:0;width:100%;height:100%;overflow:hidden;background:transparent;font-family:'DM Sans',sans-serif; }}
      .hero {{ position:relative;isolation:isolate;box-sizing:border-box;overflow:hidden;height:235px;border:1px solid var(--hero-border);border-radius:22px;padding:31px 36px;background:var(--hero-background);color:var(--hero-text); }}
      .hero-ground {{ position:absolute;z-index:0;right:0;top:0;width:55%;height:100%;pointer-events:none; }}
      .ground-ring {{ fill:none;stroke:var(--hero-interactive);stroke-opacity:.22;stroke-width:1; }}
      .ground-inner {{ fill:none;stroke:var(--hero-accent);stroke-opacity:.42;stroke-width:1; }}
      .shot-trail {{ fill:none;stroke:var(--hero-accent);stroke-width:2;stroke-linecap:round;stroke-dasharray:100;stroke-dashoffset:100;opacity:0;filter:drop-shadow(0 0 4px var(--hero-accent));animation:shot-trail 9s ease-out infinite;animation-delay:var(--shot-delay); }}
      .shot-ball {{ fill:var(--hero-accent);opacity:0;filter:drop-shadow(0 0 5px var(--hero-accent));animation:shot-ball 9s ease-out infinite;animation-delay:var(--shot-delay); }}
      .shot-ripple {{ fill:none;stroke:var(--hero-secondary);stroke-width:1.5;opacity:0;transform-box:fill-box;transform-origin:center;animation:shot-ripple 9s ease-out infinite;animation-delay:var(--shot-delay); }}
      .shot-label {{ fill:var(--hero-accent-text);font:500 11px 'DM Mono',monospace;text-anchor:middle;opacity:0;animation:shot-label 9s ease-out infinite;animation-delay:var(--shot-delay); }}
      /* Stage 1: the shot trail draws away from the striker. */
      @keyframes shot-trail {{ 0%,4% {{ stroke-dashoffset:100;opacity:0; }} 6% {{ opacity:.7; }} 17% {{ stroke-dashoffset:0;opacity:.55; }} 25%,100% {{ stroke-dashoffset:0;opacity:0; }} }}
      /* Stage 2: the ball follows the SVG wagon-wheel arc and fades at the rope. */
      @keyframes shot-ball {{ 0%,4% {{ opacity:0; }} 6%,14% {{ opacity:1; }} 20%,100% {{ opacity:0; }} }}
      /* Stage 3: the rope ripples and the four-or-six callout briefly appears. */
      @keyframes shot-ripple {{ 0%,14% {{ opacity:0;transform:scale(.55); }} 17% {{ opacity:.48; }} 25% {{ opacity:0;transform:scale(2.1); }} 100% {{ opacity:0;transform:scale(2.1); }} }}
      @keyframes shot-label {{ 0%,15% {{ opacity:0;transform:translateY(4px); }} 18%,23% {{ opacity:.85;transform:translateY(0); }} 29%,100% {{ opacity:0;transform:translateY(-3px); }} }}
      .eyebrow {{ position:relative;z-index:1;color:var(--hero-accent-text);font:11px 'DM Mono',monospace;letter-spacing:2px;text-transform:uppercase; }}
      .hero-title {{ position:relative;z-index:1;font:600 clamp(32px,4.2vw,56px)/1.04 'Space Grotesk',sans-serif;letter-spacing:-2.5px;margin:14px 0 9px;max-width:680px; }}
      .hero-title span {{ color:var(--hero-accent); }}
      .hero-copy {{ position:relative;z-index:1;color:var(--hero-muted);font-size:14px;max-width:490px;line-height:1.55; }}
      .live-badge {{ position:absolute;z-index:2;right:30px;bottom:27px;border:1px solid var(--hero-border);background:color-mix(in srgb,var(--hero-surface) 78%,transparent);border-radius:999px;padding:9px 13px;color:var(--hero-text);font:10px 'DM Mono',monospace;letter-spacing:.8px; }}
      .live-dot {{ display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--hero-accent);margin-right:8px;box-shadow:0 0 9px var(--hero-accent);pointer-events:none;animation:live-pulse 2.4s ease-in-out infinite; }}
      @keyframes live-pulse {{ 0%,100% {{ opacity:.72;transform:scale(1); }} 50% {{ opacity:1;transform:scale(1.16); }} }}
      @media(max-width:700px) {{ .hero {{ padding:25px 22px; }}.hero-ground {{ opacity:.38;width:72%; }}.live-badge {{ position:relative;display:inline-block;right:auto;bottom:auto;margin-top:20px; }}.hero-title {{ letter-spacing:-1.6px; }} }}
      @media(prefers-reduced-motion:reduce) {{
        *,*:before,*:after {{ animation:none!important;transition:none!important; }}
        .hero-ground .shot-trail {{ stroke-dashoffset:0;opacity:.38; }}
        .hero-ground .shot-ball {{ display:none; }}
        .hero-ground .shot-ripple {{ opacity:.24;transform:scale(1.5); }}
        .hero-ground .shot-label {{ opacity:.65;transform:none; }}
      }}
    </style>
    <div class="hero">
      {hero_illustration()}
      <div class="eyebrow">Beyond the boundary · {season}</div>
      <div class="hero-title">Cricket is a game<br>of <span>moments.</span></div>
      <div class="hero-copy">Follow every run, wicket and turning point across the international game. The numbers tell the story.</div>
      <div class="live-badge"><span class="live-dot" aria-hidden="true"></span>THE ARCHIVE IS IN PLAY</div>
    </div>
    """


def inject_cricket_animations(theme):
    variables = {
        "--ink": theme["background"],
        "--sidebar": theme["sidebar"],
        "--panel": theme["surface"],
        "--panel-strong": theme["surface_alt"],
        "--line": theme["border"],
        "--primary": theme["primary"],
        "--interactive": theme["interactive"],
        "--accent": theme["accent"],
        "--accent-text": theme["accent_text"],
        "--secondary": theme["secondary"],
        "--muted": theme["muted"],
        "--subtle": theme["subtle"],
        "--text": theme["text"],
    }
    css_variables = ";".join(f"{key}:{value}" for key, value in variables.items())
    css = """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@400;500;600;700&display=swap');
    :root { __THEME_VARIABLES__; color-scheme:__COLOR_SCHEME__; }
    html, body, [class*="css"] { font-family:'DM Sans',sans-serif; }
    .stApp { background:radial-gradient(ellipse at 86% 0%,color-mix(in srgb,var(--interactive) 22%,transparent),transparent 36%),var(--ink);color:var(--text); }
    [data-testid="stHeader"] { background:color-mix(in srgb,var(--ink) 82%,transparent); }
    [data-testid="stSidebar"] { background:var(--sidebar);border-right:1px solid var(--line); }
    [data-testid="stSidebar"] > div:first-child { padding-top:1.2rem; }
    .block-container { max-width:1440px;padding-top:1.35rem;padding-bottom:4rem; }
    .brand-copy { min-height:48px;display:flex;flex-direction:column;justify-content:center;padding-bottom:20px; }
    .brand-name { font:700 18px 'Space Grotesk',sans-serif;letter-spacing:-.7px;color:var(--accent); }
    .brand-caption { color:var(--subtle);font:10px 'DM Mono',monospace;letter-spacing:1.4px;text-transform:uppercase;margin-top:1px; }
    .side-label { color:var(--subtle);font:10px 'DM Mono',monospace;letter-spacing:1.4px;text-transform:uppercase;margin:16px 0 7px; }
    .metric-card { background:linear-gradient(145deg,color-mix(in srgb,var(--panel-strong) 72%,var(--ink)),var(--panel));border:1px solid var(--line);border-radius:16px;padding:17px 19px 16px;min-height:119px;transition:transform .22s ease,border-color .22s ease; }
    .metric-card:hover { transform:translateY(-3px);border-color:color-mix(in srgb,var(--accent) 56%,var(--line)); }
    /* Stage 4: dashboard cards arrive with a gentle, staggered lift. */
    @keyframes card-rise { from {opacity:0;transform:translateY(8px)} to {opacity:1;transform:translateY(0)} }
    .metric-top { display:flex;justify-content:space-between;color:var(--muted);font-size:11px;letter-spacing:.4px;text-transform:uppercase; }
    .metric-icon { color:var(--accent);font-size:15px;pointer-events:none;animation:icon-pulse 2.8s ease-in-out infinite; }
    /* Stage 5: KPI corner glyphs breathe subtly without drawing focus. */
    @keyframes icon-pulse { 0%,100% {opacity:.78;transform:scale(1)} 50% {opacity:1;transform:scale(1.12)} }
    .metric-value { font:600 29px 'Space Grotesk',sans-serif;letter-spacing:-1px;margin:9px 0 2px;color:var(--text); }
    .count-display { display:inline-flex;align-items:flex-end;white-space:pre; }
    .count-digit { display:inline-block;height:1em;overflow:hidden;vertical-align:bottom; }
    .count-strip { display:flex;flex-direction:column;line-height:1em;transform:var(--target); }
    .count-strip span { height:1em; }
    /* Stage 6: each digit rolls from zero to its data value using CSS alone. */
    @keyframes count-roll { from {transform:translateY(0)} to {transform:var(--target)} }
    .count-separator { display:inline-block; }
    .metric-note { color:var(--subtle);font-size:11px; }
    .section-head { font:600 18px 'Space Grotesk',sans-serif;color:var(--text);margin:23px 0 3px;letter-spacing:-.3px; }
    .section-sub { color:var(--muted);font-size:12px;margin-bottom:12px; }
    .panel { background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:17px 19px; }
    .match-card { transition:transform .2s ease,border-color .2s ease; }
    .match-card:hover { transform:translateY(-2px);border-color:var(--interactive); }
    [data-testid="stTabs"] [role="tablist"] { position:relative;gap:8px;border-bottom:1px solid var(--line); }
    [data-testid="stTabs"] [data-testid="stTab"] { position:relative;color:var(--muted);height:44px;font-size:13px; }
    /* Stage 9: the active theme accent slides under the selected tab. */
    [data-testid="stTabs"] [data-testid="stTab"]::after { content:"";position:absolute;left:0;right:0;bottom:0;height:2px;border-radius:2px;background:var(--accent);pointer-events:none;transform:scaleX(0);transform-origin:left center;transition:transform .28s cubic-bezier(.2,.7,.25,1); }
    [data-testid="stTabs"] [data-testid="stTab"][aria-selected="true"] { color:var(--accent-text)!important; }
    [data-testid="stTabs"] [data-testid="stTab"][aria-selected="true"]::after { transform:scaleX(1); }
    [data-testid="stTabs"] .react-aria-SelectionIndicator { opacity:0;pointer-events:none; }
    /* Stage 7: Plotly bars scale in from the baseline with a small per-bar stagger. */
    [data-testid="stPlotlyChart"] .barlayer g.point path { transform-box:fill-box;transform-origin:left center;opacity:1;transform:scaleX(1); }
    [data-testid="stPlotlyChart"] .barlayer g.point:nth-of-type(1) path { animation-delay:40ms; }
    [data-testid="stPlotlyChart"] .barlayer g.point:nth-of-type(2) path { animation-delay:90ms; }
    [data-testid="stPlotlyChart"] .barlayer g.point:nth-of-type(3) path { animation-delay:140ms; }
    [data-testid="stPlotlyChart"] .barlayer g.point:nth-of-type(4) path { animation-delay:190ms; }
    [data-testid="stPlotlyChart"] .barlayer g.point:nth-of-type(5) path { animation-delay:240ms; }
    [data-testid="stPlotlyChart"] .barlayer g.point:nth-of-type(6) path { animation-delay:290ms; }
    [data-testid="stPlotlyChart"] .barlayer g.point:nth-of-type(7) path { animation-delay:340ms; }
    [data-testid="stPlotlyChart"] .barlayer g.point:nth-of-type(8) path { animation-delay:390ms; }
    [data-testid="stPlotlyChart"] .barlayer g.point:nth-of-type(9) path { animation-delay:440ms; }
    [data-testid="stPlotlyChart"] .barlayer g.point:nth-of-type(10) path { animation-delay:490ms; }
    /* Stage 8: bars reveal from left to right in their active chart palette. */
    @keyframes bar-grow { from {opacity:.35;transform:scaleX(0)} to {opacity:1;transform:scaleX(1)} }
    /* Stage 10: analytics surfaces lift in together with their data. */
    @keyframes chart-rise { from {opacity:0;transform:translateY(8px)} to {opacity:1;transform:translateY(0)} }
    /* Stage 11: the over-by-over scoring trace draws on like a shot map. */
    @keyframes line-draw { to {stroke-dashoffset:0} }
    /* Stage 12: switching analytics views brings the selected panel into focus. */
    @keyframes panel-enter { from {opacity:0;transform:translateY(8px)} to {opacity:1;transform:translateY(0)} }
    [data-testid="stTabPanel"]:not([inert]) { animation:panel-enter .42s cubic-bezier(.2,.7,.25,1) both; }
    [data-testid="stSelectbox"] [role="combobox"] { color:var(--text);background:var(--panel);border-color:var(--line);transition:transform .18s ease,box-shadow .18s ease; }
    [data-testid="stSelectbox"]:focus-within [role="combobox"] { transform:translateY(-1px);box-shadow:0 0 0 1px var(--interactive); }
    [data-baseweb="popover"] [role="listbox"],[data-baseweb="menu"] { background:var(--panel-strong);color:var(--text); }
    [data-baseweb="popover"] [role="option"] { color:var(--text); }
    [data-baseweb="popover"] [role="option"]:hover,[data-baseweb="popover"] [aria-selected="true"] { background:var(--primary); }
    [data-testid="stTextInput"] input { color:var(--text);background:var(--panel);border-color:var(--line); }
    [data-testid="stTextInput"] input::placeholder { color:var(--subtle); }
    [data-testid="stTextInput"]:focus-within input { border-color:var(--interactive);box-shadow:0 0 0 1px var(--interactive); }
    [data-testid="stChatInput"] > div:first-child,
    [data-testid="stChatInput"] > div:first-child:focus-within { color:var(--text)!important;background:var(--panel)!important;border-color:var(--line)!important; }
    [data-testid="stChatInput"] textarea { color:var(--text)!important;-webkit-text-fill-color:var(--text); }
    [data-testid="stChatInput"] textarea::placeholder { color:var(--subtle)!important;-webkit-text-fill-color:var(--subtle);opacity:1; }
    [data-testid="stChatInput"] button { color:var(--text)!important;background:var(--panel-strong)!important; }
    [data-testid="stAppViewContainer"] { color:var(--text); }
    [data-testid="stButton"] button,[data-testid="stDownloadButton"] button { color:var(--text);background:var(--panel);border-color:var(--line); }
    [data-testid="stButton"] button:hover,[data-testid="stDownloadButton"] button:hover { color:var(--text);border-color:var(--accent); }
    [data-testid="stElementToolbarButtonContainer"] { background:var(--panel)!important;border:1px solid var(--line);border-radius:8px; }
    [data-testid="stElementToolbar"] button { color:var(--muted); }
    [data-testid="stElementToolbar"] button:hover { color:var(--text);background:var(--panel-strong); }
    [data-testid="stCheckbox"] label,[data-testid="stRadio"] label,[data-testid="stSlider"] label { color:var(--muted); }
    .archive-dot { display:inline-block;color:var(--accent);font-size:9px;pointer-events:none;animation:icon-pulse 2.8s ease-in-out infinite; }
    .archive-dot:nth-of-type(2) { animation-delay:.35s; }
    .archive-dot:nth-of-type(3) { animation-delay:.7s; }
    [data-testid="stMetric"] { background:var(--panel);padding:14px 17px;border-radius:14px;border:1px solid var(--line); }
    [data-testid="stMetricLabel"] { color:var(--muted); }
    [data-testid="stMetricValue"] { color:var(--text); }
    [data-testid="stDataFrame"] { border:1px solid var(--line);border-radius:12px;overflow:hidden;background:var(--panel); }
    .stSelectbox label,.stSlider label { color:var(--muted)!important;font-size:12px!important; }
    [data-testid="stCaptionContainer"],[data-testid="stMarkdownContainer"] p { color:var(--muted); }
    .footer { color:var(--subtle);font:10px 'DM Mono',monospace;letter-spacing:.7px;border-top:1px solid var(--line);padding-top:14px;margin-top:32px; }
    .initial-motion { display:none!important;pointer-events:none; }
    @media(max-width:1100px) {
      .metric-card { padding:14px 9px 12px; }
      .metric-top { font-size:9px; }
      .metric-value { font-size:clamp(13px,1.8vw,18px);letter-spacing:-.8px; }
    }
    /* Entrance motion runs only on the first dashboard render, not widget reruns. */
    .stApp:has(.initial-motion) .metric-card,
    .stApp:has(.initial-motion) .match-card { animation:card-rise .55s cubic-bezier(.2,.7,.25,1) both;animation-delay:var(--card-delay,0ms); }
    .stApp:has(.initial-motion) .count-strip { animation:count-roll 1.45s cubic-bezier(.16,1,.3,1) both; }
    .stApp:has(.initial-motion) [data-testid="stPlotlyChart"] .barlayer g.point path { animation:bar-grow .72s cubic-bezier(.16,1,.3,1) both; }
    .stApp:has(.initial-motion) [data-testid="stPlotlyChart"],
    .stApp:has(.initial-motion) [data-testid="stDataFrame"] { animation:chart-rise .58s cubic-bezier(.2,.7,.25,1) both;animation-delay:180ms; }
    .stApp:has(.initial-motion) [data-testid="stPlotlyChart"] .scatterlayer path.js-line { stroke-dasharray:1200;stroke-dashoffset:1200;animation:line-draw 1.5s ease-out both; }
    @media(prefers-reduced-motion:reduce) {
      *,*:before,*:after { animation:none!important;transition:none!important; }
      .metric-card,.match-card { opacity:1;transform:none; }
      .count-strip { transform:var(--target); }
      [data-testid="stTabPanel"]:not([inert]),
      [data-testid="stPlotlyChart"],
      [data-testid="stDataFrame"] { opacity:1;transform:none; }
      [data-testid="stPlotlyChart"] .scatterlayer path.js-line { stroke-dashoffset:0; }
      [data-testid="stPlotlyChart"] .barlayer g.point path { opacity:1;transform:scaleX(1); }
    }
    </style>
    """.replace("__THEME_VARIABLES__", css_variables).replace(
        "__COLOR_SCHEME__", "light" if theme["background"] == "#F5F7FB" else "dark"
    )
    st.markdown(css, unsafe_allow_html=True)


with st.sidebar:
    logo_column, brand_column = st.columns([1, 3])
    with logo_column:
        st.image(LOGO, width=48, caption=None)
    with brand_column:
        st.markdown(
            '<div class="brand-copy"><div class="brand-name">boundary</div><div class="brand-caption">the cricket intelligence</div></div>',
            unsafe_allow_html=True,
        )
    selected_theme = st.selectbox(
        "Dashboard theme",
        list(THEMES),
        index=list(THEMES).index("Rajasthan Royals Theme"),
        key="dashboard_theme",
    )
    selected_appearance = st.selectbox(
        "Appearance",
        ["Dark mode", "Light mode"],
        key="dashboard_appearance",
    )
    st.caption(f"Active palette: {selected_theme} · {selected_appearance}")

theme = theme_for_appearance(THEMES[selected_theme], selected_appearance)
inject_cricket_animations(theme)
if not st.session_state.get("_boundary_entrance_played", False):
    st.session_state["_boundary_entrance_played"] = True
    st.markdown('<span class="initial-motion" aria-hidden="true"></span>', unsafe_allow_html=True)

matches, balls, competitions, roster = load_data()
team_names = sorted(set(matches["home_team"].dropna()) | set(matches["away_team"].dropna()))
years = sorted(matches["match_date"].dropna().dt.year.unique().astype(int).tolist(), reverse=True)
competition_names = sorted(competitions["comp_name"].dropna().astype(str).unique())

with st.sidebar:
    st.markdown('<div class="side-label">Match filters</div>', unsafe_allow_html=True)
    selected_competition = st.selectbox(
        "Competition",
        ["All competitions", *competition_names],
        index=0,
    )
    selected_year = st.selectbox("Season", ["All seasons", *years], index=0)
    selected_team = st.selectbox("Team", ["All teams", *team_names], index=0)
    st.markdown('<div class="side-label">The archive</div>', unsafe_allow_html=True)
    st.markdown(
        f"""
        <div style="font-size:12px;color:var(--muted);line-height:2">
        <span class="archive-dot" aria-hidden="true">●</span> {len(matches):,} match records<br>
        <span class="archive-dot" aria-hidden="true">●</span> {len(balls):,} ball-by-ball events<br>
        <span class="archive-dot" aria-hidden="true">●</span> {len(competitions):,} competitions<br>
        <span class="archive-dot" aria-hidden="true">●</span> {roster['player_id'].nunique():,} mapped players
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div style="margin-top:24px;padding:12px;border:1px solid var(--line);border-radius:12px;color:var(--muted);font-size:11px;line-height:1.5">Every over has a story.<br><span style="color:var(--accent-text)">Explore the numbers behind it.</span></div>',
        unsafe_allow_html=True,
    )

filtered_matches = matches.copy()
if selected_competition != "All competitions":
    selected_competition_ids = set(
        competitions.loc[
            competitions["comp_name"].astype(str).eq(selected_competition), "comp_id"
        ]
    )
    filtered_matches = filtered_matches[
        filtered_matches["comp_id"].isin(selected_competition_ids)
    ]
if selected_year != "All seasons":
    filtered_matches = filtered_matches[filtered_matches["match_date"].dt.year == selected_year]
team_ids = set()
if selected_team != "All teams":
    filtered_matches = filtered_matches[
        (filtered_matches["home_team"] == selected_team)
        | (filtered_matches["away_team"] == selected_team)
    ]
filtered_balls = balls[balls["match_id"].isin(filtered_matches["match_id"])]
if selected_team != "All teams":
    team_ids = set(
        filtered_matches.loc[filtered_matches["home_team"] == selected_team, "home_team_id"].dropna()
    ) | set(
        filtered_matches.loc[filtered_matches["away_team"] == selected_team, "away_team_id"].dropna()
    )
    filtered_balls = filtered_balls[
        filtered_balls["batting_team_id"].isin(team_ids)
        | filtered_balls["bowling_team_id"].isin(team_ids)
    ]
match_ids = tuple(sorted(filtered_matches["match_id"].dropna().unique().tolist()))
pressure_data = load_pressure_data()
filtered_pressure = pressure_data[pressure_data["match_id"].isin(match_ids)]
if team_ids:
    filtered_pressure = filtered_pressure[
        filtered_pressure["batting_team_id"].isin(team_ids)
        | filtered_pressure["bowling_team_id"].isin(team_ids)
    ]
filtered_metrics = (
    calculate_filtered_metrics(match_ids, tuple(sorted(team_ids)))
    if not filtered_pressure.empty
    else None
)

run_count = int(filtered_balls["total_runs"].sum())
four_count = int(filtered_balls["is_four"].sum())
six_count = int(filtered_balls["is_six"].sum())
wicket_count = int(filtered_balls["is_wicket"].sum())
season_label = "All seasons" if selected_year == "All seasons" else str(selected_year)

st.iframe(
    hero_scene(season_label, theme),
    width="stretch",
    height=237,
    tab_index=-1,
    alt="Animated cricket wagon-wheel illustration",
)

metric_cols = st.columns(4)
with metric_cols[0]:
    metric("Matches tracked", f"{len(filtered_matches):,}", f"{len(filtered_balls):,} deliveries in view", "◉", 0)
with metric_cols[1]:
    metric("Runs on the board", f"{run_count:,}", "Including recorded extras", "↗", 1)
with metric_cols[2]:
    metric("Boundary count", f"{four_count + six_count:,}", f"{four_count:,} fours · {six_count:,} sixes", "✦", 2)
with metric_cols[3]:
    metric("Wickets fallen", f"{wicket_count:,}", "Dismissals across all innings", "⌁", 3)

if filtered_matches.empty:
    st.info("No matches found for these filters. Adjust the competition, season, or team.")

rankings = load_rankings()
overview, pressure_analytics, batting, bowling, player_insights, methodology, fixtures, final_validation_tab, ai_analyst_tab = st.tabs(
    [
        "  Match centre  ",
        "  Pressure Analytics  ",
        "  Batting room  ",
        "  Bowling lab  ",
        "  Player Insights  ",
        "  Methodology  ",
        "  Fixtures  ",
        "  Final Methodology & Validation  ",
        "  AI Cricket Analyst  ",
    ],
    key="dashboard_tabs",
    default="  Match centre  ",
    on_change="rerun",
)

with overview:
    left, right = st.columns([1.55, 1], gap="large")
    with left:
        st.markdown('<div class="section-head">Scoring, over by over</div><div class="section-sub">Average runs scored in each over · first and second innings</div>', unsafe_allow_html=True)
        if not filtered_balls.empty:
            innings_summary = (
                filtered_balls[filtered_balls["innings"].isin([1, 2])]
                .groupby(["innings", "overid"], as_index=False)["total_runs"]
                .mean()
            )
            innings_summary["Innings"] = innings_summary["innings"].map({1: "1st innings", 2: "2nd innings"})
            innings_summary = innings_summary[innings_summary["overid"] <= 20]
            fig = px.area(
                innings_summary,
                x="overid",
                y="total_runs",
                color="Innings",
                color_discrete_map={
                    "1st innings": theme["interactive"],
                    "2nd innings": theme["accent"],
                },
                labels={"overid": "Over", "total_runs": "Average runs"},
                line_shape="spline",
            )
            fig.update_traces(fill="tozeroy", opacity=.19, line={"width": 2.5})
            chart_theme(fig, theme, 310)
            fig.update_layout(hovermode="x unified")
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    with right:
        st.markdown('<div class="section-head">The winning edge</div><div class="section-sub">Most victories in this selection</div>', unsafe_allow_html=True)
        winners = filtered_matches[filtered_matches["win_team_id"].notna()]
        if not winners.empty:
            winner_counts = winners["win_team_id"].value_counts().head(7).rename_axis("team_id").reset_index(name="Wins")
            names = pd.concat(
                [
                    filtered_matches[["home_team_id", "home_team"]].rename(columns={"home_team_id": "team_id", "home_team": "Team"}),
                    filtered_matches[["away_team_id", "away_team"]].rename(columns={"away_team_id": "team_id", "away_team": "Team"}),
                ]
            ).drop_duplicates("team_id")
            winner_counts = winner_counts.merge(names, on="team_id", how="left")
            fig = px.bar(
                winner_counts.sort_values("Wins"),
                x="Wins",
                y="Team",
                orientation="h",
                text="Wins",
                color="Wins",
                color_continuous_scale=theme["chart_scale"],
            )
            fig.update_traces(textposition="outside", marker_line_width=0)
            fig.update_layout(coloraxis_showscale=False, yaxis_title=None, xaxis_title=None)
            chart_theme(fig, theme, 310)
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    st.markdown('<div class="section-head">Latest from the middle</div><div class="section-sub">Recent results from the selected season and team</div>', unsafe_allow_html=True)
    recent = filtered_matches.sort_values("match_date", ascending=False).head(5)
    for card_index, row in enumerate(recent.itertuples()):
        date = row.match_date.strftime("%d %b %Y") if pd.notna(row.match_date) else "Date unavailable"
        result = row.result if pd.notna(row.result) else "Result unavailable"
        st.markdown(
            f"""
            <div class="panel match-card" style="--card-delay:{card_index * 80}ms;display:flex;align-items:center;justify-content:space-between;gap:14px;margin:8px 0;padding:13px 17px">
              <div><div style="font:10px 'DM Mono',monospace;color:var(--subtle)">{date} &nbsp;·&nbsp; {row.venue_country or 'International'}</div>
              <div style="font:600 14px 'Space Grotesk',sans-serif;color:var(--text);margin-top:5px">{row.home_team} <span style="color:var(--muted)">vs</span> {row.away_team}</div></div>
              <div style="text-align:right;color:var(--accent-text);font-size:12px;max-width:48%">{result}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.markdown(
        '<div class="section-head">Pressure timeline</div>'
        '<div class="section-sub">Pre-delivery pressure scores from the curated analytical archive</div>',
        unsafe_allow_html=True,
    )
    if filtered_pressure.empty:
        st.info("No curated pressure deliveries match these filters.")
    else:
        timeline_matches = sorted(filtered_pressure["match_id"].dropna().unique().tolist())
        match_labels = (
            filtered_matches.drop_duplicates("match_id")
            .set_index("match_id")
            .to_dict("index")
        )
        selected_match_id = st.selectbox(
            "Timeline match",
            timeline_matches,
            format_func=lambda match_id: (
                f"{match_labels[match_id]['home_team']} vs "
                f"{match_labels[match_id]['away_team']} · "
                f"{match_labels[match_id]['match_date'].strftime('%d %b %Y')}"
            ),
            key="pressure_timeline_match",
        )
        timeline = filtered_pressure[filtered_pressure["match_id"].eq(selected_match_id)]
        innings_options = sorted(timeline["innings"].dropna().astype(int).unique().tolist())
        selected_innings = st.selectbox(
            "Innings",
            innings_options,
            format_func=lambda innings: f"Innings {innings}",
            key="pressure_timeline_innings",
        )
        timeline = timeline[timeline["innings"].eq(selected_innings)].sort_values(
            ["innings_ball_num", "overid"], kind="stable"
        )
        fig = go.Figure()
        fig.add_scatter(
            x=timeline["innings_ball_num"],
            y=timeline["batting_pressure"],
            mode="lines",
            name="Batting pressure",
            line={"color": theme["interactive"], "width": 2.5},
            customdata=timeline[["score_before", "wickets_before", "striker_name"]],
            hovertemplate=(
                "Ball %{x}<br>Pressure %{y:.1f}<br>Score %{customdata[0]} "
                "· %{customdata[1]} wickets<br>Batter %{customdata[2]}<extra></extra>"
            ),
        )
        fig.add_scatter(
            x=timeline["innings_ball_num"],
            y=timeline["bowling_pressure"],
            mode="lines",
            name="Bowling pressure",
            line={"color": theme["accent"], "width": 2.5},
            customdata=timeline[["score_before", "wickets_before", "bowler_name"]],
            hovertemplate=(
                "Ball %{x}<br>Pressure %{y:.1f}<br>Score %{customdata[0]} "
                "· %{customdata[1]} wickets<br>Bowler %{customdata[2]}<extra></extra>"
            ),
        )
        chart_theme(fig, theme, 300)
        fig.update_layout(xaxis_title="Delivery sequence", yaxis_title="Pressure score (0–100)")
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

with pressure_analytics:
    st.markdown(
        '<div class="section-head">Pressure analytics</div>'
        '<div class="section-sub">Explore classified pressure deliveries and their reconstructed match context</div>',
        unsafe_allow_html=True,
    )
    if filtered_pressure.empty:
        st.info("No curated pressure deliveries match these filters.")
    else:
        pressure_events = filtered_pressure[
            filtered_pressure["is_batting_pressure"]
            | filtered_pressure["is_bowling_pressure"]
        ].copy()
        pressure_events["pressure_intensity"] = pressure_events[
            ["batting_pressure", "bowling_pressure"]
        ].max(axis=1)
        pressure_events = pressure_events.sort_values(
            ["pressure_intensity", "match_id", "innings", "innings_ball_num"],
            ascending=[False, True, True, True],
        ).head(100)
        display_columns = [
            "comp_name",
            "season",
            "match_id",
            "innings",
            "overid",
            "innings_ball_num",
            "score_before",
            "wickets_before",
            "runs_required",
            "required_run_rate",
            "striker_name",
            "bowler_name",
            "batting_pressure",
            "bowling_pressure",
            "is_batting_pressure",
            "is_bowling_pressure",
        ]
        st.dataframe(
            pressure_events[display_columns],
            hide_index=True,
            width="stretch",
            height=440,
        )
        st.caption(
            f"{int(filtered_pressure['is_batting_pressure'].sum()):,} batting-pressure "
            f"and {int(filtered_pressure['is_bowling_pressure'].sum()):,} "
            "bowling-pressure delivery flags in the filtered curated scope."
        )
    st.markdown(
        "Pressure is a provisional, state-based 0–100 heuristic, not a match-win "
        "probability. Labels use the documented component weights and threshold "
        "of 50. Each event shows pre-delivery score, wickets, chase requirements, "
        "and the batter/bowler involved. The verified curated data covers the "
        "project’s selected IPL and post-2022 T20I scope; source-data semantics "
        "and pressure assumptions remain under review."
    )

with batting:
    st.markdown('<div class="section-head">Batting room</div><div class="section-sub">Run makers and boundary finders from the selected match set</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-head">Top 10 batters under pressure</div>', unsafe_allow_html=True)
    batter_columns = [
        "rank",
        "player_name",
        "spi",
        "pressure_strike_rate",
        "normal_strike_rate",
        "pressure_opportunities",
        "pressure_matches",
        "reliability",
        "evidence_summary",
    ]
    st.dataframe(
        rankings["top_batters"][batter_columns],
        hide_index=True,
        width="stretch",
        height=330,
    )
    st.download_button(
        "Download top 10 batters CSV",
        data=rankings["top_batters"].to_csv(index=False).encode("utf-8"),
        file_name="top_10_batters.csv",
        mime="text/csv",
    )
    st.caption(
        "This table is read from the generated ranking export and remains the "
        "same as the published CSV. Filters below affect the match/player "
        "exploration, not this run’s provisional ranking scope."
    )
    if filtered_metrics is not None:
        st.markdown('<div class="section-head">Batter pressure metrics in this selection</div>', unsafe_allow_html=True)
        st.dataframe(
            filtered_metrics["batters"]
            .sort_values(["pressure_opportunities", "pressure_strike_rate"], ascending=False)
            .head(20)[
                [
                    "striker_name",
                    "pressure_strike_rate",
                    "normal_strike_rate",
                    "pressure_opportunities",
                    "pressure_matches",
                    "consistency",
                ]
            ],
            hide_index=True,
            width="stretch",
        )
    batter_data = filtered_balls.copy()
    if selected_team != "All teams":
        batter_data = batter_data[batter_data["batting_team_id"].isin(team_ids)]
    if batter_data.empty:
        st.info("No batting deliveries in this selection.")
    else:
        batters = (
            batter_data.groupby("striker_name", as_index=False)
            .agg(
                Runs=("runs", "sum"),
                Fours=("is_four", "sum"),
                Sixes=("is_six", "sum"),
                Balls=("innings_ball_num", "count"),
            )
        )
        batters["Strike rate"] = (100 * batters["Runs"] / batters["Balls"].replace(0, pd.NA)).round(1)
        batting_cols = st.columns([1.65, 1], gap="large")
        with batting_cols[0]:
            leaders = batters.nlargest(10, "Runs").sort_values("Runs")
            fig = px.bar(
                leaders,
                x="Runs",
                y="striker_name",
                orientation="h",
                text="Runs",
                color="Runs",
                color_continuous_scale=theme["chart_scale"],
                labels={"striker_name": "", "Runs": "Runs"},
            )
            fig.update_traces(textposition="outside", marker_line_width=0)
            fig.update_layout(coloraxis_showscale=False, xaxis_title=None, yaxis_title=None)
            chart_theme(fig, theme, 400)
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
        with batting_cols[1]:
            st.markdown('<div class="section-head" style="margin-top:4px">Top run scorers</div>', unsafe_allow_html=True)
            st.dataframe(
                batters.nlargest(12, "Runs")[["striker_name", "Runs", "Fours", "Sixes", "Strike rate"]]
                .rename(columns={"striker_name": "Batter"}),
                hide_index=True,
                width="stretch",
                height=410,
            )
        total_scored = int(batter_data["runs"].sum())
        boundary_runs = int((4 * batter_data["is_four"] + 6 * batter_data["is_six"]).sum())
        st.caption(f"Batters scored {boundary_runs:,} of {total_scored:,} runs through boundaries in this selection.")

with bowling:
    st.markdown('<div class="section-head">Bowling lab</div><div class="section-sub">Wicket takers, dismissal patterns and the pace-versus-spin split</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-head">Top 10 bowlers under pressure</div>', unsafe_allow_html=True)
    bowler_columns = [
        "rank",
        "player_name",
        "spi",
        "pressure_economy",
        "normal_economy",
        "pressure_opportunities",
        "pressure_matches",
        "reliability",
        "evidence_summary",
    ]
    st.dataframe(
        rankings["top_bowlers"][bowler_columns],
        hide_index=True,
        width="stretch",
        height=330,
    )
    st.download_button(
        "Download top 10 bowlers CSV",
        data=rankings["top_bowlers"].to_csv(index=False).encode("utf-8"),
        file_name="top_10_bowlers.csv",
        mime="text/csv",
    )
    st.caption(
        "This table is the exact generated ranking export; filter-scoped "
        "bowling metrics are shown separately below."
    )
    if filtered_metrics is not None:
        st.markdown('<div class="section-head">Bowler pressure metrics in this selection</div>', unsafe_allow_html=True)
        st.dataframe(
            filtered_metrics["bowlers"]
            .sort_values(["pressure_opportunities", "pressure_economy"], ascending=[False, True])
            .head(20)[
                [
                    "bowler_name",
                    "pressure_economy",
                    "normal_economy",
                    "pressure_wickets",
                    "pressure_opportunities",
                    "pressure_matches",
                    "consistency",
                ]
            ],
            hide_index=True,
            width="stretch",
        )
    bowling_cols = st.columns([1.2, 1, 1], gap="large")
    wickets = filtered_balls[filtered_balls["is_wicket"]]
    with bowling_cols[0]:
        st.markdown('<div class="section-head" style="margin-top:4px">Wicket leaders</div>', unsafe_allow_html=True)
        if not wickets.empty:
            bowlers = wickets.groupby("bowler_name").size().sort_values(ascending=False).head(12).sort_values()
            fig = go.Figure(go.Bar(
                x=bowlers.values,
                y=bowlers.index,
                orientation="h",
                marker={
                    "color": bowlers.values,
                    "colorscale": [
                        [0, theme["primary"]],
                        [1, theme["accent"]],
                    ],
                    "line": {"width": 0},
                },
                text=bowlers.values,
                textposition="outside",
            ))
            fig.update_layout(xaxis_title="Wickets", yaxis_title=None)
            chart_theme(fig, theme, 420)
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
        else:
            st.info("No wickets recorded for this selection.")
    with bowling_cols[1]:
        st.markdown('<div class="section-head" style="margin-top:4px">How wickets fall</div>', unsafe_allow_html=True)
        dismissals = wickets["dismissal_type"].fillna("Unspecified").replace("", "Unspecified").value_counts().head(7)
        if not dismissals.empty:
            fig = px.pie(
                values=dismissals.values,
                names=dismissals.index,
                hole=.69,
                color_discrete_sequence=theme["chart_colors"],
            )
            fig.update_traces(
                textinfo="percent",
                marker={"line": {"color": theme["background"], "width": 3}},
            )
            fig.update_layout(showlegend=True, legend={"orientation": "h", "y": -.13, "font": {"size": 10}})
            chart_theme(fig, theme, 340)
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    with bowling_cols[2]:
        st.markdown('<div class="section-head" style="margin-top:4px">Pace & spin</div>', unsafe_allow_html=True)
        bowling_styles = filtered_balls["pace_or_spin"].fillna("Unclassified").replace("", "Unclassified").value_counts()
        if not bowling_styles.empty:
            fig = px.pie(
                values=bowling_styles.values,
                names=bowling_styles.index,
                hole=.69,
                color_discrete_sequence=theme["chart_colors"],
            )
            fig.update_traces(
                textinfo="percent",
                marker={"line": {"color": theme["background"], "width": 3}},
            )
            fig.update_layout(showlegend=True, legend={"orientation": "h", "y": -.13, "font": {"size": 10}})
            chart_theme(fig, theme, 340)
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    st.caption(f"{wicket_count:,} wickets across {filtered_balls['match_id'].nunique():,} matches in this selection.")

with player_insights:
    st.markdown(
        '<div class="section-head">Player insights</div>'
        '<div class="section-sub">Pressure metrics, baselines, reliability, and match-by-match history</div>',
        unsafe_allow_html=True,
    )
    if filtered_metrics is None:
        st.info("No curated player analytics match these filters.")
    else:
        batter_col, bowler_col = st.columns(2, gap="large")
        with batter_col:
            batter_metrics = filtered_metrics["batters"].dropna(subset=["striker_id"])
            if batter_metrics.empty:
                st.info("No batter records in this selection.")
            else:
                batter_options = {
                    f"{row.striker_name} · {int(row.striker_id)}": int(row.striker_id)
                    for row in batter_metrics.sort_values("striker_name").itertuples()
                }
                selected_batter = st.selectbox(
                    "Batter",
                    list(batter_options),
                    key="insight_batter",
                )
                batter_id = batter_options[selected_batter]
                batter_row = batter_metrics[batter_metrics["striker_id"].eq(batter_id)].iloc[0]
                st.metric(
                    "Pressure strike rate",
                    f"{batter_row['pressure_strike_rate']:.1f}"
                    if pd.notna(batter_row["pressure_strike_rate"])
                    else "—",
                    f"{batter_row['pressure_strike_rate'] - batter_row['normal_strike_rate']:+.1f} vs normal"
                    if pd.notna(batter_row["pressure_strike_rate"])
                    and pd.notna(batter_row["normal_strike_rate"])
                    else None,
                )
                st.caption(
                    f"{int(batter_row['pressure_opportunities']):,} pressure balls · "
                    f"{int(batter_row['pressure_matches'])} pressure matches · "
                    f"{batter_row['consistency']:.1f} consistency"
                    if pd.notna(batter_row["consistency"])
                    else f"{int(batter_row['pressure_opportunities']):,} pressure balls"
                )
                history = filtered_metrics["batter_matches"]
                history = history[history["striker_id"].eq(batter_id)].sort_values("match_id")
                st.dataframe(
                    history[["match_id", "comp_name", "pressure_balls", "pressure_strike_rate"]],
                    hide_index=True,
                    width="stretch",
                    height=240,
                )
                if history["pressure_strike_rate"].notna().any():
                    fig = px.line(
                        history,
                        x="match_id",
                        y="pressure_strike_rate",
                        markers=True,
                        labels={"match_id": "Match", "pressure_strike_rate": "Pressure SR"},
                    )
                    chart_theme(fig, theme, 240)
                    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
        with bowler_col:
            bowler_metrics = filtered_metrics["bowlers"].dropna(subset=["bowler_id"])
            if bowler_metrics.empty:
                st.info("No bowler records in this selection.")
            else:
                bowler_options = {
                    f"{row.bowler_name} · {int(row.bowler_id)}": int(row.bowler_id)
                    for row in bowler_metrics.sort_values("bowler_name").itertuples()
                }
                selected_bowler = st.selectbox(
                    "Bowler",
                    list(bowler_options),
                    key="insight_bowler",
                )
                bowler_id = bowler_options[selected_bowler]
                bowler_row = bowler_metrics[bowler_metrics["bowler_id"].eq(bowler_id)].iloc[0]
                st.metric(
                    "Pressure economy",
                    f"{bowler_row['pressure_economy']:.2f}"
                    if pd.notna(bowler_row["pressure_economy"])
                    else "—",
                    f"{bowler_row['normal_economy'] - bowler_row['pressure_economy']:+.2f} vs normal"
                    if pd.notna(bowler_row["pressure_economy"])
                    and pd.notna(bowler_row["normal_economy"])
                    else None,
                )
                st.caption(
                    f"{int(bowler_row['pressure_opportunities']):,} pressure balls · "
                    f"{int(bowler_row['pressure_matches'])} pressure matches · "
                    f"{bowler_row['consistency']:.1f} consistency"
                    if pd.notna(bowler_row["consistency"])
                    else f"{int(bowler_row['pressure_opportunities']):,} pressure balls"
                )
                history = filtered_metrics["bowler_matches"]
                history = history[history["bowler_id"].eq(bowler_id)].sort_values("match_id")
                st.dataframe(
                    history[["match_id", "comp_name", "pressure_balls", "pressure_economy"]],
                    hide_index=True,
                    width="stretch",
                    height=240,
                )
                if history["pressure_economy"].notna().any():
                    fig = px.line(
                        history,
                        x="match_id",
                        y="pressure_economy",
                        markers=True,
                        labels={"match_id": "Match", "pressure_economy": "Pressure economy"},
                    )
                    chart_theme(fig, theme, 240)
                    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

with methodology:
    st.markdown(
        '<div class="section-head">Methodology and limitations</div>'
        '<div class="section-sub">Reproducible pressure definitions, SPI formula, evidence, and scope warnings</div>',
        unsafe_allow_html=True,
    )
    st.warning(
        "Pressure weights, threshold, eligibility floors, and rankings remain "
        "provisional. They have not been approved against the official Rajasthan "
        "Royals problem statement, which is not present in the workspace."
    )
    st.markdown(
        """
        - Delivery state is reconstructed **before** each event; chase pressure uses
          the required run rate, wickets, time, and closeness to the reference rate.
        - Batter and bowler pressure are separate 0–100 weighted heuristics; a score
          of 50 or more is labeled pressure. The score is not a win probability.
        - SPI combines a bounded, competition-adjusted performance difference,
          match consistency, and pressure-exposure reliability using 60/20/20 weights.
        - Reliability is `n / (n + 30)` and the provisional eligibility floor is
          three pressure matches plus twelve pressure balls.
        - Top-ten rows come directly from the exported CSV files; they are not
          recalculated in the dashboard.
        - Machine-learning clusters, PageRank, and replay checks are supplementary
          demonstrations and do not enter SPI.
        """
    )
    st.download_button(
        "Download generated methodology report",
        data=load_methodology_text().encode("utf-8"),
        file_name="methodology_report.md",
        mime="text/markdown",
    )
    with st.expander("Full generated methodology and ranking evidence"):
        st.markdown(load_methodology_text())

with ai_analyst_tab:
    st.markdown(
        '<div class="section-head">AI Cricket Analyst</div>'
        '<div class="section-sub">Ask about the supplied historical IPL and T20I archive; calculations stay grounded in verified delivery records.</div>',
        unsafe_allow_html=True,
    )
    st.info(
        "The analyst uses the full historical archive independently of the sidebar "
        "match filters. Include a season, competition, player role, or match ID when "
        "you want a narrower answer. Pressure and SPI methodology remain provisional."
    )
    try:
        analyst_provider = provider_from_environment()
    except LLMProviderError as error:
        analyst_provider = None
        st.warning(str(error))
    if analyst_provider is None:
        st.caption(
            "The local evidence-backed analyst is active. Enable SUPERR_LLM_API_KEY "
            "and SUPERR_LLM_MODEL for dynamic multi-step tool calling and follow-up "
            "interpretation; no external provider is configured."
        )
    else:
        st.caption(
            f"Dynamic multi-step tool calling is enabled with model "
            f"`{analyst_provider.model}`. All calculations run through the "
            "validated local analytics tools."
        )

    analyst_state_key = "cricket_analyst_conversation"
    if analyst_state_key not in st.session_state:
        st.session_state[analyst_state_key] = []
    suggested_questions = [
        "Who is the best batter under pressure in IPL 2023?",
        "Who is the best bowler under pressure in T20I 2024?",
        "Compare batter Rinku Singh and David Miller under pressure",
        "Show the most consistent bowlers under pressure",
    ]
    if not st.session_state[analyst_state_key]:
        st.markdown("**Try asking**")
        suggestion_columns = st.columns(2)
        for index, suggested_question in enumerate(suggested_questions):
            if suggestion_columns[index % 2].button(
                suggested_question,
                key=f"analyst_suggestion_{index}",
                use_container_width=True,
            ):
                st.session_state["analyst_pending_question"] = suggested_question
                st.rerun()

    prompt = st.chat_input(
        "Ask a cricket question…",
        key="cricket_analyst_chat_input",
    )
    pending_prompt = st.session_state.pop("analyst_pending_question", None)
    submitted_prompt = pending_prompt or prompt
    if submitted_prompt:
        with st.spinner("Investigating the archive and verifying analytical evidence…"):
            deliveries = load_pressure_data()
            analyst_teams = roster[["comp_id", "team_id", "team_name"]].drop_duplicates()
            active_provider = analyst_provider
            if active_provider is not None:
                try:
                    toolbox = CricketToolbox(curated_deliveries=deliveries)
                    result = analyze_with_tools(
                        submitted_prompt,
                        active_provider,
                        toolbox,
                        conversation=st.session_state[analyst_state_key],
                    )
                except LLMProviderError as error:
                    active_provider = None
                    st.warning(
                        f"Dynamic provider analysis was unavailable; using the "
                        f"local evidence-backed parser instead. {error}"
                    )
                    result = analyze_question(
                        submitted_prompt,
                        deliveries,
                        teams=analyst_teams,
                    )
            else:
                result = analyze_question(
                    submitted_prompt,
                    deliveries,
                    teams=analyst_teams,
                )
            if active_provider is not None and not result.get("tool_trace") and result["status"] == "answer":
                try:
                    result["commentary"] = generate_commentary(
                        active_provider, result
                    )
                except LLMProviderError as error:
                    result["commentary_notice"] = str(error)
        st.session_state[analyst_state_key].append(
            {"question": submitted_prompt, "result": result}
        )

    for conversation_index, conversation_item in enumerate(
        st.session_state[analyst_state_key]
    ):
        with st.chat_message("user"):
            st.markdown(conversation_item["question"])
        result = conversation_item["result"]
        with st.chat_message("assistant"):
            st.markdown(result["answer"])
            if result.get("commentary"):
                st.caption(result["commentary"])
            if result.get("commentary_notice"):
                st.caption(result["commentary_notice"])
            if result.get("clarification_options"):
                st.markdown("Please choose or specify:")
                for option in result["clarification_options"]:
                    st.markdown(f"- {option}")
            if result.get("scope"):
                with st.expander("Competition, season, and calculation scope"):
                    st.json(result["scope"], expanded=False)
            if result.get("metrics"):
                metrics_frame = pd.DataFrame(result["metrics"])
                st.markdown("**Analytical results**")
                st.dataframe(metrics_frame, hide_index=True, width="stretch")
                chart_value = next(
                    (
                        column
                        for column in (
                            "SPI",
                            "spi",
                            "performance",
                            "pressure_performance",
                            "pressure_score",
                        )
                        if column in metrics_frame
                        and pd.to_numeric(metrics_frame[column], errors="coerce").notna().any()
                    ),
                    None,
                )
                if (
                    chart_value
                    and "player_name" in metrics_frame
                    and len(metrics_frame) > 1
                ):
                    chart_frame = metrics_frame.copy()
                    chart_frame[chart_value] = pd.to_numeric(
                        chart_frame[chart_value], errors="coerce"
                    )
                    chart_frame = chart_frame.dropna(subset=[chart_value]).head(10)
                    if not chart_frame.empty:
                        chart = px.bar(
                            chart_frame,
                            x="player_name",
                            y=chart_value,
                            color_discrete_sequence=theme["chart_colors"],
                            labels={"player_name": "Player", chart_value: chart_value},
                        )
                        chart_theme(chart, theme, height=280)
                        st.plotly_chart(
                            chart,
                            width="stretch",
                            config={"displayModeBar": False},
                        )
            if result.get("evidence"):
                with st.expander(
                    f"Supporting match-level evidence ({len(result['evidence']):,} records)"
                ):
                    st.dataframe(
                        pd.DataFrame(result["evidence"]),
                        hide_index=True,
                        width="stretch",
                    )
            if result.get("verification"):
                st.caption(f"Evidence check: {result['verification']}")
            if result.get("limitations"):
                with st.expander("Limitations and uncertainty"):
                    for limitation in result["limitations"]:
                        st.markdown(f"- {limitation}")
            if result.get("tool_trace"):
                with st.expander(
                    f"Analysis tools used ({len(result['tool_trace'])})"
                ):
                    st.dataframe(
                        pd.DataFrame(result["tool_trace"]),
                        hide_index=True,
                        width="stretch",
                    )
                    for tool_index, tool_result in enumerate(
                        result.get("tool_results", [])
                    ):
                        tool_name = tool_result.get("tool", "Tool result")
                        with st.expander(f"{tool_index + 1}. {tool_name}"):
                            payload = tool_result.get("result", tool_result)
                            if isinstance(payload, dict) and isinstance(payload.get("rows"), list):
                                rows = payload["rows"]
                                if rows:
                                    st.dataframe(
                                        pd.DataFrame(rows),
                                        hide_index=True,
                                        width="stretch",
                                    )
                                st.caption(
                                    f"Read-only query · row limit {payload.get('row_limit', 'not applicable')} · "
                                    f"truncated: {payload.get('truncated', False)}"
                                )
                                remaining = {
                                    key: value
                                    for key, value in payload.items()
                                    if key != "rows"
                                }
                                if remaining:
                                    st.json(remaining, expanded=False)
                            elif isinstance(payload, dict) and (
                                isinstance(payload.get("metrics"), list)
                                or isinstance(payload.get("evidence"), list)
                            ):
                                for key in ("metrics", "evidence"):
                                    if payload.get(key):
                                        st.markdown(f"**{key.replace('_', ' ').title()}**")
                                        st.dataframe(
                                            pd.DataFrame(payload[key]),
                                            hide_index=True,
                                            width="stretch",
                                        )
                                st.json(
                                    {
                                        key: value
                                        for key, value in payload.items()
                                        if key not in {"metrics", "evidence"}
                                    },
                                    expanded=False,
                                )
                            else:
                                st.json(payload, expanded=False)
            if result["status"] != "answer":
                st.warning(f"Answer status: {result['status']}")
                if st.button(
                    "Retry analysis",
                    key=f"analyst_retry_{conversation_index}",
                ):
                    st.session_state["analyst_pending_question"] = conversation_item["question"]
                    st.rerun()

    with st.expander("Supported question categories"):
        for category, description in SUPPORTED_QUESTION_CATEGORIES.items():
            st.markdown(f"- **{category.replace('_', ' ').title()}** — {description}")

with fixtures:
    st.markdown('<div class="section-head">The fixture book</div><div class="section-sub">Searchable results, venues and match context from the archive</div>', unsafe_allow_html=True)
    fixture_search = st.text_input("Search teams, venue, or result", placeholder="Try India, London, Won by…")
    fixture_view = filtered_matches.copy()
    if fixture_search.strip():
        searchable = fixture_view[
            ["home_team", "away_team", "venue_country", "result", "stage"]
        ].fillna("").astype(str).agg(" ".join, axis=1)
        fixture_view = fixture_view[searchable.str.contains(fixture_search.strip(), case=False, regex=False)]
    fixture_view = fixture_view.sort_values("match_date", ascending=False)
    display = fixture_view[["match_date", "home_team", "away_team", "venue_country", "stage", "result"]].copy()
    display["match_date"] = display["match_date"].dt.strftime("%d %b %Y")
    display.columns = ["Date", "Home", "Away", "Venue", "Stage", "Result"]
    st.dataframe(display, hide_index=True, width="stretch", height=540)
    st.caption(f"Showing {len(display):,} of {len(filtered_matches):,} matches.")

with final_validation_tab:
    artifacts = load_final_validation_artifacts()
    validation = artifacts["validation"]
    ranking_run = artifacts["ranking_run"]
    quality = artifacts["quality"]
    validation_summary = quality["validation"]["summary"]
    st.markdown(
        '<div class="section-head">Final Methodology &amp; Validation</div>'
        '<div class="section-sub">Evidence, sensitivity and ranking provenance for the historical-data run</div>',
        unsafe_allow_html=True,
    )
    st.warning(
        "PROVISIONAL — NOT OFFICIALLY APPROVED. The official Round 1 problem "
        "statement and MASTER_SPECIFICATION.md are not present in the workspace. "
        "The rankings are generated from the current requested IPL/T20I scope, "
        "but methodology and source-field interpretations require review."
    )

    st.markdown('<div class="section-head">A. Project and dataset scope</div>', unsafe_allow_html=True)
    st.markdown(
        "Requested objective: compare batter and bowler performance in pressure "
        "situations using only the supplied historical IPL and T20I archive from "
        "2022 onward. No live feed or fabricated match data is used. This scope "
        "cannot be confirmed against the absent official brief."
    )
    scope_cols = st.columns(4)
    for column, label, value in zip(
        scope_cols,
        ["IPL matches", "T20I matches", "Deliveries", "ETL validation"],
        [
            f"{validation['scope']['ipl_matches']:,}",
            f"{validation['scope']['t20i_matches']:,}",
            f"{validation['scope']['selected_deliveries']:,}",
            f"{validation_summary['passed_checks']} pass · {validation_summary['warnings']} warnings",
        ],
    ):
        column.metric(label, value)
    dataset_inventory = pd.DataFrame(
        [
            {"Dataset": name, "Rows": profile["rows"], "Columns": profile["columns"]}
            for name, profile in quality["validation"]["datasets"].items()
        ]
    )
    st.dataframe(dataset_inventory, hide_index=True, width="stretch")
    st.caption(
        f"Scope start: {validation['scope']['start_date']}. "
        f"IPL competitions: {len(validation['scope']['ipl_competitions'])}; "
        f"T20I competitions: {len(validation['scope']['t20i_competitions'])}. "
        f"Raw hashes match ETL manifest: {validation['raw_hashes_match_etl_manifest']}."
    )

    st.markdown('<div class="section-head">B. Pressure methodology</div>', unsafe_allow_html=True)
    st.markdown(
        """
        The score is a provisional 0–100 heuristic, **not** a win probability.
        For chases, let `r = required run rate / prior format reference rate`.
        Batting run-rate pressure is `clip((r − 1) / 1.5, 0, 1)`; bowling uses
        `clip((1 − r) / 1.5, 0, 1)`. For first innings, run-rate departure from
        the reference is normalized and multiplied by innings progress.
        """
    )
    pressure_indicator_descriptions = {
        "run_rate": "Chase difficulty direction differs by role; first-innings rate vs prior reference.",
        "wickets": "Batting: wickets lost/10. Bowling: wickets remaining/10 (may be opportunity, not pressure).",
        "time": "Legal balls used / scheduled legal balls; later innings raise score for both roles.",
        "closeness": "exp(−|rate ratio − 1|); peaks at rate parity and overlaps rate-difficulty information.",
    }
    for role, label in [("batter", "Batting"), ("bowler", "Bowling")]:
        diagnostic = ranking_run["pressure_diagnostics"][role]
        side_weights = diagnostic["weights"]
        rows = [
            {
                "Indicator": component,
                "Weight": side_weights[component],
                "Mean normalized value": item["mean_normalized_component"],
                "Mean score points": item["mean_score_points"],
                "Meaning / limitation": pressure_indicator_descriptions[component],
            }
            for component, item in diagnostic["mean_normalized_contributions"].items()
        ]
        st.markdown(f"**{label} pressure components**")
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        sample = diagnostic["sample_event"]
        if sample:
            sample_columns = {
                "match_id": "Match",
                "innings": "Innings",
                "innings_ball_num": "Delivery",
                "score_before": "Score before",
                "wickets_before": "Wickets before",
                "balls_remaining": "Balls remaining",
                "target": "Target",
                "required_run_rate": "Required RR",
                "reference_run_rate": "Reference RR",
                "pressure_score": "Pressure score",
            }
            st.caption(
                f"Actual highest-scoring {label.lower()} event in this dataset slice "
                f"(match {sample['match_id']}, innings {sample['innings']}, "
                f"delivery {sample['innings_ball_num']}):"
            )
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            display: sample[field]
                            for field, display in sample_columns.items()
                        }
                    ]
                ),
                hide_index=True,
                width="stretch",
            )
            component_rows = [
                {
                    "Indicator": component,
                    "Normalized value": values["normalized_value"],
                    "Weight": values["weight"],
                    "Score-point contribution": values["score_points"],
                }
                for component, values in sample["components"].items()
            ]
            st.dataframe(pd.DataFrame(component_rows), hide_index=True, width="stretch")
    st.info(
        "Current threshold: score ≥ 50. Pressure labels are role-specific, but "
        "the shared time and closeness terms do not establish equal fairness. "
        "Closeness peaks at rate parity; bowling wickets remaining may indicate "
        "wicket opportunity. No replacement was adopted without domain evidence."
    )

    st.markdown('<div class="section-head">C. SPI calculation</div>', unsafe_allow_html=True)
    st.markdown(
        """
        **Batter:** `SPI = 0.60 × performance + 0.20 × consistency + 0.20 × reliability`  
        **Bowler:** same component weights, but pressure economy and normal economy
        are direction-adjusted so lower pressure economy relative to normal is better.

        `performance = 50 + 50 × tanh(adjusted_difference / (2 × s))`, where
        `s` is the eligible-player median absolute adjusted difference.
        Player pressure and normal rates are separately shrunk toward competition
        baselines with a 30-ball prior; adjusted differences are shrunk by
        `n / (n + 30)`. `reliability = 100 × n/(n+30)`. Consistency is
        `100/(1+CV)` across match pressure rates. Eligibility is at least
        3 pressure matches and 12 role-specific pressure balls (batter balls
        faced; bowler legal balls). These are provisional floors.
        """
    )
    st.warning(
        "Exposure is used both to shrink performance and to calculate reliability, "
        "so SPI may double-count sample size. Consistency is also outcome-derived. "
        "The weight sensitivity and component correlations below are diagnostic; "
        "60/20/20 is not domain-approved."
    )

    st.markdown('<div class="section-head">D. Methodology validation</div>', unsafe_allow_html=True)
    independent_comparison = validation["independent_raw_to_curated_comparison"]
    checks_frame = pd.DataFrame(
        [
            {
                "Independent raw calculation": field,
                "Matched rows": item["matched_rows"],
                "Mismatches": item["mismatch_rows"],
            }
            for field, item in independent_comparison.items()
            if isinstance(item, dict) and "mismatch_rows" in item
        ]
    )
    st.dataframe(checks_frame, hide_index=True, width="stretch")
    st.caption(
        f"Raw-only rows: {independent_comparison['raw_only_rows']}; "
        f"curated-only rows: {independent_comparison['curated_only_rows']}. "
        "This verifies arithmetic against the supplied archive, not the source "
        "archive against an external scorecard."
    )
    for role in ("batter", "bowler"):
        st.markdown(f"**{role.title()} pressure-threshold and SPI sensitivity**")
        scenario_rows = [
            {
                "Scenario": item["scenario"],
                "Pressure deliveries": item["pressure_event_count"],
                "Pressure opportunities": item["pressure_opportunity_count"],
                "Eligible players": item["eligible_players"],
                "Top-10 Jaccard overlap": round(item["top_10_overlap_jaccard"], 3),
                "Top-10 player IDs": ", ".join(map(str, item["top_10_player_ids"])),
            }
            for item in ranking_run["sensitivity"][role]
        ]
        st.dataframe(pd.DataFrame(scenario_rows), hide_index=True, width="stretch")
        st.markdown(f"**{role.title()} pressure-indicator correlations**")
        st.dataframe(
            pd.DataFrame(
                ranking_run["pressure_diagnostics"][role]["component_spearman_pairs"]
            ),
            hide_index=True,
            width="stretch",
        )
        st.markdown(f"**{role.title()} SPI-component correlations**")
        st.dataframe(
            pd.DataFrame(
                ranking_run["correlation_diagnostics"][role]["spearman_pairs"]
            ),
            hide_index=True,
            width="stretch",
        )

    st.markdown("**Unresolved source-data observations**")
    unresolved = pd.DataFrame(
        [
            {
                "Check": "Source runs on byes/legbyes/Penalty",
                "Observed": validation["run_and_extras"]["nonzero_source_runs_on_byes_legbyes_or_penalty"],
                "Interpretation": "No scoped occurrences; source semantics still require documentation.",
            },
            {
                "Check": "Extras without extras_type",
                "Observed": validation["run_and_extras"]["records_with_extras_runs_but_no_extras_type"],
                "Interpretation": "Retained; source classification is missing.",
            },
            {
                "Check": "Unknown 'other' extras deliveries",
                "Observed": validation["delivery_rules"]["unknown_other_extra_deliveries"],
                "Interpretation": "Included in current bowler-conceded runs and legal-ball treatment; provisional.",
            },
            {
                "Check": "Four boundary flag disagreements",
                "Observed": validation["boundaries"]["four_flag_mismatches_against_source_runs_equals_4"],
                "Interpretation": "Flags retained, not rewritten.",
            },
            {
                "Check": "Six boundary flag disagreements",
                "Observed": validation["boundaries"]["six_flag_mismatches_against_source_runs_equals_6"],
                "Interpretation": "Flags retained, not rewritten.",
            },
            {
                "Check": "Over-ball number above six",
                "Observed": validation["innings_and_not_outs"]["over_ball_num_above_six_rows"],
                "Interpretation": "Source field is not used as legal-ball count.",
            },
            {
                "Check": "Approximate striker not-out appearances",
                "Observed": validation["innings_and_not_outs"]["approximate_striker_not_out_appearances"],
                "Interpretation": validation["innings_and_not_outs"]["not_out_limitation"],
            },
        ]
    )
    st.dataframe(unresolved, hide_index=True, width="stretch")

    st.markdown('<div class="section-head">E. Provisional batter ranking export</div>', unsafe_allow_html=True)
    batter_rankings = rankings["top_batters"]
    st.dataframe(batter_rankings, hide_index=True, width="stretch", height=360)
    st.download_button(
        "Download exact generated top 10 batters CSV",
        data=batter_rankings.to_csv(index=False).encode("utf-8"),
        file_name="top_10_batters.csv",
        mime="text/csv",
        key="download_final_validation_batters",
    )
    with st.expander("Player evidence for all selected batters"):
        st.dataframe(
            batter_rankings[["rank", "player_id", "player_name", "evidence_summary"]],
            hide_index=True,
            width="stretch",
        )

    st.markdown('<div class="section-head">F. Provisional bowler ranking export</div>', unsafe_allow_html=True)
    bowler_rankings = rankings["top_bowlers"]
    st.dataframe(bowler_rankings, hide_index=True, width="stretch", height=360)
    st.download_button(
        "Download exact generated top 10 bowlers CSV",
        data=bowler_rankings.to_csv(index=False).encode("utf-8"),
        file_name="top_10_bowlers.csv",
        mime="text/csv",
        key="download_final_validation_bowlers",
    )
    with st.expander("Player evidence for all selected bowlers"):
        st.dataframe(
            bowler_rankings[["rank", "player_id", "player_name", "evidence_summary"]],
            hide_index=True,
            width="stretch",
        )

    st.markdown('<div class="section-head">G. Evidence, limitations and provenance</div>', unsafe_allow_html=True)
    st.markdown(
        f"**Methodology version:** `{ranking_run['methodology_version']}`  \n"
        f"**Ranking run ID:** `{ranking_run['ranking_run_id']}`  \n"
        "**Limitations:** no official problem statement or external scorecard "
        "oracle; boundary and extras semantics unresolved; revised-target and "
        "super-over conventions need authoritative confirmation; rankings are "
        "sensitive to threshold and eligibility assumptions."
    )
    with st.expander("Raw source SHA-256 hashes"):
        st.dataframe(
            pd.DataFrame(
                [
                    {"File": filename, "SHA-256": digest}
                    for filename, digest in validation["raw_input_sha256"].items()
                ]
            ),
            hide_index=True,
            width="stretch",
        )
    with st.expander("All twenty evidence summaries"):
        st.dataframe(
            pd.concat(
                [
                    batter_rankings.assign(role="Batter"),
                    bowler_rankings.assign(role="Bowler"),
                ],
                ignore_index=True,
            )[["role", "rank", "player_id", "player_name", "evidence_summary"]],
            hide_index=True,
            width="stretch",
        )

    st.markdown('<div class="section-head">H. Final submission readiness</div>', unsafe_allow_html=True)
    ranking_validation = ranking_run["ranking_validation"]
    report_available = (REPORTS / "methodology_report.md").exists()
    report_text = load_methodology_text() if report_available else ""
    ranking_files_match = all(
        ranking_run["ranking_file_sha256"][f"{role}s"]
        == hashlib.sha256(
            (REPORTS / f"top_10_{role}s.csv").read_bytes()
        ).hexdigest()
        for role in ("batter", "bowler")
    )
    dashboard_rankings_match = all(
        rankings[f"top_{role}s"].equals(
            pd.read_csv(REPORTS / f"top_10_{role}s.csv")
        )
        for role in ("batter", "bowler")
    )
    report_run_matches = (
        ranking_run["ranking_run_id"] in report_text
        and all(
            ranking_run["ranking_file_sha256"][f"{role}s"] in report_text
            for role in ("batter", "bowler")
        )
    )
    final_report_checks = [
        ("Official requirements covered", "NOT VERIFIED — official brief unavailable"),
        ("Methodology validation", "IN PROGRESS — provisional assumptions need approval"),
        (
            "Cricket calculation validation",
            "ARITHMETIC CHECKS PASSED — external source oracle unavailable"
            if all(item["mismatch_rows"] == 0 for item in independent_comparison.values() if isinstance(item, dict) and "mismatch_rows" in item)
            else "CHECKS FAILED — inspect validation report",
        ),
        (
            "Exactly 10 unique batters",
            "PASS" if ranking_validation["batter"]["exactly_ten"] and ranking_validation["batter"]["unique_player_ids"] else "FAIL",
        ),
        (
            "Exactly 10 unique bowlers",
            "PASS" if ranking_validation["bowler"]["exactly_ten"] and ranking_validation["bowler"]["unique_player_ids"] else "FAIL",
        ),
        (
            "Report/CSV/dashboard consistency",
            "HASH-VERIFIED" if ranking_files_match and dashboard_rankings_match and report_run_matches else "MISMATCH",
        ),
        ("Methodology report available", "YES" if report_available else "NO"),
    ]
    st.dataframe(
        pd.DataFrame(final_report_checks, columns=["Readiness item", "Status"]),
        hide_index=True,
        width="stretch",
    )
    st.download_button(
        "Download final methodology and validation report",
        data=load_methodology_text().encode("utf-8"),
        file_name="methodology_report.md",
        mime="text/markdown",
        key="download_final_methodology_report",
    )

st.markdown(
    '<div class="footer">BOUNDARY · EVERY BALL HAS A STORY &nbsp; / &nbsp; SOURCE: PROJECT CRICKET DATA ARCHIVE</div>',
    unsafe_allow_html=True,
)
