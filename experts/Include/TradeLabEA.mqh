//+------------------------------------------------------------------+
//| TradeLabEA.mqh                                                   |
//| Mandatory execution infrastructure for TradeLab Expert Advisors. |
//+------------------------------------------------------------------+
#ifndef TRADELAB_EA_MQH
#define TRADELAB_EA_MQH

#include <Trade/Trade.mqh>

enum ENUM_TRADELAB_MODE
{
   TRADELAB_SWING = 0,
   TRADELAB_DAYTRADE = 1
};

bool TradeLabValidNumber(const double value)
{
   return (MathIsValidNumber(value) && value > 0.0 && value != EMPTY_VALUE);
}

bool TradeLabNormalizePrice(const string symbol,
                            const ENUM_ORDER_TYPE order_type,
                            const double raw_price,
                            double &normalized_price)
{
   normalized_price = 0.0;
   const double tick_size = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_SIZE);
   const int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   if(!TradeLabValidNumber(raw_price) || tick_size <= 0.0 || digits < 0)
      return false;

   const double units = raw_price / tick_size;
   // A buy SL is rounded down; a sell SL is rounded up. Rounding must never
   // make the protective stop closer to the market than the requested rule.
   const double ticks = (order_type == ORDER_TYPE_BUY)
                        ? MathFloor(units + 1e-10)
                        : MathCeil(units - 1e-10);
   normalized_price = NormalizeDouble(ticks * tick_size, digits);
   return TradeLabValidNumber(normalized_price);
}

bool TradeLabValidateStop(const string symbol,
                          const ENUM_ORDER_TYPE order_type,
                          const double entry_price,
                          const double stop_price)
{
   if(!TradeLabValidNumber(entry_price) || !TradeLabValidNumber(stop_price))
      return false;
   if(order_type != ORDER_TYPE_BUY && order_type != ORDER_TYPE_SELL)
      return false;

   const long order_mode = SymbolInfoInteger(symbol, SYMBOL_ORDER_MODE);
   if((order_mode & SYMBOL_ORDER_SL) == 0)
      return false;

   MqlTick tick;
   if(!SymbolInfoTick(symbol, tick) || tick.bid <= 0.0 || tick.ask <= 0.0)
      return false;

   const double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
   const int stops_level = (int)SymbolInfoInteger(symbol, SYMBOL_TRADE_STOPS_LEVEL);
   if(point <= 0.0 || stops_level < 0)
      return false;
   const double minimum_distance = stops_level * point;

   if(order_type == ORDER_TYPE_BUY)
   {
      if(stop_price >= entry_price || stop_price >= tick.bid)
         return false;
      if((tick.bid - stop_price) + 1e-12 < minimum_distance)
         return false;
   }
   else
   {
      if(stop_price <= entry_price || stop_price <= tick.ask)
         return false;
      if((stop_price - tick.ask) + 1e-12 < minimum_distance)
         return false;
   }
   return true;
}

bool TradeLabIndicatorValue(const int handle,
                            const int buffer_number,
                            const int bar_index,
                            double &value)
{
   value = 0.0;
   if(handle == INVALID_HANDLE || (bar_index != 0 && bar_index != 1))
      return false;
   double buffer[1];
   if(CopyBuffer(handle, buffer_number, bar_index, 1, buffer) != 1)
      return false;
   if(!TradeLabValidNumber(buffer[0]))
      return false;
   value = buffer[0];
   return true;
}

bool TradeLabBuildStopLoss(const string symbol,
                           const ENUM_ORDER_TYPE order_type,
                           const double entry_price,
                           const double original_stop,
                           const int fallback_atr20_handle,
                           double &stop_price)
{
   stop_price = 0.0;
   double raw_stop = original_stop;
   if(raw_stop <= 0.0)
   {
      double atr20_bar1 = 0.0;
      if(!TradeLabIndicatorValue(fallback_atr20_handle, 0, 1, atr20_bar1))
         return false;
      raw_stop = (order_type == ORDER_TYPE_BUY)
                 ? entry_price - 3.0 * atr20_bar1
                 : entry_price + 3.0 * atr20_bar1;
   }

   if(!TradeLabNormalizePrice(symbol, order_type, raw_stop, stop_price))
      return false;
   return TradeLabValidateStop(symbol, order_type, entry_price, stop_price);
}

bool TradeLabNormalizeRiskVolume(const string symbol,
                                 const double raw_volume,
                                 double &volume)
{
   volume = 0.0;
   const double volume_min = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
   const double volume_max = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX);
   const double volume_step = SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP);
   if(!TradeLabValidNumber(raw_volume) || volume_min <= 0.0 ||
      volume_max < volume_min || volume_step <= 0.0)
      return false;
   if(raw_volume + 1e-12 < volume_min)
      return false;

   const double step_count = MathFloor((raw_volume - volume_min) / volume_step + 1e-10);
   volume = NormalizeDouble(volume_min + step_count * volume_step, 8);
   if(volume > volume_max)
      volume = NormalizeDouble(volume_max, 8);
   return (volume >= volume_min && volume <= volume_max && volume > 0.0);
}

