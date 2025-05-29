import os
import json
import requests
import pandas as pd
import datetime
import matplotlib.pyplot as plt
import ta
import calendar

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

def load_or_fetch_ohlcv_json(pair='btc_jpy', candle_type='30min', days=365, cache_file='ohlcv_cache.json'):
    # キャッシュファイルがあれば読み込み
    if os.path.exists(cache_file):
        with open(cache_file, 'r') as f:
            klines = json.load(f)
        df = pd.DataFrame(klines)
        print(f"Loaded OHLCV from {cache_file}")
        return df

    # なければAPIから取得して保存
    df = fetch_bitbank_ohlcv(pair=pair, candle_type=candle_type, days=days)
    df.to_json(cache_file, orient='records')
    print(f"Fetched and saved OHLCV to {cache_file}")
    return df

# 1年分の30分足データをキャッシュ利用で取得
ohlcv_df = load_or_fetch_ohlcv_json(pair='btc_jpy', candle_type='30min', days=365, cache_file='ohlcv_btc_30min_1y.json')

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

# RSI計算（window=14が一般的）
ohlcv_df['rsi'] = ta.momentum.RSIIndicator(ohlcv_df['close'], window=14).rsi()

# シグナル生成（ADXが閾値未満＝レンジ相場のみ逆張り、RSIも条件に追加）
adx_thr = 25  # 35以上はトレンド、35未満はレンジ
rsi_buy = 18  # RSIが18以下で買い
rsi_sell = 70  # RSIが70以上で売り

ohlcv_df['signal'] = 0

# 買い：BB下抜け＆ADXレンジ＆RSI18以下
ohlcv_df.loc[
    (ohlcv_df['close'] < ohlcv_df['bb_low']) &
    (ohlcv_df['adx'] < adx_thr) |
    (ohlcv_df['rsi'] <= rsi_buy),
    'signal'
] = 1

# 売り：BB上抜け＆ADXレンジ＆RSI70以上
ohlcv_df.loc[
    (ohlcv_df['close'] > ohlcv_df['bb_high']) &
    (ohlcv_df['adx'] < adx_thr) |
    (ohlcv_df['rsi'] >= rsi_sell),
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

# 月ごとに区切る
ohlcv_df['datetime'] = pd.to_datetime(ohlcv_df['start_at'], unit='s')
ohlcv_df['year_month'] = ohlcv_df['datetime'].dt.to_period('M')

results = []
for ym, group in ohlcv_df.groupby('year_month'):
    print(f"\n=== {ym} のバックテスト結果 ===")
    pl_df = backtest_bb(group)
    results.append((str(ym), pl_df['jpy_amount'].iloc[-1]))

# 月ごとの最終残高を表示
print("\n【月ごとの最終残高】")
for ym, last_jpy in results:
    print(f"{ym}: {last_jpy:.2f} 円")

# 年ごとの最終残高を集計・表示
ohlcv_df['year'] = ohlcv_df['datetime'].dt.year
year_results = []
for year, group in ohlcv_df.groupby('year'):
    pl_df = backtest_bb(group)
    year_results.append((str(year), pl_df['jpy_amount'].iloc[-1]))

print("\n【年ごとの最終残高】")
for year, last_jpy in year_results:
    print(f"{year}: {last_jpy:.2f} 円")