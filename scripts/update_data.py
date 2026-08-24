"""
TK Capital ホームページ用データ更新スクリプト
- ticker.json : ドル円・ユーロ円・ポンド円（現在値＋変動幅＋前日比%）・
               米10年債利回り（前日比bp付き）・
               VIX指数・S&P500・ダウ平均・ラッセル2000・SOX指数・
               ダウ先物・S&P500先物・ラッセル2000先物・
               金・銀・銅・WTI原油（現在値＋変動幅＋前日比%）
- headlines.json : 日経・Bloomberg・Reuters（Googleニュース経由）＋
                   BigGo Finance（サイト直接取得）の見出し＋リンク
日経平均・TOPIXは公式の無料データが無いため、このスクリプトでは扱いません。
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

def _get_meta(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=5d"
    data = fetch_json(url)
    return data["chart"]["result"][0]["meta"]


def get_yahoo_change(symbol, label):
    try:
        meta = _get_meta(symbol)
        price = meta["regularMarketPrice"]
        prev = meta.get("previousClose") or meta.get("chartPreviousClose")
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
        meta = _get_meta(symbol)
        price = meta["regularMarketPrice"] / scale
        prev = meta.get("previousClose") or meta.get("chartPreviousClose")
        if not prev:
            return {"label": label, "value": f"{price:.2f}%", "direction": None}
        prev = prev / scale
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


# ---------- ニュース見出し ----------

def clean_title(title):
    return re.sub(r"\s-\s[^-]{1,30}$", "", title).strip()


def build_google_news_headlines():
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


def build_biggo_headlines():
    """BigGo Financeのページを直接読み取って見出し＋リンクを抽出する。
    サイトのHTML構造が変わると取得できなくなる可能性があります。"""
    try:
        html = fetch_text("https://finance.biggo.jp/topics/Latest")
        pattern = r'href="(https://finance\.biggo\.jp/news/[a-zA-Z0-9\-]+)"[^>]*>([^<]{10,120})<'
        matches = re.findall(pattern, html)
        seen = set()
        items = []
        for url, title in matches:
            if url in seen:
                continue
            seen.add(url)
            items.append({"source": "BigGo Finance", "title": title.strip(), "url": url})
            if len(items) >= 4:
                break
        return items
    except Exception:
        return []


def build_headlines():
    items = build_google_news_headlines()
    items.extend(build_biggo_headlines())
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
