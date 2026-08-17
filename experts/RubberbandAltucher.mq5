//+------------------------------------------------------------------+
//| RubberbandAltucher.mq5                                           |
//| James Altucher Rubber Band / %b Mean Reversion Strategy          |
//| Core Idea: Buy when price is stretched below lower Bollinger Band|
//| Exit on mean reversion (middle/upper band), max bars, or ATR SL. |
//+------------------------------------------------------------------+
#property copyright "TradeLab-MCP"
#property link      "https://github.com/CaioAllgayer/TradeLab-MCP"
#property version   "1.00"
#property strict

#include <Trade/Trade.mqh>
#include "Include/ResearchExport.mqh"

enum ENUM_EXIT_MODE
{
   EXIT_MIDDLE_BAND = 0, // Exit on Middle Band (SMA)
   EXIT_UPPER_BAND  = 1, // Exit on Upper Band
   EXIT_PCT_B_TARGET= 2  // Exit when %b reaches Exit Threshold
};

input group "--- Bollinger Bands & Entry ---"
input int             InpBBPeriod       = 20;         // BB Period (e.g., 10 or 20)
input double          InpBBDev          = 2.0;        // BB Standard Deviation
input double          InpPctBEntry      = 0.0;        // %b Entry Trigger (0.0 = at/below Lower Band, -0.1 = 10% below)

input group "--- Trend Filter ---"
input bool            InpUseTrendFilter = true;       // Use Trend Filter
input int             InpTrendPeriod    = 200;        // Trend SMA Period (e.g., 200 or 50)

input group "--- Exit Rules ---"
input int             InpExitMode       = 0;          // Exit Mode: 0=Middle Band(SMA), 1=Upper Band, 2=Target %b
input double          InpExitPctB       = 0.5;        // Target %b if InpExitMode=2 (0.5 = middle, 1.0 = upper)
input int             InpMaxBars        = 5;          // Max Holding Bars (Time Stop, 0 = disabled)

input group "--- Risk & Position Sizing ---"
input int             InpAtrPeriod      = 14;         // ATR Period
input double          InpAtrMult        = 3.0;        // SL = X * ATR (0 = without ATR SL)
input double          InpRiskPct        = 1.5;        // Risk % of Equity
input double          InpLots           = 0.0;        // Fixed Lots (>0 fixed, 0 = dynamic by risk)
input ulong           InpMagic          = 20260818;
input string          InpResearchRunId  = "";

CTrade trade;
int    g_bb = INVALID_HANDLE;
int    g_trend_ma = INVALID_HANDLE;
int    g_atr = INVALID_HANDLE;
datetime g_last_bar_time = 0;

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

bool HasOurPosition(ulong &ticket_out, datetime &open_time_out)
{
   for(int i = PositionsTotal() - 1; i >= 0; --i)
   {
      const ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if(PositionGetString(POSITION_SYMBOL) == _Symbol &&
         (ulong)PositionGetInteger(POSITION_MAGIC) == InpMagic)
      {
         ticket_out = ticket;
         open_time_out = (datetime)PositionGetInteger(POSITION_TIME);
         return true;
      }
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

   const double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   const double risk_money = equity * (InpRiskPct / 100.0);
   if(risk_money <= 0.0)
      return 0.0;

   const double tick_size = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   const double tick_value = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);

   if(stop_distance > 0.0 && tick_size > 0.0 && tick_value > 0.0)
   {
      const double loss_per_lot = (stop_distance / tick_size) * tick_value;
      if(loss_per_lot > 0.0)
         return NormalizeVolume(risk_money / loss_per_lot);
   }

   // Fallback if no SL defined: size by % capital (e.g., invest 50% equity)
   const double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   if(ask > 0.0 && tick_size > 0.0 && tick_value > 0.0)
   {
      double approx_lots = (equity * 0.5) / (ask * (tick_value / tick_size));
      return NormalizeVolume(approx_lots);
   }

   return NormalizeVolume(100.0);
}

