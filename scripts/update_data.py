"""
TK Capital ホームページ用データ更新スクリプト
- ticker.json : ドル円・NYダウ・SOX指数・NY金先物・WTI原油先物（無料で自動取得できるもののみ）
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


def get_usdjpy():
    try:
        data = fetch_json("https://api.frankfurter.dev/v1/latest?from=USD&to=JPY")
        rate = data["rates"]["JPY"]
        return {"label": "ドル円", "value": f"{rate:.2f}", "direction": None}
    except Exception:
        return None


def get_stooq(symbol, label):
    try:
        url = f"https://stooq.com/q/l/?s={symbol}&f=sd2t2c2p2&h&e=csv"
        text = fetch_text(url)
        last_line = text.strip().split("\n")[-1]
        parts = last_line.split(",")
        change_pct = float(parts[-1])
        direction = "up" if change_pct >= 0 else "down"
        arrow = "▲" if direction == "up" else "▼"
        return {"label": label, "value": f"{arrow}{abs(change_pct):.2f}%", "direction": direction}
    except Exception:
        return None


def build_ticker():
    items = []
    for item in [
        get_usdjpy(),
        get_stooq("^dji", "NYダウ"),
        get_stooq("^sox", "SOX指数"),
        get_stooq("gc.f", "NY金先物"),
        get_stooq("cl.f", "WTI原油先物"),
    ]:
        if item:
            items.append(item)
    return items


def clean_title(title):
    # Googleニュースのタイトル末尾に付く " - サイト名" を除去
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
