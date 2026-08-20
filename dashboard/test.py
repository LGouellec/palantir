import pandas as pd
from collections import deque

COLUMNS = ['symbol', 'side', 'buy_at', 'buy_filled_qty', 'buy_filled_avg_price',
           'sell_at', 'sell_filled_qty', 'sell_filled_avg_price', 'pnl']

EPS = 1e-9

df = pd.read_csv("filled_orders.csv")
df.sort_values(by=['submitted_at'], inplace=True, ascending=True)

buys = {}
sells = {}
for _, row in df.iterrows():
    lots = buys if row['side'] == 'buy' else sells
    lots.setdefault(row['symbol'], deque()).append(
        {'qty': row['filled_qty'], 'price': row['filled_avg_price'], 'at': row['filled_at']}
    )

rows = []
for symbol in sorted(set(buys) | set(sells)):
    buy_lots = buys.get(symbol, deque())
    sell_lots = sells.get(symbol, deque())

    # match by quantity, splitting a lot when the counterpart order is smaller
    # (a single buy/sell can be filled across several partial orders)
    while buy_lots and sell_lots:
        buy_lot = buy_lots[0]
        sell_lot = sell_lots[0]
        matched_qty = min(buy_lot['qty'], sell_lot['qty'])

        pnl = round(matched_qty * (sell_lot['price'] - buy_lot['price']), 2)
        rows.append([symbol, 'closed', buy_lot['at'], matched_qty, buy_lot['price'],
                     sell_lot['at'], matched_qty, sell_lot['price'], pnl])

        buy_lot['qty'] -= matched_qty
        sell_lot['qty'] -= matched_qty
        if buy_lot['qty'] <= EPS:
            buy_lots.popleft()
        if sell_lot['qty'] <= EPS:
            sell_lots.popleft()

    # leftover quantity is a still-open position, not an error
    for buy_lot in buy_lots:
        rows.append([symbol, 'buy', buy_lot['at'], buy_lot['qty'], buy_lot['price'],
                     None, None, None, None])
    for sell_lot in sell_lots:
        rows.append([symbol, 'sell', None, None, None,
                     sell_lot['at'], sell_lot['qty'], sell_lot['price'], None])

df_pnl = pd.DataFrame(rows, columns=COLUMNS)
df_pnl.to_csv("filled_orders_pnl.csv", index=False)
