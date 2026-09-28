# -*- coding: utf-8 -*-
"""
AIShan+ 個股獨立分析系統
- EXTRA_COMPANIES：補充到 300 家覆蓋的公司清單（無研報、僅監測）
- fetch_fundamentals：Yahoo quoteSummary（crumb 流程）+ 1y 日線，快取至 js/fund_cache.json
- compute_stock：DCF（含敏感性）、DDM、相對估值、技術面、機構持倉、催化劑、AI 論點
- render_stock_pages：為每家公司生成 stocks/<name>.html（內嵌 JSON，js/stock.js 渲染）
"""

import json
import os
import re
import shutil
import time
import urllib.parse
import urllib.request

SITE_DIR = os.path.dirname(os.path.abspath(__file__))
STOCKS_DIR = os.path.join(SITE_DIR, "stocks")
FUND_CACHE = os.path.join(SITE_DIR, "js", "fund_cache.json")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

# ---------------------------------------------------------------------------
# 1. 補充公司清單（與現有 168 家去重後併入，目標 300 家覆蓋）
#    sector 沿用全站行業著色（SECTOR_COLORS）；region 僅供頁面展示
# ---------------------------------------------------------------------------

EXTRA_COMPANIES = [
    # --- 美股 · 科技 / AI 產業鏈 ---
    {"name": "微软", "ticker": "MSFT", "sector": "科技", "region": "美股"},
    {"name": "英伟达", "ticker": "NVDA", "sector": "科技", "region": "美股"},
    {"name": "亚马逊", "ticker": "AMZN", "sector": "科技", "region": "美股"},
    {"name": "Meta", "ticker": "META", "sector": "互聯網", "region": "美股"},
    {"name": "博通", "ticker": "AVGO", "sector": "科技", "region": "美股"},
    {"name": "AMD", "ticker": "AMD", "sector": "科技", "region": "美股"},
    {"name": "美光科技", "ticker": "MU", "sector": "科技", "region": "美股"},
    {"name": "Palantir", "ticker": "PLTR", "sector": "科技", "region": "美股"},
    {"name": "甲骨文", "ticker": "ORCL", "sector": "科技", "region": "美股"},
    {"name": "Salesforce", "ticker": "CRM", "sector": "科技", "region": "美股"},
    {"name": "奈飛", "ticker": "NFLX", "sector": "互聯網", "region": "美股"},
    {"name": "Adobe", "ticker": "ADBE", "sector": "科技", "region": "美股"},
    {"name": "英特爾", "ticker": "INTC", "sector": "科技", "region": "美股"},
    {"name": "高通", "ticker": "QCOM", "sector": "科技", "region": "美股"},
    {"name": "德州儀器", "ticker": "TXN", "sector": "科技", "region": "美股"},
    {"name": "ServiceNow", "ticker": "NOW", "sector": "科技", "region": "美股"},
    {"name": "Palo Alto Networks", "ticker": "PANW", "sector": "科技", "region": "美股"},
    {"name": "CrowdStrike", "ticker": "CRWD", "sector": "科技", "region": "美股"},
    {"name": "Snowflake", "ticker": "SNOW", "sector": "科技", "region": "美股"},
    {"name": "超微电脑", "ticker": "SMCI", "sector": "科技", "region": "美股"},
    {"name": "Arm Holdings", "ticker": "ARM", "sector": "科技", "region": "美股"},
    {"name": "Cloudflare", "ticker": "NET", "sector": "科技", "region": "美股"},
    {"name": "Reddit", "ticker": "RDDT", "sector": "互聯網", "region": "美股"},
    {"name": "Robinhood", "ticker": "HOOD", "sector": "金融", "region": "美股"},
    # --- 美股 · 消費 ---
    {"name": "沃尔玛", "ticker": "WMT", "sector": "消費", "region": "美股"},
    {"name": "可口可乐", "ticker": "KO", "sector": "消費", "region": "美股"},
    {"name": "百事", "ticker": "PEP", "sector": "消費", "region": "美股"},
    {"name": "麦当劳", "ticker": "MCD", "sector": "消費", "region": "美股"},
    {"name": "星巴克", "ticker": "SBUX", "sector": "消費", "region": "美股"},
    {"name": "耐克", "ticker": "NKE", "sector": "消費", "region": "美股"},
    {"name": "宝洁", "ticker": "PG", "sector": "消費", "region": "美股"},
    {"name": "家得宝", "ticker": "HD", "sector": "消費", "region": "美股"},
    {"name": "迪士尼", "ticker": "DIS", "sector": "消費", "region": "美股"},
    {"name": "Booking", "ticker": "BKNG", "sector": "互聯網", "region": "美股"},
    # --- 美股 · 醫藥 ---
    {"name": "礼来", "ticker": "LLY", "sector": "醫藥", "region": "美股"},
    {"name": "诺和诺德", "ticker": "NVO", "sector": "醫藥", "region": "美股 ADR"},
    {"name": "联合健康", "ticker": "UNH", "sector": "醫藥", "region": "美股"},
    {"name": "强生", "ticker": "JNJ", "sector": "醫藥", "region": "美股"},
    {"name": "辉瑞", "ticker": "PFE", "sector": "醫藥", "region": "美股"},
    {"name": "默克", "ticker": "MRK", "sector": "醫藥", "region": "美股"},
    {"name": "艾伯维", "ticker": "ABBV", "sector": "醫藥", "region": "美股"},
    {"name": "赛默飞", "ticker": "TMO", "sector": "醫藥", "region": "美股"},
    {"name": "直觉外科", "ticker": "ISRG", "sector": "醫藥", "region": "美股"},
    # --- 美股 · 金融 ---
    {"name": "摩根大通", "ticker": "JPM", "sector": "金融", "region": "美股"},
    {"name": "伯克希尔哈撒韦", "ticker": "BRK-B", "sector": "金融", "region": "美股"},
    {"name": "美国银行", "ticker": "BAC", "sector": "金融", "region": "美股"},
    {"name": "富国银行", "ticker": "WFC", "sector": "金融", "region": "美股"},
    {"name": "高盛", "ticker": "GS", "sector": "金融", "region": "美股"},
    {"name": "摩根士丹利", "ticker": "MS", "sector": "金融", "region": "美股"},
    {"name": "贝莱德", "ticker": "BLK", "sector": "金融", "region": "美股"},
    {"name": "美国运通", "ticker": "AXP", "sector": "金融", "region": "美股"},
    # --- 美股 · 能源 / 工業 / 材料 / 公用 ---
    {"name": "埃克森美孚", "ticker": "XOM", "sector": "能源", "region": "美股"},
    {"name": "雪佛龙", "ticker": "CVX", "sector": "能源", "region": "美股"},
    {"name": "康菲石油", "ticker": "COP", "sector": "能源", "region": "美股"},
    {"name": "卡特彼勒", "ticker": "CAT", "sector": "工業", "region": "美股"},
    {"name": "波音", "ticker": "BA", "sector": "工業", "region": "美股"},
    {"name": "雷神技术", "ticker": "RTX", "sector": "工業", "region": "美股"},
    {"name": "通用电气", "ticker": "GE", "sector": "工業", "region": "美股"},
    {"name": "霍尼韦尔", "ticker": "HON", "sector": "工業", "region": "美股"},
    {"name": "洛克希德马丁", "ticker": "LMT", "sector": "工業", "region": "美股"},
    {"name": "联合太平洋铁路", "ticker": "UNP", "sector": "工業", "region": "美股"},
    {"name": "林德", "ticker": "LIN", "sector": "材料", "region": "美股"},
    {"name": "宣伟", "ticker": "SHW", "sector": "材料", "region": "美股"},
    {"name": "纽蒙特矿业", "ticker": "NEM", "sector": "材料", "region": "美股"},
    {"name": "新纪元能源", "ticker": "NEE", "sector": "公用事業", "region": "美股"},
    {"name": "美国铁塔", "ticker": "AMT", "sector": "房地產", "region": "美股"},
    {"name": "普洛斯", "ticker": "PLD", "sector": "房地產", "region": "美股"},
    # --- 美股 · 通信 / 汽車 ---
    {"name": "美国电话电报", "ticker": "T", "sector": "電信", "region": "美股"},
    {"name": "威瑞森", "ticker": "VZ", "sector": "電信", "region": "美股"},
    {"name": "T-Mobile", "ticker": "TMUS", "sector": "電信", "region": "美股"},
    {"name": "特斯拉", "ticker": "TSLA", "sector": "汽車", "region": "美股"},
    {"name": "通用汽车", "ticker": "GM", "sector": "汽車", "region": "美股"},
    {"name": "福特汽车", "ticker": "F", "sector": "汽車", "region": "美股"},
    # --- 加密相關 ---
    {"name": "Coinbase", "ticker": "COIN", "sector": "金融", "region": "美股"},
    {"name": "MicroStrategy", "ticker": "MSTR", "sector": "科技", "region": "美股"},
    {"name": "MARA Holdings", "ticker": "MARA", "sector": "科技", "region": "美股"},
    {"name": "iShares比特幣信託", "ticker": "IBIT", "sector": "商品", "region": "美股 ETF"},
    # --- 中概股（納斯達克金龍） ---
    {"name": "阿里巴巴", "ticker": "BABA", "sector": "互聯網", "region": "中概股"},
    {"name": "百度", "ticker": "BIDU", "sector": "互聯網", "region": "中概股"},
    {"name": "京東", "ticker": "JD", "sector": "互聯網", "region": "中概股"},
    {"name": "網易", "ticker": "NTES", "sector": "互聯網", "region": "中概股"},
    {"name": "蔚來", "ticker": "NIO", "sector": "汽車", "region": "中概股"},
    {"name": "小鵬汽車", "ticker": "XPEV", "sector": "汽車", "region": "中概股"},
    {"name": "理想汽車", "ticker": "LI", "sector": "汽車", "region": "中概股"},
    {"name": "哔哩哔哩", "ticker": "BILI", "sector": "互聯網", "region": "中概股"},
    {"name": "腾讯音乐", "ticker": "TME", "sector": "互聯網", "region": "中概股"},
    {"name": "贝壳找房", "ticker": "BEKE", "sector": "房地產", "region": "中概股"},
    {"name": "百胜中国", "ticker": "YUMC", "sector": "消費", "region": "中概股"},
    {"name": "携程", "ticker": "TCOM", "sector": "互聯網", "region": "中概股"},
    # --- 港股（恒指核心，未在現有 168 家內） ---
    {"name": "小米集团", "ticker": "1810.HK", "sector": "科技", "region": "港股"},
    {"name": "比亚迪股份", "ticker": "1211.HK", "sector": "汽車", "region": "港股"},
    {"name": "中国银行", "ticker": "3988.HK", "sector": "金融", "region": "港股"},
    {"name": "汇丰控股", "ticker": "0005.HK", "sector": "金融", "region": "港股"},
    {"name": "中国人寿", "ticker": "2628.HK", "sector": "金融", "region": "港股"},
    {"name": "中国神华", "ticker": "1088.HK", "sector": "能源", "region": "港股"},
    {"name": "药明生物", "ticker": "2269.HK", "sector": "醫藥", "region": "港股"},
    {"name": "安踏体育", "ticker": "2020.HK", "sector": "消費", "region": "港股"},
    {"name": "李宁", "ticker": "2331.HK", "sector": "消費", "region": "港股"},
    {"name": "联想集团", "ticker": "0992.HK", "sector": "科技", "region": "港股"},
    {"name": "中石化", "ticker": "0386.HK", "sector": "能源", "region": "港股"},
    # --- A股（滬深300核心，未在現有 168 家內） ---
    {"name": "贵州茅台", "ticker": "600519.SS", "sector": "消費", "region": "A股"},
    {"name": "中国平安", "ticker": "601318.SS", "sector": "金融", "region": "A股"},
    {"name": "招商银行", "ticker": "600036.SS", "sector": "金融", "region": "A股"},
    {"name": "宁德时代", "ticker": "300750.SZ", "sector": "汽車", "region": "A股"},
    {"name": "长江电力", "ticker": "600900.SS", "sector": "公用事業", "region": "A股"},
    {"name": "恒瑞医药", "ticker": "600276.SS", "sector": "醫藥", "region": "A股"},
    {"name": "迈瑞医疗", "ticker": "300760.SZ", "sector": "醫藥", "region": "A股"},
    {"name": "海康威视", "ticker": "002415.SZ", "sector": "科技", "region": "A股"},
    {"name": "美的集团", "ticker": "000333.SZ", "sector": "消費", "region": "A股"},
    {"name": "格力电器", "ticker": "000651.SZ", "sector": "消費", "region": "A股"},
    {"name": "伊利股份", "ticker": "600887.SS", "sector": "消費", "region": "A股"},
    {"name": "中国中免", "ticker": "601888.SS", "sector": "消費", "region": "A股"},
    {"name": "兴业银行", "ticker": "601166.SS", "sector": "金融", "region": "A股"},
    {"name": "平安银行", "ticker": "000001.SZ", "sector": "金融", "region": "A股"},
    {"name": "万华化学", "ticker": "600309.SS", "sector": "材料", "region": "A股"},
    {"name": "海螺水泥", "ticker": "600585.SS", "sector": "材料", "region": "A股"},
    {"name": "立讯精密", "ticker": "002475.SZ", "sector": "科技", "region": "A股"},
    {"name": "东方财富", "ticker": "300059.SZ", "sector": "金融", "region": "A股"},
    {"name": "金山办公", "ticker": "688111.SS", "sector": "科技", "region": "A股"},
    {"name": "隆基绿能", "ticker": "601012.SS", "sector": "科技", "region": "A股"},
    {"name": "中国联通", "ticker": "600050.SS", "sector": "電信", "region": "A股"},
    {"name": "保利发展", "ticker": "600048.SS", "sector": "房地產", "region": "A股"},
    {"name": "万科A", "ticker": "000002.SZ", "sector": "房地產", "region": "A股"},
    {"name": "中国建筑", "ticker": "601668.SS", "sector": "工業", "region": "A股"},
    # --- 美股補充 ---
    {"name": "雅培", "ticker": "ABT", "sector": "醫藥", "region": "美股"},
    {"name": "吉利德科學", "ticker": "GILD", "sector": "醫藥", "region": "美股"},
    {"name": "財捷", "ticker": "INTU", "sector": "科技", "region": "美股"},
    {"name": "優步", "ticker": "UBER", "sector": "互聯網", "region": "美股"},
    {"name": "愛彼迎", "ticker": "ABNB", "sector": "互聯網", "region": "美股"},
    {"name": "Shopify", "ticker": "SHOP", "sector": "互聯網", "region": "美股"},
    {"name": "IBM", "ticker": "IBM", "sector": "科技", "region": "美股"},
    {"name": "思科", "ticker": "CSCO", "sector": "科技", "region": "美股"},
    {"name": "應用材料", "ticker": "AMAT", "sector": "科技", "region": "美股"},
    {"name": "邁威爾科技", "ticker": "MRVL", "sector": "科技", "region": "美股"},
    {"name": "嘉信理財", "ticker": "SCHW", "sector": "金融", "region": "美股"},
    {"name": "標普全球", "ticker": "SPGI", "sector": "金融", "region": "美股"},
    {"name": "菲利普莫里斯", "ticker": "PM", "sector": "消費", "region": "美股"},
    {"name": "億滋國際", "ticker": "MDLZ", "sector": "消費", "region": "美股"},
    {"name": "迪爾公司", "ticker": "DE", "sector": "工業", "region": "美股"},
    # --- 港股補充 ---
    {"name": "蒙牛乳業", "ticker": "2319.HK", "sector": "消費", "region": "港股"},
    {"name": "龍湖集團", "ticker": "0960.HK", "sector": "房地產", "region": "港股"},
    {"name": "長實集團", "ticker": "1113.HK", "sector": "房地產", "region": "港股"},
    {"name": "華潤啤酒", "ticker": "0291.HK", "sector": "消費", "region": "港股"},
    # --- A股補充 ---
    {"name": "中國銀行", "ticker": "601988.SS", "sector": "金融", "region": "A股"},
    {"name": "中國太保", "ticker": "601601.SS", "sector": "金融", "region": "A股"},
    {"name": "上汽集團", "ticker": "600104.SS", "sector": "汽車", "region": "A股"},
    {"name": "京東方A", "ticker": "000725.SZ", "sector": "科技", "region": "A股"},
    {"name": "三一重工", "ticker": "600031.SS", "sector": "工業", "region": "A股"},
    {"name": "科大訊飛", "ticker": "002230.SZ", "sector": "科技", "region": "A股"},
    {"name": "中際旭創", "ticker": "300308.SZ", "sector": "科技", "region": "A股"},
    # --- 全球補充 ---
    {"name": "本田汽車", "ticker": "7267.T", "sector": "汽車", "region": "日本"},
    {"name": "信越化學", "ticker": "4063.T", "sector": "材料", "region": "日本"},
    {"name": "瑞可利", "ticker": "6098.T", "sector": "工業", "region": "日本"},
    {"name": "羅氏製藥", "ticker": "ROG.SW", "sector": "醫藥", "region": "歐洲"},
    {"name": "賽諾菲", "ticker": "SAN.PA", "sector": "醫藥", "region": "歐洲"},
    {"name": "聯合利華", "ticker": "UL", "sector": "消費", "region": "歐洲"},
    # --- 全球龍頭 ---
    {"name": "路威酩轩", "ticker": "MC.PA", "sector": "消費", "region": "歐洲"},
    {"name": "西门子", "ticker": "SIE.DE", "sector": "工業", "region": "歐洲"},
    {"name": "空中客车", "ticker": "AIR.PA", "sector": "工業", "region": "歐洲"},
    {"name": "诺华制药", "ticker": "NVS", "sector": "醫藥", "region": "歐洲"},
    {"name": "丰田汽车", "ticker": "7203.T", "sector": "汽車", "region": "日本"},
    {"name": "索尼集团", "ticker": "6758.T", "sector": "科技", "region": "日本"},
    {"name": "软银集团", "ticker": "9984.T", "sector": "科技", "region": "日本"},
    {"name": "三菱UFJ金融", "ticker": "8306.T", "sector": "金融", "region": "日本"},
    {"name": "日立制作所", "ticker": "6501.T", "sector": "工業", "region": "日本"},
    {"name": "任天堂", "ticker": "7974.T", "sector": "科技", "region": "日本"},
    {"name": "迅销（优衣库）", "ticker": "9983.T", "sector": "消費", "region": "日本"},
    {"name": "信实工业", "ticker": "RELIANCE.NS", "sector": "能源", "region": "印度"},
    {"name": "塔塔咨询", "ticker": "TCS.NS", "sector": "科技", "region": "印度"},
    {"name": "HDFC银行", "ticker": "HDFCBANK.NS", "sector": "金融", "region": "印度"},
    {"name": "印孚瑟斯", "ticker": "INFY", "sector": "科技", "region": "印度 ADR"},
    {"name": "巴西石油", "ticker": "PBR", "sector": "能源", "region": "新興市場"},
    {"name": "淡水河谷", "ticker": "VALE", "sector": "材料", "region": "新興市場"},
    {"name": "伊塔乌银行", "ticker": "ITUB", "sector": "金融", "region": "新興市場"},
]

