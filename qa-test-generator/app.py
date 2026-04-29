"""
Streamlit UI — Public landing page + login + dashboard.
Flow: landing → login → dashboard
"""

import streamlit as st

st.set_page_config(
    page_title="QA Test Generator",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="auto",
)

DEMO_USERS = {"admin": "admin123", "qa": "qa2024", "demo": "demo"}

for key, val in [("page", "landing"), ("logged_in", False), ("username", ""), ("login_error", ""), ("selected_suite_path", None)]:
    if key not in st.session_state:
        st.session_state[key] = val

# ── Global CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
#MainMenu, footer, header { visibility: hidden; }
html, body, [class*="css"] { font-family: 'Segoe UI', sans-serif; }

/* ── Dark background everywhere — eliminates white gaps between sections ── */
.stApp, .main { background: #080d1a !important; }
.block-container { padding: 0 !important; max-width: 100% !important; }

/* Remove gap Streamlit inserts between stacked elements */
[data-testid="stVerticalBlock"] { gap: 0 !important; }

/* ── Navbar row styling ── */
/* Target the first horizontal block (navbar columns) */
.navbar-row [data-testid="stHorizontalBlock"] {
    background: #080d1a;
    border-bottom: 1px solid #1e3a5f;
    padding: 0 !important;
    align-items: center;
    min-height: 60px;
}
.navbar-row [data-testid="column"] {
    padding: 10px 16px !important;
    display: flex;
    align-items: center;
}
.nav-brand {
    color: #3b82f6; font-size: 1.2rem; font-weight: 800;
    white-space: nowrap; letter-spacing: 0.3px;
}
.nav-links {
    display: flex; align-items: center; gap: 24px;
    justify-content: center; width: 100%;
}
.nav-link  { color: #64748b; font-size: 0.88rem; }
.nav-badge {
    background: rgba(59,130,246,0.15); color: #60a5fa;
    border: 1px solid #3b82f6; border-radius: 20px;
    padding: 3px 12px; font-size: 0.72rem; letter-spacing: 1px;
}
/* Navbar button — compact */
.navbar-row .stButton > button {
    width: auto !important;
    padding: 7px 18px !important;
    font-size: 0.86rem !important;
    margin: 0 !important;
}

/* ── Hero ── */
.hero-outer {
    background: linear-gradient(160deg, #080d1a 0%, #0f1e3d 55%, #080d1a 100%);
    padding: 88px 48px 40px;
    text-align: center;
    position: relative;
    overflow: hidden;
}
.hero-glow {
    position: absolute; width: 700px; height: 700px; border-radius: 50%;
    background: radial-gradient(circle, rgba(59,130,246,0.1) 0%, transparent 70%);
    top: -150px; left: 50%; transform: translateX(-50%); pointer-events: none;
}
.hero-pill {
    display: inline-block;
    background: rgba(59,130,246,0.12); color: #60a5fa;
    border: 1px solid rgba(59,130,246,0.35); border-radius: 20px;
    padding: 5px 18px; font-size: 0.78rem;
    letter-spacing: 1.5px; text-transform: uppercase; margin-bottom: 24px;
}
.hero-title {
    font-size: 3.2rem; font-weight: 900; color: #f1f5f9;
    line-height: 1.15; margin: 0 auto 20px; max-width: 800px;
}
.hero-title span { color: #3b82f6; }
.hero-sub {
    color: #94a3b8; font-size: 1.1rem;
    max-width: 600px; margin: 0 auto; line-height: 1.8;
}

/* Hero button row — same gradient as hero so it blends seamlessly */
.hero-btn-row [data-testid="stHorizontalBlock"] {
    background: linear-gradient(160deg, #080d1a 0%, #0f1e3d 55%, #080d1a 100%);
    padding: 40px 0 64px !important;
    justify-content: center;
}
.hero-btn-row [data-testid="column"] { padding: 0 !important; }

/* ── Stats strip ── */
.stats-strip {
    display: flex; justify-content: center;
    background: #0d1424;
    border-top: 1px solid #1e3a5f;
    border-bottom: 1px solid #1e3a5f;
    padding: 30px 0;
}
.stat-item {
    text-align: center; padding: 0 52px;
    border-right: 1px solid #1e3a5f;
}
.stat-item:last-child { border-right: none; }
.stat-num { font-size: 2.2rem; font-weight: 900; color: #3b82f6; display: block; }
.stat-lbl { color: #64748b; font-size: 0.8rem; margin-top: 4px; }

/* ── Sections ── */
.section     { padding: 72px 8%; background: #080d1a; }
.section-alt { padding: 72px 8%; background: #0a0f1c; }
.section-title {
    text-align: center; font-size: 1.9rem; font-weight: 800;
    color: #f1f5f9; margin: 0 0 12px;
}
.section-sub {
    text-align: center; color: #64748b; font-size: 0.93rem;
    max-width: 560px; margin: 0 auto 48px; line-height: 1.7;
}

/* ── Feature cards ── */
.feature-grid {
    display: grid; grid-template-columns: repeat(3, 1fr);
    gap: 20px; max-width: 1100px; margin: 0 auto;
}
.feat-card {
    background: #0d1424; border: 1px solid #1e3a5f; border-radius: 16px;
    padding: 30px 24px; transition: border-color .25s, transform .25s;
}
.feat-card:hover { border-color: #3b82f6; transform: translateY(-3px); }
.feat-icon  { font-size: 2rem; margin-bottom: 14px; }
.feat-title { color: #e2e8f0; font-size: 1rem; font-weight: 700; margin-bottom: 8px; }
.feat-desc  { color: #64748b; font-size: 0.84rem; line-height: 1.6; }

/* ── Pipeline ── */
.pipeline-wrap { max-width: 1000px; margin: 0 auto; }
.pipe-steps {
    display: flex; align-items: flex-start;
    justify-content: space-between; gap: 0;
}
.pipe-step  { flex: 1; text-align: center; padding: 0 4px; }
.pipe-circle {
    width: 64px; height: 64px; border-radius: 50%;
    background: linear-gradient(135deg, #1d4ed8, #3b82f6);
    display: flex; align-items: center; justify-content: center;
    font-size: 1.5rem; margin: 0 auto 10px;
    box-shadow: 0 0 20px rgba(59,130,246,0.3);
}
.pipe-num {
    display: block; color: #3b82f6; font-size: 0.7rem;
    font-weight: 700; letter-spacing: 1px; margin-bottom: 5px;
    text-transform: uppercase;
}
.pipe-label { color: #e2e8f0; font-size: 0.88rem; font-weight: 700; margin-bottom: 5px; }
.pipe-desc  { color: #64748b; font-size: 0.76rem; line-height: 1.5; }
/* Center arrow against 64px circle height */
.pipe-arrow {
    color: #1e40af; font-size: 1.6rem;
    flex: 0 0 28px; text-align: center;
    padding-top: 18px; align-self: flex-start;
}

/* ── Output cards ── */
.output-grid {
    display: grid; grid-template-columns: repeat(3, 1fr);
    gap: 20px; max-width: 1000px; margin: 0 auto;
}
.out-card {
    background: #0d1424; border-radius: 16px; padding: 30px 24px;
    border: 1px solid #1e3a5f;
}
.out-card.green  { border-top: 3px solid #22c55e; }
.out-card.blue   { border-top: 3px solid #3b82f6; }
.out-card.purple { border-top: 3px solid #a855f7; }
.out-title { color: #e2e8f0; font-size: 1rem; font-weight: 700; margin-bottom: 10px; }
.out-desc  { color: #64748b; font-size: 0.84rem; line-height: 1.6; }
.out-tags  { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 14px; }
.out-tag {
    background: rgba(59,130,246,0.1); color: #60a5fa;
    border: 1px solid rgba(59,130,246,0.25); border-radius: 20px;
    padding: 2px 10px; font-size: 0.72rem;
}

/* ── Scenarios ── */
.scenario-grid { display: flex; gap: 16px; justify-content: center; flex-wrap: wrap; }
.sc-pill {
    display: flex; align-items: center; gap: 12px;
    background: #0d1424; border: 1px solid #1e3a5f;
    border-radius: 12px; padding: 16px 24px; min-width: 165px;
}
.sc-icon { font-size: 1.5rem; }
.sc-name { color: #e2e8f0; font-size: 0.9rem; font-weight: 700; }
.sc-desc { color: #64748b; font-size: 0.75rem; margin-top: 2px; }

/* ── CTA band ── */
.cta-band {
    background: linear-gradient(135deg, #0f172a, #1e3a5f);
    padding: 72px 8%; text-align: center;
    border-top: 1px solid #1e40af; border-bottom: 1px solid #1e40af;
}
.cta-h2 { font-size: 2.1rem; font-weight: 800; color: #f1f5f9; margin: 0 0 14px; }
.cta-p  { color: #94a3b8; font-size: 1rem; margin: 0; }

/* ── Footer ── */
.footer-wrap {
    background: #080d1a; border-top: 1px solid #1e3a5f;
    padding: 28px 8%; display: flex;
    justify-content: space-between; align-items: center;
}
.footer-brand { color: #e2e8f0; font-weight: 700; font-size: 0.95rem; }
.footer-copy  { color: #334155; font-size: 0.78rem; }

/* ── Buttons (global default) ── */
.stButton > button {
    width: 100%;
    background: linear-gradient(135deg, #1d4ed8, #3b82f6) !important;
    color: white !important; border: none !important;
    border-radius: 10px; padding: 12px;
    font-size: 1rem; font-weight: 700; transition: opacity .2s;
}
.stButton > button:hover { opacity: 0.87; color: white !important; }

/* ── Text inputs — cover all Streamlit/BaseWeb layers ── */

/* Label above the input */
div[data-testid="stTextInput"] label,
div[data-testid="stTextInput"] label p {
    color: #94a3b8 !important;
    font-size: 0.85rem !important;
    font-weight: 600 !important;
}

/* Outer BaseWeb container */
div[data-testid="stTextInput"] div[data-baseweb="input"],
div[data-testid="stTextInput"] div[data-baseweb="base-input"] {
    background: #0a0f1c !important;
    border: 1px solid #1e3a5f !important;
    border-radius: 8px !important;
}

/* Inner input element */
div[data-testid="stTextInput"] input {
    background: #0a0f1c !important;
    color: #e2e8f0 !important;
    caret-color: #3b82f6 !important;
    font-size: 0.95rem !important;
    padding: 12px 14px !important;
    border: none !important;
    outline: none !important;
}

/* Placeholder text */
div[data-testid="stTextInput"] input::placeholder {
    color: #475569 !important;
    opacity: 1 !important;
}

/* Focus state — highlight border */
div[data-testid="stTextInput"] div[data-baseweb="input"]:focus-within,
div[data-testid="stTextInput"] div[data-baseweb="base-input"]:focus-within {
    border-color: #3b82f6 !important;
    box-shadow: 0 0 0 2px rgba(59,130,246,0.15) !important;
}

/* ── Login card (st.container border=True) ── */
[data-testid="stVerticalBlockBorderWrapper"] {
    background: #0d1424 !important;
    border: 1px solid #1e3a5f !important;
    border-radius: 20px !important;
    box-shadow: 0 16px 48px rgba(0,0,0,0.5) !important;
}
.login-logo  { text-align: center; font-size: 3rem; margin-bottom: 4px; }
.login-title { text-align: center; font-size: 1.6rem; font-weight: 800; color: #f1f5f9; margin-bottom: 4px; }
.login-sub   { text-align: center; color: #64748b; font-size: 0.85rem; margin-bottom: 8px; }
.login-hint  { text-align: center; color: #475569; font-size: 0.78rem; margin-top: 16px; }
.err-msg {
    background: rgba(239,68,68,0.1); border: 1px solid #ef4444;
    color: #fca5a5; border-radius: 8px; padding: 10px 14px;
    font-size: 0.85rem; text-align: center;
}

/* ── Dashboard divider ── */
[data-testid="stDivider"] hr { border-color: #1e3a5f !important; }

/* ── Dashboard info box ── */
[data-testid="stNotification"] {
    background: rgba(59,130,246,0.08) !important;
    border: 1px solid #1e40af !important;
    color: #94a3b8 !important;
    border-radius: 10px !important;
}
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# NAVBAR — uses st.columns so the Sign In / Sign Out button is a real widget
# ══════════════════════════════════════════════════════════════════════════════

def render_navbar(show_login_btn=True):
    st.markdown('<div class="navbar-row">', unsafe_allow_html=True)
    col_brand, col_links, col_action = st.columns([2, 6, 1.5])

    with col_brand:
        st.markdown('<div class="nav-brand">🧪 QA Test Generator</div>', unsafe_allow_html=True)

    with col_links:
        st.markdown(
            '<div class="nav-links">'
            '<span class="nav-link">Features</span>'
            '<span class="nav-link">How it works</span>'
            '<span class="nav-link">Outputs</span>'
            '<span class="nav-badge">DeepSeek Powered</span>'
            '</div>',
            unsafe_allow_html=True,
        )

    with col_action:
        if show_login_btn:
            if st.button("Sign In →", key="nav_login"):
                st.session_state.page = "login"
                st.rerun()
        else:
            col_user, col_out = st.columns([1.6, 1])
            with col_user:
                st.markdown(
                    f'<div style="color:#64748b;font-size:0.85rem;padding-top:10px;">'
                    f'👤 <b style="color:#e2e8f0">{st.session_state.username}</b></div>',
                    unsafe_allow_html=True,
                )
            with col_out:
                if st.button("Sign Out", key="signout"):
                    st.session_state.logged_in = False
                    st.session_state.username = ""
                    st.session_state.page = "landing"
                    st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: PUBLIC LANDING
# ══════════════════════════════════════════════════════════════════════════════

def page_landing():
    render_navbar(show_login_btn=True)

    # Hero
    st.markdown("""
    <div class="hero-outer">
      <div class="hero-glow"></div>
      <div class="hero-pill">AI · Multi-Agent · RAG · Quality-Gated</div>
      <div class="hero-title">
        Generate <span>Comprehensive QA Tests</span><br>from Any Requirement
      </div>
      <div class="hero-sub">
        Paste a user story, acceptance criteria, or plain description — get back
        manual test cases, API automation scripts, and UI end-to-end tests in seconds.
        Powered by a self-healing 4-agent AI pipeline.
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Hero CTA — rendered in a row whose background matches the hero gradient via CSS
    st.markdown('<div class="hero-btn-row">', unsafe_allow_html=True)
    _, btn_col, _ = st.columns([2, 1, 2])
    with btn_col:
        if st.button("Get Started — Sign In", key="hero_login"):
            st.session_state.page = "login"
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    # Stats strip
    st.markdown("""
    <div class="stats-strip">
      <div class="stat-item"><span class="stat-num">5</span><div class="stat-lbl">Scenario Types</div></div>
      <div class="stat-item"><span class="stat-num">4</span><div class="stat-lbl">AI Agents</div></div>
      <div class="stat-item"><span class="stat-num">3</span><div class="stat-lbl">Test Formats</div></div>
      <div class="stat-item"><span class="stat-num">70%</span><div class="stat-lbl">Quality Gate</div></div>
      <div class="stat-item"><span class="stat-num">RAG</span><div class="stat-lbl">Context Memory</div></div>
    </div>
    """, unsafe_allow_html=True)

    # Features
    st.markdown("""
    <div class="section">
      <div class="section-title">Everything a QA team needs</div>
      <div class="section-sub">One tool that replaces hours of manual test-case writing with intelligent, coverage-complete output.</div>
      <div class="feature-grid">
        <div class="feat-card">
          <div class="feat-icon">📥</div>
          <div class="feat-title">Flexible Input Formats</div>
          <div class="feat-desc">Accepts plain text, Gherkin acceptance criteria, or structured user stories. No special formatting required.</div>
        </div>
        <div class="feat-card">
          <div class="feat-icon">🤖</div>
          <div class="feat-title">4-Agent AI Pipeline</div>
          <div class="feat-desc">Planner, Generator, Reviewer, and Formatter agents collaborate to produce complete, reviewed test suites.</div>
        </div>
        <div class="feat-card">
          <div class="feat-icon">🔁</div>
          <div class="feat-title">Self-Healing Quality Gate</div>
          <div class="feat-desc">Output scoring below 70 automatically reruns the pipeline with structured feedback until quality is met.</div>
        </div>
        <div class="feat-card">
          <div class="feat-icon">🧠</div>
          <div class="feat-title">RAG Context Memory</div>
          <div class="feat-desc">All generated suites are stored in a vector database. Future runs benefit from your team's accumulated knowledge.</div>
        </div>
        <div class="feat-card">
          <div class="feat-icon">📊</div>
          <div class="feat-title">100-Point Quality Score</div>
          <div class="feat-desc">Scenario coverage, automation quality, clarity, and best practices — every suite is objectively scored.</div>
        </div>
        <div class="feat-card">
          <div class="feat-icon">⚡</div>
          <div class="feat-title">DeepSeek Powered</div>
          <div class="feat-desc">Fast, cost-effective, and accurate. DeepSeek's OpenAI-compatible API handles code generation and structured output with ease.</div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Pipeline
    st.markdown("""
    <div class="section-alt">
      <div class="section-title">How the Pipeline Works</div>
      <div class="section-sub">Four specialised agents, one seamless flow — from raw requirement to production-ready test suite.</div>
      <div class="pipeline-wrap">
        <div class="pipe-steps">
          <div class="pipe-step">
            <div class="pipe-circle">📥</div>
            <span class="pipe-num">Step 1</span>
            <div class="pipe-label">Requirement Input</div>
            <div class="pipe-desc">User story, AC, or plain text</div>
          </div>
          <div class="pipe-arrow">→</div>
          <div class="pipe-step">
            <div class="pipe-circle">🗺️</div>
            <span class="pipe-num">Step 2</span>
            <div class="pipe-label">Planner Agent</div>
            <div class="pipe-desc">Extracts domain, endpoints & test focus areas</div>
          </div>
          <div class="pipe-arrow">→</div>
          <div class="pipe-step">
            <div class="pipe-circle">⚙️</div>
            <span class="pipe-num">Step 3</span>
            <div class="pipe-label">Generator Agent</div>
            <div class="pipe-desc">Creates manual, API & UI tests across 5 scenario types</div>
          </div>
          <div class="pipe-arrow">→</div>
          <div class="pipe-step">
            <div class="pipe-circle">🔍</div>
            <span class="pipe-num">Step 4</span>
            <div class="pipe-label">Review Agent</div>
            <div class="pipe-desc">Scores quality, detects gaps & triggers remediation loops</div>
          </div>
          <div class="pipe-arrow">→</div>
          <div class="pipe-step">
            <div class="pipe-circle">📄</div>
            <span class="pipe-num">Step 5</span>
            <div class="pipe-label">Formatter Agent</div>
            <div class="pipe-desc">Clean Markdown ready for Jira, Confluence, or CI</div>
          </div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Outputs
    st.markdown("""
    <div class="section">
      <div class="section-title">Three Test Formats, One Run</div>
      <div class="section-sub">Every generation produces a complete suite covering manual testing, backend APIs, and end-to-end UI flows.</div>
      <div class="output-grid">
        <div class="out-card green">
          <div class="out-title">📋 Manual Test Cases</div>
          <div class="out-desc">Step-by-step test cases with preconditions, numbered actions, expected results, and test data — ready for testers to execute immediately.</div>
          <div class="out-tags">
            <span class="out-tag">Preconditions</span><span class="out-tag">Steps</span>
            <span class="out-tag">Expected Results</span><span class="out-tag">Test Data</span>
          </div>
        </div>
        <div class="out-card blue">
          <div class="out-title">🔌 API Automation</div>
          <div class="out-desc">Pytest-based scripts with request/response assertions, status code checks, JSON schema validation, and auth token handling.</div>
          <div class="out-tags">
            <span class="out-tag">Pytest</span><span class="out-tag">Assertions</span>
            <span class="out-tag">Schema Check</span><span class="out-tag">Auth</span>
          </div>
        </div>
        <div class="out-card purple">
          <div class="out-title">🖥️ UI Automation</div>
          <div class="out-desc">Playwright TypeScript end-to-end tests with page objects, smart locators, wait strategies, and cross-browser support built in.</div>
          <div class="out-tags">
            <span class="out-tag">Playwright</span><span class="out-tag">TypeScript</span>
            <span class="out-tag">Page Objects</span><span class="out-tag">E2E</span>
          </div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Scenarios
    st.markdown("""
    <div class="section-alt">
      <div class="section-title">5 Scenario Types — Always Covered</div>
      <div class="section-sub">The pipeline guarantees tests for every scenario. No gaps, no manual planning needed.</div>
      <div class="scenario-grid">
        <div class="sc-pill">
          <div class="sc-icon">✅</div>
          <div><div class="sc-name">Happy Path</div><div class="sc-desc">Normal success flows</div></div>
        </div>
        <div class="sc-pill">
          <div class="sc-icon">❌</div>
          <div><div class="sc-name">Negative</div><div class="sc-desc">Invalid inputs & errors</div></div>
        </div>
        <div class="sc-pill">
          <div class="sc-icon">⚠️</div>
          <div><div class="sc-name">Edge Case</div><div class="sc-desc">Uncommon conditions</div></div>
        </div>
        <div class="sc-pill">
          <div class="sc-icon">📐</div>
          <div><div class="sc-name">Boundary</div><div class="sc-desc">Min / max values</div></div>
        </div>
        <div class="sc-pill">
          <div class="sc-icon">🔒</div>
          <div><div class="sc-name">Security</div><div class="sc-desc">Auth & injection tests</div></div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # CTA band
    st.markdown("""
    <div class="cta-band">
      <div class="cta-h2">Ready to generate your first test suite?</div>
      <div class="cta-p">Sign in and paste your requirement — results in under a minute.</div>
    </div>
    """, unsafe_allow_html=True)

    # Footer
    st.markdown("""
    <div class="footer-wrap">
      <div class="footer-brand">🧪 QA Test Generator</div>
      <div class="footer-copy">Capstone Project · 2026 · Powered by DeepSeek API</div>
    </div>
    """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: LOGIN
# ══════════════════════════════════════════════════════════════════════════════

def page_login():
    _, col, _ = st.columns([1, 1.1, 1])
    with col:
        st.markdown("<div style='height:48px'></div>", unsafe_allow_html=True)

        with st.container(border=True):
            st.markdown("""
            <div class="login-logo">🧪</div>
            <div class="login-title">Welcome back</div>
            <div class="login-sub">Sign in to your QA Test Generator account</div>
            """, unsafe_allow_html=True)

            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

            username = st.text_input("Username", placeholder="Enter your username", key="li_user")
            password = st.text_input("Password", type="password", placeholder="Enter your password", key="li_pass")

            st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

            if st.button("Sign In", key="do_login"):
                if username in DEMO_USERS and DEMO_USERS[username] == password:
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    st.session_state.page = "dashboard"
                    st.session_state.login_error = ""
                    st.rerun()
                else:
                    st.session_state.login_error = "Invalid credentials. Try demo / demo"

            if st.session_state.login_error:
                st.markdown(
                    f'<div class="err-msg">⚠ {st.session_state.login_error}</div>',
                    unsafe_allow_html=True,
                )

            st.markdown("""
            <div class="login-hint">
              Demo: <b>admin / admin123</b> &nbsp;·&nbsp; <b>demo / demo</b>
            </div>
            """, unsafe_allow_html=True)
            st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

        if st.button("← Back to Home", key="back_home"):
            st.session_state.page = "landing"
            st.session_state.login_error = ""
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: DASHBOARD (post-login)
# ══════════════════════════════════════════════════════════════════════════════

def page_dashboard():
    render_navbar(show_login_btn=False)

    st.divider()

    st.markdown(
        f'<h2 style="color:#f1f5f9;margin:24px 0 6px;padding:0 8%;">Welcome, {st.session_state.username} 👋</h2>'
        f'<p style="color:#64748b;margin:0 0 32px;padding:0 8%;">You\'re all set. '
        f'Use the <b style="color:#94a3b8">sidebar</b> or the cards below to get started.</p>',
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("""
        <div class="feat-card" style="text-align:center;margin:0 8px;">
          <div class="feat-icon">⚡</div>
          <div class="feat-title">Generate Tests</div>
          <div class="feat-desc">Paste a requirement and generate a complete test suite in one click.</div>
        </div>
        """, unsafe_allow_html=True)
    with c2:
        st.markdown("""
        <div class="feat-card" style="text-align:center;margin:0 8px;">
          <div class="feat-icon">📂</div>
          <div class="feat-title">View History</div>
          <div class="feat-desc">Browse all previously generated test suites saved to GitHub.</div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Open History →", key="goto_history"):
            st.session_state.page = "history"
            st.rerun()
    with c3:
        st.markdown("""
        <div class="feat-card" style="text-align:center;margin:0 8px;">
          <div class="feat-icon">⚙️</div>
          <div class="feat-title">Settings</div>
          <div class="feat-desc">Configure LLM provider, framework, language, and RAG options.</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)
    st.info("Open the **sidebar (›)** on the left to navigate to Generate Tests.", icon="🚀")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: HISTORY (reads from GitHub DB)
# ══════════════════════════════════════════════════════════════════════════════

def page_history():
    render_navbar(show_login_btn=False)
    st.divider()

    st.markdown(
        '<h2 style="color:#f1f5f9;margin:24px 0 4px;padding:0 8%;">📂 Test Suite History</h2>'
        '<p style="color:#64748b;margin:0 0 28px;padding:0 8%;">All previously generated test suites saved to GitHub.</p>',
        unsafe_allow_html=True,
    )

    # Back button
    col_back, _ = st.columns([1, 8])
    with col_back:
        if st.button("← Dashboard", key="hist_back"):
            st.session_state.page = "dashboard"
            st.session_state.selected_suite_path = None
            st.rerun()

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # Load Supabase DB
    try:
        import sys, os
        sys.path.insert(0, os.path.dirname(__file__))
        from core.supabase_db import get_supabase_db
        db = get_supabase_db()
    except Exception as e:
        st.error(f"Could not load Supabase DB module: {e}")
        return

    if not db.is_configured():
        st.markdown("""
        <div style="background:#0d1424;border:1px solid #f59e0b;border-radius:14px;
                    padding:32px;text-align:center;margin:0 8%;">
          <div style="font-size:2.5rem;margin-bottom:12px;">⚙️</div>
          <div style="color:#f1f5f9;font-weight:700;font-size:1.1rem;margin-bottom:8px;">
            Supabase not configured
          </div>
          <div style="color:#64748b;font-size:0.9rem;line-height:1.6;">
            Add <b style="color:#94a3b8">SUPABASE_URL</b> and
            <b style="color:#94a3b8">SUPABASE_KEY</b> to your <code>.env</code> file,
            then run <code>supabase_schema.sql</code> in your Supabase SQL editor.
          </div>
        </div>
        """, unsafe_allow_html=True)
        return

    # Suite detail view
    if st.session_state.selected_suite_path:
        _render_suite_detail(db, st.session_state.selected_suite_path)
        return

    # Search bar
    _, search_col, _ = st.columns([0.4, 2, 2.6])
    with search_col:
        search_query = st.text_input("", placeholder="🔍  Search by feature name...", key="suite_search", label_visibility="collapsed")

    # Suite list view
    with st.spinner("Loading history from Supabase..."):
        try:
            suites = db.search_suites(search_query) if search_query else db.list_suites()
        except Exception as e:
            st.error(f"Failed to fetch history: {e}")
            return

    if not suites:
        st.markdown("""
        <div style="background:#0d1424;border:1px solid #1e3a5f;border-radius:14px;
                    padding:48px;text-align:center;margin:0 8%;">
          <div style="font-size:2.5rem;margin-bottom:12px;">🧪</div>
          <div style="color:#64748b;font-size:1rem;">No test suites yet. Generate your first one!</div>
        </div>
        """, unsafe_allow_html=True)
        return

    st.markdown(f'<p style="color:#64748b;padding:0 8%;margin-bottom:16px;">{len(suites)} suite(s) found</p>', unsafe_allow_html=True)

    for suite in suites:
        _render_suite_card(suite)


def _render_suite_card(suite: dict):
    score = suite.get("score", 0)
    score_color = "#22c55e" if score >= 80 else "#f59e0b" if score >= 60 else "#ef4444"
    generated_at = suite.get("generated_at", "")[:16].replace("T", "  ")

    with st.container():
        st.markdown(f"""
        <div style="background:#0d1424;border:1px solid #1e3a5f;border-radius:14px;
                    padding:22px 28px;margin:0 8% 12px;display:flex;
                    align-items:center;justify-content:space-between;gap:16px;">
          <div style="flex:1;">
            <div style="color:#e2e8f0;font-weight:700;font-size:1rem;margin-bottom:4px;">
              🧪 {suite.get("feature_name","—")}
            </div>
            <div style="color:#64748b;font-size:0.8rem;">
              {generated_at} &nbsp;·&nbsp; {suite.get("domain","—")}
            </div>
          </div>
          <div style="display:flex;gap:20px;align-items:center;flex-wrap:wrap;">
            <div style="text-align:center;">
              <div style="color:#94a3b8;font-size:0.7rem;margin-bottom:2px;">MANUAL</div>
              <div style="color:#22c55e;font-weight:700;">{suite.get("manual_count",0)}</div>
            </div>
            <div style="text-align:center;">
              <div style="color:#94a3b8;font-size:0.7rem;margin-bottom:2px;">API</div>
              <div style="color:#3b82f6;font-weight:700;">{suite.get("api_count",0)}</div>
            </div>
            <div style="text-align:center;">
              <div style="color:#94a3b8;font-size:0.7rem;margin-bottom:2px;">UI</div>
              <div style="color:#a855f7;font-weight:700;">{suite.get("ui_count",0)}</div>
            </div>
            <div style="text-align:center;">
              <div style="color:#94a3b8;font-size:0.7rem;margin-bottom:2px;">SCORE</div>
              <div style="color:{score_color};font-weight:800;font-size:1.1rem;">{score:.0f}</div>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        _, btn_col, _ = st.columns([10, 1.5, 1])
        with btn_col:
            if st.button("View Details", key=f"view_{suite.get('id','')}"):
                st.session_state.selected_suite_path = suite.get("id")
                st.rerun()


def _render_suite_detail(db, suite_id: str):
    col_back, _ = st.columns([1, 8])
    with col_back:
        if st.button("← Back to List", key="detail_back"):
            st.session_state.selected_suite_path = None
            st.rerun()

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    with st.spinner("Loading suite from Supabase..."):
        try:
            row = db.get_full_row(suite_id)
        except Exception as e:
            st.error(f"Failed to load suite: {e}")
            return

    if not row:
        st.error("Suite not found.")
        return

    suite_data = row.get("suite_json", {})
    output_md  = row.get("output_md", "")

    score = 0
    if suite_data.get("review"):
        score = suite_data["review"].get("final_score", 0)
    score_color = "#22c55e" if score >= 80 else "#f59e0b" if score >= 60 else "#ef4444"

    st.markdown(f"""
    <div style="background:#0d1424;border:1px solid #1e3a5f;border-radius:16px;
                padding:28px 32px;margin:0 8% 24px;">
      <div style="color:#e2e8f0;font-size:1.4rem;font-weight:800;margin-bottom:8px;">
        🧪 {suite_data.get("feature_name","—")}
      </div>
      <div style="display:flex;gap:32px;flex-wrap:wrap;">
        <div><span style="color:#64748b;font-size:0.8rem;">Generated</span>
             <div style="color:#94a3b8;font-weight:600;">{suite_data.get("generated_at","")[:16].replace("T"," ")}</div></div>
        <div><span style="color:#64748b;font-size:0.8rem;">Quality Score</span>
             <div style="color:{score_color};font-weight:800;font-size:1.2rem;">{score:.0f} / 100</div></div>
        <div><span style="color:#64748b;font-size:0.8rem;">Manual Tests</span>
             <div style="color:#22c55e;font-weight:700;">{len(suite_data.get("manual_test_cases",[]))}</div></div>
        <div><span style="color:#64748b;font-size:0.8rem;">API Tests</span>
             <div style="color:#3b82f6;font-weight:700;">{len(suite_data.get("api_test_cases",[]))}</div></div>
        <div><span style="color:#64748b;font-size:0.8rem;">UI Tests</span>
             <div style="color:#a855f7;font-weight:700;">{len(suite_data.get("ui_test_cases",[]))}</div></div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["📄 Markdown Output", "🗂 Raw JSON"])
    with tab1:
        if output_md:
            st.markdown(output_md)
        else:
            st.info("No markdown output found.")
    with tab2:
        st.json(suite_data)


# ══════════════════════════════════════════════════════════════════════════════
# ROUTER
# ══════════════════════════════════════════════════════════════════════════════

if st.session_state.page == "landing":
    page_landing()
elif st.session_state.page == "login":
    page_login()
elif st.session_state.page in ("dashboard", "history"):
    if st.session_state.logged_in:
        if st.session_state.page == "dashboard":
            page_dashboard()
        else:
            page_history()
    else:
        st.session_state.page = "login"
        st.rerun()