int OnInit()
{
   trade.SetExpertMagicNumber((int)InpMagic);
   trade.SetDeviationInPoints(20);

   g_bb = iBands(_Symbol, PERIOD_CURRENT, InpBBPeriod, 0, InpBBDev, PRICE_CLOSE);
   if(g_bb == INVALID_HANDLE)
   {
      Print("Failed to create Bollinger Bands handle.");
      return INIT_FAILED;
   }

   if(InpUseTrendFilter)
   {
      g_trend_ma = iMA(_Symbol, PERIOD_CURRENT, InpTrendPeriod, 0, MODE_SMA, PRICE_CLOSE);
      if(g_trend_ma == INVALID_HANDLE)
      {
         Print("Failed to create Trend SMA handle.");
         return INIT_FAILED;
      }
   }

   if(InpAtrMult > 0.0)
   {
      g_atr = iATR(_Symbol, PERIOD_CURRENT, InpAtrPeriod);
      if(g_atr == INVALID_HANDLE)
      {
         Print("Failed to create ATR handle.");
         return INIT_FAILED;
      }
   }

   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   if(g_bb != INVALID_HANDLE)
      IndicatorRelease(g_bb);
   if(g_trend_ma != INVALID_HANDLE)
      IndicatorRelease(g_trend_ma);
   if(g_atr != INVALID_HANDLE)
      IndicatorRelease(g_atr);
   ResearchExportDeals(InpResearchRunId);
}

void OnTick()
{
   const datetime current_bar_time = iTime(_Symbol, PERIOD_CURRENT, 0);
   if(current_bar_time == 0)
      return;

   // Check once per bar opening for bar-based setups
   const bool is_new_bar = (current_bar_time != g_last_bar_time);
   if(is_new_bar)
      g_last_bar_time = current_bar_time;

   // Buffer 0: Middle, Buffer 1: Upper, Buffer 2: Lower
   double bb_mid[], bb_up[], bb_low[], close_arr[];
   ArraySetAsSeries(bb_mid, true);
   ArraySetAsSeries(bb_up, true);
   ArraySetAsSeries(bb_low, true);
   ArraySetAsSeries(close_arr, true);

   if(CopyBuffer(g_bb, 0, 0, 3, bb_mid) < 3 ||
      CopyBuffer(g_bb, 1, 0, 3, bb_up) < 3 ||
      CopyBuffer(g_bb, 2, 0, 3, bb_low) < 3 ||
      CopyClose(_Symbol, PERIOD_CURRENT, 0, 3, close_arr) < 3)
      return;

   const double c1 = close_arr[1];
   const double mid1 = bb_mid[1];
   const double up1 = bb_up[1];
   const double low1 = bb_low[1];

   const double band_width = up1 - low1;
   if(band_width <= 0.0)
      return;

   const double pct_b = (c1 - low1) / band_width;

   ulong pos_ticket = 0;
   datetime pos_open_time = 0;
   const bool in_position = HasOurPosition(pos_ticket, pos_open_time);

   if(in_position)
   {
      bool should_close = false;

      // 1. Time stop (Max bars)
      if(InpMaxBars > 0 && pos_open_time > 0)
      {
         if(iBarShift(_Symbol, PERIOD_CURRENT, pos_open_time, true) >= InpMaxBars)
            should_close = true;
      }

      // 2. Target / Band Reversion exit
      if(!should_close)
      {
         switch(InpExitMode)
         {
            case 0: // Middle Band (SMA)
               if(c1 >= mid1 || pct_b >= 0.5)
                  should_close = true;
               break;
            case 1: // Upper Band
               if(c1 >= up1 || pct_b >= 1.0)
                  should_close = true;
               break;
            case 2: // Target %b
               if(pct_b >= InpExitPctB)
                  should_close = true;
               break;
         }
      }

      if(should_close)
      {
         trade.PositionClose(_Symbol);
      }
      return;
   }

   // We only enter on the opening of a new bar following the signal
   if(!is_new_bar)
      return;

   if(SoldThisBar())
      return;

   // Entry Condition: %b at or below threshold (Rubberband stretched)
   if(pct_b > InpPctBEntry)
      return;

   // Trend Filter: Close > SMA(TrendPeriod)
   if(InpUseTrendFilter && g_trend_ma != INVALID_HANDLE)
   {
      double ma_val[];
      ArraySetAsSeries(ma_val, true);
      if(CopyBuffer(g_trend_ma, 0, 0, 3, ma_val) < 3)
         return;
      if(c1 < ma_val[1])
         return; // Filter out if below trend MA
   }

   const double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   const double sl = StopLossBuy(ask, AtrValue());
   const double stop_dist = (sl > 0.0 ? ask - sl : 0.0);
   const double lots = LotsForStop(stop_dist);

   if(lots <= 0.0)
      return;

   trade.Buy(lots, _Symbol, ask, sl, 0.0, "Altucher Rubberband");
}
