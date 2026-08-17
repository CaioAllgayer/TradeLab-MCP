# TradeLab EA — contexto compacto para agentes

Antes de gerar/modificar EA, chame `plan_ea_creation`; ele consulta o Registry e devolve
`equivalent`, `similar` ou `new`, além de defaults e decisões abertas.

Regras invariáveis:

- Preserve o setup original. Filtro, TP, trailing, breakeven ou calendário extra = variante
  explicitamente nomeada; nunca adicione silenciosamente.
- Toda entrada nasce com SL hard. Preserve stop original; se não existir, use exatamente
  `3 x ATR(20)[1]`, fixo. Qualquer falha bloqueia a ordem.
- Default `RiskPct=2%` do Equity até o SL. Use perda de 1 lote via `OrderCalcProfit` e normalize
  `MIN/MAX/STEP`. Não existe fallback de lote/sizing.
- Sinal default `[1]` (fechado, ordem na barra seguinte). `[0]` somente explícito.
- Em MTF, registre TF de execução, TF de cada condição e `[0]/[1]`. TF maior usa `[1]` por default;
  informe ao usuário antes de implementar. Nunca assuma `[0]`.
- DAYTRADE: sessão oficial do símbolo, cutoff default 60 min, bloqueio de entrada e fechamento
  reiterado em `OnTick`/`OnTimer`, com `ResultRetcode` e confirmação de posição ausente.
- Barras: `iBarShift(..., false)`/helper; não dependa de datetime igual à abertura.

Use `experts/templates/TradeLabEA.template.mq5` e `experts/Include/TradeLabEA.mqh`. Documente tags
`@tradelab.*`, valide, compile/teste e chame `refresh_ea_registry` após qualquer mudança `.mq5`.
