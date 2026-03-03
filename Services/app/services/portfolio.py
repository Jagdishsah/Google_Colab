from __future__ import annotations

import pandas as pd


def medium_exposure(trx_df: pd.DataFrame) -> pd.DataFrame:
    if trx_df.empty:
        return pd.DataFrame(columns=["Medium", "Net_Amount"])
    work = trx_df.copy()
    work["Amount"] = pd.to_numeric(work.get("Amount", 0), errors="coerce").fillna(0)
    return work.groupby("Medium", as_index=False)["Amount"].sum().rename(columns={"Amount": "Net_Amount"})


def sector_exposure(portfolio_df: pd.DataFrame) -> pd.DataFrame:
    if portfolio_df.empty:
        return pd.DataFrame(columns=["Sector", "Units"])
    work = portfolio_df.copy()
    work["Units"] = pd.to_numeric(work.get("Units", 0), errors="coerce").fillna(0)
    return work.groupby("Sector", as_index=False)["Units"].sum().sort_values("Units", ascending=False)