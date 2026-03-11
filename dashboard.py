"""
Greenwashing Risk Monitor — FTSE 100 Dashboard
================================================
Professional Streamlit dashboard for visualising greenwashing risk data
from the FTSE 100 data extraction pipeline.

Run:  streamlit run dashboard.py
"""

import json
import sqlite3
import pathlib
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ══════════════════════════════════════════════════════════════════════════════
# CONSTANTS & PATHS
# ══════════════════════════════════════════════════════════════════════════════

BASE = pathlib.Path(__file__).parent / "data"
DB_PATH = BASE / "greenwashing.db"

# Raw parquets
PARQUET_CLAIMS = BASE / "raw" / "company_claims.parquet"
PARQUET_NEWS = BASE / "raw" / "news_articles.parquet"
PARQUET_REDDIT = BASE / "raw" / "reddit_posts.parquet"
PARQUET_CO2 = BASE / "raw" / "owid_co2.parquet"
PARQUET_SOCIAL = BASE / "raw" / "social_signal.parquet"

# Processed parquets
PARQUET_FINAL = BASE / "processed" / "gw_final.parquet"
PARQUET_RISK_RANK = BASE / "processed" / "risk_ranking.parquet"
PARQUET_SECTOR = BASE / "processed" / "sector_analysis.parquet"
PARQUET_CREDIBILITY = BASE / "processed" / "claim_credibility.parquet"
PARQUET_CO2_TREND = BASE / "processed" / "uk_co2_trend.parquet"

LINEAGE_PATH = BASE / "lineage_log.jsonl"

RISK_COLOURS = {
    "HIGH": "#EF4444",
    "MEDIUM": "#F59E0B",
    "LOW": "#3B82F6",
    "MINIMAL": "#10B981",
}

RISK_ORDER = ["HIGH", "MEDIUM", "LOW", "MINIMAL"]



# ══════════════════════════════════════════════════════════════════════════════
# CSS THEME
# ══════════════════════════════════════════════════════════════════════════════

CSS_THEME = """
<style>
/* ── KPI Cards ── */
div[data-testid="stMetric"] {
    background: linear-gradient(135deg, #1A1F2E 0%, #242938 100%);
    border: 1px solid #2D3748;
    border-radius: 12px;
    padding: 20px 24px;
    box-shadow: 0 4px 6px -1px rgba(0,0,0,0.3);
}
div[data-testid="stMetric"] label {
    color: #94A3B8 !important;
    font-size: 0.85rem !important;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
div[data-testid="stMetric"] [data-testid="stMetricValue"] {
    font-size: 1.8rem !important;
    font-weight: 700;
}

/* ── Tab styling ── */
.stTabs [data-baseweb="tab-list"] {
    gap: 4px;
    background-color: #1A1F2E;
    border-radius: 12px;
    padding: 4px;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px;
    padding: 10px 16px;
}
.stTabs [aria-selected="true"] {
    background-color: #3B82F6 !important;
    color: white !important;
}

/* ── Sidebar ── */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0F1419 0%, #1A1F2E 100%);
}

/* ── Risk badges ── */
.risk-badge {
    display: inline-block;
    padding: 4px 14px;
    border-radius: 9999px;
    font-weight: 600;
    font-size: 0.8rem;
}
.risk-HIGH    { background: #FEE2E2; color: #991B1B; }
.risk-MEDIUM  { background: #FEF3C7; color: #92400E; }
.risk-LOW     { background: #DBEAFE; color: #1E40AF; }
.risk-MINIMAL { background: #D1FAE5; color: #065F46; }

/* ── Section header ── */
.section-header {
    font-size: 1.3rem;
    font-weight: 700;
    border-bottom: 2px solid #3B82F6;
    padding-bottom: 8px;
    margin-bottom: 16px;
}
</style>
"""

# ══════════════════════════════════════════════════════════════════════════════
# PLOTLY TEMPLATE
# ══════════════════════════════════════════════════════════════════════════════

PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, sans-serif"),
    xaxis=dict(gridcolor="#2D3748", zerolinecolor="#2D3748"),
    yaxis=dict(gridcolor="#2D3748", zerolinecolor="#2D3748"),
    colorway=["#3B82F6", "#10B981", "#F59E0B", "#EF4444",
              "#8B5CF6", "#EC4899", "#06B6D4", "#84CC16"],
    margin=dict(l=40, r=20, t=50, b=40),
)


def style_fig(fig, **kwargs):
    """Apply the dark theme to any Plotly figure."""
    layout = {**PLOTLY_LAYOUT, **kwargs}
    fig.update_layout(**layout)
    return fig


# ══════════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=300)
def load_parquet(path):
    p = pathlib.Path(path)
    if p.exists():
        return pd.read_parquet(p)
    return None


@st.cache_data(ttl=300)
def load_sqlite():
    if not DB_PATH.exists():
        return None, None
    con = sqlite3.connect(str(DB_PATH))
    claims = pd.read_sql("SELECT * FROM company_claims", con)
    try:
        sectors = pd.read_sql("SELECT * FROM sector_summary", con)
    except Exception:
        sectors = None
    con.close()
    return claims, sectors


