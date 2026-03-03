from datetime import date

import pandas as pd

from Services.app.transactions import SmartTransaction, apply_smart_transaction


def test_apply_smart_transaction_syncs_holdings_for_buy():
    ledger = pd.DataFrame(columns=[
        "Date", "Type", "Category", "Amount", "Status", "Due_Date", "Ref_ID", "Description", "Is_Non_Cash", "Dispute_Note", "Fiscal_Year"
    ])
    holdings = pd.DataFrame(columns=["Symbol", "Total_Qty", "Pledged_Qty", "LTP", "Haircut"])

    txn = SmartTransaction(
        txn_date=date(2026, 1, 1),
        mode="BUY",
        symbol="TEST",
        qty=10,
        price=100,
        amount=0,
        status="Cleared",
        ref_id="r1",
        description="buy test",
    )

    l2, h2 = apply_smart_transaction(ledger, holdings, txn)
    assert len(l2) == 1
    assert float(h2[h2["Symbol"] == "TEST"]["Total_Qty"].iloc[0]) == 10.0