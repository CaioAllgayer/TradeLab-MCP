# EAs do TradeLab

Fonte versionada dos experts. O MCP publica cópias no terminal:

```text
MQL5\Experts\TradeLab MCP\
```

Não edite só a cópia do MT5 se a mudança precisa entrar no git.

## Catálogo

- `registry.json` — dados estruturados e assinaturas lógicas
- `REGISTRY.md` — consulta humana resumida
- `registry_overrides.json` — metadados curados dos EAs legados

## Infraestrutura padrão

- `Include/TradeLabEA.mqh` — stop, sizing, barras e DAYTRADE compartilhados
- `templates/TradeLabEA.template.mq5` — ponto de partida para novos EAs

`RSI2.mq5` e `RubberbandAltucher.mq5` estão catalogados como legados. Ambos permanecem executáveis,
mas devem ser migrados e revalidados individualmente antes de receber status `standard`.
