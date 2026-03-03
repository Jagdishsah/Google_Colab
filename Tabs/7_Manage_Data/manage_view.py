from Services.app.ui import render_manage_data


def render(storage):
    render_manage_data(storage.get_ledger(), storage)