"""
app.py — GEO Meta-Analysis Toolkit — Streamlit Dashboard.

Run with:
    streamlit run app.py

Enter a search query (e.g. "lung cancer single cell RNA-seq") and the toolkit
will search NCBI GEO, fetch metadata for matching datasets, compute aggregate
statistics, and generate an LLM-powered narrative summary of the research
landscape.

Unified Smart Hybrid Engine (3-phase):
    Phase 1: Deterministic GEO search + metadata aggregation (~2s)
    Phase 2: Autonomous LangChain ReAct agent for PubMed literature synthesis
    Phase 3: Self-healing fallback to linear summarizer on any failure
"""

import json
import html as html_lib
import streamlit as st
import pandas as pd

from config import settings
from utils.formatters import pretty_json

st.set_page_config(
    page_title=settings.APP_TITLE,
    page_icon="🧬",
    layout="wide",
)

# ── Custom CSS ──────────────────────────────────────────────────────────────────

st.markdown("""
<style>
    /* ── Google Font ─────────────────────────────────────────── */
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&display=swap');

    /* ── Base typography & Background ────────────────────────── */
    html, body, [class*="css"], .stApp {
        font-family: 'Outfit', -apple-system, BlinkMacSystemFont, sans-serif;
        background-color: #0a0f0d !important;
        background-image: radial-gradient(at 15% 15%, rgba(16, 185, 129, 0.12) 0px, transparent 60%),
                          radial-gradient(at 85% 85%, rgba(245, 158, 11, 0.10) 0px, transparent 60%),
                          url("data:image/svg+xml,%3Csvg width='80' height='80' viewBox='0 0 80 80' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23ffffff' fill-opacity='0.015'%3E%3Cpath d='M50 50c0-5.523 4.477-10 10-10s10 4.477 10 10-4.477 10-10 10c0 5.523-4.477 10-10 10s-10-4.477-10-10 4.477-10 10-10zM10 10c0-5.523 4.477-10 10-10s10 4.477 10 10-4.477 10-10 10c0 5.523-4.477 10-10 10S0 25.523 0 20s4.477-10 10-10zm10 8c4.418 0 8-3.582 8-8s-3.582-8-8-8-8 3.582-8 8 3.582 8 8 8zm40 40c4.418 0 8-3.582 8-8s-3.582-8-8-8-8 3.582-8 8 3.582 8 8 8z' /%3E%3C/g%3E%3C/g%3E%3C/svg%3E") !important;
        color: #e2e8f0;
    }

    /* ── Page layout ─────────────────────────────────────────── */
    .stMainBlockContainer { padding: 2rem 2.5rem 3rem 2.5rem; max-width: 1400px; }

    /* ── Giant Title ──────────────────────────────────────────── */
    h1 {
        font-size: clamp(2.8rem, 5.5vw, 4.5rem) !important;
        font-weight: 800 !important; letter-spacing: -1.5px;
        background: linear-gradient(135deg, #10b981 0%, #f59e0b 100%);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        margin-bottom: 0.5rem !important;
    }

    /* ── Subheadings ──────────────────────────────────────────── */
    h2, h3, h4 { color: #f1f5f9 !important; font-weight: 600 !important; }

    /* ── Body text ────────────────────────────────────────────── */
    p, li, span, label, .stMarkdown { font-size: clamp(0.9rem, 1vw, 1rem); line-height: 1.7; }

    /* ── Metric cards (Glassmorphism) ────────────────────────── */
    [data-testid="stMetric"] {
        background: rgba(20, 35, 28, 0.5); backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
        border: 1px solid rgba(16, 185, 129, 0.15); border-radius: 16px; padding: 1.5rem;
        box-shadow: 0 8px 32px 0 rgba(0,0,0,0.3); transition: all 0.3s cubic-bezier(0.4,0,0.2,1);
        position: relative; overflow: hidden;
    }
    [data-testid="stMetric"]::before {
        content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px;
        background: linear-gradient(90deg, #10b981, #f59e0b); opacity: 0; transition: opacity 0.3s ease;
    }
    [data-testid="stMetric"]:hover::before { opacity: 1; }
    [data-testid="stMetric"]:hover {
        transform: translateY(-6px); box-shadow: 0 16px 48px 0 rgba(16,185,129,0.2);
        border-color: rgba(16,185,129,0.4);
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.85rem !important; font-weight: 500; text-transform: uppercase;
        letter-spacing: 0.05em; color: #94a3b8 !important;
    }
    [data-testid="stMetricValue"] {
        font-size: clamp(1.5rem, 2.5vw, 2rem) !important; font-weight: 700;
        background: linear-gradient(90deg, #f8fafc, #94a3b8);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    }

    /* ── Tabs ─────────────────────────────────────────────────── */
    .stTabs [data-baseweb="tab-list"] {
        gap: 1rem; background: rgba(10,20,16,0.6); padding: 0.5rem; border-radius: 12px;
        border: 1px solid rgba(255,255,255,0.05);
    }
    .stTabs [data-baseweb="tab"] {
        font-size: 0.95rem; font-weight: 500; padding: 0.5rem 1.5rem; border-radius: 8px;
        color: #94a3b8; transition: all 0.3s ease;
    }
    .stTabs [data-baseweb="tab"]:hover { background: rgba(255,255,255,0.05); color: #e2e8f0; }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #059669, #10b981) !important; color: white !important;
        border-radius: 8px !important; box-shadow: 0 4px 15px rgba(16,185,129,0.3);
    }
    .stTabs [data-baseweb="tab-panel"] { padding-top: 2rem; }

    /* ── Buttons ──────────────────────────────────────────────── */
    .stButton > button {
        font-weight: 600; border-radius: 12px; padding: 0.6rem 2rem;
        transition: all 0.3s cubic-bezier(0.4,0,0.2,1); text-transform: uppercase;
        letter-spacing: 0.05em; font-size: 0.9rem;
    }
    .stButton > button:hover { transform: translateY(-2px) scale(1.02); }
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #10b981, #34d399, #f59e0b) !important;
        background-size: 200% auto !important; color: white !important; border: none;
        box-shadow: 0 8px 25px rgba(16,185,129,0.4); animation: gradientPulse 3s ease infinite;
    }
    @keyframes gradientPulse {
        0% { background-position: 0% 50%; } 50% { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
    }

    /* ── Text input ───────────────────────────────────────────── */
    .stTextInput input {
        background: rgba(20,35,28,0.5) !important; border: 1px solid rgba(255,255,255,0.1) !important;
        color: #f1f5f9 !important; font-size: 1rem !important; padding: 0.8rem 1.2rem;
        border-radius: 12px; transition: all 0.3s ease; box-shadow: inset 0 2px 4px rgba(0,0,0,0.1);
    }
    .stTextInput input:focus {
        border-color: #10b981 !important;
        box-shadow: 0 0 0 3px rgba(16,185,129,0.2), inset 0 2px 4px rgba(0,0,0,0.1) !important;
    }

    /* ── Dataframes ───────────────────────────────────────────── */
    .stDataFrame {
        border-radius: 12px; border: 1px solid rgba(255,255,255,0.05);
        box-shadow: 0 10px 30px rgba(0,0,0,0.2); overflow: hidden;
    }

    /* ── Expander ─────────────────────────────────────────────── */
    .streamlit-expanderHeader {
        font-size: 1rem !important; font-weight: 600; border-radius: 12px !important;
        background: rgba(20,35,28,0.4) !important;
    }

    /* ── Sidebar ──────────────────────────────────────────────── */
    section[data-testid="stSidebar"] {
        background: rgba(10,20,16,0.85) !important; backdrop-filter: blur(20px);
        -webkit-backdrop-filter: blur(20px); border-right: 1px solid rgba(255,255,255,0.05);
        padding-top: 2rem;
    }

    /* ── Summary card ─────────────────────────────────────────── */
    .meta-card {
        background: rgba(20,35,28,0.4); backdrop-filter: blur(12px); border-radius: 16px;
        padding: 1.5rem 2rem; margin-bottom: 1rem; border: 1px solid rgba(255,255,255,0.05);
        box-shadow: 0 8px 32px 0 rgba(0,0,0,0.2); transition: transform 0.3s ease;
    }
    .meta-card:hover { transform: translateY(-3px); }
    .meta-card h4 {
        margin: 0 0 0.5rem 0; color: #94a3b8; font-size: 0.8rem; font-weight: 600;
        text-transform: uppercase; letter-spacing: 0.1em;
    }
    .meta-card p { margin: 0; color: #f1f5f9; font-size: 1.1rem; line-height: 1.5; }

    /* ── Metric badges ───────────────────────────────────────── */
    .metric-row { display: flex; gap: 1rem; flex-wrap: wrap; margin-top: 1rem; }
    .metric-badge {
        background: rgba(16,185,129,0.1); border: 1px solid rgba(16,185,129,0.3);
        border-radius: 20px; padding: 0.5rem 1rem; font-size: 0.85rem; color: #a7f3d0;
        backdrop-filter: blur(5px); transition: all 0.3s ease;
    }
    .metric-badge:hover {
        background: rgba(16,185,129,0.2); transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(16,185,129,0.2);
    }
    .metric-badge strong { color: #fff; }

    /* ── Section labels ───────────────────────────────────────── */
    .section-label {
        font-size: 0.8rem; font-weight: 700; text-transform: uppercase;
        letter-spacing: 0.1em; color: #10b981; margin: 2rem 0 1rem 0;
    }

    /* ── Narrative block ──────────────────────────────────────── */
    .narrative-block {
        background: rgba(20,35,28,0.4); backdrop-filter: blur(12px); border-radius: 16px;
        padding: 2rem 2.5rem; border-left: 4px solid #10b981;
        border-top: 1px solid rgba(255,255,255,0.05);
        border-right: 1px solid rgba(255,255,255,0.05);
        border-bottom: 1px solid rgba(255,255,255,0.05);
        color: #cbd5e1; font-size: 1.05rem; line-height: 1.8; margin: 1.5rem 0;
        box-shadow: 0 10px 40px rgba(0,0,0,0.2); position: relative; overflow: hidden;
    }
    .narrative-block::before {
        content: ''; position: absolute; top: 0; left: 0; right: 0; bottom: 0;
        background: linear-gradient(135deg, rgba(16,185,129,0.05), transparent);
        pointer-events: none;
    }
    .narrative-block p { margin-bottom: 1.2rem; color: #e2e8f0; }
    .narrative-block p:last-child { margin-bottom: 0; }

    /* ── Chart titles ─────────────────────────────────────────── */
    .chart-title { font-size: 1.1rem; font-weight: 600; margin-bottom: 1rem; color: #e2e8f0; }

    /* ── Alerts/Warnings ──────────────────────────────────────── */
    [data-testid="stAlert"] {
        border-radius: 12px; border: 1px solid rgba(255,255,255,0.1); backdrop-filter: blur(10px);
    }

    /* ── Footer ───────────────────────────────────────────────── */
    footer { visibility: hidden; }
    .stCaption { font-size: 0.85rem !important; color: #64748b !important; }
</style>
""", unsafe_allow_html=True)


