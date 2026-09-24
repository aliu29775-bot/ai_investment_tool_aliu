#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Berkshire 投研網站 — 一鍵建站腳本

用法:
    python3 build_site.py                 # 完整建站（含行情抓取）
    python3 build_site.py --no-market     # 跳過行情抓取（離線）
    python3 build_site.py --repo ../ai-berkshire   # 指定 repo 路徑

做的事:
  1. 讀取 repo 的 reports/index.json，按公司/專題聚合
  2. 從各公司最新報告萃取評分（★）、結論、一句話摘要、ticker
  3. 用 Yahoo Finance API 抓取最新行情（可跳過，失敗不影響建站）
  4. 把全部 2354 份 Markdown 報告預渲染成獨立 HTML 頁
  5. 輸出 js/data.js 供網站前端使用
"""

import argparse
import json
import os
import re
import shutil
import sys
import time
import urllib.parse
from datetime import datetime
import urllib.request
from collections import defaultdict

SITE_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# 1. 讀取資料
# ---------------------------------------------------------------------------

def load_index(repo):
    with open(os.path.join(repo, "reports", "index.json"), encoding="utf-8") as f:
        return json.load(f)

# ---------------------------------------------------------------------------
# 2. 評分 / 結論 / ticker 萃取
# ---------------------------------------------------------------------------

RE_STARS = re.compile(r"[综綜]合评分[：:]\s*\*{0,2}(★+[★☆]*)(?:（|\()?([\d.]+)?\s*/\s*([\d.]+)?")
RE_SCORE_NUM = re.compile(r"[综綜]合评分[：:]\s*\**([\d.]+)\s*/\s*5")
RE_VERDICT = re.compile(r"[综綜]合[评評]级[：:]\s*\**(.{0,80}?)(?=[\n。|])")
RE_ONE_LINE = re.compile(r"一句话[结結]论[：:]*\s*\n+\s*>\s*([^\n]+)")
RE_ONE_LINE_H = re.compile(r"#{1,6}\s*[^#\n]*[结結]论[^#\n]*\s*\n+\s*>\s*([^\n]+)")
RE_BUY = re.compile(r"(买入区间[^\n。|]{0,40}|買入區間[^\n。|]{0,40})")
RE_PASS = re.compile(r"(✅\s*[通过通過]{2}|❓\s*灰色[地带地帶]?|❌\s*[不]?[通过通過]{2})")

# 報告標題中的 ticker 模式
RE_TICKER_HK = re.compile(r"[(（]?(\d{4,5})\.HK[)）]?", re.I)
RE_TICKER_NASDAQ = re.compile(r"NASDAQ[:：]\s*([A-Z]{1,5})", re.I)
RE_TICKER_NYSE = re.compile(r"NYSE[:：]\s*([A-Z]{1,5})", re.I)
RE_TICKER_CN = re.compile(r"[（(](\d{6})\.[A-Z]{2}[)）]")

# 公司名 -> Yahoo 代碼（手動對照表，覆蓋主要上市公司）
TICKER_MAP = {
    "腾讯": "0700.HK", "拼多多": "PDD", "美团": "3690.HK", "快手": "1024.HK",
    "泡泡玛特": "9992.HK", "MiniMax": "0100.HK", "英伟达": "NVDA", "Google": "GOOGL",
    "微软": "MSFT", "Apple": "AAPL", "Meta": "META", "Amazon": "AMZN", "Tesla": "TSLA",
    "Netflix": "NFLX", "AMD": "AMD", "Intel": "INTC", "Marvell": "MRVL", "Qualcomm": "QCOM",
    "TSM": "TSM", "SK海力士": "000660.KS", "Alibaba": "BABA", "阿里巴巴": "9988.HK",
    "BYD": "1211.HK", "茅台": "600519.SS", "五粮液": "000858.SZ", "泸州老窖": "000568.SZ",
    "汾酒": "600809.SS", "洋河股份": "002304.SZ", "招商银行": "600036.SS",
    "浦发银行": "600000.SS", "平安集团": "601318.SS", "中国神华": "601088.SS",
    "中国广核": "003816.SZ", "长江电力": "600900.SS", "中远海控": "601919.SS",
    "小米": "1810.HK", "网易": "NTES", "百度": "BIDU", "唯品会": "VIPS",
    "理想汽车": "LI", "搜狐": "SOHU", "腾讯音乐": "TME", "汽车之家": "ATHM",
    "PayPal": "PYPL", "Booking": "BKNG", "Adobe": "ADBE", "Accenture": "ACN",
    "Mastercard": "MA", "Progressive": "PGR", "Uber": "UBER", "Zoetis": "ZTS",
    "Nike": "NKE", "lululemon": "LULU", "Novo Nordisk": "NVO", "Prosus": "PRX.AS",
    "Rheinmetall": "RHM.DE", "Elekta": "EKTA-B.ST", "GE Vernova": "GEV",
    "WiseTech": "WTC.AX", "Nittobo": "3110.T", "NewbornTown": "9911.HK",
    "RKLB": "RKLB", "ADP": "ADP", "CMOC": "3993.HK", "Goldwind": "2208.HK",
    "金风科技": "2208.HK", "杰瑞股份": "002353.SZ", "Jereh": "002353.SZ",
    "德业股份": "605117.SS", "英维克": "002837.SZ", "赛力斯": "601127.SS",
    "赛轮轮胎": "601058.SS", "兴发集团": "600141.SS", "华工科技": "000988.SZ",
    "杭叉集团": "603298.SS", "永新股份": "002014.SZ", "江波龙": "301308.SZ",
    "澜起科技": "688008.SS", "中科飞测": "688361.SS", "绿的谐波": "688017.SS",
    "神火股份": "000933.SZ", "藏格矿业": "000408.SZ", "川润股份": "002272.SZ",
    "海尔智家": "600690.SS", "领益智造": "002600.SZ", "众安在线": "6060.HK",
    "康方生物": "9926.HK", "晶泰科技": "2228.HK", "长光辰芯": "688582.SS",
    "滴滴": "DIDIY",
}

# 7 家公司橫評的備用評分（README 的 Checklist 表）
FALLBACK_SCORE = {
    "茅台": (4.7, "✅ 通過"), "腾讯": (4.7, "✅ 通過"), "英伟达": (4.3, "✅ 有條件"),
    "美团": (4.0, "✅ 有條件"), "快手": (4.0, "✅ 有條件"),
    "拼多多": (3.8, "❓ 灰色"), "泡泡玛特": (3.7, "❓ 灰色"),
}


def extract_ticker(name, titles):
    """從公司名與報告標題推測 Yahoo ticker。"""
    if name in TICKER_MAP:
        return TICKER_MAP[name]
    for t in titles:
        m = (RE_TICKER_NASDAQ.search(t) or RE_TICKER_NYSE.search(t)
             or RE_TICKER_CN.search(t) or RE_TICKER_HK.search(t))
        if m:
            sym = m.group(1)
            if RE_TICKER_HK.search(t):
                return sym + ".HK"
            if RE_TICKER_CN.search(t):
                return sym + (".SS" if sym.startswith(("6", "9")) else ".SZ")
            return sym
    return None


def extract_score(repo, reports):
    """從最新報告中萃取評分。回傳 (stars, value, verdict, summary)。"""
    score = verdict = summary = None
    files = sorted(
        (r for r in reports if r.get("type") not in ("底稿",)),
        key=lambda r: r["date"], reverse=True,
    )
    for r in files[:50]:
        p = os.path.join(repo, r["path"])
        if not os.path.exists(p):
            continue
        try:
            txt = open(p, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        if score is None:
            m = RE_STARS.search(txt)
            if m:
                stars = len(m.group(1).replace("☆", ""))
                value = float(m.group(2)) if m.group(2) else float(stars)
                score = {"stars": min(5, max(1, stars)),
                         "value": round(value, 2),
                         "text": m.group(0).strip()[:60]}
            else:
                m = RE_SCORE_NUM.search(txt)
                if m:
                    v = float(m.group(1))
                    score = {"stars": min(5, max(1, round(v))),
                             "value": round(v, 2),
                             "text": m.group(0).strip()[:60]}
        if verdict is None:
            m = RE_VERDICT.search(txt)
            if m:
                v = m.group(1).strip().strip("*").strip()
                # 截斷表格殘留的續文
                v = re.split(r"\*\*[：:]|——|[（(]", v)[0].strip()
                verdict = v[:60]
            else:
                m = RE_BUY.search(txt) or RE_PASS.search(txt)
                if m:
                    verdict = m.group(1).strip()[:60]
        if summary is None:
            m = RE_ONE_LINE.search(txt) or RE_ONE_LINE_H.search(txt)
            if m:
                summary = m.group(1).replace("**", "").strip()[:180]
        if score and verdict and summary:
            break
    return score, verdict, summary


def site_path(p):
    """把 repo 內的報告路徑轉成網站相對路徑（去掉 reports/ 前綴）。"""
    return re.sub(r"^reports/", "", p).replace(".md", ".html")


def classify_verdict(v):
    """把結論文字歸類為正面/中性/負面（給網站顯示顏色用）。"""
    if not v:
        return None
    if re.search(r"买入|買入|建仓|建倉|通过|通過|增持|持有待|低估|✅", v):
        return "positive"
    if re.search(r"灰色|观望|觀望|觀察|待定|❓|不确定|不確定", v):
        return "neutral"
    if re.search(r"不通过|不通過|卖出|賣出|回避|迴避|清仓|清倉|淘汰|❌", v):
        return "negative"
    return None

# ---------------------------------------------------------------------------
# 3. 行情抓取（Yahoo Finance，失敗不影響建站）
# ---------------------------------------------------------------------------

def fetch_quotes(symbols, verbose=True):
    quotes = {}
    for i, sym in enumerate(sorted(set(s for s in symbols if s))):
        url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
               f"{urllib.parse.quote(sym)}?range=5d&interval=1d")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode())
            meta = data["chart"]["result"][0]["meta"]
            closes = data["chart"]["result"][0]["indicators"]["quote"][0]["close"]
            valid = [c for c in closes if c is not None]
            price = meta.get("regularMarketPrice") or (valid[-1] if valid else None)
            prev = valid[-2] if len(valid) >= 2 else meta.get("chartPreviousClose")
            if price is not None:
                chg = (price - prev) / prev * 100 if prev else None
                quotes[sym] = {
                    "price": round(price, 2),
                    "currency": meta.get("currency", ""),
                    "change_pct": round(chg, 2) if chg is not None else None,
                    "asof": time.strftime("%Y-%m-%d"),
                    "name": meta.get("shortName") or meta.get("longName") or "",
                }
                if verbose:
                    print(f"  ✓ {sym:14s} {price:>10.2f} {meta.get('currency','')}")
        except Exception as e:
            if verbose:
                print(f"  ✗ {sym:14s} {e}")
        time.sleep(0.25)
    return quotes

# ---------------------------------------------------------------------------
# 4. Markdown → HTML（自製輕量轉換器，支援表格/列表/引言/程式碼）
# ---------------------------------------------------------------------------

_HTML_TAG = re.compile(
    r"(</?(?:details|summary|br|hr|img|a|sup|sub|kbd|strong|em|b|i|u|s|del|ins|"
    r"span|div|p|table|thead|tbody|tr|td|th|ul|ol|li|blockquote|pre|code|h[1-6]|"
    r"font|center|small|big|mark|q|cite|abbr|wbr|col|colgroup|video|audio|iframe)"
    r"\b[^>]*/?>)",
    re.I,
)

_GITHUB_BASE = "https://github.com/xbtlin/ai-berkshire/blob/main/"


class Markdown:
    def __init__(self, repo_rel_path, repo_root):
        """repo_rel_path: 報告在 repo 內的相對路徑（如 reports/腾讯/xxx.md），
        用於計算圖片/連結的相對位址。"""
        self.rel = repo_rel_path
        self.repo = repo_root
        self.depth = len(os.path.dirname(repo_rel_path).split("/"))
        # out_dir：報告所在目錄相對網站 reports/ 根目錄。depth-1 時 dirname 是
        # "reports"（無尾斜線），字串替換會漏掉，故用 relpath 計算。
        self.out_dir = os.path.relpath(os.path.dirname(repo_rel_path), "reports")

    def _repo_target(self, url):
        """回傳 md 內相對連結對應的 repo 檔案路徑；外鏈/錨點回傳 None。"""
        if not url or url.startswith(("#", "http://", "https://", "mailto:", "//")):
            return None
        base = url.split("#")[0]
        m = re.match(r"(?:\.\./)*reports/(.+)$", base)
        if m:
            return os.path.normpath(os.path.join(self.repo, "reports", m.group(1)))
        m = re.match(r"(?:\.\./)*assets/(.+)$", base)
        if m:
            return os.path.normpath(os.path.join(self.repo, "assets", m.group(1)))
        return os.path.normpath(os.path.join(self.repo, os.path.dirname(self.rel), base))

    def _rewrite_url(self, url):
        """把 repo 內部的相對連結改寫成網站內的相對連結。"""
        if not url or url.startswith(("#", "http://", "https://", "mailto:", "//")):
            return url
        base = url.split("#")[0] or url
        frag = ("#" + url.split("#", 1)[1]) if "#" in url else ""
        # 報告互鏈（reports/... 或 ../reports/...）
        m = re.match(r"(?:\.\./)*reports/(.+)$", base)
        if m:
            target = m.group(1)
            if target.lower().endswith(".md"):
                target = target[:-3] + ".html"
                rel_path = os.path.relpath(target, self.out_dir)
                return rel_path + frag
            # 非 md（csv 等）→ 指向 GitHub
            return _GITHUB_BASE + "reports/" + target
        # 資源圖片（assets/ 或 ../assets/）
        m = re.match(r"(?:\.\./)*assets/(.+)$", base)
        if m:
            rel_path = os.path.relpath("assets/" + m.group(1), self.out_dir)
            return rel_path + frag
        # 同目錄 .md
        if base.lower().endswith(".md"):
            return base[:-3] + ".html" + frag
        return url

    def _inline(self, text):
        # 1. 保護原始 HTML 標籤與 inline code
        protects = []
        def _protect(m):
            protects.append(m.group(0))
            return f"\x00{len(protects)-1}\x00"
        text = _HTML_TAG.sub(_protect, text)
        text = re.sub(r"`([^`\n]+)`", lambda m: (
            protects.append(f"<code>{_esc(m.group(1))}</code>"),
            f"\x00{len(protects)-1}\x00")[1], text)
        # 2. 先轉義剩餘原始文字，之後生成的標籤才不會被二次轉義
        text = _esc(text)
        # 3. 圖片 / 連結（repo 內不存在的目標改為佔位或純文字，避免網站 404；
        #    reports/、assets/ 以外的檔案改連 GitHub 原文）
        def _outside(t):
            relp = os.path.relpath(t, self.repo)
            return relp not in ("reports", "assets") and \
                not relp.startswith("reports/") and not relp.startswith("assets/")

        def _img(m):
            url = m.group(2)
            t = self._repo_target(url)
            if t is None or os.path.isfile(t):
                if t is not None and os.path.isfile(t) and _outside(t):
                    relp = os.path.relpath(t, self.repo)
                    return f'<img src="https://raw.githubusercontent.com/xbtlin/ai-berkshire/main/{relp}" alt="{m.group(1)}">'
                return f'<img src="{self._rewrite_url(url)}" alt="{m.group(1)}">'
            return '<span class="img-missing">🖼 ' + _esc(m.group(1)) + \
                "（源資料庫未收錄此圖）</span>"

        def _link(m):
            url = m.group(2)
            t = self._repo_target(url)
            if t is not None and not os.path.isfile(t):
                return _esc(m.group(1))
            if t is not None and _outside(t):
                relp = os.path.relpath(t, self.repo)
                return f'<a href="{_GITHUB_BASE + relp}">{m.group(1)}</a>'
            return f'<a href="{self._rewrite_url(url)}">{m.group(1)}</a>'

        text = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+&quot;[^&]*&quot;)?\)", _img, text)
        text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", _link, text)
        # 4. 粗體 / 斜體 / 刪除線
        text = re.sub(r"\*\*([^*\n]+)\*\*", r"<strong>\1</strong>", text)
        text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", text)
        text = re.sub(r"~~([^~\n]+)~~", r"<del>\1</del>", text)
        # 5. 還原保護的原始 HTML
        def _restore(m):
            return protects[int(m.group(1))]
        return re.sub(r"\x00(\d+)\x00", _restore, text)

    def render(self, text):
        # 去 YAML front-matter
        if text.startswith("---\n"):
            end = text.find("\n---", 4)
            if end != -1:
                text = text[end + 4:].lstrip("\n")
        lines = text.split("\n")
        out, i, n = [], 0, len(lines)
        while i < n:
            line = lines[i]
            # 程式碼區塊
            m = re.match(r"^```(.*)$", line)
            if m:
                buf, i = [], i + 1
                while i < n and not lines[i].startswith("```"):
                    buf.append(lines[i]); i += 1
                code_html = _esc("\n".join(buf))
                out.append(f"<pre><code>{code_html}</code></pre>")
                i += 1
                continue
            # 表格
            if line.lstrip().startswith("|") and i + 1 < n and re.match(
                    r"^\s*\|?[\s:|-]+\|?\s*$", lines[i + 1]) and "---" in lines[i + 1]:
                rows, i = [line], i + 2
                while i < n and lines[i].lstrip().startswith("|"):
                    rows.append(lines[i]); i += 1
                out.append(self._table(rows))
                continue
            # 標題
            m = re.match(r"^(#{1,6})\s+(.+)$", line)
            if m:
                lv = len(m.group(1))
                out.append(f"<h{lv}>{self._inline(m.group(2).strip())}</h{lv}>")
                i += 1
                continue
            # 分隔線
            if re.match(r"^\s*(---+|\*\*\*+|___+)\s*$", line):
                out.append("<hr>")
                i += 1
                continue
            # 引言
            if line.lstrip().startswith(">"):
                buf, i = [], i
                while i < n and lines[i].lstrip().startswith(">"):
                    buf.append(re.sub(r"^\s*>\s?", "", lines[i])); i += 1
                inner = self.render("\n".join(buf))
                out.append(f"<blockquote>{inner}</blockquote>")
                continue
            # 非表格的孤立管線行 → 跳過（防止死循環）
            if line.lstrip().startswith("|"):
                i += 1
                continue
            # 列表（含巢狀）
            if re.match(r"^\s*([-*+]|\d+[.)])\s+", line):
                html, i = self._list(lines, i)
                out.append(html)
                continue
            # 原始 HTML 行
            if re.match(r"^\s*<", line):
                out.append(line)
                i += 1
                continue
            # 一般段落
            if line.strip():
                buf, i = [], i
                while i < n and lines[i].strip() and not re.match(
                        r"^(```|#{1,6}\s|\s*\||\s*>|\s*([-*+]|\d+[.)])\s|\s*<|"
                        r"\s*(---+|\*\*\*+|___+)\s*$)", lines[i]):
                    buf.append(lines[i]); i += 1
                if buf:
                    out.append(f"<p>{self._inline(' '.join(buf))}</p>")
                else:  # 防護：任何未被前面分支處理的行直接跳過
                    i += 1
            else:
                i += 1
        return "\n".join(out)

    def _table(self, rows):
        def cells(row):
            return [c.strip() for c in row.strip().strip("|").split("|")]
        head = cells(rows[0])
        thead = "<tr>" + "".join(
            f"<th>{self._inline(c)}</th>" for c in head) + "</tr>"
        body = ""
        for r in rows[1:]:
            if re.match(r"^\s*\|?[\s:|-]+\|?\s*$", r):
                continue
            cs = cells(r)
            cs += [""] * (len(head) - len(cs))
            body += "<tr>" + "".join(
                f"<td>{self._inline(c)}</td>" for c in cs[:len(head)]) + "</tr>"
        return f"<table><thead>{thead}</thead><tbody>{body}</tbody></table>"

    def _list(self, lines, i):
        """解析列表區塊（支援巢狀）。回傳 (html, 下一個行號)。"""
        n = len(lines)
        m0 = re.match(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$", lines[i])
        base_indent = len(m0.group(1))
        tag = "ol" if re.match(r"\d", m0.group(2)) else "ul"
        html = [f"<{tag}>"]
        while i < n:
            m = re.match(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$", lines[i])
            if not m:
                break
            indent = len(m.group(1))
            if indent < base_indent:
                break
            if indent > base_indent:
                if html and html[-1].endswith("</li>"):
                    sub, i = self._list(lines, i)
                    html[-1] = html[-1][:-5] + sub + "</li>"
                else:
                    i += 1
                continue
            task = re.match(r"\[([ xX])\]\s*(.*)$", m.group(3))
            if task:
                checked = " checked" if task.group(1).lower() == "x" else ""
                inner = (f'<input type="checkbox" disabled{checked}> '
                         f"{self._inline(task.group(2))}")
            else:
                inner = self._inline(m.group(3))
            html.append(f"<li>{inner}</li>")
            i += 1
        html.append(f"</{tag}>")
        return "\n".join(html), i


def _esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

# ---------------------------------------------------------------------------
# 5. 主流程
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=os.path.join(os.path.dirname(SITE_DIR), "ai-berkshire"))
    ap.add_argument("--no-market", action="store_true")
    args = ap.parse_args()

    repo = os.path.abspath(args.repo)
    if not os.path.exists(os.path.join(repo, "reports", "index.json")):
        sys.exit(f"找不到 repo: {repo}")

    print("== 1/4 讀取報告索引 ==")
    idx = load_index(repo)
    reports = [r for r in idx["reports"] if os.path.exists(os.path.join(repo, r["path"]))]
    if len(reports) < len(idx["reports"]):
        print(f"⚠️ 跳過 {len(idx['reports']) - len(reports)} 條失效路徑（源 repo 內檔案不存在）")

    # index 未收錄、但會被報告互鏈引用的 md（如各資料夾 README）也一併渲染，
    # 否則互鏈會 404。這些頁面不進 data.js 列表，僅供報告內互鏈到達。
    indexed = {r["path"] for r in reports}
    extra = []
    for root, _dirs, files in os.walk(os.path.join(repo, "reports")):
        for f in files:
            if not f.endswith(".md"):
                continue
            p = os.path.relpath(os.path.join(root, f), repo)
            if p in indexed:
                continue
            title = f[:-3]
            try:
                for line in open(os.path.join(repo, p), encoding="utf-8", errors="replace"):
                    m = re.match(r"^#\s+(.+)$", line.strip())
                    if m:
                        title = m.group(1).strip()
                        break
            except OSError:
                pass
            mtime = datetime.fromtimestamp(os.path.getmtime(os.path.join(repo, p)))
            extra.append({
                "title": title, "path": p, "group": "附屬文件", "bucket": "專題",
                "type": "附屬", "date": mtime.strftime("%Y-%m-%d"),
            })
    if extra:
        print(f"   另渲染 {len(extra)} 份 index 未收錄的附屬文件（供互鏈）")

    by_company = defaultdict(list)
    by_topic = defaultdict(list)
    for r in reports:
        if r["bucket"] == "公司":
            by_company[r["group"]].append(r)
        else:
            by_topic[r["group"]].append(r)

    print(f"== 2/4 萃取公司資料（{len(by_company)} 家）==")
    companies = []
    for name, rs in sorted(by_company.items()):
        rs = sorted(rs, key=lambda r: r["date"])
        latest = rs[-1]["date"]
        titles = [r["title"] for r in rs]
        ticker = extract_ticker(name, titles)
        score, verdict, summary = extract_score(repo, rs)
        if score is None and name in FALLBACK_SCORE:
            v, vd = FALLBACK_SCORE[name]
            score = {"stars": round(v), "value": v, "text": f"橫評備用分 {v}/5"}
            verdict = verdict or vd
        companies.append({
            "name": name,
            "ticker": ticker,
            "count": len(rs),
            "latest": latest,
            "score": score,
            "verdict": verdict,
            "verdict_class": classify_verdict(verdict),
            "summary": summary,
            "reports": [
                {"title": r["title"], "date": r["date"], "type": r["type"],
                 "path": site_path(r["path"])}
                for r in reversed(rs)
            ],
        })

    topics = []
    for name, rs in sorted(by_topic.items(), key=lambda kv: -len(kv[1])):
        rs = sorted(rs, key=lambda r: r["date"])
        topics.append({
            "name": name, "bucket": rs[0]["bucket"], "count": len(rs),
            "latest": rs[-1]["date"],
            "reports": [
                {"title": r["title"], "date": r["date"], "type": r["type"],
                 "path": site_path(r["path"])}
                for r in reversed(rs)
            ],
        })

    all_reports = sorted(reports, key=lambda r: r["date"], reverse=True)
    tickers = [c["ticker"] for c in companies]

    quotes = {}
    cache_file = os.path.join(SITE_DIR, "js", "market_cache.json")
    if not args.no_market:
        print(f"== 3/4 抓取行情（{len([t for t in tickers if t])} 個代碼，約 30 秒）==")
        quotes = fetch_quotes(tickers)
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(quotes, f, ensure_ascii=False)
    elif os.path.exists(cache_file):
        quotes = json.load(open(cache_file, encoding="utf-8"))
        print(f"== 3/4 使用行情快取（{len(quotes)} 檔，{cache_file}）==")

    print(f"== 4/4 預渲染 {len(reports)} + {len(extra)} 份報告 ==")
    render_reports(repo, reports + extra)
    print(f"   完成，輸出至 {os.path.relpath(os.path.join(SITE_DIR, 'reports'))}")

    # 實盤資料（取自 README 與 实盘记录/）
    data = {
        "stats": {
            "reports": idx["count"], "companies": len(companies),
            "topics": len(topics), "updated": max(r["date"] for r in reports),
        },
        "companies": companies,
        "topics": topics,
        "latest_reports": [
            {"title": r["title"], "date": r["date"], "type": r["type"],
             "group": r["group"], "bucket": r["bucket"],
             "path": site_path(r["path"])}
            for r in all_reports[:30]
        ],
        "market": quotes,
        "trackrecord": {
            "years": ["2024", "2025"],
            "returns": [
                {"name": "本框架實盤", "values": [69.29, 66.38]},
                {"name": "恒生指數", "values": [17.67, 27.77]},
                {"name": "標普500", "values": [23.31, 16.39]},
                {"name": "滬深300", "values": [14.68, 17.66]},
                {"name": "納斯達克", "values": [28.64, 20.36]},
            ],
            "note": "兩年累計實盤收益超 146 萬元，連續兩年大幅跑贏全球主要指數。截圖來自富途證券真實帳戶。",
            "disclaimer": "歷史收益不代表未來表現。",
        },
        "portfolio": {
            "asof": "2026-09-07",
            "holdings": [
                {"name": "PDD（拼多多）", "weight": 32, "cost": "$91.484", "pnl": -10.1},
                {"name": "騰訊控股（0700.HK）", "weight": 28, "cost": "HK$453.75", "pnl": -3.4},
                {"name": "快手-W（1024.HK）", "weight": 24, "cost": "HK$34.5", "pnl": -1.5},
                {"name": "美團-W（3690.HK）", "weight": 10, "cost": "HK$96.75", "pnl": -17.3},
                {"name": "MiniMax（0100.HK）", "weight": 7, "cost": "HK$200", "pnl": 75.4},
            ],
            "trades": [
                ["2026-09-07", "泡泡玛特（9992.HK）", "賣出（清倉）", "HK$156.20", "8% → 0%，退出組合", "建倉僅兩個交易日即清倉，已實現盈虧約 +0.8%。清倉理由待補寫"],
                ["2026-09-07", "快手-W（1024.HK）", "減倉（零頭）", "HK$33.98", "權重不變（仍約 24%）", "不同帳號之間換倉，不構成減倉信號"],
                ["2026-09-05", "騰訊控股（0700.HK）", "減倉", "待補", "45% → 26%", "減持約兩成三，剩餘倉位成本價不變"],
                ["2026-09-05", "MiniMax（0100.HK）", "買入（加倉）", "約 HK$204", "2% → 7%", "破例操作，留痕待覆盤"],
                ["2026-09-05", "泡泡玛特（9992.HK）", "買入", "HK$155", "首次建倉（約 8%）", "研究見泡泡玛特-thesis"],
                ["2026-09-05", "快手-W（1024.HK）", "買入", "HK$34.5", "首次建倉（約 22%）", "超出建議倉位上限（8%–12%），破例，留痕待覆盤"],
                ["2026-07-27", "MiniMax（0100.HK）", "買入", "HK$189.5", "首次建倉（約 2%）", "詳見鏡子測試記錄"],
                ["2026-04-21", "PDD（拼多多）", "買入", "$103.66", "首次建倉（試探倉）", "詳見鏡子測試記錄"],
                ["2026-04-21", "美團（3690.HK）", "賣出 PUT（行權價 85）", "權利金待補", "若行權，美團權重將升至約三成", "實際成本約 83~84"],
            ],
            "note": "組合浮動盈虧約 -3.6%（相對成本）。公開每筆操作的方向、價格與權重變化，不公開股數與金額——參考段永平：公開決策，不公開規模。",
        },
    }

    # 寫 js/data.js
    with open(os.path.join(SITE_DIR, "js", "data.js"), "w", encoding="utf-8") as f:
        f.write("// 由 build_site.py 自動生成，勿手動編輯\n")
        f.write("window.SITE_DATA = ")
        json.dump(data, f, ensure_ascii=False)
        f.write(";\n")
    print(f"✓ js/data.js 已生成（{os.path.getsize(os.path.join(SITE_DIR, 'js', 'data.js'))/1024:.0f} KB）")


def render_reports(repo, reports):
    """把全部報告預渲染成獨立 HTML 頁面。"""
    out_root = os.path.join(SITE_DIR, "reports")
    # 複製 repo 的 assets（報告內圖片會用到）
    repo_assets = os.path.join(repo, "assets")
    if os.path.isdir(repo_assets):
        shutil.copytree(repo_assets, os.path.join(out_root, "assets"),
                        dirs_exist_ok=True)
    # 複製 reports/ 下的資料檔（csv/txt/py/json 等，報告互鏈會用到）
    for root, __dirs, files in os.walk(os.path.join(repo, "reports")):
        for f in files:
            if f.lower().endswith(".md") or f == "index.json" or f == ".DS_Store":
                continue
            src = os.path.join(root, f)
            dst = os.path.join(out_root, os.path.relpath(src, os.path.join(repo, "reports")))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
    done = 0
    for r in reports:
        src = os.path.join(repo, r["path"])
        if not os.path.exists(src):
            continue
        try:
            text = open(src, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        md = Markdown(r["path"], repo)
        body = md.render(text)
        rel = "../" * md.depth
        title = r["title"]
        group_html = _esc(r["group"])
        html = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)} — AI Berkshire 投研網站</title>
<link rel="stylesheet" href="{rel}css/style.css">
<link rel="stylesheet" href="{rel}css/report.css">
</head>
<body data-page="report">
<header class="site-nav">
  <a class="brand" href="{rel}index.html">◆ AI Berkshire <span>投研網站</span></a>
  <nav>
    <a href="{rel}index.html">首頁</a>
    <a href="{rel}companies.html">公司</a>
    <a href="{rel}reports.html">報告</a>
    <a href="{rel}trackrecord.html">實盤</a>
  </nav>
</header>
<main class="report-wrap">
  <nav class="crumbs">
    <a href="{rel}reports.html">報告總覽</a>
    <span>›</span>
    <a href="{rel}companies.html">{group_html}</a>
  </nav>
  <div class="report-head">
    <h1>{_esc(title)}</h1>
    <div class="report-meta">
      <span class="badge">{_esc(r['bucket'])}</span>
      <span class="badge badge-type">{_esc(r['type'])}</span>
      <span class="meta-item">📅 {r['date']}</span>
      <span class="meta-item">📁 {group_html}</span>
    </div>
  </div>
  <article class="report-body">
{body}
  </article>
  <footer class="report-foot">
    <p>資料來源：<a href="https://github.com/xbtlin/ai-berkshire" target="_blank" rel="noopener">github.com/xbtlin/ai-berkshire</a>
    · 本網站為研究框架展示，所有內容不構成投資建議。投資有風險，決策需謹慎。</p>
  </footer>
</main>
</body>
</html>
"""
        rel_path = site_path(r["path"])
        out_path = os.path.join(out_root, rel_path)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)
        done += 1
        if done % 500 == 0:
            print(f"   已渲染 {done}/{len(reports)}")


if __name__ == "__main__":
    main()
