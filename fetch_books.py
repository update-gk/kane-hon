#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
楽天ブックスAPIから「お金の本」（投資・お金の教養・副業）を集めて books.json を作る。
標準ライブラリだけで動きます。

必要な環境変数
  RAKUTEN_APP_ID      楽天ウェブサービスのアプリID
  RAKUTEN_ACCESS_KEY  同アクセスキー
  SITE_URL            公開するページのURL（アプリ登録の「許可されたWebサイト」と同じドメインにする）

任意の環境変数
  BOOKS_GENRE_ID      楽天ブックスのジャンルIDを固定したいとき（通常は自動で「ビジネス」系を探します）
  RANK_PAGES / CAL_PAGES / OUT_FILE
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

API_BASE = "https://openapi.rakuten.co.jp/services/api"
JST = timezone(timedelta(hours=9))
OUT_FILE = os.environ.get("OUT_FILE", "books.json")
INTERVAL = 1.6  # 新APIは間隔が短いと429（アクセス過多）になりやすい
RANK_PAGES = int(os.environ.get("RANK_PAGES", "6"))   # 売れ順で30冊×6ページ（上位180冊）から探す
CAL_PAGES = int(os.environ.get("CAL_PAGES", "40"))    # 発売日の新しい順に最大40ページ
RANK_LIMIT = 20
PAST_DAYS = 14

# 書名・副題に下のことばが入っている本だけを「お金の本」として残す。
# 同点のときは上にあるカテゴリーを優先する。
CATEGORY_RULES = [
    ("inv", ["NISA", "ニーサ", "iDeCo", "イデコ", "投資", "資産運用", "資産形成", "配当", "高配当",
             "積立", "つみたて", "インデックス", "ETF", "債券", "米国株", "日本株", "個別株", "株式",
             "株価", "株主", "オルカン", "S&P", "ファンド", "為替", "FX", "トレード", "証券"]),
    ("biz", ["副業", "起業", "稼ぐ", "稼げ", "稼ぎ", "フリーランス", "個人事業", "スモールビジネス",
             "せどり", "アフィリエイト", "ネットビジネス", "収益化", "マネタイズ", "一人社長", "ひとり社長"]),
    ("eco", ["経済", "お金", "マネー", "金利", "物価", "円安", "円高", "インフレ", "デフレ",
             "財政", "日銀", "金融", "資本主義", "貨幣", "通貨"]),
]


class ApiError(Exception):
    pass


def _headers():
    h = {"User-Agent": "kane-hon-tracker/1.0"}
    site = os.environ.get("SITE_URL", "").strip()
    if site:
        p = urllib.parse.urlparse(site)
        h["Referer"] = site
        h["Origin"] = "{}://{}".format(p.scheme, p.netloc)
    return h


def call(path, **params):
    """楽天APIを1回呼ぶ。429/5xxは少し待って再試行する。"""
    q = {
        "applicationId": os.environ["RAKUTEN_APP_ID"],
        "accessKey": os.environ["RAKUTEN_ACCESS_KEY"],
        "format": "json",
    }
    q.update(params)
    url = "{}/{}?{}".format(API_BASE, path, urllib.parse.urlencode(q))
    for attempt in range(1, 4):
        try:
            req = urllib.request.Request(url, headers=_headers())
            with urllib.request.urlopen(req, timeout=30) as res:
                data = json.loads(res.read().decode("utf-8"))
            time.sleep(INTERVAL)
            return data
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:300]
            if e.code == 404:  # 該当なし
                time.sleep(INTERVAL)
                return {}
            if e.code in (429, 500, 502, 503) and attempt < 3:
                wait = 10 * attempt
                print("  HTTP {}。{}秒待って再試行します ({}/3)".format(e.code, wait, attempt))
                time.sleep(wait)
                continue
            raise ApiError("HTTP {} ({}): {}".format(e.code, path, body)) from None
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < 3:
                time.sleep(5 * attempt)
                continue
            raise ApiError("通信に失敗しました ({}): {}".format(path, e)) from None
    return {}


def find_business_genre():
    """「ビジネス」を含むジャンル（本の直下）のIDを探す。見つからなければ既定値を使う。"""
    forced = os.environ.get("BOOKS_GENRE_ID", "").strip()
    if forced:
        return forced, "(指定)"
    data = call("BooksGenre/Search/20121128", booksGenreId="001")
    for ch in data.get("children") or []:
        g = ch.get("child", ch) if isinstance(ch, dict) else {}
        name = str(g.get("booksGenreName", ""))
        if "ビジネス" in name and g.get("booksGenreId"):
            return str(g["booksGenreId"]), name
    print("警告: ビジネス系ジャンルを自動で見つけられなかったため、既定のID 001006 を使います。")
    return "001006", "ビジネス・経済・就職"


def classify(it):
    """お金の本なら 'inv' / 'biz' / 'eco' を返し、そうでなければ None。"""
    head = " ".join(str(it.get(k) or "") for k in ("title", "subTitle", "seriesName"))
    head = head.replace("株式会社", "")
    caption = str(it.get("itemCaption") or "").replace("株式会社", "")
    best, best_score = None, 0.0
    for cat, words in CATEGORY_RULES:
        s = 2 * sum(1 for w in words if w in head)
        if s == 0:
            continue
        s += 0.5 * sum(1 for w in words if w in caption)
        if s > best_score:
            best, best_score = cat, s
    return best


