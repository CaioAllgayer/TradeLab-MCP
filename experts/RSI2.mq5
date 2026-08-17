//+------------------------------------------------------------------+
//| RSI2.mq5                                                         |
//| Buy when RSI < InpRSIBuy; exit RSI > InpRSIExit, ATR stop,       |
//| or max bars. One position. CTrade + ArraySetAsSeries.            |
//+------------------------------------------------------------------+
#property copyright "TradeLab-MCP"
#property link      "https://github.com/CaioAllgayer/TradeLab-MCP"
#property version   "1.10"
#property strict

#include <Trade/Trade.mqh>
#include "Include/ResearchExport.mqh"

input int    InpRSIPeriod      = 2;
input double InpRSIBuy         = 10.0;
input double InpRSIExit        = 70.0;
input int    InpAtrPeriod      = 20;
input double InpAtrMult        = 3.0;        // SL = X * ATR(20); 0 = sem stop
input int    InpMaxBars        = 9;          // sai após X barras; 0 = desliga
input double InpLots           = 0.0;        // 0 = SYMBOL_VOLUME_MIN
input ulong  InpMagic          = 20260817;
input string InpResearchRunId  = "";

CTrade trade;
int    g_rsi = INVALID_HANDLE;
int    g_atr = INVALID_HANDLE;

double Lots()
{
   if(InpLots > 0.0)
      return InpLots;
   const double vmin = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   return (vmin > 0.0 ? vmin : 1.0);
}

double NormalizePrice(const double price)
{
   const double tick = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tick <= 0.0)
      return NormalizeDouble(price, (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS));
   return NormalizeDouble(MathRound(price / tick) * tick,
                          (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS));
}

bool HasOurPosition()
{
   for(int i = PositionsTotal() - 1; i >= 0; --i)
   {
      const ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if(PositionGetString(POSITION_SYMBOL) == _Symbol &&
         (ulong)PositionGetInteger(POSITION_MAGIC) == InpMagic)
         return true;
   }
   return false;
}

bool MaxBarsReached()
{
   if(InpMaxBars <= 0)
      return false;
   const datetime opened = (datetime)PositionGetInteger(POSITION_TIME);
   if(opened <= 0)
      return false;
   const int shift = iBarShift(_Symbol, PERIOD_CURRENT, opened, true);
   return (shift >= InpMaxBars);
}

double StopLossBuy(const double ask, const double atr)
{
   if(InpAtrMult <= 0.0 || atr <= 0.0)
      return 0.0;
   double sl = ask - InpAtrMult * atr;
   sl = NormalizePrice(sl);
   const int stops = (int)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   const double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   if(stops > 0 && point > 0.0 && (ask - sl) < stops * point)
      sl = NormalizePrice(ask - stops * point);
   if(sl >= ask)
      return 0.0;
   return sl;
}

int OnInit()
{
   trade.SetExpertMagicNumber((int)InpMagic);
   trade.SetDeviationInPoints(20);
   g_rsi = iRSI(_Symbol, PERIOD_CURRENT, InpRSIPeriod, PRICE_CLOSE);
   g_atr = iATR(_Symbol, PERIOD_CURRENT, InpAtrPeriod);
   if(g_rsi == INVALID_HANDLE || g_atr == INVALID_HANDLE)
      return INIT_FAILED;
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   if(g_rsi != INVALID_HANDLE)
      IndicatorRelease(g_rsi);
   if(g_atr != INVALID_HANDLE)
      IndicatorRelease(g_atr);
   ResearchExportDeals(InpResearchRunId);
}

void OnTick()
{
   double rsi[], atr[];
   ArraySetAsSeries(rsi, true);
   ArraySetAsSeries(atr, true);
   if(CopyBuffer(g_rsi, 0, 0, 3, rsi) < 3)
      return;
   if(CopyBuffer(g_atr, 0, 0, 3, atr) < 3)
      return;
   if(rsi[0] == EMPTY_VALUE)
      return;

   if(HasOurPosition())
   {
      if(MaxBarsReached() || rsi[0] > InpRSIExit)
         trade.PositionClose(_Symbol);
      return;
   }

   if(rsi[0] < InpRSIBuy)
   {
      const double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      const double atr_val = (atr[1] > 0.0 && atr[1] != EMPTY_VALUE) ? atr[1] : atr[0];
      const double sl = StopLossBuy(ask, atr_val);
      trade.Buy(Lots(), _Symbol, ask, sl, 0.0);
   }
}