bool TradeLabRiskVolumeForStop(const string symbol,
                               const ENUM_ORDER_TYPE order_type,
                               const double entry_price,
                               const double stop_price,
                               const double risk_pct,
                               double &volume)
{
   volume = 0.0;
   if(risk_pct <= 0.0 || !TradeLabValidateStop(symbol, order_type, entry_price, stop_price))
      return false;

   const double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   const double risk_money = equity * risk_pct / 100.0;
   if(equity <= 0.0 || risk_money <= 0.0)
      return false;

   double profit_one_lot = 0.0;
   ResetLastError();
   if(!OrderCalcProfit(order_type, symbol, 1.0, entry_price, stop_price, profit_one_lot))
      return false;
   const double loss_per_lot = MathAbs(profit_one_lot);
   if(loss_per_lot <= 0.0 || !MathIsValidNumber(loss_per_lot))
      return false;

   return TradeLabNormalizeRiskVolume(symbol, risk_money / loss_per_lot, volume);
}

bool TradeLabRetcodeAccepted(const uint retcode)
{
   return (retcode == TRADE_RETCODE_DONE ||
           retcode == TRADE_RETCODE_DONE_PARTIAL ||
           retcode == TRADE_RETCODE_PLACED);
}

bool TradeLabOpenPosition(CTrade &trade,
                          const string symbol,
                          const ENUM_ORDER_TYPE order_type,
                          const double original_stop,
                          const int fallback_atr20_handle,
                          const double risk_pct = 2.0,
                          const double take_profit = 0.0,
                          const string comment = "TradeLab")
{
   MqlTick tick;
   if(!SymbolInfoTick(symbol, tick) || tick.ask <= 0.0 || tick.bid <= 0.0)
      return false;
   const double entry_price = (order_type == ORDER_TYPE_BUY) ? tick.ask : tick.bid;

   double stop_price = 0.0;
   if(!TradeLabBuildStopLoss(symbol, order_type, entry_price, original_stop,
                             fallback_atr20_handle, stop_price))
   {
      Print("TradeLab: entrada bloqueada; Stop Loss inválido ou indisponível.");
      return false;
   }

   double volume = 0.0;
   if(!TradeLabRiskVolumeForStop(symbol, order_type, entry_price, stop_price, risk_pct, volume))
   {
      Print("TradeLab: entrada bloqueada; sizing por risco até o SL indisponível.");
      return false;
   }

   trade.SetTypeFillingBySymbol(symbol);
   const bool request_ok = trade.PositionOpen(symbol, order_type, volume, entry_price,
                                               stop_price, take_profit, comment);
   const uint retcode = trade.ResultRetcode();
   if(!request_ok || !TradeLabRetcodeAccepted(retcode))
   {
      PrintFormat("TradeLab: falha ao abrir posição; retcode=%u (%s).",
                  retcode, trade.ResultRetcodeDescription());
      return false;
   }
   return true;
}

int TradeLabBarsSince(const string symbol,
                      const ENUM_TIMEFRAMES timeframe,
                      const datetime event_time)
{
   if(event_time <= 0)
      return -1;
   return iBarShift(symbol, timeframe, event_time, false);
}

bool TradeLabTradedThisBar(const string symbol,
                           const ENUM_TIMEFRAMES timeframe,
                           const ulong magic,
                           const bool exits_only = false)
{
   const datetime bar_open = iTime(symbol, timeframe, 0);
   if(bar_open <= 0 || !HistorySelect(bar_open, TimeCurrent()))
      return false;

   for(int index = HistoryDealsTotal() - 1; index >= 0; --index)
   {
      const ulong ticket = HistoryDealGetTicket(index);
      if(ticket == 0 || HistoryDealGetString(ticket, DEAL_SYMBOL) != symbol)
         continue;
      if((ulong)HistoryDealGetInteger(ticket, DEAL_MAGIC) != magic)
         continue;
      const datetime deal_time = (datetime)HistoryDealGetInteger(ticket, DEAL_TIME);
      if(deal_time < bar_open)
         continue;
      const long entry = HistoryDealGetInteger(ticket, DEAL_ENTRY);
      if(!exits_only || entry == DEAL_ENTRY_OUT || entry == DEAL_ENTRY_INOUT || entry == DEAL_ENTRY_OUT_BY)
         return true;
   }
   return false;
}

