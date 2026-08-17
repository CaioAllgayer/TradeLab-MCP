# RSI2 universo B3 — batch 2026-08-17

Setup congelado: RSI 2/10/70, stop 3×ATR(20), max 9 barras, close>close[50], risco 1% equity, Model=1, 100000 BRL.

| Janela | Datas |
|---|---|
| IS | 2018.01.01 – 2023.12.31 |
| OOS | 2024.01.01 – 2025.12.31 |

30/30 runs completed no Strategy Tester.

## Ranking por comportamento IS+OOS

Melhores candidatos (lucro e PF > 1 nos dois lados):

| Símbolo | IS PF | IS lucro | OOS PF | OOS lucro | Notas |
|---|---:|---:|---:|---:|---|
| EQTL3 | 2.39 | 7650 | 3.79 | 2913 | Forte nos dois |
| BBAS3 | 1.85 | 6370 | 5.02 | 5437 | Melhor OOS; PF 5 é curto (25 trades) |
| VIVT3 | 3.80 | 12681 | 1.91 | 2406 | Melhor IS; OOS ainda positivo |
| ABEV3 | 1.63 | 5282 | 3.52 | 1859 | OOS curto (19 trades) |
| RENT3 | 1.87 | 7853 | 1.63 | 1534 | Estável |
| ITUB4 | 1.45 | 3298 | 1.74 | 2091 | Estável, mais fraco no IS |

Quem só brilha de um lado (não levar como “melhor ativo”):

- PETR4, VALE3, PRIO3, WEGE3, GGBR4, CSAN3 — IS ok, **OOS negativo**
- BBDC4, SUZB3 — IS ruim, OOS bom (instável)
- B3SA3 — OOS ~zero

Experimento: `exp_20260817_131116_b0ce93`