# ── Display helpers ─────────────────────────────────────────────────────────────

def render_overview(analysis: dict, query: str) -> None:
    """Render the overview metrics and key stats."""
    if not analysis or analysis.get("total_datasets", 0) == 0:
        st.info("No results to display.")
        return

    # Key metrics
    cols = st.columns(4)
    cols[0].metric("📊 Datasets Found", analysis["total_datasets"])
    cols[1].metric("🧪 Total Samples", f"{analysis['total_samples']:,}")

    top_org = next(iter(analysis.get("organism_counts", {})), "N/A")
    cols[2].metric("🧬 Top Organism", top_org)

    top_exp = next(iter(analysis.get("experiment_type_counts", {})), "N/A")
    cols[3].metric("🔬 Top Exp. Type", top_exp[:30])

    # Sample count stats
    stats = analysis.get("sample_count_stats", {})
    if stats:
        st.markdown('<p class="section-label">Sample Count Distribution</p>', unsafe_allow_html=True)
        stat_cols = st.columns(4)
        stat_cols[0].metric("Min", stats.get("min", 0))
        stat_cols[1].metric("Max", stats.get("max", 0))
        stat_cols[2].metric("Mean", f"{stats.get('mean', 0):.1f}")
        stat_cols[3].metric("Median", f"{stats.get('median', 0):.1f}")


