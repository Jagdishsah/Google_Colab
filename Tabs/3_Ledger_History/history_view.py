from Services.app.ui import render_history


def render(storage):
    render_history(storage.get_ledger())