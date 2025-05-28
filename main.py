import os
import json
import python_bitbankcc
import requests
import pandas as pd
import time
import datetime
import matplotlib.pyplot as plt
import ta
from dotenv import load_dotenv

def fetch_bitbank_ohlcv(pair='btc_jpy', candle_type='30min', days=31):
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

def make_bb_adx_signal(ohlcv_df):
    # ボリンジャーバンド
    window = 20
    ohlcv_df['ma'] = ohlcv_df['close'].rolling(window).mean()
    ohlcv_df['std'] = ohlcv_df['close'].rolling(window).std()
    ohlcv_df['bb_high'] = ohlcv_df['ma'] + 2 * ohlcv_df['std']
    ohlcv_df['bb_low'] = ohlcv_df['ma'] - 2 * ohlcv_df['std']
    # ADX
    ohlcv_df['adx'] = ta.trend.ADXIndicator(
        high=ohlcv_df['high'],
        low=ohlcv_df['low'],
        close=ohlcv_df['close'],
        window=14
    ).adx()
    # シグナル生成（ADXが閾値未満＝レンジ相場のみ逆張り）
    adx_thr = 25
    ohlcv_df['signal'] = 0
    ohlcv_df.loc[
        (ohlcv_df['close'] < ohlcv_df['bb_low']) & (ohlcv_df['adx'] < adx_thr),
        'signal'
    ] = "buy"
    ohlcv_df.loc[
        (ohlcv_df['close'] > ohlcv_df['bb_high']) & (ohlcv_df['adx'] < adx_thr),
        'signal'
    ] = "sell"
    return ohlcv_df

def get_latest_signal(ohlcv_df):
    latest = ohlcv_df.iloc[-1]
    if latest['signal'] == "buy":
        return "buy"
    elif latest['signal'] == "sell":
        return "sell"
    else:
        return "hold"

def get_btc_balance(priv):
    value = priv.get_asset()
    print("get_assetレスポンス:", value)
    assets = value.get('assets') or value.get('data', {}).get('assets')
    if not assets:
        print("APIエラーまたは認証エラーです")
        return 0.0
    for asset in assets:
        if asset['asset'] == 'btc':
            return float(asset['free_amount'])
    return 0.0

def load_settings(path):
    settings = {}
    with open(path, encoding='utf-8') as f:
        for line in f:
            if '=' in line and not line.strip().startswith('#'):
                k, v = line.strip().split('=', 1)
                settings[k.strip()] = v.strip()
    return settings

# 代わりにsetting.txtを同じディレクトリから読み込む
setting_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'setting.txt')
settings = load_settings(setting_path)

API_KEY = settings.get("BITBANK_API_KEY")
API_SECRET = settings.get("BITBANK_API_SECRET")
BTC_BUY_JPY = float(settings.get("BTC_BUY_JPY", "2000"))

def main():
    # API認証
    config = {'auth_method': 'nonce'}
    priv = python_bitbankcc.private(API_KEY, API_SECRET, config=config)

    print("API_KEY:", os.getenv("BITBANK_API_KEY"))
    print("API_SECRET:", os.getenv("BITBANK_API_SECRET"))
    print("BTC_BUY_JPY:", BTC_BUY_JPY)

    # データ取得・シグナル生成
    ohlcv_df = fetch_bitbank_ohlcv(days=31)
    ohlcv_df = make_bb_adx_signal(ohlcv_df)
    signal = get_latest_signal(ohlcv_df)
    print(f"最新シグナル: {signal}")

    # 現在価格取得
    ticker = requests.get("https://public.bitbank.cc/btc_jpy/ticker").json()
    price = float(ticker["data"]["last"])

    # 残高取得
    btc_balance = get_btc_balance(priv)
    print(f"BTC残高: {btc_balance}")

    # 売買判定＆注文
    if signal == "buy" and btc_balance < 0.0001:
        btc_amount = round(BTC_BUY_JPY / price, 8)
        order_res = priv.order(
            "btc_jpy",
            None,
            str(btc_amount),
            "buy",
            "market"
        )
        print("BTC購入注文:", json.dumps(order_res, indent=2, ensure_ascii=False))
    elif signal == "sell" and btc_balance > 0.0001:
        order_res = priv.order(
            "btc_jpy",
            None,
            str(btc_balance),
            "sell",
            "market"
        )
        print("BTC売却注文:", json.dumps(order_res, indent=2, ensure_ascii=False))
    else:
        print("売買シグナルなし or ポジション維持")

if __name__ == "__main__":
    while True:
        main()
        print("次の実行まで待機します...")
        time.sleep(60 * 30)  # 30分ごとに実行