def render_charts(analysis: dict) -> None:
    """Render charts for the meta-analysis results."""
    if not analysis or analysis.get("total_datasets", 0) == 0:
        st.info("No data for charts.")
        return

    chart_col1, chart_col2 = st.columns(2)

    # Organism distribution
    with chart_col1:
        org_counts = analysis.get("organism_counts", {})
        if org_counts:
            st.markdown("#### 🧬 Organism Distribution")
            df = pd.DataFrame(
                list(org_counts.items()),
                columns=["Organism", "Count"]
            )
            st.bar_chart(df.set_index("Organism"), horizontal=True)

    # Experiment type breakdown
    with chart_col2:
        exp_counts = analysis.get("experiment_type_counts", {})
        if exp_counts:
            st.markdown("#### 🔬 Experiment Types")
            df = pd.DataFrame(
                list(exp_counts.items()),
                columns=["Type", "Count"]
            )
            st.bar_chart(df.set_index("Type"), horizontal=True)

    chart_col3, chart_col4 = st.columns(2)

    # Submission timeline
    with chart_col3:
        yearly = analysis.get("yearly_counts", {})
        if yearly:
            st.markdown("#### 📅 Submission Timeline")
            df = pd.DataFrame(
                list(yearly.items()),
                columns=["Year", "Datasets"]
            )
            st.bar_chart(df.set_index("Year"))

    # Top title terms
    with chart_col4:
        terms = analysis.get("top_title_terms", [])
        if terms:
            st.markdown("#### 🏷️ Top Terms in Titles")
            df = pd.DataFrame(terms[:15], columns=["Term", "Count"])
            st.bar_chart(df.set_index("Term"), horizontal=True)

    # Platform usage
    platform_counts = analysis.get("platform_counts", {})
    if platform_counts and len(platform_counts) > 1:
        st.markdown("#### ⚙️ Platform Usage")
        df = pd.DataFrame(
            list(platform_counts.items()),
            columns=["Platform", "Count"]
        )
        st.dataframe(df, width="stretch", hide_index=True)