# 熱門加厚清單（迭代 2 深度版對象；迭代 1 先標記「深度版即將上線」）
HOT_COMPANIES = {"英伟达", "微软", "Apple", "Google", "Amazon", "Meta", "台積電", "AMD",
                 "Broadcom", "美光科技", "Palantir", "阿里巴巴", "腾讯", "拼多多", "BYD",
                 "Tesla", "宁德时代", "埃克森美孚", "JPMorgan", "Berkshire",
                 "Eli Lilly", "诺和诺德", "Coinbase", "MicroStrategy"}

HOT_TICKERS = {"NVDA", "MSFT", "AAPL", "GOOGL", "AMZN", "META", "TSM", "AMD",
              "AVGO", "MU", "PLTR", "9988.HK", "0700.HK", "PDD", "1211.HK",
              "TSLA", "300750.SZ", "XOM", "JPM", "BRK-B", "LLY", "NVO",
              "COIN", "MSTR"}

# 分析師評級刻度（recommendationMean 1.0=強力買入 … 5.0=賣出）
REC_SCALE = [(1.5, "強力買入"), (2.5, "買入"), (3.5, "持有"), (4.5, "減持"), (99, "賣出")]


def slugify(name):
    return re.sub(r'[\\/:*?"<>|]', "-", name).strip()


