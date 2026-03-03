from __future__ import annotations

import pandas as pd

from Services.app.market_predictor import _detect_fvg, _prepare_ohlcv, _signal_engine, _vpvr


def run_all_signal_models(df: pd.DataFrame) -> dict:
    work = _prepare_ohlcv(df)
    vpvr_df, poc = _vpvr(work, bins=20)
    bull, bear = _detect_fvg(work)
    out = _signal_engine(work, poc, bull, bear)
    return {
        "poc": out.poc_price,
        "latest_close": out.latest_close,
        "vpvr_signal": out.vpvr_signal,
        "fvg_signal": out.fvg_signal,
        "wyckoff_signal": out.wyckoff_signal,
        "bullish_fvg_count": len(bull),
        "bearish_fvg_count": len(bear),
        "vpvr_rows": len(vpvr_df),
    }