def render_dataset_table(datasets: list[dict]) -> None:
    """Render the full dataset results table."""
    if not datasets:
        st.info("No datasets to display.")
        return

    rows = []
    for d in datasets:
        if "error" in d:
            continue
        rows.append({
            "GSE ID":      d.get("gse_id", ""),
            "Title":       d.get("title", ""),
            "Organism":    d.get("organism", ""),
            "Samples":     d.get("sample_count", 0),
            "Type":        d.get("experiment_type", ""),
            "Platform":    d.get("platform", ""),
            "Submitted":   d.get("submission_date", ""),
        })

    if rows:
        df = pd.DataFrame(rows)
        st.dataframe(
            df,
            width="stretch",
            hide_index=True,
            column_config={
                "GSE ID": st.column_config.TextColumn("GSE ID", width="small"),
                "Samples": st.column_config.NumberColumn("Samples", width="small"),
                "Platform": st.column_config.TextColumn("Platform", width="small"),
                "Submitted": st.column_config.TextColumn("Submitted", width="small"),
            },
        )


def render_narrative(narrative: str) -> None:
    """Render the LLM-generated narrative summary."""
    if not narrative:
        st.info("No narrative summary available.")
        return

    # Sanitize the narrative to prevent XSS, then convert newlines to paragraphs
    safe_narrative = html_lib.escape(narrative)
    paragraphs = safe_narrative.split("\n\n")
    html_paragraphs = "".join(f"<p>{p.strip()}</p>" for p in paragraphs if p.strip())

    st.markdown(
        f'<div class="narrative-block">{html_paragraphs}</div>',
        unsafe_allow_html=True
    )


# ── Header ─────────────────────────────────────────────────────────────────────

st.title("🧬 GEO Meta-Analysis Toolkit")
st.caption(
    "Search NCBI GEO, aggregate metadata across datasets, and generate "
    "autonomous AI-powered research landscape summaries using LangChain."
)

# ── Sidebar: status ────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("⚙️ Configuration")

    max_results = st.slider(
        "Max datasets to fetch",
        min_value=5,
        max_value=10000,
        value=settings.GEO_SEARCH_MAX_RESULTS,
        step=5,
        help="Higher values = more complete analysis but slower (NCBI rate limits).",
    )

    st.divider()
    st.subheader("System status")

    # LLM backend check
    from utils.llm_client import llm
    backend = llm.backend()
    if backend == "ollama":
        st.success(f"Local LLM: Ollama ({settings.OLLAMA_MODEL})")
    else:
        st.error("Local LLM: Offline (Run `ollama serve`)")

    st.divider()
    st.caption(f"Max agent steps: {settings.AGENT_MAX_STEPS}")

# ── Main input ──────────────────────────────────────────────────────────────────

