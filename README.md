# NEPSE Unified Intelligence Terminal (Enterprise Layout)

This repo has been restructured into a strict enterprise hierarchy.

## Folder architecture

```text
Services/
  app/
    config.py
    logic.py
    storage.py
    transactions.py
    market_predictor.py
    terminal_ui.py
    ui.py
    logger.py
    services/
      signals.py
      risk.py
      portfolio.py
  Data.py
  Advisor.py
  scrape.py
  Stock_Graph/

Tabs/
  1_Dashboard/portfolio_view.py
  2_Transaction_Center/transaction_view.py
  3_Ledger_History/history_view.py
  4_Analytics/analytics_view.py
  5_Terminal_Hub/terminal_view.py
  6_Research_Hub/research_view.py
  7_Manage_Data/manage_view.py
  8_Market_Predictor/market_predictor_view.py

Data/
  User_Data/
  TMS_Data/
  Logs/
  Market_Data/
```

## Routing model
- `Main_Nepse.py` now acts as a **custom router**.
- It loads tab modules from `Tabs/**` using `importlib.util.spec_from_file_location` and calls `render(storage)`.
- The Streamlit `pages/` dependency is removed.

## Data paths
All core data paths are centralized in `Services/app/storage.py` under `PATHS`.
This enforces strict relative-path consistency across Services/Tabs.

## Run
```bash
pip install -r requirements.txt
streamlit run Main_Nepse.py
```

## Optional storage backend
```toml
[storage]
backend = "sqlite"          # csv | sqlite
sqlite_path = "data/terminal.db"
```

## Suggested next-level upgrade
For even stronger enterprise quality, introduce a domain-layer package (`domain/`) with Pydantic schemas for each row type (ledger, tms_trx, cache, history) and force schema validation before every write.