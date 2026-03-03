from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd


@dataclass
class LedgerSummary:
    net_cash_invested: float = 0.0
    tms_cash_balance: float = 0.0
    trading_power: float = 0.0
    utilization_rate: float = 0.0
    payable_due: float = 0.0
    receivable_due: float = 0.0
    net_due: float = 0.0
    t0_due: float = 0.0
    t1_due: float = 0.0
    t2_due: float = 0.0
    pending_df: pd.DataFrame = field(default_factory=pd.DataFrame)


def fiscal_year_for_nepal(date_obj: date) -> str:
    return f"{date_obj.year}/{date_obj.year+1}" if date_obj.month >= 7 else f"{date_obj.year-1}/{date_obj.year}"


def calc_net_flow(frame: pd.DataFrame) -> float:
    return frame[frame["Category"] == "RECEIVABLE"]["Amount"].sum() - frame[frame["Category"] == "PAYABLE"]["Amount"].sum()


def summarize_ledger(df: pd.DataFrame, holdings_df: pd.DataFrame, today: date) -> LedgerSummary:
    s = LedgerSummary()
    if df.empty:
        return s

    money_out = df[(df["Category"].isin(["DEPOSIT", "DIRECT_PAY", "PRIMARY_INVEST", "EXPENSE"])) & (df["Is_Non_Cash"] == False)]["Amount"].sum()
    money_in = df[df["Category"] == "WITHDRAW"]["Amount"].sum()
    s.net_cash_invested = float(money_out - money_in)

    tms_credits = df[df["Category"].isin(["DEPOSIT", "RECEIVABLE", "DIRECT_PAY"])]["Amount"].sum()
    tms_debits = df[df["Category"].isin(["WITHDRAW", "PAYABLE", "EXPENSE"])]["Amount"].sum()
    s.tms_cash_balance = float(tms_credits - tms_debits)

    non_cash_value = 0.0
    if not holdings_df.empty:
        h = holdings_df.copy()
        h["Collateral_Val"] = h["Pledged_Qty"] * h["LTP"] * (1 - (h["Haircut"] / 100))
        non_cash_value = h["Collateral_Val"].sum()
    s.trading_power = float(s.tms_cash_balance + non_cash_value)

    used_collateral = abs(s.tms_cash_balance) if s.tms_cash_balance < 0 else 0
    s.utilization_rate = float((used_collateral / non_cash_value * 100) if non_cash_value > 0 else 0)

    pending_df = df[df["Status"].astype(str).str.lower() == "pending"].copy()
    s.pending_df = pending_df
    s.payable_due = float(pending_df[pending_df["Category"] == "PAYABLE"]["Amount"].sum())
    s.receivable_due = float(pending_df[pending_df["Category"] == "RECEIVABLE"]["Amount"].sum())
    s.net_due = float(s.payable_due - s.receivable_due)

    if not pending_df.empty:
        pending_df["Due_Date"] = pd.to_datetime(pending_df["Due_Date"]).dt.date
        s.t0_due = calc_net_flow(pending_df[pending_df["Due_Date"] <= today])
        s.t1_due = calc_net_flow(pending_df[pending_df["Due_Date"] == today + timedelta(days=1)])
        s.t2_due = calc_net_flow(pending_df[pending_df["Due_Date"] >= today + timedelta(days=2)])
    return s