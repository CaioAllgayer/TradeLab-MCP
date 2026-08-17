// @tradelab.strategy: SETUP_ORIGINAL
// @tradelab.description: Descrever o setup sem filtros experimentais silenciosos.
// @tradelab.execution_timeframe: CURRENT
// @tradelab.signal_timeframes: CURRENT
// @tradelab.bar_indices: 1
// @tradelab.entry: DOCUMENTAR_REGRA_DE_ENTRADA
// @tradelab.exit: DOCUMENTAR_REGRA_DE_SAIDA
// @tradelab.stop: original ou fallback fixo 3 x ATR(20)[1]
// @tradelab.take_profit: false
// @tradelab.trailing: false
// @tradelab.time_stop: false
// @tradelab.position_sizing: 2% do Equity até o SL via OrderCalcProfit
// @tradelab.risk_pct_default: 2.0
// @tradelab.trade_mode: SWING
// @tradelab.filters:
// @tradelab.indicators:
// @tradelab.direction: long
// @tradelab.variant_of:

#property copyright "TradeLab-MCP"
#property link      "https://github.com/CaioAllgayer/TradeLab-MCP"
#property version   "1.00"
#property strict

#include "../Include/TradeLabEA.mqh"

input int                InpSignalBar      = 1; // 1=fechada (default), 0=intrabar explícito
input double             InpRiskPct        = 2.0;
input ENUM_TRADELAB_MODE InpTradeMode      = TRADELAB_SWING;
input int                InpDayCutoffMin   = 60;
input ulong              InpMagic          = 0; // atribuir Magic Number único antes de usar

CTrade g_trade;
int g_atr20 = INVALID_HANDLE;
datetime g_last_bar = 0;

bool EntrySignal()
{
   // Implementar o setup original. Indicadores de barra usam InpSignalBar.
   return false;
}

bool ExitSignal()
{
   // Não adicionar TP, trailing, breakeven ou filtro sem solicitação explícita.
   return false;
}

int OnInit()
{
   if(InpSignalBar != 0 && InpSignalBar != 1)
      return INIT_PARAMETERS_INCORRECT;
   if(InpRiskPct <= 0.0 || InpDayCutoffMin < 0 || InpMagic == 0)
      return INIT_PARAMETERS_INCORRECT;
   g_trade.SetExpertMagicNumber((int)InpMagic);
   g_trade.SetDeviationInPoints(20);
   g_atr20 = iATR(_Symbol, PERIOD_CURRENT, 20);
   if(g_atr20 == INVALID_HANDLE)
      return INIT_FAILED;
   EventSetTimer(5);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   if(g_atr20 != INVALID_HANDLE)
      IndicatorRelease(g_atr20);
}

void EnforceDayTrade()
{
   bool can_enter = false;
   TradeLabDayTradeGuard(g_trade, _Symbol, InpMagic, InpTradeMode, InpDayCutoffMin, can_enter);
}

void OnTimer()
{
   EnforceDayTrade();
}

void OnTick()
{
   bool can_enter = false;
   TradeLabDayTradeGuard(g_trade, _Symbol, InpMagic, InpTradeMode, InpDayCutoffMin, can_enter);

   if(TradeLabHasPosition(_Symbol, InpMagic))
   {
      if(ExitSignal())
         g_trade.PositionClose(_Symbol);
      return;
   }
   if(!can_enter || TradeLabTradedThisBar(_Symbol, PERIOD_CURRENT, InpMagic))
      return;

   const datetime bar_open = iTime(_Symbol, PERIOD_CURRENT, 0);
   const bool new_bar = (bar_open > 0 && bar_open != g_last_bar);
   if(new_bar)
      g_last_bar = bar_open;
   if(InpSignalBar == 1 && !new_bar)
      return;
   if(!EntrySignal())
      return;

   // original_stop=0 ativa obrigatoriamente 3 x ATR(20)[1]. Se o setup
   // original tiver stop, calcular a regra original e passá-la no 3º argumento.
   TradeLabOpenPosition(g_trade, _Symbol, ORDER_TYPE_BUY, 0.0, g_atr20,
                        InpRiskPct, 0.0, "SETUP_ORIGINAL");
}
