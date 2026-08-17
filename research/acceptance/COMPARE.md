# Aceite 1 — manual Strategy Tester × MCP

Baseline manual: `ReportTester-46522742.html` (Desktop)  
MCP run: `20260817_085141_dd59db`

## Setup (congelado)

| Campo | Valor |
|---|---|
| Expert | TradeLab MCP\RSI2 |
| Símbolo | BBAS3 |
| Período | D1 |
| Datas | 2024.01.01 – 2024.08.16 |
| Model | 1 (1 min OHLC) |
| Depósito | 10000 |
| Moeda | BRL |
| Alavancagem | 1:100 |
| InpLots | 100 |
| InpRSIPeriod / Buy / Exit | 2 / 10 / 70 |
| InpMagic | 20260817 |

## Métricas oficiais do Tester

| Métrica | Manual | MCP |
|---|---:|---:|
| Total Trades | 13 | 13 |
| Net Profit | 455.00 | 455.00 |
| Gross Profit | 527.00 | 527.00 |
| Gross Loss | -72.00 | -72.00 |
| Profit Factor | 7.32 | 7.32 |
| Expected Payoff | 35.00 | 35.00 |
| Recovery Factor | 3.55 | 3.55 |
| Sharpe | 2.15 | 2.15 |
| Balance DD | 54.00 | 54.00 |
| Equity DD | 128.00 | 128.00 |
| Initial deposit | 10000.00 | 10000.00 |

Critério do guia: **iguais**.

Os 13 fechamentos têm os mesmos preços e lucros (45, 79, 97, 71, -54, 49, 3, 25, 8, 38, 12, -18, 100).

O parser agora lê o HTML oficial (não o “último arquivo”): ignora cabeçalho `Tipo`, pega win rate 84.62 do Tester e emparelha Transações `in`/`out`.
