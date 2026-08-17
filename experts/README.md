# EAs do TradeLab

Fonte versionada dos experts. O MCP publica cópias no terminal:

```text
MQL5\Experts\TradeLab MCP\
```

Não edite só a cópia do MT5 se a mudança precisa entrar no git.

## Agora

- `RSI2.mq5` — RSI 2 + filtro close > close[N] (N=50, 10–200), stop ATR, 9 barras, risco 1%

## Depois

EA-base para os demais: simples, `CTrade`, `ArraySetAsSeries`, sem motor paralelo de execução.
