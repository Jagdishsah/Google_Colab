from pathlib import Path

import google.generativeai as genai
import pandas as pd
import streamlit as st

from Services.app.config import load_storage_config, load_supabase_config
from Services.app.storage import DataStorage

st.header("🤖 AI Quantitative Advisor")
st.markdown("Your personal AI analyst powered by Google Gemini. Select a dataset, and let the AI find hidden patterns in broker behavior.")

storage = DataStorage(supabase_config=load_supabase_config(), local_root=Path('.'), storage_config=load_storage_config())

try:
    genai.configure(api_key=st.secrets["gemini"]["api_key"])
    model = genai.GenerativeModel("gemini-2.0-flash")
except Exception as e:
    st.error(f"❌ Gemini setup error: {e}")
    st.stop()

files = storage.list_analysis_files()
if not files:
    st.info("No saved data found. Go to Data Analysis and save a file first!")
else:
    selected_file = st.selectbox("Select Broker Data for AI Analysis:", files)
    if selected_file:
        try:
            df = storage.get_analysis_data(selected_file)
            if df.empty:
                st.warning("Selected file has no rows.")
                st.stop()

            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
            total_days = len(df)
            net_inventory = (pd.to_numeric(df["Buy_Qty"], errors="coerce").fillna(0) - pd.to_numeric(df["Sell_Qty"], errors="coerce").fillna(0)).sum()
            total_buy_amt = pd.to_numeric(df["Buy_Amount"], errors="coerce").fillna(0).sum()
            total_buy_qty = pd.to_numeric(df["Buy_Qty"], errors="coerce").fillna(0).sum()
            wacc = (total_buy_amt / total_buy_qty) if total_buy_qty > 0 else 0
            recent_df = df.tail(5).copy()
            recent_df["Net_Qty"] = pd.to_numeric(recent_df["Buy_Qty"], errors="coerce").fillna(0) - pd.to_numeric(recent_df["Sell_Qty"], errors="coerce").fillna(0)
            recent_trend = recent_df[["Date", "Net_Qty"]].to_string(index=False)

            st.write(f"**Analyzing:** `{selected_file}` | **Total Days:** `{total_days}`")
            user_question = st.text_input(
                "Ask the AI a specific question, or leave blank for a general report:",
                placeholder="E.g., Are they accumulating or distributing? What is their WACC?",
            )

            if st.button("🧠 Generate AI Analysis", type="primary"):
                prompt = f"""
                You are an elite quantitative analyst for NEPSE.
                DATA SUMMARY:
                - Broker File: {selected_file}
                - Trading Days Logged: {total_days}
                - Current Holding Inventory (Net Qty): {net_inventory}
                - Estimated Weighted Average Cost (WACC): Rs {wacc:.2f}
                RECENT 5-DAY MOMENTUM (Net Qty):
                {recent_trend}
                User's specific question: {user_question if user_question else "Provide a general accumulation/distribution analysis and strategic advice."}
                """
                response = model.generate_content(prompt)
                st.write("---")
                st.markdown("### 🤖 AI Analyst Report")
                st.write(response.text)
        except Exception as e:
            st.error(f"Error reading data or contacting AI: {e}")