//+------------------------------------------------------------------+
//| RSI2.mq5                                                         |
//| Buy RSI < InpRSIBuy. Exit: RSI, ATR stop, or max bars.           |
//| Size = InpRiskPct of equity given the ATR stop.                  |
//| No new buy on a bar that already sold. Same-bar exit is allowed. |
//+------------------------------------------------------------------+
#property copyright "TradeLab-MCP"
#property link      "https://github.com/CaioAllgayer/TradeLab-MCP"
#property version   "1.20"
#property strict

#include <Trade/Trade.mqh>
#include "Include/ResearchExport.mqh"

input int    InpRSIPeriod      = 2;
input double InpRSIBuy         = 10.0;
input double InpRSIExit        = 70.0;
input int    InpAtrPeriod      = 20;
input double InpAtrMult        = 3.0;        // SL = X * ATR; 0 = sem stop (não calcula risco)
input int    InpMaxBars        = 9;          // sai após X barras; 0 = desliga
input double InpRiskPct        = 1.0;        // % do equity em risco no stop
input double InpLots           = 0.0;        // >0 fixo; 0 = dimensiona pelo risco
input ulong  InpMagic          = 20260817;
input string InpResearchRunId  = "";

CTrade trade;
int    g_rsi = INVALID_HANDLE;
int    g_atr = INVALID_HANDLE;

double NormalizePrice(const double price)
{
   const double tick = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   const int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   if(tick <= 0.0)
      return NormalizeDouble(price, digits);
   return NormalizeDouble(MathRound(price / tick) * tick, digits);
}

double NormalizeVolume(const double volume)
{
   const double vmin = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   const double vmax = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   const double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   if(step <= 0.0 || vmin <= 0.0)
      return 0.0;
   double lots = MathFloor(volume / step + 1e-8) * step;
   lots = NormalizeDouble(lots, 8);
   if(lots < vmin)
      return 0.0;
   if(lots > vmax)
      lots = vmax;
   return lots;
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

bool SoldThisBar()
{
   const datetime bar0 = iTime(_Symbol, PERIOD_CURRENT, 0);
   if(bar0 <= 0)
      return false;
   if(!HistorySelect(bar0, TimeCurrent()))
      return false;
   for(int i = HistoryDealsTotal() - 1; i >= 0; --i)
   {
      const ulong ticket = HistoryDealGetTicket(i);
      if(ticket == 0)
         continue;
      if(HistoryDealGetString(ticket, DEAL_SYMBOL) != _Symbol)
         continue;
      if((ulong)HistoryDealGetInteger(ticket, DEAL_MAGIC) != InpMagic)
         continue;
      const long entry = HistoryDealGetInteger(ticket, DEAL_ENTRY);
      if(entry != DEAL_ENTRY_OUT && entry != DEAL_ENTRY_INOUT && entry != DEAL_ENTRY_OUT_BY)
         continue;
      const datetime when = (datetime)HistoryDealGetInteger(ticket, DEAL_TIME);
      if(iBarShift(_Symbol, PERIOD_CURRENT, when, true) == 0)
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
   return (iBarShift(_Symbol, PERIOD_CURRENT, opened, true) >= InpMaxBars);
}

double AtrValue()
{
   double atr[];
   ArraySetAsSeries(atr, true);
   if(CopyBuffer(g_atr, 0, 0, 3, atr) < 3)
      return 0.0;
   if(atr[1] > 0.0 && atr[1] != EMPTY_VALUE)
      return atr[1];
   if(atr[0] > 0.0 && atr[0] != EMPTY_VALUE)
      return atr[0];
   return 0.0;
}

double StopLossBuy(const double ask, const double atr)
{
   if(InpAtrMult <= 0.0 || atr <= 0.0)
      return 0.0;
   double sl = NormalizePrice(ask - InpAtrMult * atr);
   const int stops = (int)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   const double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   if(stops > 0 && point > 0.0 && (ask - sl) < stops * point)
      sl = NormalizePrice(ask - stops * point);
   if(sl >= ask)
      return 0.0;
   return sl;
}

double LotsForStop(const double stop_distance)
{
   if(InpLots > 0.0)
      return NormalizeVolume(InpLots);

   if(InpRiskPct <= 0.0 || stop_distance <= 0.0)
      return 0.0;

   const double tick_size = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   const double tick_value = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   if(tick_size <= 0.0 || tick_value <= 0.0)
      return 0.0;

   const double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   const double risk_money = equity * (InpRiskPct / 100.0);
   if(risk_money <= 0.0)
      return 0.0;

   const double loss_per_lot = (stop_distance / tick_size) * tick_value;
   if(loss_per_lot <= 0.0)
      return 0.0;

   return NormalizeVolume(risk_money / loss_per_lot);
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
   double rsi[];
   ArraySetAsSeries(rsi, true);
   if(CopyBuffer(g_rsi, 0, 0, 3, rsi) < 3)
      return;
   if(rsi[0] == EMPTY_VALUE)
      return;

   if(HasOurPosition())
   {
      if(MaxBarsReached() || rsi[0] > InpRSIExit)
         trade.PositionClose(_Symbol);
      return;
   }

   if(SoldThisBar())
      return;

   if(rsi[0] >= InpRSIBuy)
      return;

   const double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   const double sl = StopLossBuy(ask, AtrValue());
   const double stop_distance = (sl > 0.0 ? ask - sl : 0.0);
   const double lots = LotsForStop(stop_distance);
   if(lots <= 0.0)
      return;
   trade.Buy(lots, _Symbol, ask, sl, 0.0);
}
