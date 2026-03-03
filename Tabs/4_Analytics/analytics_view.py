from Services.app.ui import render_analytics


def render(storage):
    render_analytics(storage.get_ledger(), storage.get_holdings())