from Services.app.ui import render_new_entry


def render(storage):
    ledger = storage.get_ledger()
    holdings = storage.get_holdings()
    render_new_entry(ledger, holdings, storage)