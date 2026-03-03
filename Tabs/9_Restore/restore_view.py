import streamlit as st
import pandas as pd
import io
import zipfile
from restore import render_restore

def render(storage):
    st.header("። Bulk Data Restoration")
    st.write("Upload CSV files named after their categories (e.g., portfolio.csv, ledger.csv) to restore your data.")

    # 1. File Uploader for multiple CSVs
    uploaded_files = st.file_uploader("Choose CSV files", type="csv", accept_multiple_files=True)

    valid_keys = ["ledger", "holdings", "tms_trx", "portfolio", "watchlist", "history", "diary", "wealth", "data_metrics", "activity_log"]

    if uploaded_files:
        for uploaded_file in uploaded_files:
            file_name = uploaded_file.name.lower()
            category = file_name.replace(".csv", "")

            if category in valid_keys:
                try:
                    df = pd.read_csv(uploaded_file)
                    if category == "ledger":
                        storage.save_ledger(df)
                    elif category == "holdings":
                        storage.save_holdings(df)
                    else:
                        storage.save_terminal_data(category, df)
                    st.success(f"✅ Successfully restored: {uploaded_file.name}")
                except Exception as e:
                    st.error(f"❌ Failed to restore {uploaded_file.name}: {e}")
            else:
                st.warning(f"⚠️ Ignored {uploaded_file.name}: Unsupported category name.")

    st.divider()
    st.header("፥ Data Export")
    st.write("Backup all your data categories into a single ZIP archive.")

    if st.button("Prepare Export Package"):
        buf = io.BytesIO()
        try:
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for key in valid_keys:
                    if key == "ledger":
                        df = storage.get_ledger()
                    elif key == "holdings":
                        df = storage.get_holdings()
                    else:
                        df = storage.get_terminal_data(key)
                    
                    if not df.empty:
                        csv_data = df.to_csv(index=False)
                        zf.writestr(f"{key}.csv", csv_data)
            
            buf.seek(0)
            st.download_button(
                label="Download Export All Data (.zip)",
                data=buf,
                file_name="nepse_tms_backup.zip",
                mime="application/zip"
            )
            st.success("✅ Export package ready for download!")
        except Exception as e:
            st.error(f"❌ Export failed: {e}")

    st.divider()
    st.header("☣️ Data Management")
    st.warning("Danger Zone: These actions are permanent and cannot be undone.")
    
    confirm_wipe = st.checkbox("Check to enable data wipe (Nuke Environment)")
    
    if st.button("Execute Nuke Environment", disabled=not confirm_wipe, type="primary"):
        try:
            with st.spinner("Wiping all user data..."):
                storage.clear_all_user_data()
            st.success("✅ Environment successfully wiped from Cloud and Local mirrors.")
            st.info("፩ Please refresh the page to clear the local session cache and reset the UI.")
        except Exception as e:
            st.error(f"❌ Failed to clear data: {e}")

    st.divider()
    st.subheader("System Restore")
    render_restore(storage)
