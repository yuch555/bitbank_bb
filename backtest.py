import requests
import pandas as pd
import datetime
import matplotlib.pyplot as plt
import ta

def fetch_bitbank_ohlcv(pair='btc_jpy', candle_type='30min', days=90):
    klines = []
    for i in range(days):
        day = (datetime.datetime.utcnow() - datetime.timedelta(days=i)).strftime('%Y%m%d')
        url = f'https://public.bitbank.cc/{pair}/candlestick/{candle_type}/{day}'
        res = requests.get(url)
        data = res.json()
        if data['success'] != 1:
            print(f"Failed to fetch data for {day}")
            continue
        for item in data['data']['candlestick'][0]['ohlcv']:
            o, h, l, c, v, ts = item
            klines.append([
                float(o), float(h), float(l), float(c), float(v), int(ts)//1000
            ])
    df = pd.DataFrame(klines, columns=['open', 'high', 'low', 'close', 'volume', 'start_at'])
    df = df.sort_values('start_at').reset_index(drop=True)
    return df

# データ取得（30分足、直近30日分）
ohlcv_df = fetch_bitbank_ohlcv(candle_type='30min', days=90)

# ボリンジャーバンド計算（30分足に最適化、window=20はそのまま）
window = 20
ohlcv_df['ma'] = ohlcv_df['close'].rolling(window).mean()
ohlcv_df['std'] = ohlcv_df['close'].rolling(window).std()
ohlcv_df['bb_high'] = ohlcv_df['ma'] + 2 * ohlcv_df['std']
ohlcv_df['bb_low'] = ohlcv_df['ma'] - 2 * ohlcv_df['std']

# ADX計算（window=14が一般的）
ohlcv_df['adx'] = ta.trend.ADXIndicator(
    high=ohlcv_df['high'],
    low=ohlcv_df['low'],
    close=ohlcv_df['close'],
    window=14
).adx()

# シグナル生成（ADXが閾値未満＝レンジ相場のみ逆張り）
adx_thr = 25  # 35以上はトレンド、35未満はレンジ
ohlcv_df['signal'] = 0
ohlcv_df.loc[
    (ohlcv_df['close'] < ohlcv_df['bb_low']) & (ohlcv_df['adx'] < adx_thr),
    'signal'
] = 1   # 買い
ohlcv_df.loc[
    (ohlcv_df['close'] > ohlcv_df['bb_high']) & (ohlcv_df['adx'] < adx_thr),
    'signal'
] = -1  # 売り

# バックテスト
def backtest_bb(predicted_df, initial_jpy=1000000, fee_rate=0.0012):
    position_price = 0.0
    has_long = False
    lot = 0.0
    pl_series = []
    jpy_amount = initial_jpy
    trade_records = []

    for i, row in predicted_df.iterrows():
        close = row['close']
        signal = row['signal']
        ts = row['start_at']

        if position_price == 0.0:
            if signal == 1:
                has_long = True
                position_price = close
                lot = jpy_amount / close
                entry_fee = close * lot * fee_rate
                jpy_amount -= entry_fee
                trade_records.append({"side": "BUY", "time": ts, "price": close, "fee": entry_fee})
        else:
            if signal == -1 and has_long:
                exit_fee = close * lot * fee_rate
                pl = (close - position_price) * lot - (entry_fee + exit_fee)
                jpy_amount += (close - position_price) * lot - exit_fee
                trade_records.append({"side": "SELL", "time": ts, "price": close, "pl": pl, "fee": exit_fee})
                has_long = False
                position_price = 0.0
        pl_series.append([ts, jpy_amount])

    # 損益チャート
    pl_df = pd.DataFrame(pl_series, columns=['ts', 'jpy_amount'])
    plt.figure(figsize=(12, 6))
    plt.plot(pl_df['ts'], pl_df['jpy_amount'], label='BB逆張り戦略')
    plt.xlabel('Time')
    plt.ylabel('Asset (JPY)')
    plt.title('BB逆張り戦略 バックテスト（30分足）')
    plt.grid()
    plt.legend()
    plt.tight_layout()
    plt.show()

    print(f"取引回数: {len([r for r in trade_records if r['side']=='BUY'])}")
    print(f"最終損益: {jpy_amount - initial_jpy:.2f} 円")
    print(f"最終残高: {jpy_amount:.2f} 円")
    return pl_df

print("\n【ボリンジャーバンド逆張り戦略】")
pl_df = backtest_bb(ohlcv_df)