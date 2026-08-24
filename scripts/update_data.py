"""
TK Capital ホームページ用データ更新スクリプト
- ticker.json : ドル円・ユーロ円・ポンド円・米10年債利回り・VIX指数・
               S&P500・ダウ平均・ラッセル2000・SOX指数・
               ダウ先物・S&P500先物・ラッセル2000先物・
               金・銀・銅・WTI原油（すべて無料・キー不要で自動取得できるもの）
- headlines.json : Googleニュース経由で、日経・Bloomberg・Reutersの見出し＋リンクを取得
日経平均・TOPIXは公式の無料データが無いため、このスクリプトでは扱いません。
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
        data = fetch_json(f"https://api.frankfurter.dev/v1/latest?from={base}&to=JPY")
        rate = data["rates"]["JPY"]
        return {"label": label, "value": f"{rate:.2f}", "direction": None}
    except Exception:
        return None


# ---------- 指数・先物・コモディティ（Yahoo Financeの無料エンドポイント） ----------
# ※ 非公式のエンドポイントのため、将来的にYahoo側の仕様変更で
#   止まる可能性があります。その場合はまたお知らせください。

def get_yahoo_change(symbol, label):
    """前日比（％）を ▲/▼ 付きで返す"""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=5d"
        data = fetch_json(url)
        meta = data["chart"]["result"][0]["meta"]
        price = meta["regularMarketPrice"]
        prev = meta.get("previousClose") or meta.get("chartPreviousClose")
        if not prev:
            return None
        change_pct = (price - prev) / prev * 100
        direction = "up" if change_pct >= 0 else "down"
        arrow = "▲" if direction == "up" else "▼"
        return {"label": label, "value": f"{arrow}{abs(change_pct):.2f}%", "direction": direction}
    except Exception:
        return None


def get_yahoo_level(symbol, label, scale=1.0, suffix=""):
    """変化率ではなく、そのままの水準を返す（VIX・金利など）"""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=5d"
        data = fetch_json(url)
        meta = data["chart"]["result"][0]["meta"]
        price = meta["regularMarketPrice"] / scale
        return {"label": label, "value": f"{price:.2f}{suffix}", "direction": None}
    except Exception:
        return None


def build_ticker():
    items = []
    for item in [
        get_fx("USD", "ドル円"),
        get_fx("EUR", "ユーロ円"),
        get_fx("GBP", "ポンド円"),
        get_yahoo_level("^TNX", "米10年債利回り", scale=10, suffix="%"),
        get_yahoo_level("^VIX", "VIX指数"),
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


# ---------- ニュース見出し（Googleニュース経由） ----------

def clean_title(title):
    return re.sub(r"\s-\s[^-]{1,30}$", "", title).strip()


def build_headlines():
    sources = [
        ("日本経済新聞", "nikkei.com"),
        ("Bloomberg", "bloomberg.co.jp"),
        ("Reuters", "jp.reuters.com"),
    ]
    items = []
    for name, site in sources:
        try:
            url = (
                f"https://news.google.com/rss/search?q=site:{site}+when:2d"
                "&hl=ja&gl=JP&ceid=JP:ja"
            )
            xml = fetch_text(url)
            titles = re.findall(r"<title>(.*?)</title>", xml)[1:4]
            links = re.findall(r"<link>(.*?)</link>", xml)[1:4]
            for t, l in zip(titles, links):
                items.append({"source": name, "title": clean_title(t), "url": l})
        except Exception:
            continue
    return items


def main():
    now = datetime.now(JST).isoformat()

    ticker_items = build_ticker()
    if ticker_items:
        with open("ticker.json", "w", encoding="utf-8") as f:
            json.dump({"updated_at": now, "items": ticker_items}, f, ensure_ascii=False, indent=2)

    headline_items = build_headlines()
    if headline_items:
        with open("headlines.json", "w", encoding="utf-8") as f:
            json.dump({"updated_at": now, "items": headline_items}, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
