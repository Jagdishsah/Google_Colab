
import streamlit as st
import os
from pathlib import Path
from Services.app.config import load_supabase_config
from Services.app.storage import DataStorage

def run_diagnostics():
    st.title("🔍 System Diagnostics")
    
    st.subheader("1. Secret Keys Audit")
    # Print keys to check for casing issues (masking values)
    secrets_dict = {}
    for key in st.secrets.keys():
        val = str(st.secrets[key])
        masked = val[:4] + "****" if len(val) > 4 else "****"
        secrets_dict[key] = masked
    st.json(secrets_dict)

    st.subheader("2. Configuration Loading")
    config = load_supabase_config()
    if config:
        st.success(f"Config Loaded: URL={config.url}")
        st.info(f"Table Name: {config.table}")
    else:
        st.error("Failed to load Supabase Config. Check secret names/nesting.")

    st.subheader("3. Connection Test")
    try:
        storage = DataStorage(supabase_config=config, local_root=Path("."))
        st.write(f"Active Backend: {storage.active_backend()}")
        
        with st.spinner("Attempting get_ledger()..."):
            ledger = storage.get_ledger()
            st.success("Successfully connected and fetched ledger!")
            st.dataframe(ledger.head())
    except ModuleNotFoundError as e:
        st.error(f"Missing Module: {e}")
    except Exception as e:
        st.error(f"Connection Error: {type(e).__name__}")
        st.exception(e)

if __name__ == "__main__":
    run_diagnostics()
