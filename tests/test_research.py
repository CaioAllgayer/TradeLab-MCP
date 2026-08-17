from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcp_mt5.parsers import parse_number, parse_tester_report
from mcp_mt5.paths import MT5Layout
from mcp_mt5.research.compare import compare_runs
from mcp_mt5.research.db import connect, fetch_run, upsert_run
from mcp_mt5.research.hashes import sha256_file, sha256_text
from mcp_mt5.research.ids import is_run_id, new_experiment_id, new_run_id
from mcp_mt5.research.lab import publish_to_lab
from mcp_mt5.research.lock import InstallLock, LockBusy
from mcp_mt5.research.manifest import new_manifest, read_manifest, update_manifest, write_manifest
from mcp_mt5.research.runner import execute_backtest, get_run, get_trades, wait_for_report
from mcp_mt5.research.snapshot import snapshot_strategy
from mcp_mt5.research.store import ResearchStore
from mcp_mt5.research.tester_ini import format_leverage, normalize_date, normalize_model, write_tester_ini
from mcp_mt5.research.trades import parse_trades_csv
from mcp_mt5.research.walk_forward import build_windows


def test_run_id_format():
    rid = new_run_id()
    assert is_run_id(rid)
    assert not is_run_id("latest")
    assert not is_run_id("foo")
    assert new_experiment_id().startswith("exp_")


def test_hashes_stable(tmp_path: Path):
    p = tmp_path / "a.mq5"
    p.write_text("int x = 1;\n", encoding="utf-8")
    assert sha256_file(p) == sha256_file(p)
    assert sha256_text("abc") == sha256_text("abc")
    assert sha256_text("abc") != sha256_text("abd")


def test_store_run_dir_and_immutability(tmp_path: Path):
    store = ResearchStore(tmp_path / "research")
    rid = new_run_id()
    store.create_run(rid)
    write_manifest(store, rid, new_manifest(rid, "RSI2", {"symbol": "PETR4"}))
    store.write_json(rid, "metrics.json", {"net_profit": 1.0})
    update_manifest(store, rid, status="completed", stage="completed")
    with pytest.raises(PermissionError):
        store.write_json(rid, "metrics.json", {"net_profit": 2.0})
    with pytest.raises(PermissionError):
        update_manifest(store, rid, status="failed")
    assert store.read_json(rid, "metrics.json")["net_profit"] == 1.0


def test_tester_ini_exclusive_and_leverage(tmp_path: Path):
    path = tmp_path / "tester.ini"
    write_tester_ini(
        path,
        expert=r"TradeLab MCP\abc",
        symbol="PETR4",
        period="D1",
        from_date="2015-01-01",
        to_date="2025.12.31",
        model="real_ticks",
        deposit=100000,
        currency="BRL",
        leverage="1:100",
        report=r"Tester\TradeLab MCP\abc\report",
        inputs={"InpRSIBuy": 10},
    )
    text = path.read_text(encoding="utf-8")
    assert "Expert=TradeLab MCP\\abc" in text
    assert "Symbol=PETR4" in text
    assert "Period=D1" in text
    assert "Model=4" in text
    assert "FromDate=2015.01.01" in text
    assert "Leverage=1:100" in text
    assert "ShutdownTerminal=0" in text
    assert "ReplaceReport=1" in text
    assert "InpRSIBuy=10||10||0||10||N" in text
    assert format_leverage("1:100") == "1:100"
    assert format_leverage(100) == "100"
    assert normalize_date("2015-01-01") == "2015.01.01"
    assert normalize_model("real_ticks") == 4


def test_lock_exclusive(tmp_path: Path):
    lock_path = tmp_path / "mt5.lock"
    a = InstallLock(lock_path)
    b = InstallLock(lock_path)
    a.acquire()
    with pytest.raises(LockBusy):
        b.acquire(timeout=0)
    a.release()
    b.acquire(timeout=0)
    b.release()
    assert not lock_path.exists()