# ---------------------------------------------------------------------------
# 2. 基本面抓取（Yahoo quoteSummary + 1y 日線；失敗不影響建站）
# ---------------------------------------------------------------------------

def _yahoo_json(url, cookie_jar=None, timeout=10):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    opener = urllib.request.build_opener()
    if cookie_jar is not None:
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
    with opener.open(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def _get_crumb(cookie_jar):
    """getcrumb 回傳的是裸字串（非 JSON），不能用 json.loads。"""
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(cookie_jar))
    try:
        req = urllib.request.Request("https://fc.yahoo.com", headers={"User-Agent": UA})
        opener.open(req, timeout=6)
    except Exception:
        pass  # fc.yahoo.com 常回 404，不影響
    try:
        req = urllib.request.Request("https://query1.finance.yahoo.com/v1/test/getcrumb",
                                     headers={"User-Agent": UA})
        with opener.open(req, timeout=6) as resp:
            return resp.read().decode("utf-8").strip()
    except Exception:
        return None


def fetch_fundamentals(symbols, verbose=True):
    """抓取各代碼的基本面（quoteSummary）與 1y 日線。回傳 {sym: data}。"""
    import http.cookiejar
    jar = http.cookiejar.CookieJar()
    crumb = _get_crumb(jar)
    if not crumb:
        if verbose:
            print("  ✗ Yahoo crumb 取得失敗，基本面抓取跳過")
        return {}
    mods = ("financialData,defaultKeyStatistics,summaryProfile,calendarEvents,"
            "earningsTrend,recommendationTrend,institutionOwnership,summaryDetail,"
            "incomeStatementHistory,cashflowStatementHistory")
    out = {}
    syms = sorted(set(s for s in symbols if s))
    for i, sym in enumerate(syms):
        entry = {"sym": sym}
        try:
            url = ("https://query1.finance.yahoo.com/v10/finance/quoteSummary/"
                   f"{urllib.parse.quote(sym)}?modules={mods}&crumb={urllib.parse.quote(crumb)}")
            d = _yahoo_json(url, jar)
            res = (d.get("quoteSummary", {}).get("result") or [None])[0]
            if res:
                entry["qs"] = res
        except Exception as e:
            if verbose and i < 5:
                print(f"  ✗ qs {sym}: {e}")
        try:
            url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
                   f"{urllib.parse.quote(sym)}?range=1y&interval=1d")
            d = _yahoo_json(url, jar)
            r = d["chart"]["result"][0]
            closes = [c for c in r["indicators"]["quote"][0]["close"] if c is not None]
            vols = [v for v in r["indicators"]["quote"][0]["volume"] if v is not None]
            entry["closes"] = closes
            entry["vols"] = vols
        except Exception:
            pass
        if entry.get("qs") or entry.get("closes"):
            out[sym] = entry
        if verbose and (i % 25 == 0):
            print(f"    基本面 {i+1}/{len(syms)} …")
        time.sleep(0.3)
    return out