datetime TradeLabDayStart(const datetime value)
{
   MqlDateTime parts;
   if(!TimeToStruct(value, parts))
      return 0;
   parts.hour = 0;
   parts.min = 0;
   parts.sec = 0;
   return StructToTime(parts);
}

int TradeLabSecondsOfDay(const datetime value)
{
   MqlDateTime parts;
   if(!TimeToStruct(value, parts))
      return -1;
   return parts.hour * 3600 + parts.min * 60 + parts.sec;
}

bool TradeLabResolveSession(const string symbol,
                            const datetime now,
                            datetime &session_open,
                            datetime &session_close)
{
   session_open = 0;
   session_close = 0;
   const datetime today = TradeLabDayStart(now);
   if(today <= 0)
      return false;

   datetime next_open = 0;
   datetime next_close = 0;
   // The previous date is required for overnight sessions; the following date
   // covers calls made before the next exchange session opens.
   for(int day_offset = -1; day_offset <= 1; ++day_offset)
   {
      const datetime day_start = today + day_offset * 86400;
      MqlDateTime day_parts;
      if(!TimeToStruct(day_start, day_parts))
         continue;
      const ENUM_DAY_OF_WEEK weekday = (ENUM_DAY_OF_WEEK)day_parts.day_of_week;

      for(uint session_index = 0; session_index < 32; ++session_index)
      {
         datetime raw_from = 0;
         datetime raw_to = 0;
         if(!SymbolInfoSessionTrade(symbol, weekday, session_index, raw_from, raw_to))
            break;
         const int from_seconds = TradeLabSecondsOfDay(raw_from);
         const int to_seconds = TradeLabSecondsOfDay(raw_to);
         if(from_seconds < 0 || to_seconds < 0)
            continue;
         const datetime opened = day_start + from_seconds;
         datetime closed = day_start + to_seconds;
         if(to_seconds <= from_seconds)
            closed += 86400;

         if(now >= opened && now < closed)
         {
            session_open = opened;
            session_close = closed;
            return true;
         }
         if(opened > now && (next_open == 0 || opened < next_open))
         {
            next_open = opened;
            next_close = closed;
         }
      }
   }

   if(next_open > 0)
   {
      session_open = next_open;
      session_close = next_close;
      return true;
   }
   return false;
}

bool TradeLabHasPosition(const string symbol, const ulong magic)
{
   for(int index = PositionsTotal() - 1; index >= 0; --index)
   {
      const ulong ticket = PositionGetTicket(index);
      if(ticket == 0)
         continue;
      if(PositionGetString(POSITION_SYMBOL) == symbol &&
         (ulong)PositionGetInteger(POSITION_MAGIC) == magic)
         return true;
   }
   return false;
}

bool TradeLabForceClose(CTrade &trade, const string symbol, const ulong magic)
{
   bool all_closed = true;
   for(int index = PositionsTotal() - 1; index >= 0; --index)
   {
      const ulong ticket = PositionGetTicket(index);
      if(ticket == 0)
         continue;
      if(PositionGetString(POSITION_SYMBOL) != symbol ||
         (ulong)PositionGetInteger(POSITION_MAGIC) != magic)
         continue;

      const bool request_ok = trade.PositionClose(ticket);
      const uint retcode = trade.ResultRetcode();
      const bool server_ok = request_ok && TradeLabRetcodeAccepted(retcode);
      const bool still_open = PositionSelectByTicket(ticket);
      if(!server_ok || still_open)
      {
         all_closed = false;
         PrintFormat("TradeLab DAYTRADE: posição %I64u ainda aberta; retcode=%u (%s).",
                     ticket, retcode, trade.ResultRetcodeDescription());
      }
   }
   return all_closed && !TradeLabHasPosition(symbol, magic);
}

bool TradeLabDayTradeGuard(CTrade &trade,
                           const string symbol,
                           const ulong magic,
                           const ENUM_TRADELAB_MODE mode,
                           const int cutoff_minutes,
                           bool &can_enter)
{
   can_enter = true;
   if(mode != TRADELAB_DAYTRADE)
      return true;

   datetime session_open = 0;
   datetime session_close = 0;
   const datetime now = TimeCurrent();
   if(cutoff_minutes < 0 || !TradeLabResolveSession(symbol, now, session_open, session_close))
   {
      // Fail closed: no new entry and no overnight exposure when the official
      // symbol session cannot be resolved. Repeated OnTick/OnTimer calls retry.
      can_enter = false;
      return TradeLabForceClose(trade, symbol, magic);
   }

   const datetime cutoff = session_close - cutoff_minutes * 60;
   if(now < cutoff)
      return true;

   can_enter = false;
   return TradeLabForceClose(trade, symbol, magic);
}

#endif // TRADELAB_EA_MQH