@st.cache_data(ttl=300)
def load_lineage():
    if not LINEAGE_PATH.exists():
        return None
    entries = []
    with open(LINEAGE_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries if entries else None


def enrich_claims(df):
    """Compute risk scores from base claim data (mirrors Spark logic)."""
    df = df.copy()
    df["has_net_zero_target"] = df["net_zero_target_year"].notna().astype(int)
    df["high_reduction_claim"] = (df["reduction_pct_claimed"] > 30).astype(int)
    df["no_certification"] = (
        df["certifications"].isna() | (df["certifications"] == "")
    ).astype(int)
    df["claim_without_cert"] = (
        (df["high_reduction_claim"] == 1) & (df["no_certification"] == 1)
    ).astype(int)

    social = load_parquet(PARQUET_SOCIAL)
    if social is not None:
        merge_cols = [c for c in [
            "company_name", "reddit_post_count", "reddit_avg_score",
            "reddit_total_comments", "news_article_count", "total_media_signals",
        ] if c in social.columns]
        df = df.merge(social[merge_cols], on="company_name", how="left")
        df["total_media_signals"] = df["total_media_signals"].fillna(0)
        df["high_media_attention"] = (df["total_media_signals"] > 50).astype(int)
    else:
        for col in ["reddit_post_count", "reddit_avg_score", "reddit_total_comments",
                     "news_article_count", "total_media_signals"]:
            if col not in df.columns:
                df[col] = 0
        df["high_media_attention"] = 0

    df["greenwashing_risk_score"] = (
        df["claim_without_cert"] * 2
        + df["no_certification"]
        + df["high_media_attention"]
    )
    df["risk_category"] = df["greenwashing_risk_score"].apply(
        lambda x: "HIGH" if x >= 3 else "MEDIUM" if x == 2 else "LOW" if x == 1 else "MINIMAL"
    )
    return df


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def data_available(data, section_name):
    """Check if data is available; show styled warning if not."""
    if data is None or (isinstance(data, pd.DataFrame) and len(data) == 0):
        st.markdown(f"""
        <div style="background:#1A1F2E; border:1px solid #F59E0B; border-radius:8px;
                    padding:16px; text-align:center; margin:20px 0;">
            <span style="color:#F59E0B; font-size:1.2rem;">&#9888;</span>
            <span style="color:#94A3B8;"> {section_name} data not available.
            Run the pipeline first (main.ipynb).</span>
        </div>
        """, unsafe_allow_html=True)
        return False
    return True


def make_risk_gauge(score, title="Risk Score"):
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        domain={"x": [0, 1], "y": [0, 1]},
        title={"text": title},
        gauge={
            "axis": {"range": [0, 4], "dtick": 1},
            "bar": {"color": "#3B82F6"},
            "bgcolor": "#1A1F2E",
            "bordercolor": "#2D3748",
            "steps": [
                {"range": [0, 1], "color": "#10B981"},
                {"range": [1, 2], "color": "#3B82F6"},
                {"range": [2, 3], "color": "#F59E0B"},
                {"range": [3, 4], "color": "#EF4444"},
            ],
        },
    ))
    style_fig(fig, height=250, margin=dict(l=20, r=20, t=60, b=20))
    return fig