def test_lock_context_manager(tmp_path: Path):
    lock_path = tmp_path / "mt5.lock"
    with InstallLock(lock_path) as held:
        assert held.path.exists()
    assert not lock_path.exists()


SAMPLE_REPORT = """
<html><body>
<table>
<tr><td>Expert:</td><td>RSI2</td></tr>
<tr><td>Symbol:</td><td>PETR4</td></tr>
<tr><td>Period:</td><td>Daily 2015.01.01 - 2025.12.31</td></tr>
<tr><td>Initial Deposit:</td><td>100000</td></tr>
<tr><td>Total Net Profit:</td><td>18342.21</td></tr>
<tr><td>Gross Profit:</td><td>40000.00</td></tr>
<tr><td>Gross Loss:</td><td>-21657.79</td></tr>
<tr><td>Profit Factor:</td><td>1.48</td></tr>
<tr><td>Expected Payoff:</td><td>136.88</td></tr>
<tr><td>Recovery Factor:</td><td>1.12</td></tr>
<tr><td>Sharpe Ratio:</td><td>1.14</td></tr>
<tr><td>Total Trades:</td><td>134</td></tr>
<tr><td>Profit Trades (% of total):</td><td>70 (52.24%)</td></tr>
<tr><td>Maximal Drawdown:</td><td>12 700.00 (12.7%)</td></tr>
<tr><td>Balance Drawdown Maximal:</td><td>8000.00</td></tr>
<tr><td>Equity Drawdown Maximal:</td><td>9000.00</td></tr>
</table>
<table>
<tr><th>Time</th><th>Type</th><th>Order</th><th>Size</th><th>Price</th><th>S/L</th><th>T/P</th><th>Profit</th><th>Balance</th></tr>
<tr><td>2015.02.01 00:00:00</td><td>buy</td><td>1</td><td>100</td><td>10.00</td><td></td><td></td><td>200.00</td><td>100200</td></tr>
<tr><td>2015.03.01 00:00:00</td><td>sell</td><td>2</td><td>100</td><td>11.00</td><td></td><td></td><td>-50.00</td><td>100150</td></tr>
</table>
</body></html>
"""

SAMPLE_REPORT_PT = """
<html><body><table>
<tr><td>Lucro líquido total:</td><td>1.234,56</td></tr>
<tr><td>Fator de lucro:</td><td>1,45</td></tr>
<tr><td>Total de negócios:</td><td>10</td></tr>
</table></body></html>
"""


def test_parse_number_formats():
    assert parse_number("1,234.56") == 1234.56
    assert parse_number("1.234,56") == 1234.56
    assert parse_number("1 234.56") == 1234.56
    assert parse_number(10) == 10.0
    assert parse_number("-21657.79") == -21657.79
    assert parse_number(None) is None


def test_parse_tester_report_typed():
    out = parse_tester_report(SAMPLE_REPORT)
    s = out["summary"]
    assert s["net_profit"] == 18342.21
    assert s["profit_factor"] == 1.48
    assert s["total_trades"] == 134
    assert s["sharpe"] == 1.14
    assert s["max_drawdown"] == 12700.0
    assert s["max_drawdown_pct"] == 12.7
    assert s["win_rate"] == 52.24
    assert s["initial_deposit"] == 100000
    assert isinstance(s["net_profit"], float)
    assert out["trade_rows_detected"] >= 2


def test_parse_tester_report_portuguese():
    s = parse_tester_report(SAMPLE_REPORT_PT)["summary"]
    assert s["net_profit"] == 1234.56
    assert s["profit_factor"] == 1.45
    assert s["total_trades"] == 10


