import importlib.util
from pathlib import Path

import streamlit as st
from datetime import datetime

# MUST BE THE FIRST STREAMLIT COMMAND!
st.set_page_config(page_title="NEPSE TMS Pro Ledger", page_icon="💹", layout="wide", initial_sidebar_state="expanded")

from Services.app.config import load_storage_config, load_supabase_config
from Services.app.storage import DataStorage
from Services.app.ui import inject_css, render_sidebar_holdings
from supabase import create_client, Client


#Caching
# Initialize Storage
storage = DataStorage(supabase_config=load_supabase_config(), local_root=Path("."), storage_config=load_storage_config())

if "user" in st.session_state:
    if "ledger_df" not in st.session_state:
        with st.spinner("Syncing with Cloud..."):
            st.session_state.ledger_df = storage.get_ledger()
            st.session_state.holdings_df = storage.get_holdings()
            st.session_state.last_sync = datetime.now()
# Now, instead of calling storage.get_ledger() in your tabs, 
    # you just use st.session_state.ledger_df. This is INSTANT (0ms).


# --- 1. SUPABASE INITIALIZATION ---
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

# --- 2. AUTHENTICATION WALL ---
if "user" not in st.session_state:
    st.markdown("<h1 style='text-align: center;'>🔐 Project Codex</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center;'>Login or create an account to access your secure terminal.</p>", unsafe_allow_html=True)
    
    with st.form("auth_form"):
        email = st.text_input("Email Address")
        password = st.text_input("Password", type="password")
        
        c1, c2 = st.columns(2)
        with c1:
            login_btn = st.form_submit_button("Log In", use_container_width=True)
        with c2:
            signup_btn = st.form_submit_button("Sign Up", use_container_width=True)

    if login_btn:
        try:
            res = supabase.auth.sign_in_with_password({"email": email, "password": password})
            st.session_state["user"] = res.user
            # 👇 ADD THIS LINE to save the user's security token!
            st.session_state["access_token"] = res.session.access_token 
            st.rerun()
        except Exception as e:
            st.error("Login Failed: Invalid email or password.")
            
    if signup_btn:
        try:
            res = supabase.auth.sign_up({"email": email, "password": password})
            st.success("Account created successfully! You can now log in.")
        except Exception as e:
            st.error(f"Signup Failed: {e}")
            
    st.stop() # 🛑 Stops the rest of the app from loading!

# --- 3. CODEX TERMINAL (User is Logged In) ---
current_user = st.session_state["user"]
st.session_state["user_id"] = current_user.id # We will need this for the database!

st.sidebar.success(f"👤 Logged in as: \n{current_user.email}")
if st.sidebar.button("Log Out", use_container_width=True):
    supabase.auth.sign_out()
    st.session_state.clear()
    st.rerun()

st.sidebar.divider()

TAB_ROUTES = {
    "🏠 Dashboard": Path("Tabs/1_Dashboard/portfolio_view.py"),
    "✍️ Transaction Center": Path("Tabs/2_Transaction_Center/transaction_view.py"),
    "📜 Ledger History": Path("Tabs/3_Ledger_History/history_view.py"),
    "📊 Analytics": Path("Tabs/4_Analytics/analytics_view.py"),
    "🖥️ Terminal Hub": Path("Tabs/5_Terminal_Hub/terminal_view.py"),
    "🧠 Research Hub": Path("Tabs/6_Research_Hub/research_view.py"),
    "🛠️ Manage Data": Path("Tabs/7_Manage_Data/manage_view.py"),
    "🔮 Market Predictor": Path("Tabs/8_Market_Predictor/market_predictor_view.py"),
    "♻️ Restore": Path("Tabs/9_Restore/restore_view.py"),
}

def run_tab(path: Path, storage: DataStorage) -> None:
    if not path.exists():
        st.error(f"Missing tab file: {path}")
        return
    spec = importlib.util.spec_from_file_location(f"tab_{path.stem}", path)
    if spec is None or spec.loader is None:
        st.error(f"Could not load tab: {path}")
        return
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if hasattr(module, "render"):
        module.render(storage)
    else:
        st.error(f"Tab missing render(storage): {path}")

inject_css()


with st.sidebar:
    st.title("💹 TMS Pro")
    selected = st.radio("Navigation", list(TAB_ROUTES.keys()))
    st.caption(f"Storage backend: {storage.active_backend()}")
    render_sidebar_holdings(storage, storage.get_holdings())

run_tab(TAB_ROUTES[selected], storage)