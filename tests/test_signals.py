import pandas as pd

from Services.app.services.signals import run_all_signal_models


def test_signal_models_return_expected_keys():
    df = pd.DataFrame(
        {
            "Date": pd.date_range("2024-01-01", periods=250, freq="D"),
            "Open": [100 + i * 0.1 for i in range(250)],
            "High": [101 + i * 0.1 for i in range(250)],
            "Low": [99 + i * 0.1 for i in range(250)],
            "Close": [100 + i * 0.1 for i in range(250)],
            "Volume": [1000 + i for i in range(250)],
        }
    )
    out = run_all_signal_models(df)
    assert out["vpvr_rows"] == 20
    assert "vpvr_signal" in out
    assert "fvg_signal" in out
    assert "wyckoff_signal" in out