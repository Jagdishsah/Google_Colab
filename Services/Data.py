import json
from pathlib import Path

import pandas as pd
import streamlit as st

from Services.app.config import load_storage_config, load_supabase_config
from Services.app.storage import DataStorage

storage = DataStorage(supabase_config=load_supabase_config(), local_root=Path('.'), storage_config=load_storage_config())

st.title("📈 Advanced Data Analysis Studio")

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📤 Upload & Analyze",
    "📂 Browse Saved Data",
    "🚀 Advanced Analysis",
    "📊 Visualization",
    "🤖 AI Advisor",
])

with tab1:
    uploaded_file = st.file_uploader("Upload raw data file (JSON or TXT)", type=["txt", "json"])
    if uploaded_file is not None:
        try:
            raw_data = json.load(uploaded_file)
            df = pd.DataFrame(raw_data.get("data", raw_data))

            num_cols = ["b_qty", "s_qty", "b_amt", "s_amt"]
            for col in num_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

            df["Date"] = pd.to_datetime(df["date"], errors="coerce")
            df = df.sort_values(by="Date").reset_index(drop=True)
            df.rename(columns={"b_qty": "Buy_Qty", "s_qty": "Sell_Qty", "b_amt": "Buy_Amount", "s_amt": "Sell_Amount"}, inplace=True, errors="ignore")

            df["Net_Qty"] = df["Buy_Qty"] - df["Sell_Qty"]
            df["Net_Amount"] = df["Buy_Amount"] - df["Sell_Amount"]
            df["Total_Vol"] = df["Buy_Qty"] + df["Sell_Qty"]
            df["Avg_30D_Vol"] = df["Total_Vol"].rolling(window=30, min_periods=1).mean()

            st.dataframe(df.tail(300), use_container_width=True, height=380)

            c_stock, c_tms, c_custom = st.columns(3)
            stock_name = c_stock.text_input("Stock Symbol (e.g., NABIL)", "").upper().strip()
            tms_no = c_tms.text_input("TMS/Broker No (e.g., 58)", "").strip()
            custom_name = c_custom.text_input("Or Custom Filename", "").strip()
            save_name = custom_name if custom_name else (f"{stock_name}_{tms_no}" if stock_name and tms_no else "")

            if st.button("Save to Supabase", use_container_width=True, type="primary"):
                if not save_name:
                    st.error("Provide a filename.")
                else:
                    cols_to_save = ["Date", "Buy_Qty", "Sell_Qty", "Net_Qty", "Buy_Amount", "Sell_Amount", "Net_Amount"]
                    save_df = df[cols_to_save].copy()
                    save_df["Date"] = pd.to_datetime(save_df["Date"], errors="coerce").dt.strftime("%Y-%m-%d")

                    existing = storage.get_analysis_data(save_name)
                    if not existing.empty and "Date" in existing.columns:
                        merged = pd.concat([existing, save_df], ignore_index=True).drop_duplicates(subset=["Date"], keep="last").sort_values("Date")
                    else:
                        merged = save_df
                    storage.save_analysis_data(save_name, merged)
                    st.success(f"Saved `{save_name}.csv` to Supabase/local mirror.")
        except Exception as e:
            st.error(f"❌ Error: {e}")

with tab2:
    st.subheader("📂 Browse Saved Data")
    saved_files = storage.list_analysis_files()
    selected_file = st.selectbox("Select file:", saved_files, key="data_tab2_browse") if saved_files else None
    if selected_file:
        hist_df = storage.get_analysis_data(selected_file)
        st.dataframe(hist_df, use_container_width=True)

with tab3:
    namespace3 = globals().copy()
    namespace3["__name__"] = "advanced_analysis_module"
    with open("Data/Market_Data/Data_analysis/Advanced_analysis.py", encoding="utf-8") as f:
        exec(compile(f.read(), "Advanced_analysis.py", "exec"), namespace3)

with tab4:
    namespace4 = globals().copy()
    namespace4["__name__"] = "visual_analysis_module"
    with open("Data/Market_Data/Data_analysis/Visual.py", encoding="utf-8") as f:
        exec(compile(f.read(), "Visual.py", "exec"), namespace4)

with tab5:
    namespace5 = globals().copy()
    namespace5["__name__"] = "ai_advisor_module"
    with open("Services/Advisor.py", encoding="utf-8") as f:
        exec(compile(f.read(), "Advisor.py", "exec"), namespace5)