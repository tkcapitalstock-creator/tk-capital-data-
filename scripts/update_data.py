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
import html as html_module
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
# 日足の終値配列から直接判定する。指数先物やVIX、商品先物はほぼ24時間
# 取引されており、取得タイミングによって meta.previousClose 系のフィールドが
# 直近の終値とずれた値を返すことがあるため。
# 判定方法：終値配列の最後のバーが現在値（regularMarketPrice）とほぼ一致する
# 場合は「本日分のバー」とみなし、その1つ前の値を前日終値として採用する。
# 一致しない場合はそのまま最後のバーを前日終値として採用する。

def _get_chart_result(symbol, range_="10d"):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range={range_}"
    data = fetch_json(url)
    return data["chart"]["result"][0]


def _get_price_and_prev_close(symbol):
    result = _get_chart_result(symbol)
    meta = result["meta"]
    price = meta["regularMarketPrice"]

    quote = result.get("indicators", {}).get("quote", [{}])[0]
    closes = quote.get("close") or []
    valid_closes = [c for c in closes if c is not None]

    tolerance = max(abs(price) * 1e-6, 1e-6)
    prev = None
    if len(valid_closes) >= 2:
        if abs(valid_closes[-1] - price) < tolerance:
            prev = valid_closes[-2]
        else:
            prev = valid_closes[-1]
    elif len(valid_closes) == 1:
        if abs(valid_closes[0] - price) >= tolerance:
            prev = valid_closes[0]

    if prev is None:
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


def get_yahoo_yield(symbol, label, scale=1.0):
    # 注：^TNXはかつて「利回り×10」で提供されていたが、現在のYahoo Financeの
    # chart APIはそのまま利回り（例：4.74 → 4.74%）を返すため、scaleは1.0とする。
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
        get_yahoo_change("NIY=F", "日経225先物"),
        get_yahoo_yield("^TNX", "米10年債利回り"),
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


# ---------- 適時開示（東証TDnet・非公式WEB-API by やのしん） ----------
# 出典: https://webapi.yanoshin.jp/tdnet/ （無料・非公式のTDnet適時開示情報API）

def normalize_code(code):
    # TDnetの銘柄コードは5桁（本来の4桁＋区分用の1桁、普通株式は末尾0）で
    # 管理されているため、表示用に末尾の0を取って4桁に直す。
    code = str(code)
    if len(code) == 5 and code.endswith("0"):
        return code[:-1]
    return code


def build_disclosures_tdnet_direct():
    """TDnet公式サイト（release.tdnet.info）から直接、本日分の一覧HTMLを取得して解析する。
    yanoshinさんのAPIを経由しない分、理論上は反映が早くなる可能性がある。
    ページ構成やクラス名が変わると取れなくなる可能性があるため、
    失敗時はbuild_disclosures()側でyanoshin経由にフォールバックする。
    """
    today_str = datetime.now(JST).strftime("%Y%m%d")
    base = "https://www.release.tdnet.info/inbs/"
    date_fmt = f"{today_str[0:4]}-{today_str[4:6]}-{today_str[6:8]}"
    items = []
    page = 1
    while page <= 6:  # 1ページ最大100件想定、600件までの安全上限
        url = f"{base}I_list_{page:03d}_{today_str}.html"
        try:
            page_html = fetch_text(url)
        except Exception:
            break  # そのページが存在しない＝これ以上続きはない
        if "kjTitle" not in page_html:
            break
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", page_html, re.S)
        found_in_page = 0
        for row in rows:
            m_time = re.search(r'class="[^"]*\bkjTime\b[^"]*"[^>]*>\s*([^<]*?)\s*<', row)
            m_code = re.search(r'class="[^"]*\bkjCode\b[^"]*"[^>]*>\s*([^<]*?)\s*<', row)
            m_name = re.search(r'class="[^"]*\bkjName\b[^"]*"[^>]*>\s*([^<]*?)\s*<', row)
            m_title_block = re.search(r'class="[^"]*\bkjTitle\b[^"]*"[^>]*>(.*?)</td>', row, re.S)
            if not (m_time and m_code and m_name and m_title_block):
                continue
            title_html = m_title_block.group(1)
            m_link = re.search(r'href="([^"]+)"', title_html)
            title_text = html_module.unescape(re.sub(r"<[^>]+>", "", title_html)).strip()
            time_text = m_time.group(1).strip()
            pdf_url = (base + m_link.group(1)) if m_link else ""
            pubdate = f"{date_fmt}T{time_text}:00+09:00" if re.match(r"^\d{2}:\d{2}$", time_text) else ""
            items.append({
                "code": normalize_code(m_code.group(1).strip()),
                "name": html_module.unescape(m_name.group(1).strip()),
                "title": title_text,
                "url": pdf_url,
                "pubdate": pubdate,
            })
            found_in_page += 1
        print(f"[build_disclosures_tdnet_direct] page {page}: {found_in_page} items")
        if found_in_page == 0:
            break
        page += 1
    return items


def build_disclosures_yanoshin():
    today_str = datetime.now(JST).strftime("%Y%m%d")
    url = f"https://webapi.yanoshin.jp/webapi/tdnet/list/{today_str}.json2"
    data = fetch_json(url)
    raw_items = data.get("items", [])
    print(f"[build_disclosures_yanoshin] date query returned {len(raw_items)} raw items")
    items = []
    for entry in raw_items:
        t = entry.get("Tdnet")
        if not t:
            continue
        items.append({
            "code": normalize_code(t.get("company_code", "")),
            "name": t.get("company_name", ""),
            "title": t.get("title", ""),
            "url": t.get("document_url", ""),
            "pubdate": t.get("pubdate", ""),
        })
    if not items:
        # 当日分がまだ0件（早朝など）の場合は、直近の一覧にフォールバック
        print("[build_disclosures_yanoshin] falling back to recent.json2")
        data = fetch_json("https://webapi.yanoshin.jp/webapi/tdnet/list/recent.json2?limit=20")
        for entry in data.get("items", []):
            t = entry.get("Tdnet")
            if not t:
                continue
            items.append({
                "code": normalize_code(t.get("company_code", "")),
                "name": t.get("company_name", ""),
                "title": t.get("title", ""),
                "url": t.get("document_url", ""),
                "pubdate": t.get("pubdate", ""),
            })
    return items


def build_disclosures():
    # ① まずTDnet公式サイトから直接取得を試みる（yanoshinさん経由の遅延を1段階減らせる可能性）
    try:
        items = build_disclosures_tdnet_direct()
    except Exception as e:
        print(f"[build_disclosures] direct TDnet scrape failed: {e}")
        items = []

    if items:
        print(f"[build_disclosures] using TDnet-direct result: {len(items)} items")
        return items

    # ② ダメならこれまで通りyanoshinさんのAPI経由にフォールバック
    print("[build_disclosures] TDnet-direct returned nothing, falling back to yanoshin")
    try:
        return build_disclosures_yanoshin()
    except Exception as e:
        print(f"[build_disclosures] yanoshin fallback also failed: {e}")
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

    disclosure_items = build_disclosures()
    print(f"[main] disclosure_items count: {len(disclosure_items)}")
    if disclosure_items:
        with open("disclosures.json", "w", encoding="utf-8") as f:
            json.dump({"updated_at": now, "items": disclosure_items}, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
