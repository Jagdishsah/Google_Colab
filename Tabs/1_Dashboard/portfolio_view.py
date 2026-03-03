from Services.app.logic import summarize_ledger
from Services.app.ui import render_dashboard


def render(storage):
    ledger = storage.get_ledger()
    holdings = storage.get_holdings()
    summary = summarize_ledger(ledger, holdings, __import__('datetime').date.today())
    render_dashboard(ledger, summary)