# ══════════════════════════════════════════════════════════════════════════════
# PAGE CONFIG
# ══════════════════════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="Greenwashing Risk Monitor | FTSE 100",
    page_icon="\U0001f6e1\ufe0f",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(CSS_THEME, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# LOAD DATA
# ══════════════════════════════════════════════════════════════════════════════

claims_raw, sector_summary_sql = load_sqlite()

gw_final = load_parquet(PARQUET_FINAL)
if gw_final is not None:
    df = gw_final.copy()
    if "risk_category" not in df.columns:
        df = enrich_claims(df)
elif claims_raw is not None:
    df = enrich_claims(claims_raw)
else:
    st.error("No data found. Run the data pipeline first (main.ipynb) to generate the database.")
    st.stop()

news_df = load_parquet(PARQUET_NEWS)
reddit_df = load_parquet(PARQUET_REDDIT)
co2_df = load_parquet(PARQUET_CO2)
sector_df = load_parquet(PARQUET_SECTOR)
credibility_df = load_parquet(PARQUET_CREDIBILITY)
co2_trend_df = load_parquet(PARQUET_CO2_TREND)
lineage = load_lineage()

# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("""
    <div style="text-align:center; padding:16px 0 8px 0;">
        <h2 style="margin:0; color:#3B82F6;">Greenwashing<br>Risk Monitor</h2>
        <p style="color:#94A3B8; font-size:0.85rem; margin-top:4px;">FTSE 100 ESG Claim Analysis</p>
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    sectors_available = sorted(df["sector"].unique())
    selected_sectors = st.multiselect(
        "Filter by Sector", sectors_available, default=sectors_available
    )

    selected_risks = st.multiselect(
        "Filter by Risk Level", RISK_ORDER, default=RISK_ORDER
    )

    st.divider()

    st.markdown("**Data Pipeline Health**")
    sources = {
        "Company Claims": PARQUET_CLAIMS,
        "News Articles": PARQUET_NEWS,
        "Reddit Posts": PARQUET_REDDIT,
        "CO2 Data": PARQUET_CO2,
        "Social Signals": PARQUET_SOCIAL,
        "Risk Scores": PARQUET_FINAL,
        "Sector Analysis": PARQUET_SECTOR,
        "Credibility": PARQUET_CREDIBILITY,
    }
    for name, path in sources.items():
        icon = "\U0001f7e2" if path.exists() else "\U0001f534"
        st.markdown(f"{icon} {name}")

    st.divider()

    st.caption(
        f"**Companies:** {len(df)}  \n"
        f"**News articles:** {len(news_df) if news_df is not None else 'N/A'}  \n"
        f"**Reddit posts:** {len(reddit_df) if reddit_df is not None else 'N/A'}  \n"
        f"**CO2 records:** {len(co2_df) if co2_df is not None else 'N/A'}"
    )

# Apply filters
mask = df["sector"].isin(selected_sectors) & df["risk_category"].isin(selected_risks)
filtered = df[mask]

# ══════════════════════════════════════════════════════════════════════════════
# MAIN TITLE
# ══════════════════════════════════════════════════════════════════════════════

st.markdown("""
<h1 style="text-align:center; padding:8px 0 0 0;">
    Greenwashing Risk Monitor
</h1>
<p style="color:#94A3B8; text-align:center; margin-top:-8px; margin-bottom:16px;">
    FTSE 100 ESG Claim Analysis Pipeline
</p>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# TABS
# ══════════════════════════════════════════════════════════════════════════════

tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
    "Executive Summary",
    "Risk Analysis",
    "Sector Intelligence",
    "Credibility & Certs",
    "Media Signals",
    "UK Emissions",
    "Company Deep Dive",
    "Methodology",
])

# ──────────────────────────────────────────────────────────────────────────────
# TAB 1 — EXECUTIVE SUMMARY
# ──────────────────────────────────────────────────────────────────────────────

with tab1:
    # KPI row
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("Companies", len(filtered))
    k2.metric(
        "Avg Risk Score",
        f"{filtered['greenwashing_risk_score'].mean():.1f}" if len(filtered) else "-",
    )
    k3.metric("High Risk", int((filtered["risk_category"] == "HIGH").sum()))
    k4.metric(
        "Uncertified Claims",
        int(filtered["claim_without_cert"].sum()) if "claim_without_cert" in filtered.columns else "-",
    )
    k5.metric(
        "Avg Reduction %",
        f"{filtered['reduction_pct_claimed'].mean():.0f}%"
        if len(filtered) and filtered["reduction_pct_claimed"].notna().any() else "-",
    )
    k6.metric(
        "Media Signals",
        int(filtered["total_media_signals"].sum())
        if "total_media_signals" in filtered.columns else "-",
    )

    st.divider()

    col_donut, col_findings = st.columns([1, 1])

    with col_donut:
        if len(filtered):
            risk_counts = filtered["risk_category"].value_counts()
            fig = go.Figure(data=[go.Pie(
                labels=risk_counts.index,
                values=risk_counts.values,
                hole=0.65,
                marker_colors=[RISK_COLOURS.get(r, "#94A3B8") for r in risk_counts.index],
                textinfo="label+percent",
                textfont_size=13,
            )])
            fig.update_layout(
                annotations=[dict(
                    text=f"<b>{len(filtered)}</b><br>Companies",
                    x=0.5, y=0.5, font_size=16, showarrow=False,
                )],
                showlegend=False,
            )
            style_fig(fig, height=380, title="Risk Distribution")
            st.plotly_chart(fig, width="stretch")

    with col_findings:
        if len(filtered):
            high_risk = filtered[filtered["risk_category"] == "HIGH"]
            uncert = filtered[filtered.get("no_certification", pd.Series(dtype=int)) == 1] if "no_certification" in filtered.columns else pd.DataFrame()
            highest_claim = filtered.loc[filtered["reduction_pct_claimed"].idxmax()] if filtered["reduction_pct_claimed"].notna().any() else None
            lowest_claim = filtered.loc[filtered["reduction_pct_claimed"].idxmin()] if filtered["reduction_pct_claimed"].notna().any() else None

            st.markdown("### Key Findings")
            st.markdown(f"""
- **{len(high_risk)}** of {len(filtered)} companies flagged as **HIGH** risk
- **{len(uncert)}** companies lack third-party certification
- Highest reduction claim: **{highest_claim['company_name']}** at **{highest_claim['reduction_pct_claimed']:.0f}%**
- Lowest reduction claim: **{lowest_claim['company_name']}** at **{lowest_claim['reduction_pct_claimed']:.0f}%**
- Average greenwashing risk score: **{filtered['greenwashing_risk_score'].mean():.1f}** / 4.0
- All {len(filtered)} companies target net-zero by **{int(filtered['net_zero_target_year'].max())}** or earlier
""" if highest_claim is not None and lowest_claim is not None else "No data available.")

            # Risk gauge
            avg_risk = filtered["greenwashing_risk_score"].mean()
            fig_gauge = make_risk_gauge(avg_risk, title="Average Risk Score")
            st.plotly_chart(fig_gauge, width="stretch")


# ──────────────────────────────────────────────────────────────────────────────
# TAB 2 — RISK ANALYSIS
# ──────────────────────────────────────────────────────────────────────────────

with tab2:
    if not len(filtered):
        st.info("No companies match the current filters.")
    else:
        # Enhanced horizontal bar chart
        chart_df = filtered.sort_values("greenwashing_risk_score", ascending=True)

        fig = go.Figure()
        for _, row in chart_df.iterrows():
            color = RISK_COLOURS.get(row["risk_category"], "#94A3B8")
            fig.add_trace(go.Bar(
                y=[row["company_name"]],
                x=[row["greenwashing_risk_score"]],
                orientation="h",
                marker_color=color,
                text=f"  {row['greenwashing_risk_score']}  ({row['risk_category']})",
                textposition="outside",
                textfont=dict(color=color, size=12),
                hovertemplate=(
                    f"<b>{row['company_name']}</b><br>"
                    f"Sector: {row['sector']}<br>"
                    f"Risk Score: {row['greenwashing_risk_score']}<br>"
                    f"Reduction Claimed: {row['reduction_pct_claimed']}%<br>"
                    f"Certifications: {row.get('certifications', 'None')}"
                    "<extra></extra>"
                ),
                showlegend=False,
            ))

        style_fig(
            fig,
            height=max(350, len(chart_df) * 50),
            xaxis_title="Greenwashing Risk Score (0-4)",
            xaxis_range=[0, 5.5],
            yaxis_title="",
            bargap=0.3,
            title="Greenwashing Risk Ranking",
        )
        st.plotly_chart(fig, width="stretch")

        st.divider()

        col_heat, col_table = st.columns([3, 2])

        with col_heat:
            # Risk factor heatmap
            risk_flags = [c for c in [
                "has_net_zero_target", "high_reduction_claim",
                "no_certification", "high_media_attention", "claim_without_cert",
            ] if c in filtered.columns]

            if risk_flags:
                flag_labels = {
                    "has_net_zero_target": "Has Net-Zero\nTarget",
                    "high_reduction_claim": "High Reduction\nClaim (>30%)",
                    "no_certification": "No\nCertification",
                    "high_media_attention": "High Media\nAttention",
                    "claim_without_cert": "Claim Without\nCertification",
                }

                heatmap_data = filtered[["company_name"] + risk_flags].set_index("company_name")
                heatmap_data = heatmap_data.fillna(0).astype(int)
                heatmap_data["_total"] = heatmap_data.sum(axis=1)
                heatmap_data = heatmap_data.sort_values("_total", ascending=True).drop("_total", axis=1)

                display_labels = [flag_labels.get(f, f) for f in risk_flags]

                fig_heat = go.Figure(data=go.Heatmap(
                    z=heatmap_data.values,
                    x=display_labels,
                    y=heatmap_data.index,
                    colorscale=[[0, "#1A1F2E"], [1, "#EF4444"]],
                    showscale=False,
                    text=heatmap_data.values,
                    texttemplate="%{text}",
                    textfont={"size": 14},
                    hovertemplate="Company: %{y}<br>Flag: %{x}<br>Active: %{z}<extra></extra>",
                    xgap=3, ygap=3,
                ))
                style_fig(fig_heat, height=max(350, len(heatmap_data) * 45), title="Risk Factor Matrix")
                st.plotly_chart(fig_heat, width="stretch")

        with col_table:
            display_cols = [c for c in [
                "company_name", "sector", "reduction_pct_claimed",
                "certifications", "greenwashing_risk_score", "risk_category",
            ] if c in filtered.columns]
            table_df = (
                filtered[display_cols]
                .sort_values("greenwashing_risk_score", ascending=False)
                .rename(columns={
                    "company_name": "Company",
                    "sector": "Sector",
                    "reduction_pct_claimed": "Reduction %",
                    "certifications": "Certifications",
                    "greenwashing_risk_score": "Score",
                    "risk_category": "Risk",
                })
            )
            st.dataframe(table_df, width="stretch", hide_index=True, height=450)


# ──────────────────────────────────────────────────────────────────────────────
# TAB 3 — SECTOR INTELLIGENCE
# ──────────────────────────────────────────────────────────────────────────────

with tab3:
    # Use processed sector_analysis.parquet if available, else build from filtered data
    if sector_df is not None and len(sector_df):
        s_df = sector_df.copy()
    elif sector_summary_sql is not None and len(sector_summary_sql):
        s_df = sector_summary_sql.copy()
    else:
        # Build from filtered
        s_df = (
            filtered.groupby("sector")
            .agg(
                companies=("company_name", "count"),
                avg_reduction_claimed_pct=("reduction_pct_claimed", "mean"),
                avg_risk_score=("greenwashing_risk_score", "mean"),
            )
            .reset_index()
        )

    if not len(s_df):
        st.info("No sector data available.")
    else:
        col_tree, col_bar = st.columns(2)

        with col_tree:
            # Treemap
            tree_cols = {"companies" if "companies" in s_df.columns else "company_count": "count"}
            count_col = "companies" if "companies" in s_df.columns else "company_count"
            risk_col = "avg_risk_score" if "avg_risk_score" in s_df.columns else None

            if count_col in s_df.columns:
                fig_tree = px.treemap(
                    s_df,
                    path=["sector"],
                    values=count_col,
                    color=risk_col if risk_col and risk_col in s_df.columns else None,
                    color_continuous_scale=["#10B981", "#F59E0B", "#EF4444"] if risk_col else None,
                    title="Sector Landscape",
                )
                fig_tree.update_traces(
                    textinfo="label+value",
                    textfont_size=15,
                    marker_line_width=2,
                    marker_line_color="#0E1117",
                )
                style_fig(fig_tree, height=400)
                st.plotly_chart(fig_tree, width="stretch")

        with col_bar:
            # Grouped bar: avg reduction claimed vs avg risk
            red_col = "avg_reduction_claimed_pct" if "avg_reduction_claimed_pct" in s_df.columns else "avg_reduction_claimed"
            if red_col in s_df.columns:
                s_sorted = s_df.sort_values(red_col, ascending=False)
                fig_sec = px.bar(
                    s_sorted,
                    x="sector",
                    y=red_col,
                    color="sector",
                    text=red_col,
                    title="Avg Emission Reduction Claimed by Sector",
                    labels={"sector": "Sector", red_col: "Avg Reduction (%)"},
                )
                fig_sec.update_traces(texttemplate="%{text:.0f}%", textposition="outside")
                fig_sec.update_layout(showlegend=False)
                style_fig(fig_sec, height=400)
                st.plotly_chart(fig_sec, width="stretch")

        st.divider()

        # Sector radar chart
        risk_col = "avg_risk_score" if "avg_risk_score" in s_df.columns else None
        red_col = "avg_reduction_claimed_pct" if "avg_reduction_claimed_pct" in s_df.columns else "avg_reduction_claimed"
        radar_metrics = [m for m in [red_col, risk_col, "uncertified", "total_media_exposure", "unverified_claims"] if m and m in s_df.columns]

        if len(radar_metrics) >= 2:
            radar_labels = {
                "avg_reduction_claimed_pct": "Avg Reduction\nClaimed",
                "avg_reduction_claimed": "Avg Reduction\nClaimed",
                "avg_risk_score": "Avg Risk\nScore",
                "uncertified": "Uncertified\nCompanies",
                "total_media_exposure": "Media\nExposure",
                "unverified_claims": "Unverified\nClaims",
            }
            display_names = [radar_labels.get(m, m) for m in radar_metrics]

            fig_radar = go.Figure()
            for _, row in s_df.iterrows():
                values = []
                for m in radar_metrics:
                    col_max = s_df[m].max()
                    values.append(row[m] / col_max if col_max > 0 else 0)
                values.append(values[0])

                fig_radar.add_trace(go.Scatterpolar(
                    r=values,
                    theta=display_names + [display_names[0]],
                    fill="toself",
                    name=row["sector"],
                    opacity=0.7,
                ))

            fig_radar.update_layout(
                polar=dict(
                    bgcolor="rgba(0,0,0,0)",
                    radialaxis=dict(visible=True, range=[0, 1], gridcolor="#2D3748"),
                    angularaxis=dict(gridcolor="#2D3748"),
                ),
            )
            style_fig(fig_radar, height=450, title="Sector Risk Profiles (Radar)")
            st.plotly_chart(fig_radar, width="stretch")
        else:
            # Fallback: simple risk by sector bar
            if len(filtered):
                sector_risk = (
                    filtered.groupby("sector")
                    .agg(avg_risk=("greenwashing_risk_score", "mean"), count=("company_name", "count"))
                    .reset_index()
                    .sort_values("avg_risk", ascending=False)
                )
                fig_risk_sec = px.bar(
                    sector_risk, x="sector", y="avg_risk",
                    color="sector", text="avg_risk",
                    title="Average Risk Score by Sector",
                )
                fig_risk_sec.update_traces(texttemplate="%{text:.1f}", textposition="outside")
                fig_risk_sec.update_layout(showlegend=False)
                style_fig(fig_risk_sec, height=400)
                st.plotly_chart(fig_risk_sec, width="stretch")


# ──────────────────────────────────────────────────────────────────────────────
# TAB 4 — CREDIBILITY & CERTIFICATIONS
# ──────────────────────────────────────────────────────────────────────────────

with tab4:
    col_cred, col_certs = st.columns(2)

    with col_cred:
        # Claim credibility scatter
        if data_available(credibility_df, "Claim Credibility"):
            cred_colors = {
                "Verified claim": "#10B981",
                "Unverified claim — HIGH RISK": "#EF4444",
                "Certified but no specific claim": "#F59E0B",
                "No claim and no certification": "#94A3B8",
            }
            size_col = "total_media_signals" if "total_media_signals" in credibility_df.columns else None

            fig_cred = px.scatter(
                credibility_df,
                x="reduction_pct_claimed",
                y=size_col if size_col else "risk_category",
                color="claim_credibility",
                color_discrete_map=cred_colors,
                size=size_col if size_col else None,
                hover_name="company_name",
                text="company_name",
                title="Claim Credibility: Reduction vs Media Scrutiny",
                labels={
                    "reduction_pct_claimed": "Emission Reduction Claimed (%)",
                    "total_media_signals": "Total Media Signals",
                },
            )
            fig_cred.update_traces(textposition="top center", textfont_size=10)
            style_fig(fig_cred, height=450)
            st.plotly_chart(fig_cred, width="stretch")

            with st.expander("Credibility Details"):
                cred_display = credibility_df[[c for c in [
                    "company_name", "sector", "reduction_pct_claimed",
                    "certifications", "claim_credibility", "risk_category",
                ] if c in credibility_df.columns]]
                st.dataframe(cred_display, width="stretch", hide_index=True)

    with col_certs:
        # Certification breakdown
        cert_counts = {}
        for certs in filtered["certifications"].dropna():
            for c in str(certs).split(","):
                c = c.strip()
                if c:
                    cert_counts[c] = cert_counts.get(c, 0) + 1

        if cert_counts:
            cert_df = (
                pd.DataFrame(list(cert_counts.items()), columns=["Certification", "Companies"])
                .sort_values("Companies", ascending=True)
            )
            fig_cert = go.Figure(go.Bar(
                y=cert_df["Certification"],
                x=cert_df["Companies"],
                orientation="h",
                marker_color="#3B82F6",
                text=cert_df["Companies"],
                textposition="outside",
            ))
            style_fig(fig_cert, height=350, title="Third-Party Certifications Held")
            st.plotly_chart(fig_cert, width="stretch")
        else:
            st.info("No certification data available.")

    st.divider()

    # Net-zero lollipop chart
    nz_df = filtered[filtered["net_zero_target_year"].notna()].copy()
    if len(nz_df):
        nz_df["net_zero_target_year"] = nz_df["net_zero_target_year"].astype(int)
        nz_df = nz_df.sort_values("net_zero_target_year")

        fig_nz = go.Figure()
        # Stems
        for _, row in nz_df.iterrows():
            fig_nz.add_trace(go.Scatter(
                x=[2024, row["net_zero_target_year"]],
                y=[row["company_name"], row["company_name"]],
                mode="lines",
                line=dict(color="#2D3748", width=2),
                showlegend=False,
                hoverinfo="skip",
            ))
        # Dots
        fig_nz.add_trace(go.Scatter(
            x=nz_df["net_zero_target_year"],
            y=nz_df["company_name"],
            mode="markers+text",
            marker=dict(size=14, color="#3B82F6"),
            text=nz_df["net_zero_target_year"].astype(str),
            textposition="middle right",
            showlegend=False,
            hovertemplate="%{y}: Net-Zero by %{x}<extra></extra>",
        ))
        style_fig(fig_nz, height=max(300, len(nz_df) * 45), title="Net-Zero Target Years", xaxis_title="Year")
        st.plotly_chart(fig_nz, width="stretch")


# ──────────────────────────────────────────────────────────────────────────────
# TAB 5 — MEDIA SIGNALS
# ──────────────────────────────────────────────────────────────────────────────

with tab5:
    has_media = "total_media_signals" in filtered.columns and filtered["total_media_signals"].sum() > 0

    if has_media or news_df is not None or reddit_df is not None:
        # KPIs
        mk1, mk2, mk3 = st.columns(3)
        mk1.metric("Total News Articles", len(news_df) if news_df is not None else "N/A")
        mk2.metric("Total Reddit Posts", len(reddit_df) if reddit_df is not None else "N/A")
        mk3.metric(
            "Total Media Signals",
            int(filtered["total_media_signals"].sum()) if has_media else "N/A",
        )

        st.divider()

        col_media_bar, col_media_scatter = st.columns(2)

        with col_media_bar:
            if has_media:
                media_cols = [c for c in ["reddit_post_count", "news_article_count"] if c in filtered.columns]
                if media_cols:
                    media_melt = (
                        filtered[["company_name"] + media_cols]
                        .melt(id_vars="company_name", var_name="Source", value_name="Count")
                        .replace({
                            "reddit_post_count": "Reddit Posts",
                            "news_article_count": "Guardian Articles",
                        })
                    )
                    fig_media = px.bar(
                        media_melt,
                        x="company_name", y="Count", color="Source",
                        barmode="group",
                        title="Media Coverage per Company",
                        labels={"company_name": "Company"},
                    )
                    fig_media.update_layout(xaxis_tickangle=-45)
                    style_fig(fig_media, height=400)
                    st.plotly_chart(fig_media, width="stretch")

        with col_media_scatter:
            if has_media:
                fig_scatter = px.scatter(
                    filtered,
                    x="total_media_signals",
                    y="greenwashing_risk_score",
                    size="reduction_pct_claimed",
                    color="risk_category",
                    color_discrete_map=RISK_COLOURS,
                    hover_name="company_name",
                    title="Risk Score vs Media Attention",
                    labels={
                        "total_media_signals": "Total Media Signals",
                        "greenwashing_risk_score": "Risk Score",
                        "reduction_pct_claimed": "Reduction %",
                    },
                )
                style_fig(fig_scatter, height=400)
                st.plotly_chart(fig_scatter, width="stretch")

        # Guardian timeline
        if news_df is not None and len(news_df):
            with st.expander(f"Guardian News Timeline ({len(news_df)} articles)"):
                news_sorted = news_df.copy()
                date_col = next((c for c in ["published_at", "webPublicationDate"] if c in news_sorted.columns), None)
                if date_col:
                    news_sorted[date_col] = pd.to_datetime(news_sorted[date_col], errors="coerce")
                    fig_timeline = px.scatter(
                        news_sorted.dropna(subset=[date_col]),
                        x=date_col,
                        y="company_name",
                        color="company_name",
                        hover_data=[c for c in ["headline", "section"] if c in news_sorted.columns],
                        title="Guardian Coverage Timeline",
                    )
                    fig_timeline.update_traces(marker_size=8, marker_opacity=0.7)
                    fig_timeline.update_layout(showlegend=False)
                    style_fig(fig_timeline, height=400)
                    st.plotly_chart(fig_timeline, width="stretch")

                show_cols = [c for c in ["company_name", "headline", "section", date_col] if c and c in news_sorted.columns]
                st.dataframe(news_sorted[show_cols].head(20), width="stretch", hide_index=True)

        # Reddit expander
        if reddit_df is not None and len(reddit_df):
            with st.expander(f"Top Reddit Posts ({len(reddit_df)} posts)"):
                reddit_sorted = reddit_df.sort_values("score", ascending=False) if "score" in reddit_df.columns else reddit_df
                show_cols = [c for c in ["company_name", "title", "score", "num_comments", "subreddit", "upvote_ratio"] if c in reddit_sorted.columns]
                st.dataframe(reddit_sorted[show_cols].head(20), width="stretch", hide_index=True)

                # Subreddit distribution
                if "subreddit" in reddit_df.columns:
                    sub_counts = reddit_df["subreddit"].value_counts().head(10)
                    fig_sub = px.pie(
                        values=sub_counts.values,
                        names=sub_counts.index,
                        title="Subreddit Distribution",
                        hole=0.4,
                    )
                    style_fig(fig_sub, height=350)
                    st.plotly_chart(fig_sub, width="stretch")
    else:
        data_available(None, "Media & Social Signals")


# ──────────────────────────────────────────────────────────────────────────────
# TAB 6 — UK EMISSIONS
# ──────────────────────────────────────────────────────────────────────────────

with tab6:
    # Use processed trend if available, else raw co2
    co2_data = co2_trend_df if co2_trend_df is not None else co2_df

    if data_available(co2_data, "UK CO2 Emissions"):
        year_col = "year" if "year" in co2_data.columns else None
        co2_col = next(
            (c for c in co2_data.columns if "co2" in c.lower() and "per" not in c.lower() and "capita" not in c.lower()),
            None,
        )

        if year_col and co2_col:
            co2_sorted = co2_data.sort_values(year_col)

            # KPIs
            latest = co2_sorted.iloc[-1]
            prev = co2_sorted.iloc[-2] if len(co2_sorted) > 1 else None
            ek1, ek2, ek3 = st.columns(3)
            ek1.metric(
                f"Latest CO2 ({int(latest[year_col])})",
                f"{latest[co2_col]:.1f} Mt",
            )
            if prev is not None:
                yoy = ((latest[co2_col] - prev[co2_col]) / prev[co2_col]) * 100
                ek2.metric("Year-on-Year Change", f"{yoy:+.1f}%")
            per_cap = next((c for c in co2_sorted.columns if "per_capita" in c.lower() or "capita" in c.lower()), None)
            if per_cap:
                ek3.metric("Per Capita", f"{latest[per_cap]:.1f} t")

            st.divider()

            # Main area chart
            fig_co2 = px.area(
                co2_sorted,
                x=year_col,
                y=co2_col,
                title="UK Annual CO2 Emissions (Million Tonnes)",
                labels={year_col: "Year", co2_col: "CO2 (Mt)"},
            )
            fig_co2.update_traces(
                line_color="#3B82F6",
                fillcolor="rgba(59,130,246,0.2)",
            )
            style_fig(fig_co2, height=400)
            st.plotly_chart(fig_co2, width="stretch")

            # YoY change bar chart
            if len(co2_sorted) > 1:
                co2_yoy = co2_sorted.copy()
                co2_yoy["yoy_change"] = co2_yoy[co2_col].pct_change() * 100
                co2_yoy = co2_yoy.dropna(subset=["yoy_change"])

                bar_colors = ["#10B981" if v < 0 else "#EF4444" for v in co2_yoy["yoy_change"]]

                fig_yoy = go.Figure(go.Bar(
                    x=co2_yoy[year_col],
                    y=co2_yoy["yoy_change"],
                    marker_color=bar_colors,
                    text=[f"{v:+.1f}%" for v in co2_yoy["yoy_change"]],
                    textposition="outside",
                    textfont_size=10,
                ))
                style_fig(
                    fig_yoy,
                    height=350,
                    title="Year-on-Year CO2 Change (%)",
                    yaxis_title="Change (%)",
                    xaxis_title="Year",
                )
                st.plotly_chart(fig_yoy, width="stretch")

            # Per capita line
            if per_cap and per_cap in co2_sorted.columns:
                fig_pc = px.line(
                    co2_sorted, x=year_col, y=per_cap,
                    title="UK CO2 Per Capita (Tonnes)",
                    labels={year_col: "Year", per_cap: "CO2 per Capita (t)"},
                    markers=True,
                )
                fig_pc.update_traces(line_color="#8B5CF6", marker_size=6)
                style_fig(fig_pc, height=350)
                st.plotly_chart(fig_pc, width="stretch")


# ──────────────────────────────────────────────────────────────────────────────
# TAB 7 — COMPANY DEEP DIVE
# ──────────────────────────────────────────────────────────────────────────────

with tab7:
    company_names = sorted(filtered["company_name"].unique())

    if not company_names:
        st.info("No companies match the current filters.")
    else:
        selected_company = st.selectbox("Select a company", company_names)
        row = filtered[filtered["company_name"] == selected_company].iloc[0]

        # Styled header card
        risk_color = RISK_COLOURS.get(row["risk_category"], "#94A3B8")
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #1A1F2E, #242938);
                    border-left: 4px solid {risk_color};
                    border-radius: 12px; padding: 24px; margin-bottom: 16px;">
            <h2 style="margin:0;">{selected_company}</h2>
            <p style="color:#94A3B8; margin:4px 0 12px 0;">{row['sector']}</p>
            <span class="risk-badge risk-{row['risk_category']}">{row['risk_category']} RISK</span>
        </div>
        """, unsafe_allow_html=True)

        # KPI row
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Risk Score", f"{row['greenwashing_risk_score']} / 4")
        c2.metric("Net-Zero Target", int(row["net_zero_target_year"]) if pd.notna(row["net_zero_target_year"]) else "None")
        c3.metric("Reduction Claimed", f"{row['reduction_pct_claimed']:.0f}%" if pd.notna(row["reduction_pct_claimed"]) else "None")
        c4.metric("Media Signals", int(row.get("total_media_signals", 0)))

        st.divider()

        col_radar, col_signals = st.columns(2)

        with col_radar:
            # Company radar chart
            radar_metrics = {
                "Reduction\nClaimed": ("reduction_pct_claimed", df["reduction_pct_claimed"].max()),
                "Media\nExposure": ("total_media_signals", df["total_media_signals"].max() if "total_media_signals" in df.columns else 1),
                "Risk\nScore": ("greenwashing_risk_score", 4),
                "Reddit\nMentions": ("reddit_post_count", df["reddit_post_count"].max() if "reddit_post_count" in df.columns else 1),
                "News\nCoverage": ("news_article_count", df["news_article_count"].max() if "news_article_count" in df.columns else 1),
            }

            categories = list(radar_metrics.keys())
            values = []
            for label, (col, max_val) in radar_metrics.items():
                val = row.get(col, 0)
                if pd.isna(val):
                    val = 0
                values.append(val / max_val if max_val > 0 else 0)
            values.append(values[0])

            fig_radar = go.Figure()
            fig_radar.add_trace(go.Scatterpolar(
                r=values,
                theta=categories + [categories[0]],
                fill="toself",
                fillcolor="rgba(59,130,246,0.3)",
                line_color="#3B82F6",
                name=selected_company,
            ))
            fig_radar.update_layout(
                polar=dict(
                    bgcolor="rgba(0,0,0,0)",
                    radialaxis=dict(visible=True, range=[0, 1], gridcolor="#2D3748"),
                    angularaxis=dict(gridcolor="#2D3748"),
                ),
            )
            style_fig(fig_radar, height=400, title=f"{selected_company} — Risk Profile")
            st.plotly_chart(fig_radar, width="stretch")

        with col_signals:
            # Risk signals
            st.markdown("### Risk Signals")
            signals = {
                "Has net-zero target": (bool(row.get("has_net_zero_target", 0)), False),
                "High reduction claim (>30%)": (bool(row.get("high_reduction_claim", 0)), True),
                "No third-party certification": (bool(row.get("no_certification", 0)), True),
                "Claim without certification": (bool(row.get("claim_without_cert", 0)), True),
                "High media attention (>50 signals)": (bool(row.get("high_media_attention", 0)), True),
            }
            for signal, (active, is_negative) in signals.items():
                if is_negative:
                    icon = "\U0001f534" if active else "\U0001f7e2"
                else:
                    icon = "\U0001f7e2" if active else "\U0001f7e0"
                st.markdown(f"{icon} {signal}")

            # Certifications
            st.markdown("### Certifications")
            certs = str(row.get("certifications", "")) if pd.notna(row.get("certifications")) else ""
            if certs:
                for cert in certs.split(","):
                    cert = cert.strip()
                    if cert:
                        st.markdown(f"""
                        <span style="display:inline-block; background:#1A1F2E; border:1px solid #3B82F6;
                                     border-radius:8px; padding:4px 12px; margin:2px 4px 2px 0;">
                            {cert}
                        </span>
                        """, unsafe_allow_html=True)
            else:
                st.markdown("_No certifications found_")

            # Credibility verdict
            if credibility_df is not None:
                cred_row = credibility_df[credibility_df["company_name"] == selected_company]
                if len(cred_row):
                    verdict = cred_row.iloc[0].get("claim_credibility", "Unknown")
                    st.markdown(f"### Credibility Verdict")
                    st.markdown(f"**{verdict}**")

        # Reddit & News expanders
        if reddit_df is not None and len(reddit_df):
            name_col_r = "company_name" if "company_name" in reddit_df.columns else None
            if name_col_r:
                company_posts = reddit_df[
                    reddit_df[name_col_r].str.contains(selected_company, case=False, na=False)
                ]
            else:
                company_posts = reddit_df[
                    reddit_df["title"].str.contains(selected_company, case=False, na=False)
                ]

            if len(company_posts):
                with st.expander(f"Reddit Mentions ({len(company_posts)} posts)"):
                    show_cols = [c for c in ["title", "score", "num_comments", "subreddit", "upvote_ratio"] if c in company_posts.columns]
                    st.dataframe(company_posts[show_cols].head(15), width="stretch", hide_index=True)

                    if "subreddit" in company_posts.columns and len(company_posts) > 1:
                        sub_counts = company_posts["subreddit"].value_counts()
                        fig_sub = px.pie(
                            values=sub_counts.values, names=sub_counts.index,
                            title=f"Subreddit Distribution — {selected_company}",
                            hole=0.4,
                        )
                        style_fig(fig_sub, height=300)
                        st.plotly_chart(fig_sub, width="stretch")

        if news_df is not None and len(news_df):
            name_col_n = "company_name" if "company_name" in news_df.columns else None
            if name_col_n:
                company_news = news_df[news_df[name_col_n].str.contains(selected_company, case=False, na=False)]
            else:
                company_news = news_df[news_df.apply(lambda r: selected_company.lower() in str(r).lower(), axis=1)]

            if len(company_news):
                with st.expander(f"Guardian News Coverage ({len(company_news)} articles)"):
                    show_cols = [c for c in ["headline", "section", "published_at", "snippet"] if c in company_news.columns]
                    st.dataframe(company_news[show_cols].head(15), width="stretch", hide_index=True)


# ──────────────────────────────────────────────────────────────────────────────
# TAB 8 — METHODOLOGY
# ──────────────────────────────────────────────────────────────────────────────

with tab8:
    st.markdown("### Risk Scoring Methodology")
    st.markdown("""
Each company receives a **Greenwashing Risk Score (0-4)** based on three signals:

| Signal | Weight | Description |
|--------|--------|-------------|
| `claim_without_cert` | **x2** | High reduction claim (>30%) with no third-party certification |
| `no_certification` | x1 | Company has zero third-party certifications |
| `high_media_attention` | x1 | More than 50 combined media signals (news + Reddit) |

**Risk Categories:**
| Category | Score | Interpretation |
|----------|-------|----------------|
| **HIGH** | 3-4 | Multiple red flags — strong greenwashing indicators |
| **MEDIUM** | 2 | Significant concerns — unverified claims |
| **LOW** | 1 | Minor concerns — some gaps in transparency |
| **MINIMAL** | 0 | No flags detected — claims appear credible |
""")

    st.divider()

    st.markdown("### Data Pipeline Architecture")
    st.markdown("""
    <div style="display:flex; justify-content:center; gap:12px; flex-wrap:wrap; padding:20px 0;">
        <div style="background:#1A1F2E; border:1px solid #3B82F6; border-radius:8px;
                    padding:12px 16px; text-align:center; min-width:110px;">
            <div style="color:#3B82F6; font-weight:600;">Web Scraping</div>
            <div style="color:#94A3B8; font-size:0.75rem;">10 companies</div>
        </div>
        <div style="color:#94A3B8; align-self:center; font-size:1.2rem;">&rarr;</div>
        <div style="background:#1A1F2E; border:1px solid #10B981; border-radius:8px;
                    padding:12px 16px; text-align:center; min-width:110px;">
            <div style="color:#10B981; font-weight:600;">Guardian API</div>
            <div style="color:#94A3B8; font-size:0.75rem;">News articles</div>
        </div>
        <div style="color:#94A3B8; align-self:center; font-size:1.2rem;">&rarr;</div>
        <div style="background:#1A1F2E; border:1px solid #F59E0B; border-radius:8px;
                    padding:12px 16px; text-align:center; min-width:110px;">
            <div style="color:#F59E0B; font-weight:600;">Reddit API</div>
            <div style="color:#94A3B8; font-size:0.75rem;">Community posts</div>
        </div>
        <div style="color:#94A3B8; align-self:center; font-size:1.2rem;">&rarr;</div>
        <div style="background:#1A1F2E; border:1px solid #8B5CF6; border-radius:8px;
                    padding:12px 16px; text-align:center; min-width:110px;">
            <div style="color:#8B5CF6; font-weight:600;">OWID CO2</div>
            <div style="color:#94A3B8; font-size:0.75rem;">UK emissions</div>
        </div>
    </div>
    <div style="text-align:center; color:#94A3B8; font-size:1.5rem; margin:-8px 0 8px 0;">&darr;</div>
    <div style="display:flex; justify-content:center; gap:12px; flex-wrap:wrap; padding:0 0 20px 0;">
        <div style="background:#1A1F2E; border:1px solid #EC4899; border-radius:8px;
                    padding:12px 16px; text-align:center; min-width:110px;">
            <div style="color:#EC4899; font-weight:600;">MongoDB</div>
            <div style="color:#94A3B8; font-size:0.75rem;">Raw text storage</div>
        </div>
        <div style="color:#94A3B8; align-self:center; font-size:1.2rem;">&rarr;</div>
        <div style="background:#1A1F2E; border:1px solid #06B6D4; border-radius:8px;
                    padding:12px 16px; text-align:center; min-width:110px;">
            <div style="color:#06B6D4; font-weight:600;">Apache Spark</div>
            <div style="color:#94A3B8; font-size:0.75rem;">Join & score</div>
        </div>
        <div style="color:#94A3B8; align-self:center; font-size:1.2rem;">&rarr;</div>
        <div style="background:#1A1F2E; border:1px solid #84CC16; border-radius:8px;
                    padding:12px 16px; text-align:center; min-width:110px;">
            <div style="color:#84CC16; font-weight:600;">DuckDB</div>
            <div style="color:#94A3B8; font-size:0.75rem;">Analytics SQL</div>
        </div>
        <div style="color:#94A3B8; align-self:center; font-size:1.2rem;">&rarr;</div>
        <div style="background:#1A1F2E; border:1px solid #EF4444; border-radius:8px;
                    padding:12px 16px; text-align:center; min-width:110px;">
            <div style="color:#EF4444; font-weight:600;">Dashboard</div>
            <div style="color:#94A3B8; font-size:0.75rem;">Streamlit + Plotly</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    # Data lineage
    st.markdown("### Data Lineage Log")
    if lineage:
        lineage_df = pd.DataFrame(lineage)
        display_cols = [c for c in ["source", "record_count", "output_path", "extracted_at", "transformations"] if c in lineage_df.columns]
        if display_cols:
            st.dataframe(
                lineage_df[display_cols].rename(columns={
                    "source": "Source",
                    "record_count": "Records",
                    "output_path": "Output Path",
                    "extracted_at": "Timestamp",
                    "transformations": "Transformations",
                }),
                width="stretch",
                hide_index=True,
            )
        else:
            st.json(lineage)
    else:
        st.info("No lineage data available. Run the pipeline to generate the audit trail.")

    st.divider()

    st.markdown("### Data Sources")
    st.markdown("""
| Source | Type | Description |
|--------|------|-------------|
| Company Websites | Web Scraping | Sustainability pages, Wikipedia, Wayback Machine, SBTi database |
| The Guardian | REST API | ESG and greenwashing journalism coverage |
| Reddit | Public JSON API | Community sentiment from 8+ subreddits |
| Our World in Data | CSV/GitHub | Peer-reviewed UK CO2 emissions dataset |
| NetworkX | Computed | Company-sector-certification relationship graph |
""")

    st.markdown("""
### Ethics & Limitations

**Ethics:** 2-second delay between scraping requests, standard browser User-Agent,
no login walls circumvented, robots.txt respected.

**Limitations:**
- Several company pages use JavaScript rendering — addressed via Wayback Machine snapshots
- Reduction % figures from free text may not represent the primary headline target
- Reddit data reflects community perception, not verified facts
- National CO2 data is country-level, not company-level — used for context only
""")


# ══════════════════════════════════════════════════════════════════════════════
# FOOTER
# ══════════════════════════════════════════════════════════════════════════════

st.divider()
st.caption(
    "Greenwashing Risk Monitor | FTSE 100 ESG Claim Analysis Pipeline | "
    "Data sourced from company websites, The Guardian API, Reddit, and Our World in Data."
)