def test_parse_tester_report_negociacoes_label():
    html = """<html><body><table>
    <tr><td>Total de Negociações:</td><td>13</td></tr>
    <tr><td>Lucro Líquido Total:</td><td>455.00</td></tr>
    <tr><td>Rebaixamento Máximo do Saldo :</td><td>54.00 (0.52%)</td></tr>
    </table></body></html>"""
    s = parse_tester_report(html)["summary"]
    assert s["total_trades"] == 13
    assert s["net_profit"] == 455.0
    assert s["balance_drawdown"] == 54.0
    assert s["balance_drawdown_pct"] == 0.52


def test_sqlite_index(tmp_path: Path):
    db = tmp_path / "research.db"
    manifest = {
        "run_id": "20260817_073412_a8f231",
        "status": "completed",
        "strategy": {"name": "RSI2", "source_sha256": "abc"},
        "test": {
            "symbol": "PETR4",
            "period": "D1",
            "from": "2015.01.01",
            "to": "2025.01.01",
            "model": 4,
            "deposit": 100000,
        },
        "started_at": "t0",
        "finished_at": "t1",
        "run_dir": str(tmp_path),
        "error": None,
    }
    upsert_run(manifest, metrics={"net_profit": 10.5, "total_trades": 3}, trades=[], db_file=db)
    row = fetch_run("20260817_073412_a8f231", db_file=db)
    assert row["symbol"] == "PETR4"
    assert row["metrics"]["net_profit"] == 10.5
    with connect(db) as conn:
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"strategies", "runs", "experiments", "metrics", "trades"} <= names


def test_walk_forward_windows():
    windows = build_windows("2020.01.01", "2020.04.10", is_days=30, oos_days=10, step_days=10)
    assert windows[0]["is_from"] == "2020.01.01"
    assert windows[0]["is_to"] == "2020.01.30"
    assert windows[0]["oos_from"] == "2020.01.31"
    assert windows[0]["oos_to"] == "2020.02.09"
    assert all(w["oos_to"] <= "2020.04.10" for w in windows)
    assert len(windows) >= 2


def test_compare_runs(tmp_path: Path):
    store = ResearchStore(tmp_path / "research")
    a = "20260817_073412_aaaaaa"
    b = "20260817_073413_bbbbbb"
    for rid, profit in ((a, 100.0), (b, 150.0)):
        store.create_run(rid)
        write_manifest(store, rid, new_manifest(rid, "RSI2", {"symbol": "PETR4"}))
        store.write_json(rid, "metrics.json", {"net_profit": profit, "total_trades": 10})
    out = compare_runs(store, [a, b])
    profit = next(d for d in out["diffs"] if d["key"] == "net_profit")
    assert profit["deltas_vs_baseline"][b]["delta"] == 50.0


def test_wait_for_report_stable(tmp_path: Path):
    folder = tmp_path / "rep"
    folder.mkdir()
    (folder / "report.htm").write_text("<html>" + "x" * 300 + "</html>", encoding="utf-8")
    found = wait_for_report(folder, timeout_sec=3, poll=0.05)
    assert found is not None
    assert found.name.startswith("report")


def test_publish_to_lab_experts(tmp_path: Path):
    layout = _fake_layout(tmp_path)
    src = tmp_path / "RSI2.mq5"
    src.write_text('#include "Include/ResearchExport.mqh"\nvoid OnTick() {}\n', encoding="utf-8")
    inc = tmp_path / "Include"
    inc.mkdir()
    (inc / "ResearchExport.mqh").write_text("// export\n", encoding="utf-8")
    binary = tmp_path / "RSI2.ex5"
    binary.write_bytes(b"EX5")
    out = publish_to_lab(layout, name="RSI2", source=src, binary=binary)
    lab = layout.experts_dir / "TradeLab MCP"
    assert out["expert"] == r"TradeLab MCP\RSI2"
    assert (lab / "RSI2.mq5").exists()
    assert (lab / "RSI2.ex5").exists()
    assert (lab / "Include" / "ResearchExport.mqh").exists()
    assert (lab / "README.txt").exists()


