from __future__ import annotations

import numpy as np
import pandas as pd


def recommended_position_size(capital: float, risk_per_trade_pct: float, entry: float, stop: float) -> float:
    if capital <= 0 or entry <= 0 or stop <= 0 or risk_per_trade_pct <= 0:
        return 0.0
    risk_budget = capital * (risk_per_trade_pct / 100)
    per_share_risk = abs(entry - stop)
    if per_share_risk == 0:
        return 0.0
    return max(risk_budget / per_share_risk, 0.0)


def portfolio_var_95(price_series: pd.Series, position_value: float) -> float:
    s = pd.to_numeric(price_series, errors="coerce").dropna()
    if len(s) < 5 or position_value <= 0:
        return 0.0
    returns = s.pct_change().dropna()
    if returns.empty:
        return 0.0
    z = 1.65
    sigma = float(returns.std())
    return float(abs(z * sigma * position_value))


def drawdown_stats(equity_curve: pd.Series) -> dict:
    s = pd.to_numeric(equity_curve, errors="coerce").dropna()
    if s.empty:
        return {"max_drawdown_pct": 0.0, "current_drawdown_pct": 0.0}
    running_max = s.cummax()
    dd = (s - running_max) / running_max.replace(0, np.nan)
    return {
        "max_drawdown_pct": float(dd.min() * 100),
        "current_drawdown_pct": float(dd.iloc[-1] * 100),
    }