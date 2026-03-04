from Services.app.terminal_ui import render_terminal_hub


def render(storage):
    render_terminal_hub(storage, storage.get_ledger(), storage.get_holdings())
