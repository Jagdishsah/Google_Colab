from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from Services.app.logic import fiscal_year_for_nepal
from Services.app.storage import HOLDINGS_COLUMNS, LEDGER_COLUMNS


@dataclass
class SmartTransaction:
    txn_date: date
    mode: str
    symbol: str
    qty: float
    price: float
    amount: float
    status: str
    ref_id: str
    description: str
    due_days: int = 2


def _safe_symbol(symbol: str) -> str:
    return (symbol or "").upper().strip()


def smart_to_ledger_row(txn: SmartTransaction) -> dict:
    symbol = _safe_symbol(txn.symbol)
    desc_symbol = f"{symbol} | " if symbol else ""

    type_map = {
        "DEPOSIT": "Load Collateral (Deposit)",
        "WITHDRAW": "Refund Request (Withdraw)",
        "BUY": "Buy Shares (Payable)",
        "SELL": "Sell Shares (Receivable)",
        "EXPENSE": "Expense",
        "DIRECT_PAY": "Direct Payment",
        "PRIMARY_INVEST": "Primary Investment",
    }
    category_map = {
        "DEPOSIT": "DEPOSIT",
        "WITHDRAW": "WITHDRAW",
        "BUY": "PAYABLE",
        "SELL": "RECEIVABLE",
        "EXPENSE": "EXPENSE",
        "DIRECT_PAY": "DIRECT_PAY",
        "PRIMARY_INVEST": "PRIMARY_INVEST",
    }
    amount = txn.amount if txn.mode in {"DEPOSIT", "WITHDRAW", "EXPENSE", "DIRECT_PAY", "PRIMARY_INVEST"} else txn.qty * txn.price

    return {
        "Date": txn.txn_date,
        "Type": type_map[txn.mode],
        "Category": category_map[txn.mode],
        "Amount": float(round(abs(amount), 2)),
        "Status": txn.status,
        "Due_Date": txn.txn_date + timedelta(days=max(txn.due_days, 0)),
        "Ref_ID": txn.ref_id,
        "Description": f"{desc_symbol}{txn.description}".strip(),
        "Is_Non_Cash": False,
        "Dispute_Note": "",
        "Fiscal_Year": fiscal_year_for_nepal(txn.txn_date),
    }


def apply_smart_transaction(
    ledger_df: pd.DataFrame,
    holdings_df: pd.DataFrame,
    txn: SmartTransaction,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    ledger_row = smart_to_ledger_row(txn)
    out_ledger = pd.concat([ledger_df, pd.DataFrame([ledger_row])], ignore_index=True)
    for col in LEDGER_COLUMNS:
        if col not in out_ledger.columns:
            out_ledger[col] = ""
    out_ledger = out_ledger[LEDGER_COLUMNS]

    out_holdings = holdings_df.copy()
    if out_holdings.empty:
        out_holdings = pd.DataFrame(columns=HOLDINGS_COLUMNS)

    mode = txn.mode
    symbol = _safe_symbol(txn.symbol)
    qty = float(txn.qty)
    if symbol and mode in {"BUY", "SELL"} and qty > 0:
        if symbol not in out_holdings["Symbol"].values:
            out_holdings = pd.concat(
                [
                    out_holdings,
                    pd.DataFrame(
                        [{"Symbol": symbol, "Total_Qty": 0.0, "Pledged_Qty": 0.0, "LTP": float(txn.price), "Haircut": 25.0}]
                    ),
                ],
                ignore_index=True,
            )

        idx = out_holdings[out_holdings["Symbol"] == symbol].index[0]
        current_total = float(out_holdings.at[idx, "Total_Qty"])
        delta = qty if mode == "BUY" else -qty
        new_total = max(0.0, current_total + delta)
        out_holdings.at[idx, "Total_Qty"] = new_total
        pledged_now = float(out_holdings.at[idx, "Pledged_Qty"])
        out_holdings.at[idx, "Pledged_Qty"] = min(new_total, pledged_now if pledged_now > 0 else new_total)
        if txn.price > 0:
            out_holdings.at[idx, "LTP"] = float(txn.price)

    for col in HOLDINGS_COLUMNS:
        if col not in out_holdings.columns:
            out_holdings[col] = 0.0 if col != "Symbol" else ""
    return out_ledger, out_holdings[HOLDINGS_COLUMNS]