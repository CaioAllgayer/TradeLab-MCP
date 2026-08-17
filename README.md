# TradeLab-MCP

Servidor MCP de pesquisa quantitativa. A IA define a estratégia. O **Strategy Tester do MetaTrader 5** executa o backtest.

```
IA (Codex / GPT / Grok / Gemini / Claude)
        │ MCP
        ▼
Trading Research MCP
        │
        ▼
terminal64.exe  →  Strategy Tester oficial  →  runs/<run_id>/
```

Fork de [`PHUICMT/mcp-mt5`](https://github.com/PHUICMT/mcp-mt5) (MIT). Não reimplementa o tester em Python.

## Princípio

O MT5 é a autoridade para ordens, fills, ticks, spread, SL/TP, margem, comissões e P&L.

Python só organiza experimentos (`run_id`, manifest, hashes, parser, estatísticas derivadas).

Cada backtest gera um identificador único. Nada é recuperado pelo “arquivo mais recente”.

```
runs/20260817_073412_a8f231/
  tester.ini
  strategy.mq5
  strategy.ex5
  report.htm
  tester.log
  trades.csv
  metrics.json
  manifest.json
```

## Ferramentas MCP (V1)

| Ferramenta | Função |
|---|---|
| `health` | MT5, MetaEditor, terminal, data dir, Experts, Tester, build |
| `compile` | Compila `.mq5` e devolve hashes |
| `run_backtest` | Tester oficial → `run_id` + métricas + artifacts |
| `run_batch` | Mesma estratégia, vários ativos, **sequencial** |
| `get_run` | Recupera um experimento pelo `run_id` |
| `get_trades` | Trades normalizados daquele `run_id` |
| `compare_runs` | Diff de métricas entre runs |
| `walk_forward` | Janelas IS/OOS, cada uma um backtest oficial |
| `smoke_test` | Compile + tester curto (símbolo/período/modelo/data configuráveis) |

## Instalação

Windows + MetaTrader 5 + Python 3.10+.

```powershell
cd C:\Users\caioa\TradeLab-MCP
python -m pip install -e ".[dev]"
```

Cliente MCP:

```json
{
  "mcpServers": {
    "tradelab": {
      "command": "tradelab-mcp",
      "env": {
        "MT5_INSTALL": "C:\\Program Files\\MetaTrader 5",
        "TRADE_LAB_ROOT": "C:\\Users\\caioa\\TradeLab-MCP\\research"
      }
    }
  }
}
```

Variáveis: `MT5_INSTALL`, `MT5_DATA`, `MT5_TERMINAL_HASH`, `TRADE_LAB_ROOT`.

## Exemplo

```
Compile este EA e faça um backtest de PETR4 D1,
entre 2015 e 2025, usando real ticks.
```

O agente chama `run_backtest(strategy="experts/RSI2.mq5", symbol="PETR4", timeframe="D1", from_date="2015.01.01", to_date="2025.08.01", model=4)` e recebe:

```json
{
  "run_id": "20260817_073412_a8f231",
  "status": "completed",
  "symbol": "PETR4",
  "period": "D1",
  "model": "real_ticks",
  "metrics": {
    "total_trades": 134,
    "net_profit": 18342.21,
    "profit_factor": 1.48
  }
}
```

`get_run("20260817_073412_a8f231")` devolve exatamente aquele experimento.

## Onde os EAs vivem no MT5

Todo EA de teste automático é publicado em:

```text
<MQL5>\Experts\TradeLab MCP\
```

Neste PC isso resolve para:

`C:\Users\caioa\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Experts\TradeLab MCP`

No Strategy Tester o expert aparece como `TradeLab MCP\RSI2`. A pasta é sempre relativa ao terminal ativo (`layout.experts_dir`), não a um hash fixo.

O fonte no git continua em `experts/`. O MCP copia fonte + `.ex5` + includes locais para a pasta do terminal.

O EA-base do laboratório (CTrade, `ArraySetAsSeries`, uma posição) ainda não foi padronizado — entra depois, com calma.

## EA de aceitação

`experts/RSI2.mq5`

- RSI(2)
- compra se RSI < 10
- sai se RSI > 70
- uma posição
- sem otimização

O teste de aceitação nº 1 é: o mesmo EA / ativo / datas / inputs / capital / model no Strategy Tester manual e via MCP devem produzir as mesmas métricas e os mesmos trades.

## Testes

```powershell
pytest
```

Testes de integração (Windows + MT5 real):

```powershell
$env:TRADE_LAB_INTEGRATION = "1"
$env:TRADE_LAB_SYMBOL = "EURUSD"
pytest tests/test_integration_mt5.py -v
```

## Prioridade

**reprodutibilidade > confiabilidade > simplicidade > velocidade > funcionalidades**

V1 é sequencial (lock `mt5.lock` na data directory). Sem backtester Python paralelo. Sem parser `.opt` como fonte oficial.
