# Review sample

Open `review.html` for a self-contained, interactive data review. It works without API keys, a server, or internet access. The page is a data-design artifact, not the investigation application.

The model and assumptions are in `../docs/DATA_MODEL.md`. `schema.sql` is the proposed relational model. `review.json`, `review.sqlite3`, and table-specific CSV files contain the same generated sample. `manifest.json` records actual counts, checks and a deterministic content hash.

Regenerate from the project root:

```sh
.venv/bin/python -m scripts.build_data_sample
.venv/bin/python -m pytest tests/test_data_sample.py -q
```

Sample regeneration uses the Python standard library and never reads credentials. The committed local market cache supplies real daily reference prices and volumes. Refresh it explicitly with `.venv/bin/python -m scripts.fetch_market_history`; that separate command uses httpx and public Yahoo Finance endpoints. It will fail rather than invent historical data if the provider is unavailable. Running it overwrites its own sample outputs. Do not put manual edits in generated files; change the generator, schema or HTML template instead.

Review Orders to trace fills and lifecycle events, then Evidence & timing to switch between all source metadata and evidence authorized for each alert as of the investigation cutoff. The future communication and denied personnel record must disappear in investigator views. The unavailable MSFT access partition remains visible as an information gap.

The sample uses real NVDA, AAPL, MSFT, AMZN, JPM and XOM securities. Market history is public and sourced; orders, participants, minute bars and private evidence are simulated. The Historical market tab exposes source links. The sample does not yet contain the full trading population or the expanded eight-family alert catalog.
