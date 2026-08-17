# Changelog

## 0.1.0 — TradeLab-MCP

Fork of PHUICMT/mcp-mt5 0.4.1 with a deterministic research layer.

### Added

- Unique `run_id` and exclusive `runs/<run_id>/` artifact directory
- Exclusive `tester.ini` per execution (never a shared global file)
- Research `manifest.json` + SHA-256 of source, binary, includes, and config
- Explicit tester report collection (no "latest file" lookup)
- SQLite index (`research.db`)
- MCP tools: `health`, `run_batch`, `get_run`, `get_trades`, `compare_runs`, `walk_forward`
- Robust tester HTML parser (numeric types, EN/PT/RU labels)
- `Leverage=1:100` accepted by the tester.ini validator
- Sequential install lock (`mt5.lock`)
- Acceptance EA `experts/RSI2.mq5` + deal export include
- Failure states preserve evidence (`created/compiling/running/completed/failed/timeout`)

### Changed

- `run_backtest` now takes strategy/symbol/timeframe/dates instead of a shared config path
- `compile` returns `success` plus source/binary SHA-256
- `smoke_test` accepts symbol, period, model, and explicit dates
- MCP surface reduced to the research V1 tools
