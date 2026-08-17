# TradeLab EA Standard

Este padrão separa a **infraestrutura obrigatória** do TradeLab, o **setup original** e qualquer
**variante experimental**. EAs legados continuam executáveis, mas aparecem no Registry como
`legacy` até serem migrados e validados individualmente.

## Regras obrigatórias

1. **Stop hard na entrada.** A regra original do setup tem precedência. Sem regra original, usar
   `3 x ATR(20)[1]`, calculado na entrada e fixo. Se preço, ATR, normalização ou distância mínima
   forem inválidos, não abrir. O fallback nunca vira trailing.
2. **Sizing até o SL.** Default `RiskPct=2%` do Equity. Calcular o prejuízo de 1 lote entre entrada
   e SL com `OrderCalcProfit`, dividir o risco monetário por esse prejuízo e normalizar por
   `SYMBOL_VOLUME_MIN/MAX/STEP`. Sem lote fixo ou sizing alternativo quando o cálculo falhar.
3. **Sinais [1] por default.** `[1]` é barra fechada; `[0]` é intrabar e somente pode ser usado por
   decisão explícita. Cada condição documenta timeframe e índice.
4. **Multi-timeframe.** Timeframe de execução e de cada sinal/filtro são independentes. Para TF
   maior, `[1]` é default e fica congelado até a próxima barra; `[0]` muda intrabar e deve ser
   informado antes da implementação.
5. **DAYTRADE.** Bloquear entradas e encerrar posições, por default, 60 minutos antes do fim da
   sessão oficial do símbolo (`SymbolInfoSessionTrade`). A guarda deve rodar em `OnTick` e
   `OnTimer`, conferir `ResultRetcode()` e continuar tentando enquanto a posição existir. Se a
   sessão não puder ser determinada, falhar fechado: bloquear entradas e reduzir exposição.
6. **Barras robustas.** Usar `iBarShift(..., false)` ou o horário/index da barra armazenado. Um
   negócio ocorrido segundos após a abertura não coincide exatamente com `iTime()`.

O include `experts/Include/TradeLabEA.mqh` implementa stop, sizing, normalização, leitura `[0]/[1]`,
sessões, forced exit, `BarsSince` e `TradedThisBar`. Novos EAs partem de
`experts/templates/TradeLabEA.template.mq5` e usam `TradeLabOpenPosition`; entradas diretas por
`CTrade::Buy/Sell/PositionOpen` não fazem parte do caminho padronizado.

## Setup original e variantes

Implemente primeiro apenas entrada e saída pertencentes ao setup solicitado. Não adicione SMA,
EMA, RSI, volatilidade, volume, regime, calendário, TP, trailing ou breakeven silenciosamente.
Qualquer alteração é variante e recebe nome explícito, por exemplo:

- `RubberBand.mq5` (setup original)
- `RubberBand_SMA_Filter.mq5` (variante)
- `RSI2_D1_Intrabar_M5.mq5` (variante MTF/intrabar)

Resultados de variantes nunca são agregados como se fossem o mesmo setup.

## Registry

`experts/registry.json` é o catálogo estruturado e `experts/REGISTRY.md` é o resumo humano. Ambos
são gerados por `refresh_ea_registry`; correções semânticas dos EAs legados ficam em
`registry_overrides.json`. O hash SHA-256, mtime e conjunto de arquivos detectam catálogo obsoleto.
A assinatura lógica é determinística (setup, entrada, saída, indicadores, filtros, direção,
timeframes e barras), sem embeddings.

Antes de criar um EA, chamar `plan_ea_creation`. O fluxo obrigatório é:

1. identificar o setup e consultar o Registry;
2. informar `equivalent`, `similar` ou `new`;
3. resumir o setup original e reaproveitar EA equivalente/base quando possível;
4. resolver somente decisões realmente abertas: TF de execução, `[0]/[1]`, TF maior e seu índice,
   DAYTRADE/SWING, saída e time stop;
5. informar defaults aplicados; gerar, validar, compilar/testar e atualizar o Registry.

Se houver equivalente, não duplicar. Se houver semelhante, derivar uma variante claramente
nomeada. Somente o cenário `new` começa do template.

## Migração e validação

`validate_ea_standard` é conservador: identifica includes ausentes, entradas que contornam o
wrapper, `iBarShift(..., true)` e fallbacks inseguros. Ele não prova a semântica do setup; revisão,
compilação no MetaEditor e Strategy Tester continuam obrigatórios. Migre EAs legados um a um para
não alterar silenciosamente séries históricas ou parâmetros de pesquisa.

Referência MQL5 usada no desenho: `OrderCalcProfit` devolve P&L na moeda da conta;
`SymbolInfoSessionTrade` devolve sessões por símbolo/dia; `iBarShift(..., false)` procura a barra
anterior mais próxima; e o sucesso booleano de `PositionClose` ainda exige conferir o retcode.
