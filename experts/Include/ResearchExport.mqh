#ifndef RESEARCH_EXPORT_MQH
#define RESEARCH_EXPORT_MQH

// Write tester deals to Terminal/Common/Files/tradelab_<run_id>.csv
void ResearchExportDeals(const string run_id)
{
   if(!MQLInfoInteger(MQL_TESTER))
      return;
   if(!HistorySelect(0, TimeCurrent()))
      return;

   const string name = "tradelab_" + (run_id == "" ? "last" : run_id) + ".csv";
   int handle = FileOpen(name, FILE_WRITE | FILE_CSV | FILE_ANSI | FILE_COMMON, ',');
   if(handle == INVALID_HANDLE)
   {
      handle = FileOpen(name, FILE_WRITE | FILE_CSV | FILE_ANSI, ',');
      if(handle == INVALID_HANDLE)
         return;
   }

   FileWrite(handle,
             "deal", "position_id", "symbol", "type", "entry", "time",
             "price", "volume", "profit", "commission", "swap", "reason");

   const int total = HistoryDealsTotal();
   for(int i = 0; i < total; i++)
   {
      const ulong ticket = HistoryDealGetTicket(i);
      if(ticket == 0)
         continue;
      const long dtype = HistoryDealGetInteger(ticket, DEAL_TYPE);
      if(dtype != DEAL_TYPE_BUY && dtype != DEAL_TYPE_SELL)
         continue;

      const long entry = HistoryDealGetInteger(ticket, DEAL_ENTRY);
      const string type_s = (dtype == DEAL_TYPE_BUY ? "buy" : "sell");
      string entry_s = "in";
      if(entry == DEAL_ENTRY_OUT)
         entry_s = "out";
      else if(entry == DEAL_ENTRY_INOUT)
         entry_s = "inout";
      else if(entry == DEAL_ENTRY_OUT_BY)
         entry_s = "out_by";

      FileWrite(handle,
                (long)ticket,
                (long)HistoryDealGetInteger(ticket, DEAL_POSITION_ID),
                HistoryDealGetString(ticket, DEAL_SYMBOL),
                type_s,
                entry_s,
                TimeToString((datetime)HistoryDealGetInteger(ticket, DEAL_TIME), TIME_DATE | TIME_SECONDS),
                DoubleToString(HistoryDealGetDouble(ticket, DEAL_PRICE), 8),
                DoubleToString(HistoryDealGetDouble(ticket, DEAL_VOLUME), 8),
                DoubleToString(HistoryDealGetDouble(ticket, DEAL_PROFIT), 8),
                DoubleToString(HistoryDealGetDouble(ticket, DEAL_COMMISSION), 8),
                DoubleToString(HistoryDealGetDouble(ticket, DEAL_SWAP), 8),
                HistoryDealGetString(ticket, DEAL_COMMENT));
   }
   FileClose(handle);
}

#endif
