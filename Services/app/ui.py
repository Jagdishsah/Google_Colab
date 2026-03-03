from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import importlib
import pandas as pd
import plotly.express as px
import streamlit as st

from Services.app.logic import LedgerSummary, fiscal_year_for_nepal
from Services.app.storage import DataStorage
from Services.app.transactions import SmartTransaction, apply_smart_transaction, smart_to_ledger_row
from Services.app.market_predictor import render_market_predictor_tab


def inject_css() -> None:
    st.markdown(
        """
        <style>
        div[data-testid="stMetric"] {background-color:#f8f9fa; border:1px solid #e9ecef; padding:10px; border-radius:8px;}
        .risk-alert {background-color:#ffcccb; padding:15px; border-radius:8px; color:#8b0000; font-weight:bold; border-left:5px solid red;}
        .safe-zone {background-color:#d4edda; padding:15px; border-radius:8px; color:#155724; border-left:5px solid green;}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _np_now() -> str:
    return (datetime.utcnow() + pd.Timedelta(hours=5, minutes=45)).strftime("%Y-%m-%d %H:%M:%S")


def _append_activity(storage: DataStorage, category: str, symbol: str, action: str, details: str, amount: float) -> None:
    log_df = storage.get_terminal_data("activity_log")
    row = pd.DataFrame([
        {
            "Timestamp": _np_now(),
            "Category": category,
            "Symbol": symbol,
            "Action": action,
            "Details": details,
            "Amount": amount,
        }
    ])
    storage.save_terminal_data("activity_log", pd.concat([row, log_df], ignore_index=True))


def _sync_tms_trx(storage: DataStorage, txn: SmartTransaction, medium: str, normalized_amount: float) -> None:
    trx_df = storage.get_terminal_data("tms_trx")
    entry = pd.DataFrame([
        {
            "Date": txn.txn_date,
            "Stock": txn.symbol,
            "Type": txn.mode,
            "Medium": medium,
            "Amount": normalized_amount,
            "Charge": 0.0,
            "Remark": txn.description,
            "Reference": txn.ref_id,
        }
    ])
    storage.save_terminal_data("tms_trx", pd.concat([trx_df, entry], ignore_index=True))


def render_sidebar_holdings(storage: DataStorage, holdings_df: pd.DataFrame) -> None:
    with st.sidebar.expander("📦 Portfolio & Collateral"):
        sym = st.text_input("Symbol", placeholder="NICA").upper().strip()
        c1, c2 = st.columns(2)
        qty = c1.number_input("Pledged Qty", min_value=0)
        ltp = c2.number_input("LTP", min_value=0.0)
        if st.button("Update Stock") and sym:
            try:
                curr_h = storage.get_holdings()
                curr_h = curr_h[curr_h["Symbol"] != sym]
                new_h = pd.DataFrame([{"Symbol": sym, "Total_Qty": qty, "Pledged_Qty": qty, "LTP": ltp, "Haircut": 25}])
                storage.save_holdings(pd.concat([curr_h, new_h], ignore_index=True))
                _append_activity(storage, "TMS", sym, "HOLDING_UPDATE", "Updated holding from sidebar", 0.0)
                st.success(f"Updated {sym}")
                st.rerun()
            except Exception as e:
                st.error(f"Save failed: {e}")

        if not holdings_df.empty:
            st.dataframe(holdings_df[["Symbol", "Total_Qty", "Pledged_Qty", "LTP"]], height=170, width="stretch")


def render_dashboard(df: pd.DataFrame, summary: LedgerSummary) -> None:
    st.title("🏦 Financial Command Center")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("📅 Today (Due)", f"Rs {abs(summary.t0_due):,.0f}", delta="Pay Now" if summary.t0_due < 0 else "Receive")
    k2.metric("📆 Tomorrow (T+1)", f"Rs {summary.t1_due:,.0f}")
    k3.metric("🔋 Trading Limit", f"Rs {summary.trading_power:,.0f}", delta=f"{summary.utilization_rate:.1f}% Used")
    k4.metric("⚖️ Net Pending", f"Rs {summary.net_due:,.0f}", delta=f"Pay: {summary.payable_due:,.0f} | Rec: {summary.receivable_due:,.0f}")

    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        st.metric("💵 Net Cash Invested", f"Rs {summary.net_cash_invested:,.0f}")
        st.metric("🏦 TMS Balance", f"Rs {summary.tms_cash_balance:,.0f}")
    with c2:
        if summary.tms_cash_balance < -50:
            st.markdown(f"<div class='risk-alert'>⚠️ Negative collateral of Rs {abs(summary.tms_cash_balance):,.2f}</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div class='safe-zone'>✅ All Systems Green.</div>", unsafe_allow_html=True)

        if not summary.pending_df.empty:
            st.dataframe(summary.pending_df[["Date", "Type", "Category", "Amount", "Due_Date"]], height=220, width="stretch")


def render_new_entry(df: pd.DataFrame, holdings_df: pd.DataFrame, storage: DataStorage) -> None:
    st.header("📝 Integrated Transaction Center")
    tab1, tab2 = st.tabs(["⚡ Smart Entry (syncs all)", "🧾 Manual Ledger Entry"])

    with tab1:
        st.caption("Smart mode updates ledger + holdings + activity log + tms transaction ledger")
        with st.form("smart_entry_form"):
            c1, c2, c3, c4 = st.columns(4)
            txn_date = c1.date_input("Date", value=date.today())
            mode = c2.selectbox("Mode", ["BUY", "SELL", "DEPOSIT", "WITHDRAW", "DIRECT_PAY", "PRIMARY_INVEST", "EXPENSE"])
            status = c3.selectbox("Status", ["Pending", "Cleared"], index=1)
            medium = c4.selectbox("Bank/Medium", ["Bank", "Global", "Collateral", "Cash", "Other"], index=0)

            c5, c6, c7 = st.columns(3)
            symbol = c5.text_input("Symbol", value="").upper().strip()
            qty = c6.number_input("Qty", min_value=0.0, step=1.0)
            price = c7.number_input("Price", min_value=0.0, step=0.01)

            amount = st.number_input("Direct Amount (for deposit/withdraw/expense)", min_value=0.0, step=1.0)
            due_days = st.number_input("Due in days", min_value=0, value=2)
            ref_id = st.text_input("Reference ID")
            desc = st.text_input("Description")
            submit = st.form_submit_button("💾 Save Smart Transaction")

        if submit:
            final_desc = f"[{medium}] {desc}".strip()
            txn = SmartTransaction(
                txn_date=txn_date,
                mode=mode,
                symbol=symbol,
                qty=qty,
                price=price,
                amount=amount,
                status=status,
                ref_id=ref_id,
                description=final_desc,
                due_days=int(due_days),
            )
            row = smart_to_ledger_row(txn)
            normalized_amount = row["Amount"] if mode in {"DEPOSIT", "SELL", "RECEIVABLE"} else -row["Amount"]
            try:
                new_ledger, new_holdings = apply_smart_transaction(df, holdings_df, txn)
                storage.save_ledger(new_ledger)
                storage.save_holdings(new_holdings)
                _sync_tms_trx(storage, txn, medium, normalized_amount)
                _append_activity(storage, "TMS", symbol or "N/A", mode, final_desc, normalized_amount)
                st.success("Smart transaction saved. All connected datasets synced.")
                st.rerun()
            except Exception as e:
                st.error(f"Smart transaction failed to persist: {e}")

    with tab2:
        with st.form("entry_form"):
            c1, c2, c3, c4 = st.columns(4)
            txn_date = c1.date_input("Date", value=date.today(), key="m_date")
            txn_type = c2.selectbox("Type", ["BUY", "SELL", "CHARGE", "FUND", "OTHER"], key="m_type")
            category = c3.selectbox("Category", ["DEPOSIT", "WITHDRAW", "PAYABLE", "RECEIVABLE", "DIRECT_PAY", "EXPENSE", "PRIMARY_INVEST"], key="m_cat")
            medium = c4.selectbox("Bank/Medium", ["Bank", "Global", "Collateral", "Cash", "Other"], key="m_medium")

            c5, c6, c7 = st.columns(3)
            amount = c5.number_input("Amount", min_value=0.0, step=1000.0, key="m_amt")
            due_days = c6.number_input("Due in days", min_value=0, value=2, key="m_due")
            is_non_cash = c7.checkbox("Non-Cash", value=False, key="m_non_cash")

            ref_id = st.text_input("Reference ID", key="m_ref")
            desc = st.text_input("Description", key="m_desc")

            if st.form_submit_button("💾 Save Manual Ledger Entry"):
                final_desc = f"[{medium}] {desc}".strip()
                new_row = pd.DataFrame([
                    {
                        "Date": txn_date,
                        "Type": txn_type,
                        "Category": category,
                        "Amount": amount,
                        "Status": "Pending",
                        "Due_Date": txn_date + timedelta(days=due_days),
                        "Ref_ID": ref_id,
                        "Description": final_desc,
                        "Is_Non_Cash": is_non_cash,
                        "Dispute_Note": "",
                        "Fiscal_Year": fiscal_year_for_nepal(txn_date),
                    }
                ])
                try:
                    storage.save_ledger(pd.concat([df, new_row], ignore_index=True))
                    _append_activity(storage, "TMS", "N/A", "MANUAL_LEDGER", final_desc, float(amount))
                    st.success("Manual entry saved.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Manual entry failed to persist: {e}")


def render_history(df: pd.DataFrame) -> None:
    st.header("📜 Transaction Ledger")
    if df.empty:
        st.info("No records found.")
        return
    search = st.text_input("Search Text")
    view_df = df.copy()
    if search:
        view_df = view_df[view_df["Description"].astype(str).str.contains(search, case=False, na=False)]
    view_df = view_df.sort_values("Date", ascending=False)

    def _row_style(row):
        cat = str(row.get("Category", ""))
        status = str(row.get("Status", "")).lower()
        if status == "pending":
            return ["background-color:#fff3cd;color:#7a4e00;font-weight:600"] * len(row)
        if cat == "DEPOSIT":
            return ["background-color:#e8f7ee"] * len(row)
        if cat in {"PAYABLE", "EXPENSE", "WITHDRAW"}:
            return ["background-color:#fdecec"] * len(row)
        if cat in {"RECEIVABLE", "DIRECT_PAY"}:
            return ["background-color:#e9f2ff"] * len(row)
        return [""] * len(row)

    styled = view_df.style.apply(_row_style, axis=1).format({"Amount": "Rs {:,.2f}"})
    st.dataframe(styled, width="stretch", height=600)
    st.download_button("⬇️ Download CSV", view_df.to_csv(index=False).encode("utf-8"), "tms_ledger.csv", "text/csv")


def render_analytics(df: pd.DataFrame, holdings_df: pd.DataFrame) -> None:
    st.header("📊 Integrated Analytics")
    if df.empty:
        st.warning("No data available to visualize.")
        return
    tab1, tab2, tab3 = st.tabs(["📈 Cash Flow", "🍰 Category Mix", "📦 Holdings Snapshot"])
    with tab1:
        cf_df = df.copy().sort_values("Date")
        cf_df["Flow"] = cf_df.apply(lambda x: -x["Amount"] if x["Category"] == "WITHDRAW" else (x["Amount"] if x["Category"] in ["DEPOSIT", "PRIMARY_INVEST", "DIRECT_PAY"] else 0), axis=1)
        cf_df["Cumulative"] = cf_df["Flow"].cumsum()
        st.plotly_chart(px.line(cf_df, x="Date", y="Cumulative", markers=True), width="stretch")
    with tab2:
        c1, c2 = st.columns(2)
        c1.plotly_chart(px.pie(df, values="Amount", names="Category", hole=0.4), width="stretch")
        exp_df = df[df["Category"] == "EXPENSE"]
        if not exp_df.empty:
            c2.plotly_chart(px.bar(exp_df, x="Type", y="Amount", color="Type"), width="stretch")
    with tab3:
        if holdings_df.empty:
            st.info("No holdings available.")
        else:
            view = holdings_df.copy()
            view["Gross_Value"] = view["Total_Qty"] * view["LTP"]
            st.dataframe(view, width="stretch")


def _run_tool(module_name: str, label: str) -> None:
    try:
        module = importlib.import_module(module_name)
        module = importlib.reload(module)
        run_fn = getattr(module, "render", None) or getattr(module, "app", None)
        if callable(run_fn):
            run_fn()
    except Exception as e:
        if type(e).__name__ in ["StopException", "RerunException"]:
            raise e
        st.error(f"❌ Error loading {label}: {e}")


def _signal_lab() -> None:
    st.subheader("📡 Signal Lab (Buy/Sell Scan)")
    csv_files = storage.list_stock_data_files()
    if not csv_files:
        st.info("No stock files in Stock_Data.")
        return
    sel = st.selectbox("Choose stock data", csv_files, key="signal_lab_stock")
    df = storage.get_stock_data(sel)

    for col in ["Close", "LTP", "close"]:
        if col in df.columns:
            price_col = col
            break
    else:
        st.warning("No close/LTP column found.")
        return

    price = pd.to_numeric(df[price_col], errors="coerce").dropna().reset_index(drop=True)
    if len(price) < 30:
        st.warning("Need at least 30 rows for MA signal scan.")
        return

    temp = pd.DataFrame({"Price": price})
    temp["MA10"] = temp["Price"].rolling(10).mean()
    temp["MA20"] = temp["Price"].rolling(20).mean()
    temp = temp.dropna().reset_index(drop=True)
    last = temp.iloc[-1]
    signal = "BUY" if last["MA10"] > last["MA20"] else "SELL"
    confidence = abs(last["MA10"] - last["MA20"]) / max(last["Price"], 1) * 100

    c1, c2 = st.columns(2)
    c1.metric("Signal", signal)
    c2.metric("MA Spread %", f"{confidence:.2f}%")
    st.plotly_chart(px.line(temp.tail(180), y=["Price", "MA10", "MA20"], title=f"{sel} Momentum Lens"), width="stretch")


def render_research_hub(storage: DataStorage) -> None:
    st.header("🧠 Research Hub")
    st.caption("Improved reliability + expanded NEPSE decision tabs.")

    health = {
        "Data Studio": "Services/Data.py",
        "AI Advisor": "Services/Advisor.py",
        "Advanced Analysis": "Data/Market_Data/Data_analysis/Advanced_analysis.py",
        "Visual Analysis": "Data/Market_Data/Data_analysis/Visual.py",
        "Stock Graph": "Services/Stock_Graph/Graph.py",
        "Elliott Scanner": "Services/Stock_Graph/Elliot_Wave.py",
    }
    with st.expander("🔍 Tool Health", expanded=False):
        for name, path in health.items():
            ok = "✅" if Path(path).exists() else "❌"
            st.write(f"{ok} {name} — `{path}`")

    t1, t2, t3, t4, t5, t6, t7, t8 = st.tabs(["Data Studio", "AI Advisor", "Advanced Analysis", "Visual Analysis", "Stock Graph", "Elliott Scanner", "Signal Lab", "Market Predictor"])
    with t1:
        _run_tool("Services.Data", "Data Analysis")
    with t2:
        _run_tool("Services.Advisor", "AI Advisor")
    with t3:
        _run_tool("Data.Market_Data.Data_analysis.Advanced_analysis", "Advanced Analysis")
    with t4:
        _run_tool("Data.Market_Data.Data_analysis.Visual", "Visual Analysis")
    with t5:
        _run_tool("Services.Stock_Graph.Graph", "Stock Graph")
    with t6:
        _run_tool("Services.Stock_Graph.Elliot_Wave", "Elliott Wave Scanner")
    with t7:
        _signal_lab()
    with t8:
        render_market_predictor_tab(storage)


def render_manage_data(df: pd.DataFrame, storage: DataStorage) -> None:
    st.header("🛠️ Data Management")
    with st.expander("🩺 Storage Health", expanded=False):
        health = storage.get_storage_health()
        st.json(health)
        if not health.get("ok", True):
            st.warning("Last write had an issue. Please review the error and retry.")

    if df.empty:
        st.info("No data to manage.")
        return
    work_df = df.copy()
    work_df["Label"] = work_df.apply(lambda x: f"{x['Date']} | {x['Category']} | Rs {x['Amount']} | {x['Description']}", axis=1)
    selected = st.selectbox("Select Transaction", work_df["Label"].tolist())
    idx = work_df[work_df["Label"] == selected].index[0]

    note = st.text_input("Dispute note", value=str(work_df.at[idx, "Dispute_Note"]))
    c1, c2 = st.columns(2)
    if c1.button("Update Note"):
        work_df.at[idx, "Dispute_Note"] = note
        storage.save_ledger(work_df.drop(columns=["Label"]))
        _append_activity(storage, "TMS", "N/A", "NOTE_UPDATE", f"Updated note for row {idx}", 0.0)
        st.success("Note updated")
        st.rerun()
    if c2.button("Delete Transaction"):
        deleted_amt = float(work_df.at[idx, "Amount"])
        work_df = work_df.drop(index=idx).drop(columns=["Label"])
        storage.save_ledger(work_df)
        _append_activity(storage, "TMS", "N/A", "DELETE", f"Deleted transaction index {idx}", deleted_amt)
        st.error("Deleted")
        st.rerun()