search_query = st.text_input(
    "Search GEO datasets",
    placeholder="e.g. lung cancer single cell RNA-seq",
    help="Free-text query to search the NCBI Gene Expression Omnibus.",
)

run_clicked = st.button("🚀 Run Meta-Analysis", type="primary")

# ── Tabbed output ────────────────────────────────────────────────────────────────

summary_tab, charts_tab, table_tab, raw_tab = st.tabs([
    "📝 Summary",
    "📈 Charts",
    "📋 Datasets",
    "🔧 Raw Data",
])

with summary_tab:
    summary_placeholder = st.empty()

with charts_tab:
    charts_placeholder = st.empty()

with table_tab:
    table_placeholder = st.empty()

with raw_tab:
    raw_placeholder = st.empty()

thoughts_expander = st.expander("🧠 Agent's Thoughts & Literature Investigation", expanded=False)

# ── Execution ────────────────────────────────────────────────────────────────────

if run_clicked:
    if not search_query.strip():
        st.error("Please enter a search query.")
        st.stop()

    clean_query = search_query.strip()

    from tools.geo_tool import search_geo
    from tools.meta_analysis import analyze_metadata, build_llm_summary_prompt
    import agents.langchain_agent as lc_module

    trace_box = thoughts_expander.container()

    # ── Phase 1: Deterministic Foundation ──────────────────────────────────────
    with st.spinner(f"⚡ Phase 1: Deterministic search fetching GEO records for '{clean_query}'..."):
        search_results = search_geo(clean_query, max_results=max_results)

    datasets = search_results.get("datasets", [])

    if search_results.get("fallback"):
        st.toast("⚠️ Strict query returned 0 results. Auto-expanded to natural language keyword matching!", icon="⚠️")

    if not datasets:
        st.warning(f"No datasets found for '{clean_query}'. Try different search terms.")
        st.stop()

    with st.spinner("📊 Phase 1: Computing statistical metadata distributions..."):
        analysis = analyze_metadata(datasets)
        lc_module._cached_datasets = datasets

    # Render overview and charts immediately
    with summary_placeholder.container():
        render_overview(analysis, clean_query)
        narrative_box = st.empty()

    with charts_placeholder.container():
        render_charts(analysis)

    with table_placeholder.container():
        render_dataset_table(datasets)

    with raw_placeholder.container():
        st.json(search_results)

    # ── Phase 2: Autonomous AI Literature Synthesis ────────────────────────────
    narrative = ""
    agent_trace_log = []

    with st.spinner("🤖 Phase 2: Autonomous LangChain ReAct Agent investigating PubMed literature..."):
        try:
            agent_exec = lc_module.build_hybrid_agent(verbose=False)
            agent_input = f"Synthesize scientific literature for query '{clean_query}'. Key GEO findings: {json.dumps({k:v for k,v in analysis.items() if k!='datasets'}, default=str)}"
            res = agent_exec.invoke({"input": agent_input})
            narrative = res.get("output", "")
            agent_trace_log = res.get("intermediate_steps", [])

            with trace_box:
                for action, obs in agent_trace_log:
                    st.markdown(f"**Action:** `{action.tool}`")
                    with st.expander(f"Observation ({action.tool})"):
                        st.write(obs)
        except Exception as e:
            # ── Phase 3: Self-Healing Fallback ────────────────────────────────
            st.toast("⚠️ AI Agent loop timed out. Self-healing via linear prompt summarizer!", icon="🤖")
            with trace_box:
                st.warning(f"Agent loop interrupted ({str(e)}). Auto-degrading to Direct linear summarizer.")

    if not narrative or "Agent stopped due to iteration limit" in narrative:
        with st.spinner("🛡️ Phase 3: Self-healing linear summarizer composing narrative..."):
            prompt = build_llm_summary_prompt(clean_query, analysis)
            narrative = llm.generate(prompt, max_tokens=2048)

    st.success("✨ Meta-Analysis & Literature Synthesis Complete!")

    with narrative_box.container():
        st.markdown("---")
        st.markdown("### 📝 AI Research Landscape Summary")
        render_narrative(narrative)

# ── Footer ──────────────────────────────────────────────────────────────────────

st.divider()
st.caption(
    "GEO Meta-Analysis Toolkit · NCBI GEO + PubMed (E-utilities) · "
    f"Running on Smart Hybrid Engine (Local Ollama: {settings.OLLAMA_MODEL})"
)
