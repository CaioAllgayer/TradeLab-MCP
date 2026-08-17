//+------------------------------------------------------------------+
//| RSI2.mq5                                                         |
//| Deterministic acceptance EA for TradeLab-MCP                     |
//| Buy when RSI(2) < 10; exit when RSI(2) > 70; one position.       |
//+------------------------------------------------------------------+
#property copyright "TradeLab-MCP"
#property link      "https://github.com/CaioAllgayer/TradeLab-MCP"
#property version   "1.00"
#property strict

#include <Trade/Trade.mqh>
#include "Include/ResearchExport.mqh"

input int    InpRSIPeriod      = 2;
input double InpRSIBuy         = 10.0;
input double InpRSIExit        = 70.0;
input double InpLots           = 0.0;        // 0 = SYMBOL_VOLUME_MIN
input ulong  InpMagic          = 20260817;
input string InpResearchRunId  = "";

CTrade trade;
int    g_rsi = INVALID_HANDLE;

double Lots()
{
   if(InpLots > 0.0)
      return InpLots;
   const double vmin = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   return (vmin > 0.0 ? vmin : 1.0);
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

int OnInit()
{
   trade.SetExpertMagicNumber((int)InpMagic);
   trade.SetDeviationInPoints(20);
   g_rsi = iRSI(_Symbol, PERIOD_CURRENT, InpRSIPeriod, PRICE_CLOSE);
   if(g_rsi == INVALID_HANDLE)
      return INIT_FAILED;
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   if(g_rsi != INVALID_HANDLE)
      IndicatorRelease(g_rsi);
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
      if(rsi[0] > InpRSIExit)
         trade.PositionClose(_Symbol);
      return;
   }

   if(rsi[0] < InpRSIBuy)
      trade.Buy(Lots(), _Symbol);
}
