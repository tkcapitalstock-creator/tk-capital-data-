"""
TK Capital ホームページ用データ更新スクリプト
- ticker.json : ドル円・ユーロ円・ポンド円（現在値＋変動幅＋前日比%）・
               米10年債利回り（前日比bp付き）・
               VIX指数・S&P500・ダウ平均・ラッセル2000・SOX指数・
               ダウ先物・S&P500先物・ラッセル2000先物・
               金・銀・銅・WTI原油（現在値＋変動幅＋前日比%）
- headlines.json : Googleニュース「主要記事」フィード（ローカルニュースを含まない全般ニュース）
日経平均・TOPIXは公式の無料データが無いため、このスクリプトでは扱いません。
BigGo FinanceはJavaScriptで後からニュースを表示するサイトのため取得不可と判明し見送り。
traderswebfx.jpは利用規約で商用サイトへの再配信が禁止されているため対象外です。
"""

import json
import re
import urllib.request
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TKCapitalBot/1.0)"}


def fetch_text(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode("utf-8", errors="ignore")


def fetch_json(url):
    return json.loads(fetch_text(url))


# ---------- 為替（Frankfurter：無料・キー不要・商用利用可） ----------

def get_fx(base, label):
    try:
        end = datetime.now(JST).date()
        start = end - timedelta(days=7)
        url = f"https://api.frankfurter.dev/v1/{start.isoformat()}..{end.isoformat()}?from={base}&to=JPY"
        data = fetch_json(url)
        rates = data.get("rates", {})
        dates = sorted(rates.keys())
        if not dates:
            return None
        latest_rate = rates[dates[-1]]["JPY"]
        if len(dates) < 2:
            return {"label": label, "value": f"{latest_rate:.2f}", "direction": None}
        prev_rate = rates[dates[-2]]["JPY"]
        change = latest_rate - prev_rate
        change_pct = (change / prev_rate) * 100 if prev_rate else 0
        direction = "up" if change >= 0 else "down"
        arrow = "▲" if direction == "up" else "▼"
        value = f"{latest_rate:.2f}（{arrow}{abs(change):.2f} / {arrow}{abs(change_pct):.2f}%）"
        return {"label": label, "value": value, "direction": direction}
    except Exception:
        return None


# ---------- 指数・先物・コモディティ（Yahoo Financeの無料エンドポイント） ----------
#
# 前日終値は meta.previousClose / meta.chartPreviousClose を信用せず、
# 日足の時系列（timestamp + close）から「取引所ローカル日付で今日より前の
# 直近の取引日の終値」を明示的に割り出す。株価指数先物やVIX、商品先物は
# ほぼ24時間取引されており、取得タイミングによって meta.previousClose 系の
# フィールドが直近の終値とずれた値を返すことがあるため。

def _get_chart_result(symbol, range_="10d"):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range={range_}"
    data = fetch_json(url)
    return data["chart"]["result"][0]


def _get_price_and_prev_close(symbol):
    result = _get_chart_result(symbol)
    meta = result["meta"]
    price = meta["regularMarketPrice"]

    gmtoffset = meta.get("gmtoffset", 0) or 0
    local_tz = timezone(timedelta(seconds=gmtoffset))
    today_local = datetime.now(local_tz).date()

    timestamps = result.get("timestamp") or []
    quote = result.get("indicators", {}).get("quote", [{}])[0]
    closes = quote.get("close") or []

    daily = []
    for ts, c in zip(timestamps, closes):
        if c is None:
            continue
        d = datetime.fromtimestamp(ts, local_tz).date()
        daily.append((d, c))

    # 今日の分（まだ確定していない可能性がある）は除外し、
    # 直近の確定済み取引日の終値を前日終値として採用する
    prior_days = [c for d, c in daily if d < today_local]
    if prior_days:
        prev = prior_days[-1]
    elif daily:
        # 念のためのフォールバック（本来は通らない想定）
        prev = daily[-1][1]
    else:
        prev = meta.get("previousClose") or meta.get("chartPreviousClose")

    return price, prev


def get_yahoo_change(symbol, label):
    try:
        price, prev = _get_price_and_prev_close(symbol)
        if not prev:
            return {"label": label, "value": f"{price:,.2f}", "direction": None}
        change = price - prev
        change_pct = (change / prev) * 100
        direction = "up" if change >= 0 else "down"
        arrow = "▲" if direction == "up" else "▼"
        value = f"{price:,.2f}（{arrow}{abs(change):,.2f} / {arrow}{abs(change_pct):.2f}%）"
        return {"label": label, "value": value, "direction": direction}
    except Exception:
        return None


def get_yahoo_yield(symbol, label, scale=10.0):
    try:
        raw_price, raw_prev = _get_price_and_prev_close(symbol)
        price = raw_price / scale
        if not raw_prev:
            return {"label": label, "value": f"{price:.2f}%", "direction": None}
        prev = raw_prev / scale
        diff_bp = (price - prev) * 100
        direction = "up" if diff_bp >= 0 else "down"
        arrow = "▲" if direction == "up" else "▼"
        value = f"{price:.2f}%（{arrow}{abs(diff_bp):.0f}bp）"
        return {"label": label, "value": value, "direction": direction}
    except Exception:
        return None


def build_ticker():
    items = []
    for item in [
        get_fx("USD", "ドル円"),
        get_fx("EUR", "ユーロ円"),
        get_fx("GBP", "ポンド円"),
        get_yahoo_yield("^TNX", "米10年債利回り", scale=10),
        get_yahoo_change("^VIX", "VIX指数"),
        get_yahoo_change("^GSPC", "S&P500"),
        get_yahoo_change("^DJI", "ダウ平均"),
        get_yahoo_change("^RUT", "ラッセル2000"),
        get_yahoo_change("^SOX", "SOX指数"),
        get_yahoo_change("YM=F", "ダウ先物"),
        get_yahoo_change("ES=F", "S&P500先物"),
        get_yahoo_change("RTY=F", "ラッセル2000先物"),
        get_yahoo_change("GC=F", "NY金先物"),
        get_yahoo_change("SI=F", "銀先物"),
        get_yahoo_change("HG=F", "銅先物"),
        get_yahoo_change("CL=F", "WTI原油先物"),
    ]:
        if item:
            items.append(item)
    return items


# ---------- ニュース見出し（Googleニュース「主要記事」フィード） ----------

def clean_title(title):
    return re.sub(r"\s-\s[^-]{1,30}$", "", title).strip()


def build_headlines():
    try:
        url = "https://news.google.com/rss?hl=ja&gl=JP&ceid=JP:ja"
        xml = fetch_text(url)
        titles = re.findall(r"<title>(.*?)</title>", xml)[1:9]
        links = re.findall(r"<link>(.*?)</link>", xml)[1:9]
        items = []
        for t, l in zip(titles, links):
            items.append({"source": "Googleニュース", "title": clean_title(t), "url": l})
        return items
    except Exception:
        return []


def main():
    now = datetime.now(JST).isoformat()

    ticker_items = build_ticker()
    if ticker_items:
        with open("ticker.json", "w", encoding="utf-8") as f:
            json.dump({"updated_at": now, "items": ticker_items}, f, ensure_ascii=False, indent=2)

    headline_items = build_headlines()
    if not headline_items:
        headline_items = [{
            "source": "システム",
            "title": "ニュースの取得に失敗しました（次回の自動更新をお待ちください）",
            "url": "https://news.google.com/home?hl=ja&gl=JP&ceid=JP:ja",
        }]
    with open("headlines.json", "w", encoding="utf-8") as f:
        json.dump({"updated_at": now, "items": headline_items}, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