def load_or_fetch_fundamentals(tickers, no_market):
    if not no_market:
        print(f"== 3.6/4 抓取個股基本面與 1y 行情（{len([t for t in tickers if t])} 個代碼，約 4-6 分鐘）==")
        data = fetch_fundamentals(list(tickers) + ["SPY"])
        with open(FUND_CACHE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        print(f"  ✓ 基本面快取已寫入（{len(data)} 檔，{FUND_CACHE}）")
        return data
    if os.path.exists(FUND_CACHE):
        data = json.load(open(FUND_CACHE, encoding="utf-8"))
        print(f"== 3.6/4 使用基本面快取（{len(data)} 檔）==")
        return data
    print("== 3.6/4 無基本面快取，個股頁降級為基礎數據 ==")
    return {}


# ---------------------------------------------------------------------------
# 3. 估值與技術面計算
# ---------------------------------------------------------------------------

def _g(section, key):
    """從 quoteSummary 模組取值：section.key.raw，缺則 None。"""
    try:
        v = section.get(key) if section else None
        if isinstance(v, dict):
            return v.get("raw")
        return v
    except Exception:
        return None


def _dcf(fcf_ttm, g, r, tg, shares, years=5):
    if not fcf_ttm or not shares or r <= tg:
        return None
    pv, f = 0.0, fcf_ttm
    for t in range(1, years + 1):
        f *= (1 + g)
        pv += f / (1 + r) ** t
    tv = f * (1 + tg) / (r - tg) / (1 + r) ** years
    return (pv + tv) / shares


def compute_stock(company, quotes, fund, sector_peers, spy_closes=None):
    """由公司資料 + 行情 + 基本面計算個股分析頁所需數據。"""
    ticker = company.get("ticker")
    s = {
        "name": company["name"], "ticker": ticker, "sector": company.get("sector", ""),
        "region": company.get("region", ""), "score": company.get("score"),
        "verdict": company.get("verdict"), "verdict_class": company.get("verdict_class"),
        "summary": company.get("summary"),
        "reports": company.get("reports", []),
        "hot": company["name"] in HOT_COMPANIES or ticker in HOT_TICKERS,
        "in_combo": company.get("_in_combo", False),
        "quote": quotes.get(ticker) or {},
    }
    qs = (fund or {}).get("qs") or {}
    fd = qs.get("financialData") or {}
    ks = qs.get("defaultKeyStatistics") or {}
    prof = qs.get("summaryProfile") or {}
    det = qs.get("summaryDetail") or {}
    cal = qs.get("calendarEvents") or {}
    inst = qs.get("institutionOwnership") or {}
    # ---- 財務 ----
    s["finance"] = {
        "margins": _g(fd, "profitMargins"), "op_margins": _g(fd, "operatingMargins"),
        "roe": _g(fd, "returnOnEquity"), "rev_growth": _g(fd, "revenueGrowth"),
        "earn_growth": _g(fd, "earningsGrowth"), "fcf": _g(fd, "freeCashflow"),
        "debt_equity": _g(fd, "debtToEquity"), "cash": _g(fd, "totalCash"),
        "debt": _g(fd, "totalDebt"), "revenue": _g(fd, "totalRevenue"),
        "ebitda": _g(fd, "ebitda"), "eps": _g(ks, "trailingEps"),
    }
    # ---- 估值倍數 ----
    price = (s["quote"] or {}).get("price")
    pe = _g(ks, "trailingPE")
    if pe is None and price and _g(ks, "trailingEps"):
        pe = price / _g(ks, "trailingEps")
    s["multiples"] = {
        "pe": pe, "fwd_pe": _g(ks, "forwardPE"),
        "pb": _g(ks, "priceToBook"), "ps": _g(ks, "priceToSales"),
        "evebitda": _g(ks, "enterpriseToEbitda"), "peg": _g(ks, "pegRatio"),
        "dy": _g(det, "dividendYield"), "beta": _g(ks, "beta"),
        "mktcap": _g(ks, "marketCap"), "shares": _g(ks, "sharesOutstanding"),
    }
    # ---- DCF ----
    shares = s["multiples"]["shares"] or (
        s["multiples"]["mktcap"] / price if (s["multiples"]["mktcap"] and price) else None)
    g_raw = s["finance"]["earn_growth"] or s["finance"]["rev_growth"] or 0.05
    g = max(-0.05, min(0.25, g_raw if isinstance(g_raw, (int, float)) else 0.05))
    r0 = 0.085
    dcf = {"g": g, "r": r0, "fcf": s["finance"]["fcf"], "shares": shares,
           "gs": [max(-0.05, g - 0.03), g, g + 0.03]}
    dcf["value"] = _dcf(s["finance"]["fcf"], g, r0, 0.025, shares)
    dcf["matrix"] = []
    for rr in (0.075, 0.085, 0.095):
        row = []
        for gg in dcf["gs"]:
            v = _dcf(s["finance"]["fcf"], gg, rr, 0.025, shares)
            row.append(round(v, 2) if v else None)
        dcf["matrix"].append({"r": rr, "cells": row})
    dcf["pessimistic"] = dcf["matrix"][2]["cells"][0]
    dcf["neutral"] = dcf["matrix"][1]["cells"][1]
    dcf["optimistic"] = dcf["matrix"][0]["cells"][2]
    if price and dcf["neutral"]:
        dcf["premium"] = round(dcf["neutral"] / price - 1, 4)
    s["dcf"] = dcf
    # ---- DDM（分紅股） ----
    dy = s["multiples"]["dy"]
    dps = _g(det, "dividendRate")
    s["ddm"] = None
    if dy and dps and g < 0.075:
        v = dps * (1 + g) / (0.075 - g)
        s["ddm"] = {"value": round(v, 2), "dps": dps, "g": g,
                    "premium": round(v / price - 1, 4) if price else None}
    # ---- 相對估值 vs 同業 ----
    rel = {}
    for k in ("pe", "pb", "ps", "evebitda"):
        own = s["multiples"][k]
        peers = [p for p in sector_peers.get(company.get("sector", ""), []) if p]
        if own and peers:
            med = sorted(peers)[len(peers) // 2]
            rel[k] = {"own": round(own, 2), "median": round(med, 2),
                      "premium": round(own / med - 1, 4) if med else None}
    s["relative"] = rel
    # ---- 技術面 ----
    closes = (fund or {}).get("closes") or []
    vols = (fund or {}).get("vols") or []
    ta = {"n": len(closes)}
    if len(closes) >= 50:
        ta["ma50"] = round(sum(closes[-50:]) / 50, 2)
    if len(closes) >= 200:
        ta["ma200"] = round(sum(closes[-200:]) / 200, 2)
    if len(closes) >= 60:
        ta["support"] = round(min(closes[-60:]), 2)
        ta["resistance"] = round(max(closes[-60:]), 2)
    if len(closes) >= 250:
        ta["52w_low"] = round(min(closes[-250:]), 2)
        ta["52w_high"] = round(max(closes[-250:]), 2)
    if len(closes) >= 2:
        ta["ret_1y"] = round(closes[-1] / closes[0] - 1, 4) if closes[0] else None
    if vols and len(vols) >= 70:
        v10 = sum(vols[-10:]) / 10
        v60 = sum(vols[-70:-10]) / 60
        ta["vol_trend"] = round(v10 / v60 - 1, 4) if v60 else None
    if spy_closes and len(spy_closes) >= 2 and len(closes) >= 2 and closes[0] and spy_closes[0]:
        spy_ret = spy_closes[-1] / spy_closes[0] - 1
        ta["spy_1y"] = round(spy_ret, 4)
        ta["rs"] = round(ta["ret_1y"] - spy_ret, 4)
    s["ta"] = ta
    # ---- 機構持倉 ----
    ol = inst.get("ownershipList") or {}
    if isinstance(ol, dict):
        holders = ol.get("HoldingsList") or ol.get("holdingsList") or []
    else:
        holders = ol or []  # Yahoo 有時直接給 list
    s["holders"] = [
        {"org": (h.get("organization") or "")[:40],
         "pct": round(_g({"v": h.get("pctHeld")}, "v") * 100, 2)
                if _g({"v": h.get("pctHeld")}, "v") is not None else None,
         "value": _g({"v": h.get("value")}, "v")}
        for h in holders[:5]
    ]
    s["inst_pct"] = _g(ks, "heldPercentInstitutions")
    # ---- 分析師 ----
    s["analyst"] = {
        "target": _g(fd, "targetMeanPrice"),
        "n": _g(fd, "numberOfAnalystOpinions"),
        "rec": _g(fd, "recommendationMean"),
        "low": _g(fd, "targetLowPrice"), "high": _g(fd, "targetHighPrice"),
    }
    # ---- 催化劑（財報日） ----
    ed = ((cal.get("earnings") or {}).get("earningsDate") or [])
    s["earnings_date"] = None
    for d in ed:
        if isinstance(d, dict) and d.get("fmt"):
            s["earnings_date"] = d["fmt"]
            break
    s["profile"] = {
        "biz": prof.get("longBusinessSummary") or "",
        "industry": prof.get("industry") or "",
        "website": prof.get("website") or "",
        "country": prof.get("country") or "",
    }
    # ---- 深研加厚（熱門公司；數據均來自已抓取的 quoteSummary 模組） ----
    offs = prof.get("companyOfficers") or []
    s["officers"] = [{"name": (o.get("name") or "")[:30], "age": o.get("age"),
                      "title": (o.get("title") or "")[:40]}
                     for o in (offs if isinstance(offs, list) else [])[:5]]
    s["income_hist"] = []
    ihl = (qs.get("incomeStatementHistory") or {}).get("incomeStatementHistory") or []
    for st_ in (ihl if isinstance(ihl, list) else [])[:4]:
        yr = ((st_.get("endDate") or {}).get("fmt") or "")[:4]
        if yr:
            s["income_hist"].append({
                "year": yr,
                "revenue": _g({"v": st_.get("totalRevenue")}, "v"),
                "gross": _g({"v": st_.get("grossProfit")}, "v"),
                "net_income": _g({"v": st_.get("netIncome")}, "v")})
    # Yahoo 免費接口已停供現金流明細/評級分布/管理層，改用 TTM 摘要
    s["shr"] = {
        "dps": _g(det, "dividendRate"), "dy": dy,
        "payout": _g(det, "payoutRatio"),
        "ocf": _g(fd, "operatingCashflow"), "fcf": _g(fd, "freeCashflow")}
    pmap = {"0q": "本期", "+1q": "下季", "0y": "今年", "+1y": "下一年", "+5y": "5年複合"}
    trl = (qs.get("earningsTrend") or {}).get("trend") or []
    s["earn_trend"] = [{"period": pmap.get(t.get("period"), t.get("period")),
                        "growth": _g({"v": t.get("growth")}, "v")}
                       for t in (trl if isinstance(trl, list) else [])[:4]]
    return s


# ---------------------------------------------------------------------------
# 4. 個股頁生成
# ---------------------------------------------------------------------------

def render_stock_pages(companies, quotes, fund_data, in_combo_names, fund_holdings=None,
                       polit_holdings=None):
    """為每家公司生成 stocks/<name>.html；回傳統計。"""
    if os.path.isdir(STOCKS_DIR):
        shutil.rmtree(STOCKS_DIR)
    os.makedirs(STOCKS_DIR, exist_ok=True)
    spy_closes = (fund_data.get("SPY") or {}).get("closes") or []
    sector_peers = {}
    for c in companies:
        for k, v in compute_stock(c, quotes, fund_data.get(c.get("ticker") or ""), {}).get("multiples", {}).items():
            if k not in ("pe", "pb", "ps", "evebitda"):
                continue
            sector_peers.setdefault(c.get("sector", ""), []).append(v)
    done = ok = 0
    for c in companies:
        c2 = dict(c)
        c2["_in_combo"] = c["name"] in in_combo_names
        st = compute_stock(c2, quotes, fund_data.get(c.get("ticker") or ""), sector_peers,
                           spy_closes)
        st["rel_peers_n"] = len(sector_peers.get(c.get("sector", ""), []))
        st["fund_mentions"] = (fund_holdings or {}).get(c.get("ticker") or "") or []
        st["polit_mentions"] = (polit_holdings or {}).get(c.get("ticker") or "") or []
        page = slugify(st["name"]) + ".html"
        html = STOCK_TEMPLATE.format(
            name=st["name"], title=st["name"], json=json.dumps(st, ensure_ascii=False),
            rel="../")  # 個股頁在 stocks/ 子目錄，靜態資源需回到根目錄
        with open(os.path.join(STOCKS_DIR, page), "w", encoding="utf-8") as f:
            f.write(html)
        done += 1
        if st["finance"].get("fcf") or st["multiples"].get("pe"):
            ok += 1
    return {"pages": done, "with_data": ok}


STOCK_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — AIShan+ 個股分析</title>
<meta name="description" content="{name} 的個股獨立分析：基本面、DCF 估值、技術面、機構持倉與催化劑。">
<link rel="stylesheet" href="{rel}css/style.css">
<link rel="stylesheet" href="{rel}css/stock.css">
</head>
<body data-page="stock">
<header class="site-nav">
  <div class="container">
    <a class="brand" href="{rel}index.html"><span class="mark">◆</span> AIShan+ <span>投研網站</span></a>
    <nav>
      <a href="{rel}index.html">首頁</a>
      <a href="{rel}companies.html">公司</a>
      <a href="{rel}reports.html">報告</a>
      <a href="{rel}trackrecord.html">組合</a>
      <a href="{rel}allocation.html">配置</a>
      <a href="{rel}fed.html">美聯儲</a>
      <a href="{rel}valuation.html">估值</a>
      <a href="{rel}events.html">事件</a>
      <a href="{rel}funds.html">基金</a>
      <a href="{rel}politician.html">政要</a>
      <a href="{rel}china.html">中國</a>
      <a href="{rel}scenarios.html">回測</a>
      <a href="{rel}risk.html">風險</a>
    </nav>
        <button class="btn-update" id="btn-update-data" title="觸發 GitHub Actions 重新抓取行情並重建報告">🔄 更新數據</button>
    <span class="update-status" id="update-status" hidden></span>
    <button class="theme-toggle" aria-label="切換亮暗主題"></button>
  </div>
</header>

<main class="container" id="stock-root" style="padding-top:32px;">
  <p class="section-desc">載入中…</p>
</main>

<footer class="site-foot">
  <div class="container">
    <div class="links">
      <a href="https://github.com/aliu29775-bot/ai_investment_tool_aliu" target="_blank" rel="noopener">GitHub：AIShan+</a>
    </div>
    <p>本網站為研究框架展示，所有內容（包括公司評分、結論與估值模型）均為自動計算與公開資料整理，<strong>不構成任何投資建議</strong>。投資有風險，決策需謹慎。</p>
  </div>
</footer>

<script type="application/json" id="stock-data">{json}</script>
<script src="{rel}js/data.js"></script>
<script src="{rel}js/stock.js"></script>
<script src="{rel}js/app.js"></script>
</body>
</html>
"""
