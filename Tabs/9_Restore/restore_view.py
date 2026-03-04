import streamlit as st
import pandas as pd
import io
import zipfile
from restore import render_restore

# --- SCHEMA VALIDATION UTILITIES ---
LEDGER_COLUMNS = ['Date', 'Type', 'Category', 'Amount', 'Status', 'Due_Date', 'Ref_ID', 'Description', 'Is_Non_Cash', 'Dispute_Note', 'Fiscal_Year']
HOLDINGS_COLUMNS = ['Symbol', 'Total_Qty', 'Pledged_Qty', 'LTP', 'Haircut']
TERMINAL_SCHEMAS = {
    'portfolio': ['Symbol', 'Sector', 'Units', 'Total_Cost', 'WACC', 'Buy_Date', 'Stop_Loss', 'Notes'],
    'watchlist': ['Symbol', 'Target', 'Remark'],
    'activity_log': ['Timestamp', 'Category', 'Symbol', 'Action', 'Details', 'Amount'],
    'history': ['Date', 'Buy_Date', 'Symbol', 'Units', 'Buy_Price', 'Sell_Price', 'Invested_Amount', 'Received_Amount', 'Net_PL', 'PL_Pct', 'Reason'],
    'diary': ['Date', 'Symbol', 'Note', 'Emotion', 'Mistake', 'Strategy'],
    'wealth': ['Date', 'Total_Investment', 'Current_Value', 'Total_PL', 'Day_Change', 'Sold_Volume'],
    'tms_trx': ['Date', 'Stock', 'Type', 'Medium', 'Amount', 'Charge', 'Remark', 'Reference']
}

def validate_csv_schema(df, category):
    if category == 'ledger':
        expected_cols = LEDGER_COLUMNS
        numeric_cols = ['Amount']
    elif category == 'holdings':
        expected_cols = HOLDINGS_COLUMNS
        numeric_cols = ['Total_Qty', 'Pledged_Qty', 'LTP', 'Haircut']
    elif category in TERMINAL_SCHEMAS:
        expected_cols = TERMINAL_SCHEMAS[category]
        numeric_lookup = {
            'portfolio': ['Units', 'Total_Cost', 'WACC', 'Stop_Loss'],
            'watchlist': ['Target'],
            'activity_log': ['Amount'],
            'history': ['Units', 'Buy_Price', 'Sell_Price', 'Invested_Amount', 'Received_Amount', 'Net_PL', 'PL_Pct'],
            'wealth': ['Total_Investment', 'Current_Value', 'Total_PL', 'Day_Change', 'Sold_Volume'],
            'tms_trx': ['Amount', 'Charge']
        }
        numeric_cols = numeric_lookup.get(category, [])
    else:
        return False, f"Unknown category: {category}"

    if set(df.columns) != set(expected_cols):
        return False, f"Column mismatch. Expected: {expected_cols}"

    for col in numeric_cols:
        if not pd.api.types.is_numeric_dtype(df[col]):
            try:
                pd.to_numeric(df[col])
            except:
                return False, f"Column '{col}' must be numeric."
    return True, "OK"

def render(storage):
    st.header("። Bulk Data Restoration")
    st.write("Upload CSV files named after their categories (e.g., portfolio.csv) to restore your data.")

    uploaded_files = st.file_uploader("Choose CSV files", type="csv", accept_multiple_files=True)
    valid_keys = ["ledger", "holdings"] + list(TERMINAL_SCHEMAS.keys())

    if uploaded_files:
        for uploaded_file in uploaded_files:
            category = uploaded_file.name.lower().replace(".csv", "")
            if category in valid_keys:
                try:
                    df = pd.read_csv(uploaded_file)
                    is_valid, msg = validate_csv_schema(df, category)
                    
                    if not is_valid:
                        st.error(f"❌ Validation Failed for {uploaded_file.name}: {msg}")
                        continue

                    if category == "ledger":
                        storage.save_ledger(df)
                    elif category == "holdings":
                        storage.save_holdings(df)
                    else:
                        storage.save_terminal_data(category, df)
                    st.success(f"✅ Successfully restored: {uploaded_file.name}")
                except Exception as e:
                    st.error(f"❌ System Error for {uploaded_file.name}: {e}")
            else:
                st.warning(f"⚠️ Ignored {uploaded_file.name}: Unsupported category name.")

    st.divider()
    st.header("፥ Data Export")
    if st.button("Prepare Export Package"):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for key in valid_keys:
                df = storage.get_ledger() if key == "ledger" else storage.get_holdings() if key == "holdings" else storage.get_terminal_data(key)
                if not df.empty:
                    zf.writestr(f"{key}.csv", df.to_csv(index=False))
        st.download_button("Download Export All Data (.zip)", buf.getvalue(), "nepse_tms_backup.zip", "application/zip")

    st.divider()
    st.header("☣️ Data Management")
    confirm_wipe = st.checkbox("Check to enable data wipe (Nuke Environment)")
    if st.button("Execute Nuke Environment", disabled=not confirm_wipe, type="primary"):
        storage.clear_all_user_data()
        st.success("✅ Environment successfully wiped.")

    st.divider()
    st.subheader("System Restore")
    render_restore(storage)