def test_snapshot_includes(tmp_path: Path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "Signal.mqh").write_text("int Signal() { return 1; }\n", encoding="utf-8")
    ea = src_dir / "EA.mq5"
    ea.write_text('#include "Signal.mqh"\nvoid OnTick() {}\n', encoding="utf-8")
    dest = tmp_path / "run"
    out = snapshot_strategy(ea, dest)
    assert (dest / "strategy.mq5").exists()
    assert (dest / "Signal.mqh").exists()
    assert out["source_sha256"]


def _fake_layout(tmp_path: Path) -> MT5Layout:
    install = tmp_path / "MT5"
    install.mkdir()
    (install / "terminal64.exe").write_bytes(b"TERM")
    (install / "MetaEditor64.exe").write_bytes(b"EDIT")
    data = tmp_path / "data"
    for sub in ("MQL5/Experts", "MQL5/Include", "MQL5/Files", "MQL5/Logs", "Tester/logs"):
        (data / sub).mkdir(parents=True)
    return MT5Layout(install=install, data=data, terminal_hash="HASHHASHHASHHASHHASHHASHHASHHASH", edition="mt5")


def test_runner_associates_report_by_run_id(tmp_path: Path):
    layout = _fake_layout(tmp_path)
    store = ResearchStore(tmp_path / "research")
    ea = tmp_path / "RSI2.mq5"
    ea.write_text("void OnTick() {}\n", encoding="utf-8")

    def fake_compile(_layout, source, include, log_file):
        binary = Path(source).with_suffix(".ex5")
        binary.write_bytes(b"EX5")
        Path(log_file).write_text("Result: 0 errors, 0 warnings\n", encoding="utf-8")
        return {
            "success": True,
            "ok": True,
            "binary": str(binary),
            "source_sha256": sha256_file(source),
            "binary_sha256": sha256_file(binary),
            "errors": [],
            "warnings": [],
            "returncode": 0,
        }

    def fake_launch(_layout, ini_path, timeout_sec, portable=False):
        text = Path(ini_path).read_text(encoding="utf-8")
        report = None
        for line in text.splitlines():
            if line.startswith("Report="):
                report = line.split("=", 1)[1]
        assert report and "TradeLab MCP" in report
        report_dir = _layout.data / Path(report).parent
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "report.htm").write_text(SAMPLE_REPORT, encoding="utf-8")
        (_layout.tester_logs / "20260817.log").write_text("tester finished\n", encoding="utf-8")
        return {"returncode": 0, "timeout": False, "cmd": ["fake"]}

    result = execute_backtest(
        layout=layout,
        strategy=str(ea),
        symbol="PETR4",
        timeframe="D1",
        from_date="2015.01.01",
        to_date="2025.01.01",
        model=4,
        deposit=100000,
        store=store,
        compile_fn=fake_compile,
        launch_fn=fake_launch,
    )
    assert result["status"] == "completed"
    assert is_run_id(result["run_id"])
    assert result["metrics"]["net_profit"] == 18342.21
    assert result["metrics"]["total_trades"] == 134
    loaded = get_run(store, result["run_id"])
    assert loaded["status"] == "completed"
    assert loaded["metrics"]["profit_factor"] == 1.48
    assert (store.run_dir(result["run_id"]) / "report.htm").exists()
    assert (store.run_dir(result["run_id"]) / "tester.ini").exists()
    assert (store.run_dir(result["run_id"]) / "strategy.mq5").exists()
    assert (store.run_dir(result["run_id"]) / "strategy.ex5").exists()
    assert (store.run_dir(result["run_id"]) / "manifest.json").exists()
    assert (layout.experts_dir / "TradeLab MCP" / "RSI2.ex5").exists()
    ini_text = (store.run_dir(result["run_id"]) / "tester.ini").read_text(encoding="utf-8")
    assert "Expert=TradeLab MCP\\RSI2" in ini_text
    manifest = json.loads((store.run_dir(result["run_id"]) / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["files"]["config_sha256"]
    assert manifest["strategy"]["source_sha256"]
    assert manifest["strategy"]["binary_sha256"]
    trades = get_trades(store, result["run_id"])
    assert trades["count"] >= 1
    # Must never have used a global latest-report search: only the run dir report.
    other = layout.tester_dir / "other.htm"
    other.write_text("<html>wrong</html>", encoding="utf-8")
    again = get_run(store, result["run_id"])
    assert again["metrics"]["net_profit"] == 18342.21


def test_runner_preserves_failed_evidence(tmp_path: Path):
    layout = _fake_layout(tmp_path)
    store = ResearchStore(tmp_path / "research")
    ea = tmp_path / "Bad.mq5"
    ea.write_text("void OnTick() {}\n", encoding="utf-8")

    def fake_compile(_layout, source, include, log_file):
        Path(log_file).write_text("Result: 1 errors, 0 warnings\n", encoding="utf-8")
        return {"success": False, "ok": False, "errors": [{"message": "boom"}], "returncode": 1}

    result = execute_backtest(
        layout=layout,
        strategy=str(ea),
        symbol="PETR4",
        timeframe="D1",
        from_date="2015.01.01",
        to_date="2015.02.01",
        store=store,
        compile_fn=fake_compile,
        launch_fn=lambda *a, **k: {"returncode": 0, "timeout": False, "cmd": []},
    )
    assert result["status"] == "failed"
    assert result["stage"] == "compiling"
    assert (store.run_dir(result["run_id"]) / "manifest.json").exists()
    assert (store.run_dir(result["run_id"]) / "error.json").exists()
    assert read_manifest(store, result["run_id"])["status"] == "failed"


def test_parse_real_acceptance_report():
    path = Path(__file__).resolve().parents[1] / "research" / "acceptance" / "mcp_BBAS3_D1_20240101_20240816.htm"
    if not path.exists():
        pytest.skip("acceptance report not in tree")
    from mcp_mt5.parsers import parse_tester_report, read_text_auto
    from mcp_mt5.research.metrics import normalize_metrics

    parsed = parse_tester_report(read_text_auto(path))
    s = parsed["summary"]
    assert s["symbol"] == "BBAS3"
    assert s["expert"] == "RSI2"
    assert s["currency"] == "BRL"
    assert s["leverage"] == "1:100"
    assert s["net_profit"] == 455.0
    assert s["total_trades"] == 13
    assert s["win_rate"] == 84.62
    assert s["profit_trades"] == 11
    assert s["initial_deposit"] == 10000.0
    closed = parsed["closed_trades"]
    assert len(closed) == 13
    assert closed[0]["entry_time"] == "2024.01.05 10:08:40"
    assert closed[0]["entry_price"] == 23.53
    assert closed[0]["exit_price"] == 23.98
    assert closed[0]["profit"] == 45.0
    assert closed[-1]["profit"] == 100.0
    profits = [t["profit"] for t in closed]
    assert profits == [45, 79, 97, 71, -54, 49, 3, 25, 8, 38, 12, -18, 100]
    metrics = normalize_metrics(s, closed)
    assert metrics["symbol"] == "BBAS3"
    assert metrics["win_rate"] == 84.62
    assert metrics["total_trades"] == 13


def test_parse_deal_csv_pairs_positions():
    csv_text = """deal,position_id,symbol,type,entry,time,price,volume,profit,commission,swap,reason
1,10,PETR4,buy,in,2015.01.02 00:00:00,10,100,0,0,0,open
2,10,PETR4,sell,out,2015.01.10 00:00:00,12,100,200,-1,0,rsi
"""
    trades = parse_trades_csv(csv_text)
    assert len(trades) == 1
    assert trades[0]["side"] == "buy"
    assert trades[0]["entry_price"] == 10
    assert trades[0]["exit_price"] == 12
    assert trades[0]["profit"] == 200
    assert trades[0]["commission"] == -1
