import os
import json
import python_bitbankcc
import requests

API_KEY = os.getenv("BITBANK_API_KEY")
API_SECRET = os.getenv("BITBANK_API_SECRET")

# 認証方式の指定（ACCESS-NONCE方式が一般的）
config = {
    'auth_method': 'nonce',
}
priv = python_bitbankcc.private(API_KEY, API_SECRET, config=config)

# 資産情報を取得
value = priv.get_asset()
print(json.dumps(value, indent=2, ensure_ascii=False))

# 現在のBTC/JPY価格を取得
ticker = requests.get("https://public.bitbank.cc/btc_jpy/ticker").json()
price = float(ticker["data"]["last"])

# 2000円分のBTC数量を計算（小数点8桁に丸める）
btc_amount = round(2000 / price, 8)

# 成行注文でBTC購入
order_res = priv.order(
    "btc_jpy",    # ペア
    None,         # 価格（成行の場合はNone）
    str(btc_amount),   # 注文枚数（文字列で渡す）
    "buy",        # サイド
    "market"      # 注文タイプ
)
print(json.dumps(order_res, indent=2, ensure_ascii=False))