def parse_date(s):
    m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", str(s or ""))
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def to_book(it, cat):
    d = parse_date(it.get("salesDate"))
    isbn = str(it.get("isbn") or "").strip()
    title = str(it.get("title") or "").strip()
    author = re.sub(r"/(著|編著|監修|編|訳|絵|写真|原作)", "", str(it.get("author") or "")).strip()
    try:
        price = int(it.get("itemPrice") or 0)
    except (TypeError, ValueError):
        price = 0
    return {
        "id": isbn or title,
        "isbn": isbn,
        "t": title,
        "a": author[:40],
        "p": str(it.get("publisherName") or "").strip(),
        "y": price,
        "c": cat,
        "date": d.isoformat() if d else None,
        "img": str(it.get("largeImageUrl") or it.get("mediumImageUrl") or ""),
        "url": str(it.get("itemUrl") or ""),
    }


def iter_items(genre_id, sort, max_pages):
    for page in range(1, max_pages + 1):
        data = call("BooksBook/Search/20170404", booksGenreId=genre_id, sort=sort,
                    hits=30, page=page, formatVersion=2)
        # 楽天APIはレスポンスで "items" ではなく "Items"（大文字始まり）を返すことがある
        items = data.get("items") or data.get("Items") or []
        if not items:
            return
        yield page, items
        try:
            if page >= int(data.get("pageCount") or page):
                return
        except (TypeError, ValueError):
            pass


def load_prev_ranks():
    """前回の順位（ISBN→順位）。前回ファイルがなければ None。"""
    try:
        with open(OUT_FILE, encoding="utf-8") as f:
            prev = json.load(f)
        ranks = {b["id"]: b["rank"] for b in prev.get("books", []) if b.get("rank")}
        return ranks or None
    except (OSError, ValueError, KeyError, TypeError):
        return None


def build():
    today = datetime.now(JST).date()
    genre_id, genre_name = find_business_genre()
    print("ジャンル: {} ({})".format(genre_name, genre_id))
    prev = load_prev_ranks()
    out = {}

    # 1) 売れ筋：楽天ブックスの売れ順から、お金の本だけを上から20冊
    picked = []
    for page, items in iter_items(genre_id, "sales", RANK_PAGES):
        for it in items:
            cat = classify(it)
            if cat and len(picked) < RANK_LIMIT:
                picked.append((it, cat))
        print("  売れ筋 {}ページ目まで: {}冊".format(page, len(picked)))
        if len(picked) >= RANK_LIMIT:
            break
    for i, (it, cat) in enumerate(picked, 1):
        b = to_book(it, cat)
        b["rank"] = i
        if prev is not None:
            old = prev.get(b["id"])
            b["mv"] = "new" if old is None else old - i  # プラス = 順位が上がった
        out[b["id"]] = b

    # 2) 発売予定と最近の発売：発売日の新しい順に、過去14日前まで
    lo = today - timedelta(days=PAST_DAYS)
    reached_past = False
    for page, items in iter_items(genre_id, "-releaseDate", CAL_PAGES):
        dates = []
        for it in items:
            d = parse_date(it.get("salesDate"))
            if d:
                dates.append(d)
            cat = classify(it)
            if not cat or not d or d < lo:
                continue
            b = to_book(it, cat)
            if b["id"] not in out:
                out[b["id"]] = b
        if dates and max(dates) < lo:
            reached_past = True
            break
    if not reached_past:
        print("注意: 過去{}日前まで届く前にページ上限になりました。CAL_PAGES を増やしてください。".format(PAST_DAYS))

    books = sorted(out.values(), key=lambda b: (b["date"] or "0000-00-00", b.get("rank") or 999))
    upcoming = sum(1 for b in books if b["date"] and b["date"] >= today.isoformat())
    print("結果: 全{}冊（発売予定{}冊、ランキング{}冊）".format(len(books), upcoming, len(picked)))
    return {
        "updated": datetime.now(JST).isoformat(timespec="seconds"),
        "genre": genre_name,
        "books": books,
    }


def main():
    for k in ("RAKUTEN_APP_ID", "RAKUTEN_ACCESS_KEY"):
        if not os.environ.get(k):
            sys.exit("環境変数 {} が設定されていません。".format(k))
    try:
        payload = build()
    except ApiError as e:
        msg = str(e)
        print("エラー: " + msg)
        if "403" in msg or "REFERRER" in msg.upper():
            print("ヒント: 楽天アプリの「許可されたWebサイト」と SITE_URL のドメインが一致しているか確認してください。")
        elif "400" in msg:
            print("ヒント: アプリIDとアクセスキーの両方が正しく設定されているか確認してください。")
        sys.exit(1)
    if not payload["books"]:
        sys.exit("該当する本が0冊でした。books.json は更新しません。")
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    print("{} を書き出しました。".format(OUT_FILE))


if __name__ == "__main__":
    main()
