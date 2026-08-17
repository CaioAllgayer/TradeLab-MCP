# EAs do TradeLab

Fonte versionada dos experts. O MCP publica cópias no terminal:

```text
MQL5\Experts\TradeLab MCP\
```

Não edite só a cópia do MT5 se a mudança precisa entrar no git.

## Agora

- `RSI2.mq5` — RSI 2, uma posição, stop `3*ATR(20)`, sai em 9 barras

## Depois

EA-base para os demais: simples, `CTrade`, `ArraySetAsSeries`, sem motor paralelo de execução.
