#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AIShan+ 投研網站 — 一鍵建站腳本

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
import html
import http.cookiejar
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
import urllib.request
from collections import Counter, defaultdict

from stock_pages import (EXTRA_COMPANIES, load_or_fetch_fundamentals,
                         render_stock_pages, slugify, _get_crumb, _yahoo_json)

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

# 新版報告（無「綜合评分/綜合评级」行）的抽取正則（注意 [ \t]* 而非 \s*，避免吞換行跨行誤匹配）：
# 結論摘要：「結論摘要：**观望 / ...**」→ 取斜線前的結論詞
RE_CONCL_SUMMARY = re.compile(r"[结結]论摘要[：:][ \t]*\**([^/\n*]{1,14})")
# 「评级：观望，不买入。」（跳過「评级：A级（信息充裕）」類；加粗冒號兼容；負向斷言排除「信息丰富度评级」）
RE_RATING_V = re.compile(r"(?<!丰富度)评级\**[：:][ \t]*\**(?!\s*[ABC]\s*[级級])([^。\n|]{1,30}?)(?=[。\n|])")
# 字母評級：「**评级: B+ —— 一流产品人…**」
RE_RATING_GRADE = re.compile(r"(?<!丰富度)评级\**[：:][ \t]*\**([A-D][+-]?)[ \t]*([—\-－][^\n。]{0,26})?")
RE_SUGGEST_V = re.compile(r"[建]议\**[：:]?[ \t]*\**([^。\n|]{1,26}?)(?=[。\n|])")
# 「結論**：…」/「核心結論：…」/「明確結論：…」
RE_CONCL_V = re.compile(r"(?:核心|明确|明確)?[结結]论\**[：:][ \t]*\**([^。\n|]{1,80}?)(?=[。\n|])")
# 行內「一句话結論：…」（新版報告不帶引用塊）
RE_SUMM_INLINE = re.compile(r"一句话[结結]论\**[：:][ \t]*\**([^\n。]{1,60})")
# 四維評分：「生意质量评分：★★★★」行
RE_DIM_INLINE = re.compile(r"((?:生意质量|生意質量|护城河|護城河|管理层|管理層|估值|商业模式|商業模式|商业模式清晰度|商業模式清晰度))[^：:\n]{0,8}评分[：:]\s*(★+[★☆]*)")
# 四維評分表：「| **生意质量** | … | ★★★★☆ |」行
RE_DIM_ROW = re.compile(r"^\s*\|\s*\*{0,2}(生意质量|生意質量|护城河|護城河|管理层|管理層|估值|最大风险|最大風險)[^*|\n]{0,12}\*{0,2}\s*\|")
# 商業模式評分表：「| 商业模式清晰度 | ★★★★★ |」行
RE_BIZ_ROW = re.compile(r"^\s*\|\s*(商业模式清晰度|商業模式清晰度|商业模式|商業模式|生意模式)[^|]*\|\s*(★+[★☆]*)\s*\|")

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
    # 2026-09-26 新增覆蓋：全球大型股與資產配置工具
    "台積電": "TSM", "Berkshire": "BRK-B", "JPMorgan": "JPM", "Visa": "V",
    "Costco": "COST", "Eli Lilly": "LLY", "Broadcom": "AVGO", "ASML": "ASML",
    "京東": "9618.HK", "中芯國際": "0981.HK", "中國移動": "0941.HK",
    "藥明康德": "2359.HK", "香港交易所": "0388.HK", "友邦保險": "1299.HK",
    "TLT": "TLT", "IEF": "IEF", "GLD": "GLD", "DBC": "DBC",
    "紫金礦業": "2899.HK", "Freeport-McMoRan": "FCX", "Barrick": "GOLD",
    # 2026-09-26 第二批新增：美股 S&P500 大型股、生技、量子、電力、歐韓、中資大型股、債券工具
    "UnitedHealth": "UNH", "强生": "JNJ", "強生": "JNJ", "宝洁": "PG", "寶潔": "PG",
    "沃尔玛": "WMT", "沃爾瑪": "WMT", "可口可乐": "KO", "可口可樂": "KO",
    "麦当劳": "MCD", "麥當勞": "MCD", "Salesforce": "CRM", "Oracle": "ORCL",
    "Moderna": "MRNA", "Regeneron": "REGN", "Vertex": "VRTX", "Amgen": "AMGN",
    "IonQ": "IONQ", "Rigetti": "RGTI", "Vistra": "VST",
    "Constellation Energy": "CEG", "NextEra": "NEE",
    "三星電子": "005930.KS", "三星电子": "005930.KS", "LVMH": "MC.PA",
    "愛馬仕": "HESAY", "爱马仕": "HESAY", "Hermès": "HESAY",
    "雀巢": "NSRGY", "Nestlé": "NSRGY", "SAP": "SAP",
    "阿斯利康": "AZN", "AstraZeneca": "AZN",
    "工商銀行": "1398.HK", "工商银行": "1398.HK",
    "建設銀行": "0939.HK", "建设银行": "0939.HK",
    "寧德時代": "300750.SZ", "宁德时代": "300750.SZ",
    "中國海洋石油": "0883.HK", "中国海洋石油": "0883.HK", "中海油": "0883.HK",
    "中國石油": "0857.HK",
    "中信證券": "6030.HK", "中信证券": "6030.HK",
    "工業富聯": "601138.SS", "工业富联": "601138.SS",
    "海光信息": "688041.SS",
    "LQD": "LQD", "HYG": "HYG", "SHY": "SHY", "TIP": "TIP",
}

# 7 家公司橫評的備用評分（README 的 Checklist 表）
FALLBACK_SCORE = {
    "茅台": (4.7, "✅ 通過"), "腾讯": (4.7, "✅ 通過"), "英伟达": (4.3, "✅ 有條件"),
    "美团": (4.0, "✅ 有條件"), "快手": (4.0, "✅ 有條件"),
    "拼多多": (3.8, "❓ 灰色"), "泡泡玛特": (3.7, "❓ 灰色"),
}

# 行業分類（供篩選器與行業分佈使用）
SECTORS = {
    "Apple": "科技", "Amazon": "互聯網", "Netflix": "互聯網", "AMD": "科技",
    "台積電": "科技", "Berkshire": "金融", "JPMorgan": "金融", "Visa": "金融",
    "Costco": "消費", "Eli Lilly": "醫藥", "Broadcom": "科技", "ASML": "科技",
    "京東": "互聯網", "中芯國際": "科技", "中國移動": "電信",
    "藥明康德": "醫藥", "香港交易所": "金融", "友邦保險": "金融",
    "TLT": "債券", "IEF": "債券", "GLD": "黃金", "DBC": "商品",
    "紫金礦業": "材料", "Freeport-McMoRan": "材料", "Barrick": "材料",
    "UnitedHealth": "醫藥", "强生": "醫藥", "宝洁": "消費", "沃尔玛": "消費",
    "可口可乐": "消費", "麦当劳": "消費", "Salesforce": "科技", "Oracle": "科技",
    "Moderna": "醫藥", "Regeneron": "醫藥", "Vertex": "醫藥", "Amgen": "醫藥",
    "IonQ": "科技", "Rigetti": "科技", "Vistra": "公用事業",
    "Constellation Energy": "公用事業", "NextEra": "公用事業",
    "三星電子": "科技", "LVMH": "消費", "愛馬仕": "消費", "雀巢": "消費",
    "SAP": "科技", "阿斯利康": "醫藥",
    "工商銀行": "金融", "建設銀行": "金融", "中信證券": "金融",
    "寧德時代": "工業", "中國海洋石油": "能源", "中國石油": "能源",
    "工業富聯": "科技", "海光信息": "科技",
    "LQD": "債券", "HYG": "債券", "SHY": "債券", "TIP": "債券",
}

SECTOR_RULES = [
    ("醫藥", ("药", "藥", "医", "醫", "康方", "晶泰", "Novo", "Zoetis", "Eli Lilly", "Elekta")),
    ("金融", ("银行", "銀行", "保险", "保險", "平安", "PayPal", "Mastercard", "Visa",
              "Progressive", "Berkshire", "JPMorgan", "招商", "浦发", "交易所", "证券", "證券",
              "蚂蚁", "九坤")),
    ("互聯網", ("腾讯", "騰訊", "拼多多", "美团", "美團", "快手", "阿里巴巴", "Alibaba",
                "京东", "京東", "网易", "網易", "百度", "Meta", "Google", "Amazon",
                "Netflix", "滴滴", "小红书", "唯品会", "搜狐", "腾讯音乐", "汽车之家",
                "Uber", "Prosus", "Booking")),
    ("科技", ("英伟达", "英偉達", "Intel", "AMD", "Qualcomm", "Marvell", "TSM",
              "台積電", "台积电", "SK海力士", "中芯", "Apple", "微软", "微軟", "Adobe",
              "Accenture", "WiseTech", "澜起", "中科飞测", "江波龙", "长光辰芯",
              "华工", "Broadcom", "ASML", "DeepSeek", "MiniMax", "幻方", "月之暗面",
              "Kimi", "智谱", "字节", "宇树", "宇视", "RKLB", "小米", "Bilibili",
              "哔哩哔哩", "liblibAI", "LiblibAI", "openrouter", "OpenRouter", "大普微",
              "智元", "演语", "灵境", "生数", "群核", "耳朵")),
    ("消費", ("茅台", "五粮液", "泸州老窖", "汾酒", "洋河", "Costco", "Nike",
              "lululemon", "泡泡玛特", "海尔", "永新", "NewbornTown", "泡泡", "追觅")),
    ("工業", ("Rheinmetall", "莱茵金属", "SpaceX", "中创智领", "郑煤机")),
    ("能源", ("思格", "GE Vernova")),
    ("汽車", ("BYD", "理想汽车", "理想汽車", "赛力斯", "Tesla", "小鹏", "蔚来",
              "吉利", "长城汽车", "上汽", "哪吒")),
    ("能源", ("神华", "广核", "长江电力", "杰瑞", "Jereh", "中远海控", "中国石油",
              "中石油", "中国石化", "Shell", "Exxon", "电力")),
    ("材料", ("紫金", "藏格", "CMOC", "神火", "兴发", "Freeport", "Barrick", "川润",
              "赛轮", "杭叉", "德业", "英维克", "领益", "绿的", "Nittobo", "金风",
              "Goldwind", "铜", "鋼", "钢")),
    ("電信", ("中國移動", "中国移动")),
    ("公用事業", ("Vistra", "Constellation", "NextEra", "核电", "核電", "電力基建")),
    ("債券", ("TLT", "IEF", "BIL", "LQD", "HYG", "SHY", "TIP", "投資級", "高收益")),
    ("黃金", ("GLD",)),
    ("商品", ("DBC",)),
]


def sector_of(name, titles):
    """依公司名與報告標題推測行業。"""
    if name in SECTORS:
        return SECTORS[name]
    hay = name + " " + " ".join(titles)
    for sec, keys in SECTOR_RULES:
        for k in keys:
            if k in hay:
                return sec
    return "其他"


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
    """從最新報告中萃取評分。回傳 (stars, value, verdict, summary)。
    兩遍式：第一遍用標準標記 + 四維評分兜底；第二遍才用字母評級（信息量較低，避免遮蔽舊文件的四維表）。"""
    score = verdict = summary = None
    files = sorted(
        (r for r in reports if r.get("type") not in ("底稿",)),
        key=lambda r: r["date"], reverse=True,
    )

    def _scan(r, allow_grade):
        nonlocal score, verdict, summary
        p = os.path.join(repo, r["path"])
        if not os.path.exists(p):
            return
        try:
            txt = open(p, encoding="utf-8", errors="replace").read()
        except OSError:
            return
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
                else:
                    score = fallback_score(txt, allow_grade)
        if verdict is None:
            m = RE_VERDICT.search(txt)
            if m:
                v = m.group(1).strip().strip("*").strip()
                # 截斷表格殘留的續文
                v = re.split(r"\*\*[：:]|——|[（(]", v)[0].strip()
                # 過長且無圖標的「綜合评级」多為正文誤匹配（如範例句），捨棄改走兜底
                if len(v) > 14 and not v.startswith(("✅", "❓", "❌")):
                    v = None
                if v:
                    verdict = v[:60]
            if verdict is None:
                m = RE_BUY.search(txt) or RE_PASS.search(txt)
                if m:
                    verdict = m.group(1).strip()[:60]
                else:
                    verdict = fallback_verdict(txt, allow_grade)
        if summary is None:
            m = RE_ONE_LINE.search(txt) or RE_ONE_LINE_H.search(txt)
            if m:
                summary = m.group(1).replace("**", "").strip()[:180]
            else:
                m = RE_SUMM_INLINE.search(txt)
                if m:
                    summary = m.group(1).replace("**", "").strip()[:180]

    for r in files[:50]:
        _scan(r, allow_grade=False)
        if score and verdict and summary:
            return score, verdict, summary
    if score is None or verdict is None:  # 第二遍：字母評級兜底
        for r in files[:50]:
            _scan(r, allow_grade=True)
            if score and verdict and summary:
                break
    return score, verdict, summary


def site_path(p):
    """把 repo 內的報告路徑轉成網站相對路徑（去掉 reports/ 前綴）。"""
    return re.sub(r"^reports/", "", p).replace(".md", ".html")


GRADE_SCORE = {"A+": 4.75, "A": 4.5, "A-": 4.25, "B+": 3.75, "B": 3.5, "B-": 3.25,
               "C+": 2.75, "C": 2.5, "C-": 2.25, "D+": 1.75, "D": 1.5}


def classify_verdict(v):
    """把結論文字歸類為正面/中性/負面（給網站顯示顏色用）。注意「不通過」含「通過」二字，負面須先匹配。"""
    if not v:
        return None
    gm = re.match(r"[A-D][+-]?(?=\s|$|—|－|（|\()", v)
    if gm:  # 字母評級（如「B+ —— 一流产品人…」）
        g = gm.group(0)
        if g.startswith("A") or g == "B+":
            return "positive"
        if g.startswith("B"):
            return "neutral"
        return "negative"
    if "模糊" in v:
        return "neutral"  # 「模糊地带」類（如 PayPal 價值陷阱 vs 低估）
    if re.search(r"不通过|不通過|不买入|不買入|卖出|賣出|减仓|減倉|回避|迴避|清仓|清倉|淘汰|价值陷阱|價值陷阱|生意差|坏行业|壞行業|平庸的生意|太贵|太貴|❌", v):
        return "negative"
    if re.search(r"买入|買入|建仓|建倉|通过|通過|增持|持有待|低估|极好的生意|極好的生意|好生意|好公司|复利机器|複利機器|印钞机|印鈔機|现金制造机|現金製造機|赚钱机器|賺錢機器|✅", v):
        return "positive"
    if re.search(r"灰色|观望|觀望|觀察|观察|持有|中性(?!场景|情景|情形|假设|約|约)|待定|重点关注|重點關注|重点跟踪|重點跟蹤|纳入观察|納入觀察|❓|不确定|不確定", v):
        return "neutral"
    return None


def _star_val(s):
    return s.count("★") + 0.5 * s.count("☆")


def _dims_score(vals, label):
    v = round(sum(vals.values()) / len(vals), 2)
    return {"stars": min(5, max(1, round(v))),
            "value": v,
            "text": ("%s抽取：%s" % (label, ",".join("%s%s" % (k, vals[k]) for k in vals)))[:60]}


def fallback_score(txt, allow_grade=False):
    """新版報告（無「綜合评分」行）的評分抽取：顯式「X评分：★」行 → 四維表星格 → 商業模式評分表 →（第二遍）字母評級。"""
    vals = {}
    for m in RE_DIM_INLINE.finditer(txt):
        vals.setdefault(m.group(1), _star_val(m.group(2)))
    if len(vals) >= 2:
        return _dims_score(vals, "四维评分行")
    for line in txt.splitlines():
        m = RE_DIM_ROW.match(line)
        if not m:
            continue
        dim = m.group(1)
        stars = re.findall(r"(★+[★☆]*)", line)
        if not stars:
            continue
        v = _star_val(stars[-1])
        if dim in ("最大风险", "最大風險"):
            v = max(0.0, 6 - v)  # 風險星級越高越差，反向計分
        if ("确信" in line or "置信" in line) and re.search(r"差|坏|风险|風險", line):
            continue  # 該行評的是「置信度」而非品質，語義相反，跳過
        vals.setdefault(dim, v)
    if len(vals) >= 2:
        return _dims_score(vals, "四维评分表")
    for m in RE_BIZ_ROW.finditer(txt):
        vals.setdefault("商业模式", _star_val(m.group(2)))
    if len(vals) >= 2:
        return _dims_score(vals, "商业模式评分表")
    if allow_grade:
        for m in RE_RATING_GRADE.finditer(txt):
            line = txt[txt.rfind("\n", 0, m.start()) + 1:txt.find("\n", m.start())]
            if "丰富度" in line or re.search(r"管理层|管理層|董事长|董事長|治理|产品人|產品人|团队|團隊", line):
                continue  # 信息丰富度评级或管理层评级，非公司评级
            g = m.group(1)
            if g in GRADE_SCORE:
                return {"stars": min(5, max(1, round(GRADE_SCORE[g]))),
                        "value": GRADE_SCORE[g],
                        "text": "评级抽取：" + g}
    return None


def fallback_verdict(txt, allow_grade=False):
    """新版報告的結論抽取：結論摘要 → 评级：X → 结论：X → 建议：X（需能被 classify 才採納；第二遍才用字母評級）。"""
    m = RE_CONCL_SUMMARY.search(txt)
    if m:
        return m.group(1).strip().strip("*").strip()[:60]
    for pat in (RE_RATING_V, RE_CONCL_V, RE_SUGGEST_V):
        for m in pat.finditer(txt):
            v = m.group(1).strip().strip("*").strip()
            if v.endswith("？"):
                continue  # 章節標題式提問（如「這是一台什麼樣的賺錢機器？」）
            v1 = re.split(r"[，,]", v)[0].strip()
            if classify_verdict(v1):
                return v1[:60]
            if classify_verdict(v):
                return v[:60]
    if allow_grade:
        for m in RE_RATING_GRADE.finditer(txt):
            line = txt[txt.rfind("\n", 0, m.start()) + 1:txt.find("\n", m.start())]
            if "丰富度" in line or re.search(r"管理层|管理層|董事长|董事長|治理|产品人|產品人|团队|團隊", line):
                continue  # 信息丰富度评级或管理层评级，非公司评级
            g = m.group(1)
            ctx = (m.group(2) or "").strip().strip("*").strip()
            return ("%s%s" % (g, ctx))[:60]
    return None

# ---------------------------------------------------------------------------
# 3. 行情抓取（Yahoo Finance，失敗不影響建站）
# ---------------------------------------------------------------------------

# 首頁市場總覽用的主要指數（Yahoo Finance 代碼 → 中文名稱）
MARKET_INDICES = {
    "^HSI": "恒生指數",
    "^GSPC": "標普500",
    "^IXIC": "納斯達克",
    "000300.SS": "滬深300",
    "^VIX": "恐慌指數 VIX",
    "^TNX": "美國10年期國債",
    "DX-Y.NYB": "美元指數",
}


def _fetch_one_quote(sym):
    """抓單一標的 5 日行情（供 fetch_quotes 並行使用）。"""
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           f"{urllib.parse.quote(sym)}?range=5d&interval=1d")
    for attempt in (0, 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode())
            meta = data["chart"]["result"][0]["meta"]
            closes = data["chart"]["result"][0]["indicators"]["quote"][0]["close"]
            valid = [c for c in closes if c is not None]
            price = meta.get("regularMarketPrice") or (valid[-1] if valid else None)
            prev = valid[-2] if len(valid) >= 2 else meta.get("chartPreviousClose")
            if price is None:
                return sym, None, "無報價"
            chg = (price - prev) / prev * 100 if prev else None
            return sym, {
                "price": round(price, 2),
                "currency": meta.get("currency", ""),
                "change_pct": round(chg, 2) if chg is not None else None,
                "asof": time.strftime("%Y-%m-%d"),
                "name": meta.get("shortName") or meta.get("longName") or "",
                "closes": [round(c, 2) for c in valid[-5:]],
            }, None
        except Exception as e:
            if attempt == 1:
                return sym, None, str(e)
            time.sleep(0.4)
    return sym, None, "重試失敗"


def fetch_quotes(symbols, verbose=True, workers=16):
    quotes = {}
    syms = sorted(set(s for s in symbols if s))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(_fetch_one_quote, sym) for sym in syms]
        for fut in as_completed(futs):
            sym, q, err = fut.result()
            if q is not None:
                quotes[sym] = q
                if verbose:
                    print(f"  ✓ {sym:14s} {q['price']:>10.2f} {q.get('currency','')}")
            elif verbose:
                print(f"  ✗ {sym:14s} {err}")
    return quotes


# ---------------------------------------------------------------------------
# 3.5 宏觀數據與資產配置（FRED + Yahoo 資產行情）
# ---------------------------------------------------------------------------

FRED_SERIES = ["CPIAUCSL", "PCEPILFE", "UNRATE", "DGS2", "DGS5", "DGS10", "DGS30",
               "DGS3MO", "DFF", "BAMLH0A0HYM2", "BAMLH0A0HYM2EY", "BAMLC0A0CM", "BAMLC0A0CMEY",
               "DFII10", "GDPC1", "PAYEMS", "T10Y2Y", "T10Y3M", "ICSA", "VIXCLS",
               "BAA10Y",
               "GEPUCURRENT", "USREC", "CSUSHPINSA",
               "DFEDTARU", "DFEDTARL", "WALCL", "PCEPI", "CPILFESL", "NCBCMDPMVCE"]

FRED_CACHE = "/tmp/fred_macro_cache.json"

# FOMC 2026 會議日程（聯儲官網預先公佈；end=決議日）
FOMC_2026 = [("2026-01-28", "1月27–28日"), ("2026-03-18", "3月17–18日"),
             ("2026-04-29", "4月28–29日"), ("2026-06-17", "6月16–17日"),
             ("2026-07-29", "7月28–29日"), ("2026-09-16", "9月15–16日"),
             ("2026-10-28", "10月27–28日"), ("2026-12-09", "12月8–9日")]

ASSET_PROXIES = {"股票": "SPY", "國債": "IEF", "長期國債": "TLT",
                 "商品": "DBC", "黃金": "GLD", "現金": "BIL"}

COMMODITY_FUTURES = [("黃金", "GC=F", "美元/盎司"), ("白銀", "SI=F", "美元/盎司"),
                     ("原油WTI", "CL=F", "美元/桶"), ("銅", "HG=F", "美元/磅")]


def _fetch_one_fred(sid):
    """抓單一 FRED 序列（供 fetch_fred 並行使用）。"""
    csv_path = os.path.join("/tmp", f"fredbuild_{sid}.csv")
    try:
        subprocess.run(
            ["curl", "-4sm", "25", "-o", csv_path,
             f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"],
            check=True, capture_output=True)
        vals = []
        for line in open(csv_path, encoding="utf-8", errors="replace").read().splitlines()[1:]:
            p = line.split(",")
            if len(p) >= 2 and p[1] and p[1] != ".":
                vals.append([p[0], float(p[1])])
        if vals:
            return sid, vals, None
        return sid, None, "空資料"
    except Exception as e:
        return sid, None, str(e)


def fetch_fred(series_ids, cache_file, workers=12):
    """用 curl -4 並行抓 FRED fredgraph.csv（部分網絡 urllib 走 IPv6 會超時）。"""
    fred = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(_fetch_one_fred, sid) for sid in series_ids]
        for fut in as_completed(futs):
            sid, vals, err = fut.result()
            if vals is not None:
                fred[sid] = vals
                print(f"  ✓ FRED {sid:16s} 最新 {vals[-1][1]:>10.2f} ({vals[-1][0]})")
            else:
                print(f"  ✗ FRED {sid:16s} {err}")
    if not fred and os.path.exists(cache_file):
        fred = json.load(open(cache_file, encoding="utf-8"))
        print("  網路不可用，使用宏觀快取")
    elif fred:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(fred, f, ensure_ascii=False)
    return fred


def _fetch_one_asset(sym):
    """抓單一資產 1 年日線（供 fetch_asset_perf 並行使用）。"""
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           f"{urllib.parse.quote(sym)}?range=1y&interval=1d")
    for attempt in (0, 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            res = data["chart"]["result"][0]
            meta = res["meta"]
            pairs = [(t, c) for t, c in zip(res["timestamp"],
                                            res["indicators"]["quote"][0]["close"])
                     if c is not None]
            if not pairs:
                return sym, None, "無資料"
            price = meta.get("regularMarketPrice") or pairs[-1][1]
            first = pairs[0][1]
            cur_year = datetime.fromtimestamp(pairs[-1][0]).year
            jan = next((c for t, c in pairs
                        if datetime.fromtimestamp(t).year == cur_year), None)
            ytd = (price / jan - 1) * 100 if jan else None
            y1 = (price / first - 1) * 100 if first else None
            return sym, {
                "price": round(price, 2),
                "ytd": round(ytd, 2) if ytd is not None else None,
                "y1": round(y1, 2) if y1 is not None else None,
                "high": meta.get("fiftyTwoWeekHigh"),
                "low": meta.get("fiftyTwoWeekLow"),
                "closes": [round(c, 2) for _, c in pairs],
                # 組合實時收益用：全精度收盤 + 日期（YYYY-MM-DD）
                "series": [round(c, 4) for _, c in pairs],
                "dates": [datetime.fromtimestamp(t).strftime("%Y-%m-%d") for t, _ in pairs],
            }, None
        except Exception as e:
            if attempt == 1:
                return sym, None, str(e)
            time.sleep(0.4)
    return sym, None, "重試失敗"


def fetch_asset_perf(symbols, workers=10):
    """並行抓 1 年（日線）行情，計算 YTD/1Y 報酬、52 周高低，並保留日期序列供組合實時收益計算。"""
    perf = {}
    syms = sorted(set(symbols))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(_fetch_one_asset, sym) for sym in syms]
        for fut in as_completed(futs):
            sym, p, err = fut.result()
            if p is not None:
                perf[sym] = p
                print(f"  ✓ 資產 {sym:8s} {p['price']:>10.2f} | YTD {p['ytd']:>7.2f}% | 1Y {p['y1']:>7.2f}%")
            else:
                print(f"  ✗ 資產 {sym:8s} {err}")
    return perf


def fetch_asset_history(symbols):
    """抓 20 年月頻收盤（供歷史情景回測：2008／2020／2022）。回傳 {sym: {dates, closes}}。"""
    hist = {}
    for sym in sorted(set(symbols)):
        url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
               f"{urllib.parse.quote(sym)}?range=20y&interval=1mo")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            res = data["chart"]["result"][0]
            pairs = [(t, c) for t, c in zip(res["timestamp"],
                                            res["indicators"]["quote"][0]["close"])
                     if c is not None]
            if len(pairs) < 60:
                continue
            hist[sym] = {
                "dates": [datetime.fromtimestamp(t).strftime("%Y-%m-%d") for t, _ in pairs],
                "closes": [round(float(c), 2) for _, c in pairs],
            }
            print(f"  ✓ 歷史 {sym:8s} {pairs[0][0]} 起 {len(pairs)} 個月（截至 {pairs[-1][0]}）")
        except Exception as e:
            print(f"  ✗ 歷史 {sym:8s} {e}")
        time.sleep(0.25)
    return hist


def _clamp(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, v))


def _yv(fred, sid, back=0):
    v = fred.get(sid) or []
    i = len(v) - 1 - back
    return v[i][1] if 0 <= i < len(v) else None


def _yoy_at(fred, sid, back=0, lag=12):
    v = fred.get(sid) or []
    i = len(v) - 1 - back
    if i - lag < 0:
        return None
    prev = v[i - lag][1]
    return (v[i][1] / prev - 1) * 100 if prev else None


def _gdp_yoy(fred):
    v = fred.get("GDPC1") or []
    if len(v) < 5:
        return None
    return (v[-1][1] / v[-5][1] - 1) * 100


def growth_score(fred, back=0):
    gdp = _gdp_yoy(fred)
    unrate = _yv(fred, "UNRATE", back)
    pay = _yoy_at(fred, "PAYEMS", back)
    if None in (gdp, unrate, pay):
        return None
    return (0.4 * _clamp((gdp - 0.5) * 25)
            + 0.3 * _clamp(100 - (unrate - 3.5) * 22)
            + 0.3 * _clamp(50 + pay * 30))


def inflation_score(fred, back=0):
    cpi = _yoy_at(fred, "CPIAUCSL", back)
    pce = _yoy_at(fred, "PCEPILFE", back)
    if cpi is None or pce is None:
        return None
    return 0.6 * _clamp((cpi - 1.5) * 40) + 0.4 * _clamp((pce - 1.5) * 35)


def liquidity_score(fred, back=0):
    ffr = _yv(fred, "DFF", back)
    spread = _yv(fred, "T10Y2Y", back)
    oas = _yv(fred, "BAMLH0A0HYM2", back)
    if None in (ffr, spread, oas):
        return None
    tight = _clamp((ffr - 1.0) * 22)
    curve = 8 if spread >= 0 else -12
    credit = _clamp(100 - (oas - 3.0) * 30)
    return 0.75 * _clamp(100 - tight + curve) + 0.25 * credit


def stress_score(fred, vix, back=0):
    oas = _yv(fred, "BAMLH0A0HYM2", back)
    if vix is None or oas is None:
        return None
    return 0.5 * _clamp((vix - 12) * 6) + 0.5 * _clamp(50 + (oas - 3.2) * 25)


def build_score_mapping(fred, vix):
    """模組 37：把每項宏觀評分拆成「原始輸入 → 權重 → 貢獻分」的映射說明，
    與 compute_allocation 使用完全相同的輸入與公式。"""
    out = []

    def row(key, label, formula, parts):
        score = sum(w * c for _, _, w, c in parts)
        out.append({
            "key": key, "label": label, "formula": formula, "score": round(score),
            "parts": [{"name": n, "value": round(v, 2) if v is not None else None,
                       "weight": w, "contrib": round(w * c, 1)}
                      for n, v, w, c in parts],
        })

    gdp = _gdp_yoy(fred)
    un = _yv(fred, "UNRATE")
    pay = _yoy_at(fred, "PAYEMS")
    if None not in (gdp, un, pay):
        row("growth", "增長", "0.4×GDP 同比 + 0.3×就業 + 0.3×薪資", [
            ("GDP 同比（%）", gdp, 0.4, _clamp((gdp - 0.5) * 25)),
            ("失業率（%）", un, 0.3, _clamp(100 - (un - 3.5) * 22)),
            ("非農就業同比（%）", pay, 0.3, _clamp(50 + pay * 30)),
        ])
    cpi = _yoy_at(fred, "CPIAUCSL")
    pce = _yoy_at(fred, "PCEPILFE")
    if cpi is not None and pce is not None:
        row("inflation", "通脹", "0.6×CPI 同比 + 0.4×核心 PCE 同比", [
            ("CPI 同比（%）", cpi, 0.6, _clamp((cpi - 1.5) * 40)),
            ("核心 PCE 同比（%）", pce, 0.4, _clamp((pce - 1.5) * 35)),
        ])
    ffr = _yv(fred, "DFF")
    spread = _yv(fred, "T10Y2Y")
    oas = _yv(fred, "BAMLH0A0HYM2")
    if None not in (ffr, spread, oas):
        tight = _clamp((ffr - 1.0) * 22)
        curve = 8 if spread >= 0 else -12
        credit = _clamp(100 - (oas - 3.0) * 30)
        row("liquidity", "流動性", "0.75×利率鬆緊與曲線 + 0.25×信用利差", [
            ("聯邦基金利率（%）", ffr, 0.75, _clamp(100 - tight + curve)),
            ("高收益 OAS（%）", oas, 0.25, credit),
        ])
    if vix is not None and oas is not None:
        row("stress", "壓力", "0.5×VIX + 0.5×信用利差", [
            ("VIX 指數", vix, 0.5, _clamp((vix - 12) * 6)),
            ("高收益 OAS（%）", oas, 0.5, _clamp(50 + (oas - 3.2) * 25)),
        ])
    return out


def _chg_at(v, back=0):
    """序列某觀測相對 back 個觀測前的變動（bp）。"""
    if v is None or len(v) <= back:
        return None
    return round((v[-1][1] - v[-1 - back][1]) * 100, 0)


def build_treasury_desk(fred, targets):
    """美聯儲頁「國債交易台視角」v2：形態／驅動因素／交易策略三層框架。
    全部數值由 FRED 序列規則式生成；框架參考 CME 期貨日報 2025-09-04
    與四形態／牛熊×陡平／利差交易方法論。"""
    def f1(x):
        return "—" if x is None else f"{x:.1f}"

    dgs2, dgs5 = fred.get("DGS2") or [], fred.get("DGS5") or []
    dgs10, dgs30 = fred.get("DGS10") or [], fred.get("DGS30") or []
    dgs3m = fred.get("DGS3MO") or []
    ffr = _yv(fred, "DFF")
    real10 = _yv(fred, "DFII10")
    spread3m = _yv(fred, "T10Y3M")
    baa = _yv(fred, "BAA10Y")
    hy = _yv(fred, "BAMLH0A0HYM2")
    ig = _yv(fred, "BAMLC0A0CM")
    cpi = _yoy_at(fred, "CPIAUCSL")
    pce = _yoy_at(fred, "PCEPILFE")
    unrate = _yv(fred, "UNRATE")
    gdp = _gdp_yoy(fred)
    asof = (dgs2 or [["—"]])[-1][0]
    if not dgs2 or not dgs10 or not dgs30:
        return None

    r = {"ffr": ffr, "dgs3m": dgs3m[-1][1] if dgs3m else None,
         "dgs2": dgs2[-1][1], "dgs5": dgs5[-1][1] if dgs5 else None,
         "dgs10": dgs10[-1][1], "dgs30": dgs30[-1][1],
         "real10": real10, "baa10y": baa, "hy_oas": hy, "ig_oas": ig,
         "cpi": cpi, "pce": pce, "unrate": unrate, "gdp": gdp}

    # 期限利差（bp，整數）
    s2s10 = round((r["dgs10"] - r["dgs2"]) * 100)
    s5s30 = round((r["dgs30"] - r["dgs5"]) * 100) if r["dgs5"] is not None else None
    s3m10 = round(spread3m * 100) if spread3m is not None else None
    gap2y = round((r["dgs2"] - ffr) * 100) if ffr is not None else None
    gap3m = round((r["dgs3m"] - ffr) * 100) if (r["dgs3m"] is not None and ffr is not None) else None
    be = round((r["dgs10"] - real10) * 100) if real10 is not None else None  # bp
    r["spread2s10s_bp"] = s2s10
    r["spread5s30s_bp"] = s5s30
    r["spread3m10y_bp"] = s3m10
    r["gap2y_bp"] = gap2y
    r["gap3m_bp"] = gap3m
    r["breakeven_bp"] = be

    # 過去 1 月／3 月／1 年變動（bp）：DGS2/DGS5/DGS10/DGS30 日頻
    ch = {}
    for sid, v in (("2Y", dgs2), ("5Y", dgs5), ("10Y", dgs10), ("30Y", dgs30)):
        if v:
            ch[sid] = {"m1": _chg_at(v, 21), "m3": _chg_at(v, 63), "y1": _chg_at(v, 252)}

    # 曲線利差歷史（按日期對齊，近 504 交易日）
    by2, by5, by10, by30 = (dict(v) for v in (dgs2, dgs5, dgs10, dgs30))
    spread_hist = [[d, round((by10[d] - by2[d]) * 100)] for d, _ in dgs10 if d in by2][-504:]
    spread5_hist = [[d, round((by30[d] - by5[d]) * 100)] for d, _ in dgs30 if d in by5][-504:]

    # ================= 第一層：形態 =================
    if s2s10 < 0:
        shape_now = "倒掛"
        shape_txt = (f"2s10s 利差 {s2s10}bp——短期利率比長期還高，曲線<b>倒掛</b>。"
                     "這是經典的衰退警報：2000、2006–07、2022–23 三次倒掛後美國都陷入衰退，"
                     "平均領先 6–18 個月。")
    elif s2s10 > 50:
        shape_now = "陡峭"
        shape_txt = (f"2s10s 利差 +{s2s10}bp——曲線<b>陡峭</b>：買 10 年債比 2 年債每年多賺 "
                     f"{s2s10 / 100:.2f}%，市場預期經濟向好、未來利率會走高。")
    else:
        shape_now = "正斜偏平坦"
        shape_txt = (f"2s10s 利差只有 +{s2s10}bp——曲線<b>正斜率但偏平坦</b>："
                     f"買 10 年債只比 2 年債每年多賺 {s2s10 / 100:.2f}%，"
                     "鎖 10 年的期限補償不算多"
                     + (f"（5s30s +{s5s30}bp 也偏平）" if s5s30 is not None else "") + "。")
    hump_txt = ""
    if r["dgs5"] is not None and r["dgs5"] > r["dgs10"]:
        hump_txt = (f"另外 5 年期 {r['dgs5']:.2f}% 比 10 年期 {r['dgs10']:.2f}% 還高——"
                    "中段凸起（<b>駝峰</b>），通常是政策方向不明或中段債券發行太多的信號。")

    # 近一年趨勢（牛陡/熊陡/牛平/熊平）
    y2, y10 = ch.get("2Y", {}).get("y1"), ch.get("10Y", {}).get("y1")
    y30, m2 = ch.get("30Y", {}).get("y1"), ch.get("2Y", {}).get("m1")
    trend, trend_txt = "—", ""
    if y2 is not None and y10 is not None:
        if y2 >= 0 and y10 >= 0:
            trend = "熊陡" if y10 > y2 else "熊平"
        elif y2 < 0 and y10 < 0:
            trend = "牛陡" if y2 < y10 else "牛平"
        else:
            trend = "震盪"
        if trend == "熊平":
            trend_txt = (f"過去一年，2 年期收益率漲了 {y2:+.0f}bp，比 10 年期（{y10:+.0f}bp）和 "
                         f"30 年期（{y30:+.0f}bp）漲得都多——<b>熊平</b>：短端被加息預期推著走、"
                         "長端相對淡定，利差反而收窄。")
        elif trend == "熊陡":
            trend_txt = (f"過去一年，10 年期漲了 {y10:+.0f}bp、比 2 年期（{y2:+.0f}bp）多——"
                         f"<b>熊陡</b>：通脹／財政擔憂推高長端，整體利率上行、曲線走闊。")
        elif trend == "牛陡":
            trend_txt = (f"過去一年，2 年期跌了 {abs(y2):.0f}bp、比 10 年期（{y10:+.0f}bp）多——"
                         f"<b>牛陡</b>：降息預期壓低短端，曲線走闊。")
        elif trend == "牛平":
            trend_txt = (f"過去一年，10 年期跌了 {abs(y10):.0f}bp、比 2 年期（{y2:+.0f}bp）多——"
                         f"<b>牛平</b>：避險資金湧入長端。")
        else:
            trend_txt = f"過去一年 2Y {y2:+.0f}bp、10Y {y10:+.0f}bp 方向分化——曲線方向待定。"
        if m2 is not None:
            trend_txt += f"最近一個月 2 年期又變動 {m2:+.0f}bp。"

    # 牛陡/熊陡/牛平/熊平速查表（含當前標記）
    trend_table = [
        {"name": "牛陡", "def": "降息初期：短端跌得比長端快", "spread": "利差走闊",
         "trade": "買 2 年期、賣 10 年期", "now": trend == "牛陡"},
        {"name": "熊陡", "def": "通脹／財政擔憂：長端漲得比短端快", "spread": "利差走闊",
         "trade": "賣長端、買短端", "now": trend == "熊陡"},
        {"name": "牛平", "def": "避險資金湧入：長端跌得比短端快", "spread": "利差收窄",
         "trade": "買長端、賣短端", "now": trend == "牛平"},
        {"name": "熊平", "def": "加息後期：短端漲得比長端快", "spread": "利差收窄",
         "trade": "賣短端、買長端", "now": trend == "熊平"},
    ]

    # 四種基本形態速查卡
    shape_cards = [
        {"name": "陡峭化", "kind": "steep",
         "desc": "長端利率漲得比短端多，利差走闊。復甦初期、通脹抬頭時常見。",
         "trade": "做陡：買短賣長"},
        {"name": "平坦化", "kind": "flat",
         "desc": "利差收窄：熊平是短端漲得多，牛平是長端跌得多。加息後期常見。",
         "trade": "做平：買長賣短"},
        {"name": "倒掛", "kind": "invert",
         "desc": "短期利率比長期還高。2000、2006–07、2022–23 三次倒掛後美國均衰退，平均領先 6–18 個月。",
         "trade": "減股票倉、長債避險"},
        {"name": "駝峰", "kind": "hump",
         "desc": "中段（3–7 年）收益率比兩頭都高。政策不明、中段發行多時出現。",
         "trade": "蝶式：賣中段、買兩端"},
    ]

    # ================= 第二層：驅動因素 =================
    drivers = []
    if gap2y is not None:
        if gap2y > 50:
            d_short = (f"2 年期 {r['dgs2']:.2f}% 比聯儲基準利率 {ffr:.2f}% 高出 {gap2y}bp"
                       + (f"、3 個月國庫券 {r['dgs3m']:.2f}% 高出 {gap3m}bp" if r["dgs3m"] is not None else "")
                       + f"——市場在定價<b>加息而非降息</b>：失業率 {f1(unrate)}%、"
                         f"核心通脹 {f1(pce)}% 還沒回到 2% 目標，聯儲不敢轉向。")
        elif gap2y < -50:
            d_short = (f"2 年期 {r['dgs2']:.2f}% 比聯儲基準利率 {ffr:.2f}% 低 {abs(gap2y)}bp"
                       "——市場在定價<b>降息預期</b>。")
        else:
            d_short = (f"2 年期 {r['dgs2']:.2f}% 與聯儲基準利率 {ffr:.2f}% 大致持平"
                       f"（差 {gap2y}bp）——市場認為政策利率短期不變。")
        drivers.append({"title": "短端：政策利率預期", "txt": d_short})
    if real10 is not None:
        d_long = (f"10 年期實際利率（扣除通脹後）{real10:.2f}%，遠高於歷史中性 0.5–1.5%；"
                  f"市場隱含未來 10 年平均通脹只有 {be / 100:.2f}%，比現在的 CPI {f1(cpi)}% 低一截"
                  "——市場賭通脹會大幅回落。如果通脹比預期粘（財政赤字、關稅），"
                  "長端還有上行風險。")
        drivers.append({"title": "長端：通脹與財政", "txt": d_long})
    if hy is not None:
        d_crd = (f"高收益債利差 {hy:.2f}%、投資級 {ig:.2f}%、BAA−10Y {baa:.2f}%——都在歷史低位："
                 "市場很樂觀、企業借錢很便宜，這是股市的支撐；"
                 "但利差已經低到沒多少收窄空間，一旦風險情緒轉差，走闊空間比收窄空間大得多。")
        drivers.append({"title": "信用：利差極窄", "txt": d_crd})
    if s3m10 is not None:
        drivers.append({"title": "衰退警報交叉驗證",
                        "txt": (f"10Y−3M 利差 +{s3m10}bp，還是正的——這條利差轉負才是歷史上的"
                                "衰退警報，現在還沒響（見本站風險頁的衰退概率模型）。")})

    # ================= 第三層：交易策略（具體場景） =================
    strategies = []
    if gap2y is not None and gap2y > 50:
        strategies.append({
            "name": "吃 carry：直接買 2–5 年期國債",
            "setup": f"2 年期 {r['dgs2']:.2f}%，比基準利率高 {gap2y}bp",
            "scenario": (f"買 2 年期國債持有 12 個月：票息 {r['dgs2']:.2f}%。就算聯儲真加息兩次"
                         f"（+50bp），價格損失約 1%，一年還能賺 {r['dgs2'] - 1:.2f}% 左右；"
                         "要虧錢需要加息超過 250bp。當前賠率最好的收入倉。"),
        })
    strategies.append({
        "name": "做平：押注利差繼續收窄",
        "setup": f"2s10s 現在 +{s2s10}bp，過去一年短端漲得多",
        "scenario": (f"如果你覺得加息預期還會推高短端、長端因衰退擔憂漲不動，"
                     f"2s10s 會從 +{s2s10}bp 繼續收窄：賣出 2 年期、買入 10 年期（久期中性）。"
                     f"利差每收窄 10bp 約賺 0.8 點；從 +{s2s10}bp 收到 0 約賺 2.5 點，"
                     "如果收到倒掛（−20bp）能賺 4 點左右。"),
    })
    strategies.append({
        "name": "牛陡條件單：等數據反轉再動手",
        "setup": "觸發條件：CPI 回落到 3% 以下＋失業率升破 4.5%",
        "scenario": (f"如果數據確認聯儲轉向降息，短端現在定價的加息溢價（2Y−基準利率 +{gap2y}bp）"
                     "會快速消失，2 年期可能跌 80–120bp——到時做陡：買 2 年期、賣 10 年期。"
                     f"2s10s 從 +{s2s10}bp 回到歷史平均 +80~100bp 區間，每走闊 10bp 約賺 0.7 點。"
                     "現在不用進場，設好觸發條件等數據。"),
    })
    if r["dgs5"] is not None:
        mid = r["dgs2"] + (r["dgs10"] - r["dgs2"]) * 3 / 8
        rich = round((r["dgs5"] - mid) * 100)
        strategies.append({
            "name": "蝶式：只押中段貴賤",
            "setup": f"5 年期 {r['dgs5']:.2f}% 比 2 年/10 年連線的中間值 {mid:.2f}% {'貴' if rich > 0 else '便宜'} {abs(rich)}bp",
            "scenario": ("賣 5 年期、同時買 2 年期和 10 年期（倉位大致對半）。"
                         "只押中段相對兩頭偏貴還是偏便宜，不押整條曲線漲跌——"
                         "適合數據空窗期，中段回到連線水平就獲利。"),
        })
    else:
        strategies.append({
            "name": "蝶式：只押中段貴賤",
            "setup": "中段（5 年期）相對兩端的偏離交易",
            "scenario": ("賣 5 年期、同時買 2 年期和 10 年期：只押中段貴賤，"
                         "不押曲線方向——適合數據空窗期。"),
        })
    if be is not None and cpi is not None:
        strategies.append({
            "name": "TIPS：通脹保值債相對便宜",
            "setup": f"市場隱含通脹 {be / 100:.2f}% vs 現在 CPI {cpi:.1f}%",
            "scenario": (f"市場賭未來 10 年平均通脹只有 {be / 100:.2f}%，比現在的 CPI {cpi:.1f}% 低——"
                         "只要通脹回落得比預期慢，TIPS 就跑贏普通國債。"
                         "用 TIP ETF 分批買；如果 10 年期實際利率從 "
                         f"{real10:.2f}% 回落到 2.5% 以下再加碼。"),
        })
    if hy is not None:
        strategies.append({
            "name": "高收益債：留出子彈",
            "setup": f"高收益利差 {hy:.2f}%，近三年低位",
            "scenario": (f"高收益債利差 {hy:.2f}% 已經很低，繼續收窄的空間很小；2022 年衰退擔憂時"
                         "利差一度衝破 5%。可以減掉一部分高收益債、換成短端國債，"
                         "等利差回到 4% 以上再買回來。"),
        })
    strategies.append({
        "name": "長債分批建倉",
        "setup": f"10 年期 {r['dgs10']:.2f}%、實際利率 {r['real10']:.2f}%",
        "scenario": (f"實際利率 {r['real10']:.2f}% 已高於中性，長債適合「配置」而不是「交易」："
                     "每漲 10–15bp 加一批 10–30 年期（TLT/EDV 或國債期貨），分 3–4 批建完；"
                     "如果以後曲線倒掛，長債就是最好的避險資產。"),
    })

    # ---- 利差總表 ----
    spreads = [
        {"name": "2s10s 期限利差", "val": f"{s2s10:+d}bp",
         "note": "正斜偏平坦" if 0 <= s2s10 <= 50 else ("陡峭" if s2s10 > 50 else "倒掛")},
        {"name": "5s30s 期限利差", "val": f"{s5s30:+d}bp" if s5s30 is not None else "—",
         "note": "長端陡峭度"},
        {"name": "10Y−3M 利差", "val": f"{s3m10:+d}bp" if s3m10 is not None else "—",
         "note": "歷史上的衰退警報線（見風險頁）"},
        {"name": "投資級信用利差 IG OAS", "val": f"{ig:.2f}%" if ig is not None else "—",
         "note": "歷史低位 → 風險補償薄"},
        {"name": "高收益信用利差 HY OAS", "val": f"{hy:.2f}%" if hy is not None else "—",
         "note": "近三年極窄，2022 年曾 >5%"},
        {"name": "BAA−10Y 利差", "val": f"{baa:.2f}%" if baa is not None else "—",
         "note": "信用周期寬鬆"},
        {"name": "10Y 盈虧平衡通脹", "val": f"{be / 100:.2f}%" if be is not None else "—",
         "note": f"< CPI {cpi:.1f}% → TIPS 有價值" if cpi is not None else "市場隱含通脹"},
    ]

    return {
        "asof": asof,
        "rates": r,
        "curve": [["FFR", 0, ffr], ["3M", 0.25, r["dgs3m"]], ["2Y", 2, r["dgs2"]],
                  ["5Y", 5, r["dgs5"]], ["10Y", 10, r["dgs10"]], ["30Y", 30, r["dgs30"]]],
        "hist": {"dgs2": dgs2[-504:], "dgs5": dgs5[-504:] if dgs5 else [],
                 "dgs10": dgs10[-504:], "dgs30": dgs30[-504:],
                 "spread2s10s": spread_hist, "spread5s30s": spread5_hist},
        "changes": ch,
        "shape": {"name": shape_now, "text": shape_txt, "hump": hump_txt,
                  "trend": trend, "trend_text": trend_txt, "trend_table": trend_table,
                  "cards": shape_cards},
        "spreads": spreads,
        "drivers": drivers,
        "strategies": strategies,
        "ref": ("分析框架參考 CME 期貨日報《美債收益率為何「長短不一」？》（2025-09-04）；"
                "全部數值來自 FRED，形態與策略由規則自動生成，非人工觀點。"),
    }


def compute_allocation(fred, quotes, asset_perf):
    """規則式宏觀評分 + 資產配置（全部規則公開透明，見頁面方法論）。"""
    vix_q = quotes.get("^VIX", {})
    vix = vix_q.get("price")
    vix_closes = vix_q.get("closes") or []
    vix_prev = vix_closes[-2] if len(vix_closes) >= 2 else vix

    g0, g1 = growth_score(fred, 0), growth_score(fred, 1)
    i0, i1 = inflation_score(fred, 0), inflation_score(fred, 1)
    l0, l1 = liquidity_score(fred, 0), liquidity_score(fred, 1)
    s0 = stress_score(fred, vix, 0)
    s1 = stress_score(fred, vix_prev, 1)

    cpi = _yoy_at(fred, "CPIAUCSL")
    pce = _yoy_at(fred, "PCEPILFE")
    gdp = _gdp_yoy(fred)
    unrate = _yv(fred, "UNRATE")
    pay = _yoy_at(fred, "PAYEMS")
    ffr = _yv(fred, "DFF")
    spread = _yv(fred, "T10Y2Y")
    oas = _yv(fred, "BAMLH0A0HYM2")
    real10 = _yv(fred, "DFII10")

    # ---- 資產配置（基準 + 規則調整） ----
    w = {"股票": 40.0, "國債": 20.0, "商品": 10.0, "黃金": 10.0, "現金": 20.0}
    fired = []
    if s0 is not None and s0 >= 60:
        w["股票"] -= 10; w["現金"] += 10; fired.append("壓力 ≥ 60 → 股票 −10、現金 +10")
    if g0 is not None and g0 < 45:
        w["股票"] -= 10; w["國債"] += 10; fired.append("增長 < 45 → 股票 −10、國債 +10")
    if i0 is not None and i0 >= 70:
        w["黃金"] += 8; w["國債"] -= 8; fired.append("通脹 ≥ 70 → 黃金 +8、國債 −8")
    if l0 is not None and l0 < 45:
        w["現金"] += 5; w["商品"] -= 5; fired.append("流動性 < 45 → 現金 +5、商品 −5")
    dbc = asset_perf.get("DBC", {})
    if dbc.get("y1") is not None and dbc["y1"] > 25:
        w["商品"] += 5; w["現金"] -= 5; fired.append("商品一年報酬 > +25% → 商品 +5、現金 −5")
    for k in ("國債", "現金"):
        if w[k] < 10:
            w["股票"] -= 10 - w[k]
            w[k] = 10
    if not fired:
        fired.append("無規則觸發，維持基準配置")

    targets = [{"cls": k, "pct": round(w[k], 1), "proxy": ASSET_PROXIES.get(k, "—")}
               for k in ("股票", "國債", "商品", "黃金", "現金")]

    macro = [
        {"key": "growth", "label": "增長", "up_good": True,
         "score": round(g0) if g0 is not None else None,
         "change": round(g0 - g1) if (g0 is not None and g1 is not None) else None,
         "note": f"GDP +{gdp:.1f}% · 失業率 {unrate:.1f}% · 非農 +{pay:.1f}%",
         "formula": "0.4×GDP + 0.3×就業 + 0.3×非農"},
        {"key": "inflation", "label": "通脹壓力", "up_good": False,
         "score": round(i0) if i0 is not None else None,
         "change": round(i0 - i1) if (i0 is not None and i1 is not None) else None,
         "note": f"CPI {cpi:.1f}% · 核心 PCE {pce:.1f}%（目標 2%）",
         "formula": "0.6×CPI + 0.4×核心PCE（越高壓力越大）"},
        {"key": "liquidity", "label": "流動性", "up_good": True,
         "score": round(l0) if l0 is not None else None,
         "change": round(l0 - l1) if (l0 is not None and l1 is not None) else None,
         "note": f"聯邦基金利率 {ffr:.2f}% · 10Y-2Y 利差 {spread:+.2f}%",
         "formula": "利率鬆緊×0.75 + 信用利差×0.25"},
        {"key": "stress", "label": "市場壓力", "up_good": False,
         "score": round(s0) if s0 is not None else None,
         "change": round(s0 - s1) if (s0 is not None and s1 is not None) else None,
         "note": f"VIX {vix:.1f} · 高收益利差 {oas:.2f}%",
         "formula": "0.5×VIX + 0.5×信用利差（越高壓力越大）"},
    ]

    judgment = [
        f"通脹壓力偏高：CPI 同比 {cpi:.1f}%、核心 PCE {pce:.1f}%，遠高於 2% 目標 → 觸發「黃金 +8、國債 −8」。",
        f"增長溫和：GDP 同比 +{gdp:.1f}%，但非農就業同比僅 +{pay:.1f}%——就業引擎降速是當前最大裂縫。",
        f"流動性中性偏緊：聯邦基金利率 {ffr:.2f}%、10Y-2Y 利差 {spread:+.2f}%，曲線已正常化但利率仍在高位。",
        f"市場壓力低：VIX {vix:.1f}、高收益利差 {oas:.2f}%——市場毫無恐懼，賠率不在買方。",
    ]
    if dbc.get("y1") is not None:
        cl = asset_perf.get("CL=F", {})
        judgment.append(
            f"商品動量極強：DBC 一年 {dbc['y1']:+.0f}%、油價 YTD "
            f"{cl.get('ytd', 0) or 0:+.0f}% → 觸發「商品 +5、現金 −5」。")
    judgment.append(
        "當前判斷：持有核心股票倉位，以黃金與現金提供下行保護；"
        "等待回調（標普 −10%、金價 3,800–4,100 美元）再加倉。")

    rules = [
        "基準配置：股票 40 / 國債 20 / 商品 10 / 黃金 10 / 現金 20",
        "壓力 ≥ 60 → 股票 −10、現金 +10",
        "增長 < 45 → 股票 −10、國債 +10",
        "通脹 ≥ 70 → 黃金 +8、國債 −8",
        "流動性 < 45 → 現金 +5、商品 −5",
        "商品一年報酬 > +25% → 商品 +5、現金 −5",
        "下限保護：國債、現金均不低於 10%",
    ]

    bonds = {
        "dgs2": round(_yv(fred, "DGS2"), 2), "dgs10": round(_yv(fred, "DGS10"), 2),
        "dgs30": round(_yv(fred, "DGS30"), 2), "ffr": round(ffr, 2),
        "spread": round(spread, 2), "real10": round(real10, 2),
        "hy_oas": round(oas, 2),
        # 投資級 / 高收益信用市場（FRED BofA ICE 指數）
        "ig_oas": round(_yv(fred, "BAMLC0A0CM"), 2),
        "ig_yield": round(_yv(fred, "BAMLC0A0CMEY"), 2),
        "hy_yield": round(_yv(fred, "BAMLH0A0HYM2EY"), 2),
        "asof": (fred.get("DGS10") or [["—"]])[-1][0],
    }

    commodities = []
    for name, sym, unit in COMMODITY_FUTURES:
        p = asset_perf.get(sym, {})
        q = quotes.get(sym, {})
        if p.get("price") is not None:
            commodities.append({
                "name": name, "sym": sym, "unit": unit,
                "price": round(p["price"], 2),
                "chg": q.get("change_pct"), "ytd": p.get("ytd"), "y1": p.get("y1"),
                "closes": q.get("closes") or p.get("closes"),
            })

    assets = []
    for label, sym in ASSET_PROXIES.items():
        p = asset_perf.get(sym, {})
        q = quotes.get(sym, {})
        if p.get("price") is not None:
            assets.append({
                "label": label, "sym": sym, "price": round(p["price"], 2),
                "ytd": p.get("ytd"), "y1": p.get("y1"),
                "high": p.get("high"), "low": p.get("low"),
                "closes": q.get("closes") or p.get("closes"),
            })

    # 美聯儲追蹤器數據（目標區間/資產負債表/通脹/FOMC 日曆）
    def _fed_at(sid, dt):
        vals = fred.get(sid) or []
        for d, v in vals:
            if d > dt:  # 取決議日之後的首個值 = 會後區間
                return v
        return None

    today = datetime.now().date().isoformat()
    next_end = next((d for d, _ in FOMC_2026 if d >= today), None)
    fomc = []
    for end, label in FOMC_2026:
        fomc.append({
            "dates": label, "end": end,
            "status": "past" if end < today else ("next" if end == next_end else "future"),
            "upper": round(_fed_at("DFEDTARU", end), 2) if _fed_at("DFEDTARU", end) is not None else None,
            "lower": round(_fed_at("DFEDTARL", end), 2) if _fed_at("DFEDTARL", end) is not None else None,
        })
    walcl = fred.get("WALCL") or []
    walcl_1y = _fed_at("WALCL", (datetime.now().date() -
                                 timedelta(days=365)).isoformat())
    fed = {
        "target_upper": round(_yv(fred, "DFEDTARU"), 2) if _yv(fred, "DFEDTARU") is not None else None,
        "target_lower": round(_yv(fred, "DFEDTARL"), 2) if _yv(fred, "DFEDTARL") is not None else None,
        "eff": round(_yv(fred, "DFF"), 2) if _yv(fred, "DFF") is not None else None,
        "eff_hist": (fred.get("DFF") or [])[-250:],
        "target_hist": (fred.get("DFEDTARU") or [])[-250:],
        "walcl": round(_yv(fred, "WALCL"), 0) if _yv(fred, "WALCL") is not None else None,
        "walcl_1y": walcl_1y,
        "walcl_hist": walcl[-60:],
        "cpi_yoy": _yoy_at(fred, "CPIAUCSL"), "core_cpi_yoy": _yoy_at(fred, "CPILFESL"),
        "pce_yoy": _yoy_at(fred, "PCEPI"), "core_pce_yoy": _yoy_at(fred, "PCEPILFE"),
        "unrate": _yv(fred, "UNRATE"),
        "fomc": fomc,
        "asof": (fred.get("DFF") or [["—"]])[-1][0],
        "treasury": build_treasury_desk(fred, targets),
    }

    return {
        "asof": max((q.get("asof", "") for q in quotes.values()), default=""),
        "macro": macro,
        "targets": targets,
        "judgment": judgment,
        "rules": rules,
        "bonds": bonds,
        "fed": fed,
        "commodities": commodities,
        "assets": assets,
        "portfolio": compute_portfolio(asset_perf, targets),
        "mapping": build_score_mapping(fred, vix),
        "sources": ["FRED 聯儲經濟數據（fredgraph.csv）", "Yahoo Finance 公開行情",
                    "ICE/COMEX 期貨報價"],
    }


def compute_valuation(fred, companies, fund_data):
    """估值儀表板：巴菲特指標（Wilshire/GDP）+ 行業估值中位數 + 高估/低估榜。"""
    def raw(x):
        return x.get("raw") if isinstance(x, dict) else x

    v = {}
    # 巴菲特指標代理（FRED 已下架 Wilshire 5000；改用 Z.1 非金融企業股權市值 / GDP）
    # 本序列值 ≈ 萬億美元（如 19.14 ≈ 19.14 兆），GDPC1 為十億美元年化 → 比值 = w×1000/g
    wil = fred.get("NCBCMDPMVCE") or []
    gdp = fred.get("GDPC1") or []
    if wil and gdp:
        hist = []
        for d_w, w in wil:
            g = None
            for d_g, gg in gdp:
                if d_g <= d_w:
                    g = gg
            if g:
                hist.append([d_w, round(w * 1000 / g, 4)])
        if hist:
            v["buffett"] = {"ratio": hist[-1][1], "hist": hist[-40:], "asof": hist[-1][0]}
    # 個股估值統計（PE 缺時用 價格/每股收益 回退）
    sec_pes, all_rows = {}, []
    for c in companies:
        t = c.get("ticker")
        ent = fund_data.get(t) or {}
        qs = ent.get("qs") or {}
        ks = qs.get("defaultKeyStatistics") or {}
        det = qs.get("summaryDetail") or {}
        closes = ent.get("closes") or []
        price = closes[-1] if closes else None
        pe = raw(ks.get("trailingPE"))
        eps = raw(ks.get("trailingEps"))
        if pe is None and price and eps:
            pe = price / eps
        pb, ps, dy, mk = raw(ks.get("priceToBook")), raw(ks.get("priceToSales")), \
            raw(det.get("dividendYield")), raw(ks.get("marketCap"))
        if pe is not None and 0 < pe < 1000:
            row = {"name": c["name"], "ticker": t, "sector": c.get("sector", ""),
                   "pe": round(pe, 1), "pb": round(pb, 2) if pb is not None else None,
                   "ps": round(ps, 2) if ps is not None else None,
                   "dy": round(dy, 4) if dy is not None else None, "mktcap": mk}
            all_rows.append(row)
            sec_pes.setdefault(c.get("sector", "其他"), []).append(pe)
    v["n_valued"] = len(all_rows)
    if all_rows:
        pes = sorted(r["pe"] for r in all_rows)
        v["pe_median_all"] = round(pes[len(pes) // 2], 1)
        v["sectors"] = []
        for sec, sp in sorted(sec_pes.items(), key=lambda kv: -len(kv[1])):
            if len(sp) >= 3:
                sp = sorted(sp)
                v["sectors"].append({"sector": sec, "n": len(sp),
                                     "pe_median": round(sp[len(sp) // 2], 1),
                                     "pe_low": round(sp[0], 1), "pe_high": round(sp[-1], 1)})
        ranked = sorted(all_rows, key=lambda r: -r["pe"])
        v["expensive"] = [{"name": r["name"], "ticker": r["ticker"], "pe": r["pe"]}
                          for r in ranked[:10]]
        v["cheap"] = [{"name": r["name"], "ticker": r["ticker"], "pe": r["pe"]}
                      for r in ranked[-10:][::-1]]
    # 股權風險溢價 = 全站 PE 中位數的盈餘收益率 − 10Y 國債（ETF 無 forwardPE，用中位 PE 代理）
    v["dgs10"] = round(_yv(fred, "DGS10"), 2) if fred.get("DGS10") else None
    if v.get("pe_median_all") and v["dgs10"] is not None:
        v["earn_yield_median"] = round(1 / v["pe_median_all"], 4)
        v["erp"] = round(v["earn_yield_median"] - v["dgs10"] / 100, 4)
    return v


def compute_events(fred, companies, fund_data):
    """政策事件日曆：FOMC 日程 + 覆蓋公司財報日（未來 60 天）+ 固定政治事件。"""
    today = datetime.now().date()
    events = {"earnings": [], "fixed": [
        {"date": "2026-11-03", "label": "美國中期選舉（參眾兩院改選）",
         "note": "財政與監管政策風向標；憲法固定日期"},
        {"date": "2026-12-09", "label": "FOMC 12 月會議（決議日）",
         "note": "同日發佈經濟預測摘要（SEP）與點陣圖"},
    ], "monthly": [
        "每月第一個週五：非農就業報告（BLS）",
        "每月中旬：CPI 通脹報告（BLS）",
        "每月下旬：PCE 通脹報告（BEA）",
    ]}
    # 財報日（Yahoo calendarEvents，僅取未來 60 天）
    rows = []
    for c in companies:
        t = c.get("ticker")
        qs = ((fund_data.get(t) or {}).get("qs") or {}) if t else {}
        cal = qs.get("calendarEvents") or {}
        ed = ((cal.get("earnings") or {}).get("earningsDate") or [])             if isinstance(cal.get("earnings"), dict) else []
        for d in ed if isinstance(ed, list) else []:
            fmt = (d or {}).get("fmt") if isinstance(d, dict) else None
            if not fmt or len(fmt) < 10:
                continue
            try:
                dt = datetime.strptime(fmt[:10], "%Y-%m-%d").date()
            except ValueError:
                continue
            if 0 <= (dt - today).days <= 60:
                rows.append({"date": fmt[:10], "name": c["name"], "ticker": t,
                             "sector": c.get("sector", ""), "page": c.get("page", "")})
    rows.sort(key=lambda r: (r["date"], r["name"]))
    events["earnings"] = rows[:40]
    return events


_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9.\-]*")


def build_fund_holdings(hedge_funds, companies):
    """13F 反向持倉：從各對沖基金披露文本（tops/alloc sub/delta，無 tops 時加 note）中
    提取代碼與公司名，反查「哪些頂級基金持有這家公司」。只以站內覆蓋公司的代碼/名稱匹配，
    ETF（SPY/IVV 等）與未覆蓋個股自然排除，不臆造任何持倉。"""
    tickers, names = {}, []
    for c in companies:
        t = (c.get("ticker") or "").strip().upper()
        if t:
            tickers[t] = c
        n = (c.get("name") or "").strip()
        if len(n) >= 2:
            names.append((n, c))
    hold = defaultdict(list)
    for f in hedge_funds:
        texts = []
        for a in f.get("alloc") or []:
            cls = a.get("cls") or ""
            for k in ("sub", "delta"):
                if a.get(k):
                    texts.append((cls, str(a[k])))
        for t in f.get("tops") or []:
            texts.append(("重倉", str(t)))
        if not f.get("tops"):
            texts.append(("備註", str(f.get("note") or "")))
        for cls, txt in texts:
            matched = set()
            for tok in _TOKEN_RE.findall(txt):
                if tok.upper() in tickers:
                    matched.add(tickers[tok.upper()]["ticker"])
            for n, c in names:
                if n in txt:
                    matched.add(c.get("ticker") or "")
            for tk in matched:
                if tk:
                    hold[tk].append({"fund": f["name"], "detail": txt[:140], "cls": cls})
    return dict(hold)


def build_13f_calendar():
    """SEC 13F 法定申報日曆：季末後 45 天內（慣例截止日為次季次月 14/15 日）。"""
    today = datetime.now().date()
    rows = []
    qs = ([(2025, 4)] + [(y, q) for y in (2026, 2027) for q in (1, 2, 3, 4)])[:7]
    for y, q in qs:
        pe = ("03-31", "06-30", "09-30", "12-31")[q - 1]
        d_y = y + (1 if q == 4 else 0)
        d_md = ("02-14" if q == 4 else "05-15" if q == 1 else "08-14" if q == 2 else "11-14")
        dead = datetime.strptime("%d-%s" % (d_y, d_md), "%Y-%m-%d").date()
        rows.append({"quarter": "%d Q%d" % (y, q), "period_end": "%d-%s" % (y, pe),
                     "deadline": dead.isoformat(), "days_left": (dead - today).days})
    upcoming = [r for r in rows if r["days_left"] >= 0]
    for r in rows:
        if r["days_left"] < 0:
            r["status"] = "past"
        elif upcoming and r is upcoming[0]:
            r["status"] = "next"
        else:
            r["status"] = "future"
    return rows


# 政要交易追蹤（模組 7）：公開披露整理，站長手動維護，只收錄有公開報導來源的記錄
# 披露規則：國會議員 STOCK Act（交易 >1,000 美元須在知悉後 30 天內、交易後 45 天內申報）；
# 總統／高級行政官員按 OGE 年度／季度財務申報，金額僅披露區間
POLITICIAN_DISCLOSURES = [
    {
        "person": "特朗普 Donald J. Trump",
        "role": "美國總統（資產置於可撤銷信託，第三方金融機構管理）",
        "period": "2026 Q1（1–3 月）",
        "disclosed": "2026-05 披露",
        "stats": "約 3,642 筆交易 · 總額區間 2.2 億–7.5 億美元",
        "buys": [
            {"name": "甲骨文", "ticker": "ORCL", "range": "220–1,060 萬美元（最大買入）"},
            {"name": "英偉達", "ticker": "NVDA", "range": "≈600 萬美元"},
            {"name": "蘋果", "ticker": "AAPL", "range": "淨買 210–720 萬（8 買 1 賣）"},
            {"name": "Alphabet", "ticker": "GOOGL", "range": "全為買入，150–310 萬"},
            {"name": "博通", "ticker": "AVGO", "range": "100–500 萬建倉"},
            {"name": "德州儀器", "ticker": "TXN", "range": "100–500 萬建倉"},
            {"name": "新思科技", "ticker": "SNPS", "range": "100–500 萬建倉"},
            {"name": "楷登電子", "ticker": "CDNS", "range": "100–500 萬建倉"},
            {"name": "戴爾科技", "ticker": "DELL", "range": "2/10 建倉 100–500 萬"},
            {"name": "英特爾", "ticker": "INTC", "range": "建倉"},
            {"name": "ServiceNow", "ticker": "NOW", "range": "買入"},
            {"name": "Adobe", "ticker": "ADBE", "range": "買入"},
            {"name": "Workday", "ticker": "WDAY", "range": "買入"},
            {"name": "特斯拉", "ticker": "TSLA", "range": "雙向、買為主"},
            {"name": "洛克希德-馬丁", "ticker": "LMT", "range": "軍工股買入"},
            {"name": "諾斯羅普·格魯曼", "ticker": "NOC", "range": "軍工股買入"},
            {"name": "通用動力", "ticker": "GD", "range": "軍工股買入"},
            {"name": "波音", "ticker": "BA", "range": "買入"},
            {"name": "KURA 壽司美國", "ticker": "KRUS", "range": "100–500 萬"},
            {"name": "9 隻跨境 ETF", "ticker": "", "range": "19 筆全買 500–1,310 萬（IEMG／加拿大／日本／歐洲／黃金信託）"},
        ],
        "sells": [
            {"name": "微軟", "ticker": "MSFT", "range": "單筆 500–2,500 萬（最高量級）"},
            {"name": "亞馬遜", "ticker": "AMZN", "range": "單筆 500–2,500 萬（最高量級）"},
            {"name": "Meta", "ticker": "META", "range": "單筆 500–2,500 萬（最高量級）"},
            {"name": "特斯拉", "ticker": "TSLA", "range": "賣出量超過買入"},
        ],
        "note": "「七巨頭」共 94 筆（64 買 30 賣，總值 5,000–7,000 萬美元）；廣持 VOO／SPY 等市場型 ETF。爭議時點：2/10 買入英偉達一周後英偉達宣佈與 Meta 合作；買入戴爾早於 5 月公開背書。監督組織批評「總統不應淪為日內交易者」；特朗普集團回應稱投資組合由第三方管理，特朗普本人及家人不參與具體決策。",
        "source": "OGE 披露整理（光明網 2026-05-21、財聯社、星島頭條等）",
    },
    {
        "person": "特朗普 Donald J. Trump",
        "role": "美國總統",
        "period": "2026 年 7 月",
        "disclosed": "2026-09 披露",
        "stats": "1,156 筆交易 · 總額區間 7,900 萬–2.7 億美元",
        "buys": [
            {"name": "英偉達", "ticker": "NVDA", "range": "增持"},
            {"name": "SpaceX", "ticker": "", "range": "6/12 史上最大 IPO（≈750 億美元）後買入"},
            {"name": "Intuit", "ticker": "INTU", "range": "買入"},
            {"name": "Salesforce", "ticker": "CRM", "range": "買入"},
            {"name": "特斯拉", "ticker": "TSLA", "range": "持續雙向交易"},
            {"name": "市政債券", "ticker": "", "range": "邁阿密戴德縣航空收入債券等"},
        ],
        "sells": [
            {"name": "微軟", "ticker": "MSFT", "range": "大手減持（單筆 500–2,500 萬）"},
            {"name": "亞馬遜", "ticker": "AMZN", "range": "大手減持（單筆 500–2,500 萬）"},
            {"name": "甲骨文", "ticker": "ORCL", "range": "同日賣出"},
        ],
        "note": "與多隻 ETF 及市政債券交易並行；延續「大賣小買」模式。",
        "source": "香港商報 2026-09-24 等公開報導",
    },
]

POLITICIAN_CONGRESS = {
    "spacex": {
        "title": "SpaceX IPO 後國會議員六日內買入",
        "note": "2026-06-12 SpaceX 以 ≈750 億美元創史上最大 IPO；6 名眾議員或其直系家屬在上市後 6 天內買入約 8.3 萬–24.5 萬美元，其中 5 人任職於監管 SpaceX 相關行業的委員會（國防、衛星、AI、證券）。交易本身合法，無內幕交易證據，但引發利益衝突質疑。",
        "source": "CNBC 2026-07-28、Digital Today 等",
        "rows": [
            {"name": "William Timmons", "party": "R-SC", "range": "8.3 萬–24.5 萬美元區間內"},
            {"name": "John McGuire", "party": "R-VA", "range": "同上區間"},
            {"name": "Dan Meuser", "party": "R-PA", "range": "同上區間"},
            {"name": "Gil Cisneros", "party": "D-CA", "range": "同上區間"},
            {"name": "John James", "party": "R-MI", "range": "同上區間"},
            {"name": "Jared Moskowitz", "party": "D-FL", "range": "同上區間"},
        ],
    },
    "violations": {
        "title": "2026 年 STOCK Act 逾期申報事件",
        "note": "STOCK Act 規定：超過 1,000 美元的證券交易須在知悉後 30 天內、且不晚於交易後 45 天申報；逾期申報標準罰款 200 美元。2026 年多起重大逾期被曝光：",
        "rows": [
            {"name": "Sen. Alan Armstrong", "party": "R-OK", "detail": "700 筆交易（324 萬–1,605 萬美元）逾期逾兩個月；辯稱第三方顧問「直接指數化策略」。已不尋求連任"},
            {"name": "Rep. Michael Rulli", "party": "R-OH", "detail": "32 筆中 22 筆逾期，最早溯及 2024-11（近兩年），最高 48 萬美元，含「七巨頭」中六隻"},
            {"name": "Rep. Julie Johnson", "party": "D-TX", "detail": "2026-08 補披露 2025-05 起交易共計最高 110 萬美元，此前曾承諾清倉"},
            {"name": "其他被點名者", "party": "—", "detail": "Crenshaw、Laurel Lee、Linda Sánchez、Letlow、Jim Jordan、McClain（眾院）；Britt、Collins、Hickenlooper、Rounds、Fetterman（參院）等亦被指逾期申報"},
        ],
        "source": "Benzinga／TradingView、NewsOn6、Public Radio Tulsa 2026 年報導",
    },
    "overlap": {
        "title": "委員會職權與持倉重疊（CNN 2026-02 分析）",
        "note": "至少 10 名參議員在與其委員會監管行業相關的公司有交易記錄，例如 Moody（健康委員會）買入禮來（Eli Lilly）、Moran 在出席 AI 聽證會當天買入 Alphabet。",
        "rows": [
            {"name": "Bill Hagerty", "party": "R-TN", "detail": "委員會重疊交易"},
            {"name": "Ashley Moody", "party": "R-FL", "detail": "健康委員會 · 買入禮來（LLY）"},
            {"name": "Jerry Moran", "party": "R-KS", "detail": "出席 AI 聽證會當天買入 Alphabet（GOOGL）"},
            {"name": "Markwayne Mullin", "party": "R-OK", "detail": "委員會重疊交易"},
            {"name": "Tommy Tuberville", "party": "R-AL", "detail": "委員會重疊交易"},
            {"name": "John Hickenlooper", "party": "D-CO", "detail": "委員會重疊交易"},
            {"name": "Gary Peters", "party": "D-MI", "detail": "委員會重疊交易"},
            {"name": "Sheldon Whitehouse", "party": "D-RI", "detail": "委員會重疊交易"},
        ],
        "source": "CNN 分析（Capitol Trades 2026-02-12 新聞稿）",
    },
}

# 披露中出現、但站內 companies 未有頁面的個股 → 對應 stock_pages.py 生成的獨立分析頁
POLIT_PAGES = {
    "CDNS": "楷登电子.html",
    "DELL": "戴尔科技.html",
    "GD": "通用动力.html",
    "KRUS": "KURA寿司美国.html",
    "NOC": "诺斯罗普格鲁曼.html",
    "SNPS": "新思科技.html",
    "WDAY": "Workday.html",
}


def build_polit_holdings(polit, companies):
    """政要交易反向匹配：僅用披露記錄中的明確代碼或公司名對照站內覆蓋公司，不做推斷。"""
    by_ticker, by_name = {}, {}
    for c in companies:
        t = (c.get("ticker") or "").strip().upper()
        if t:
            by_ticker[t] = c
        n = (c.get("name") or "").strip()
        if len(n) >= 2:
            by_name[n] = c
    hold = defaultdict(list)
    for p in polit:
        for side in ("buys", "sells"):
            for it in p.get(side) or []:
                tk = (it.get("ticker") or "").strip().upper()
                matched = None
                if tk and tk in by_ticker:
                    matched = tk
                elif it.get("name") in by_name:
                    matched = by_name[it["name"]].get("ticker") or ""
                if matched:
                    hold[matched].append({
                        "person": p["person"].split(" ")[0],
                        "side": "買入" if side == "buys" else "賣出",
                        "period": p["period"],
                        "item": it["name"],
                        "range": it.get("range") or "",
                        "disclosed": p["disclosed"],
                    })
    return dict(hold)


def build_politician(companies):
    """政要區數據：披露交易逐筆附上站內個股獨立分析頁路徑（僅披露中明確的個股，無頁面者為空）。"""
    by_ticker = {}
    for c in companies:
        t = (c.get("ticker") or "").strip().upper()
        if t:
            by_ticker[t] = c.get("page") or ""
    dis = json.loads(json.dumps(POLITICIAN_DISCLOSURES))
    for p in dis:
        for side in ("buys", "sells"):
            for it in p.get(side) or []:
                tk = (it.get("ticker") or "").strip().upper()
                pg = by_ticker.get(tk) or POLIT_PAGES.get(tk, "")
                it["page"] = pg if not pg or pg.startswith("stocks/") else "stocks/" + pg
    return {"disclosures": dis, "congress": POLITICIAN_CONGRESS}


# 中國資產專區（模組 8）：宏觀與指數為公開數據手動維護（附來源），個股行情由站內抓取
CHINA_MACRO = {
    "lpr_1y": 3.0, "lpr_5y": 3.5,
    "lpr_note": "連續 16 個月不變（2026-09-20 人行授權公告）",
    "gdp_h1": 4.7, "gdp_q1": 5.0, "gdp_q2": 4.3, "gdp_target": "全年目標 ≈4.5%",
    "gdp_note": "上半年 GDP 69.57 萬億元；內需對增長貢獻率超 80%；Q2 名義增速 5.9%，GDP 平減指數 12 個季度以來首次轉正（+1.53%）",
    "pmi": [{"m": "6 月", "v": 50.3}, {"m": "7 月", "v": 49.2}, {"m": "8 月", "v": 49.8}],
    "pmi_note": "8 月連續第 2 個月處收縮區間；生產指數 50.4、新訂單 50.6 重回景氣區間",
    "source": "人行、國家統計局公開數據（2026-09）",
}

CHINA_INDICES = [
    {"name": "恆生指數", "ticker": "^HSI", "price": 24693.40, "chg": 183.31,
     "ytd": -4.37, "asof": "2026-09-28", "note": "月內區間 24,510–25,275"},
    {"name": "滬深300", "ticker": "000300.SS", "price": 4342.58, "chg": -96.56,
     "ytd": -4.12, "asof": "2026-09-28", "note": "月內區間 4,340–4,990"},
]

CHINA_TRADE_TIMELINE = [
    {"date": "2025-10", "title": "吉隆坡聯合安排",
     "detail": "部分關稅與非關稅措施暫停實施至 2026-11-10（含美方 24% 對等關稅與中方反制措施）"},
    {"date": "2026-02", "title": "美最高法院裁決 IEEPA 關稅違法",
     "detail": "美政府依據《國際緊急經濟權力法案》加徵的關稅被裁違法；美方轉向以新 301 調查關稅替代"},
    {"date": "2026-05-13/15", "title": "特朗普訪華 · 北京元首會晤",
     "detail": "5/12-13 韓國磋商初步成果：原則同意各 300 億美元規模產品對等降稅框架、設貿易理事會與投資理事會"},
    {"date": "2026-09-20/23", "title": "第八輪經貿磋商（紐約／華盛頓）",
     "detail": "「300 億對 300 億」對等降稅達成共識（各自約 90% 產品降至最惠國稅率）；設農業工作組（年底前首次會議）；金融服務原則共識；擴大自美進口煤炭（2027／2028 每年）"},
]


def compute_china(companies, quotes, fund_data):
    """中國資產專區：站內港股／A股／中概股行情與估值聚合（宏觀與指數見 CHINA_* 常量）。"""
    cn_regions = {"港股", "A股", "中概股"}
    rows = []
    for c in companies:
        t = c.get("ticker") or ""
        is_hk = t.endswith(".HK")
        is_a = t.endswith((".SZ", ".SS"))
        is_uscno = c.get("region") == "中概股"
        if not (is_hk or is_a or is_uscno) and c.get("region") not in cn_regions:
            continue
        q = quotes.get(t) or {}
        ks = (((fund_data.get(t) or {}).get("qs") or {}).get("defaultKeyStatistics") or {})

        def _u(v):
            return v.get("raw") if isinstance(v, dict) else v

        pe = _u(ks.get("trailingPE"))
        price = q.get("price")
        eps = _u(ks.get("trailingEps"))
        if pe is None and price and eps:
            pe = price / eps
        rows.append({
            "name": c["name"], "ticker": t, "sector": c.get("sector", ""),
            "region": "中概股" if is_uscno else ("港股" if is_hk else "A股"),
            "currency": q.get("currency") or "",
            "price": price, "change_pct": q.get("change_pct"),
            "pe": pe, "mktcap": _u(ks.get("marketCap")),
            "page": c.get("page", ""),
        })
    with_price = [r for r in rows if r["price"] is not None]
    with_chg = [r for r in rows if r["change_pct"] is not None]
    gainers = sorted(with_chg, key=lambda r: -r["change_pct"])[:8]
    losers = sorted(with_chg, key=lambda r: r["change_pct"])[:8]
    cap_top = sorted([r for r in rows if r.get("mktcap")],
                     key=lambda r: -r["mktcap"])[:10]
    sectors = defaultdict(list)
    for r in rows:
        if r.get("pe") and r["pe"] > 0:
            sectors[r["sector"] or "其他"].append(r["pe"])
    sector_rows = [{"sector": s, "n": len(v), "pe_median": round(sorted(v)[len(v) // 2], 1)}
                   for s, v in sorted(sectors.items(), key=lambda kv: -kv[1][0])
                   if len(v) >= 2]
    pes = [r["pe"] for r in rows if r.get("pe") and r["pe"] > 0]
    return {
        "stats": {
            "n": len(rows),
            "hk": sum(1 for r in rows if r["region"] == "港股"),
            "a": sum(1 for r in rows if r["region"] == "A股"),
            "uscno": sum(1 for r in rows if r["region"] == "中概股"),
            "with_price": len(with_price),
            "pe_median": round(sorted(pes)[len(pes) // 2], 1) if pes else None,
        },
        "gainers": gainers, "losers": losers, "cap_top": cap_top,
        "sectors": sector_rows, "rows": rows,
    }


def compute_portfolio(asset_perf, targets):
    """依建議配置權重，用日線序列計算組合的實時收益（買入持有、每日以目標權重再平衡），對比 SPY 基準。"""
    sym_map = {"股票": "SPY", "國債": "IEF", "商品": "DBC", "黃金": "GLD", "現金": "BIL"}
    weights = {}
    for t in targets:
        sym = sym_map.get(t["cls"])
        if sym and (asset_perf.get(sym, {}) or {}).get("series"):
            weights[sym] = t["pct"] / 100.0
    bench = asset_perf.get("SPY", {})
    if not weights or not bench.get("series"):
        return None

    # 以 SPY 交易日為主軸，其餘資產用「最近一次收盤」前向填充
    maps = {}
    for sym in list(weights) + ["SPY"]:
        d = asset_perf.get(sym, {})
        maps[sym] = dict(zip(d.get("dates") or [], d.get("series") or []))
    dates = bench.get("dates") or []
    pf, bm, lasts = [], [], {s: None for s in maps}
    base = None
    for dt in dates:
        for s, m in maps.items():
            if dt in m:
                lasts[s] = m[dt]
        b = lasts["SPY"]
        if any(lasts[s] is None for s in weights) or b is None:
            if base is not None:
                pf.append(pf[-1]); bm.append(bm[-1])
            continue
        if base is None:
            base = {s: lasts[s] for s in weights}
            base_b = b
        pf.append(sum(weights[s] * lasts[s] / base[s] for s in weights) * 100)
        bm.append(b / base_b * 100)
    if len(pf) < 30:
        return None

    def ret(series, n):
        if n <= 0 or n >= len(series):
            return None
        return round((series[-1] / series[-1 - n] - 1) * 100, 2)

    cur_year = str(datetime.now().year) + "-01-01"
    ytd = bytd = None
    for i, d in enumerate(dates):
        if d >= cur_year and ytd is None and pf[i]:
            ytd = round((pf[-1] / pf[i] - 1) * 100, 2)
            break
    for i, d in enumerate(dates):
        if d >= cur_year and bytd is None and bm[i]:
            bytd = round((bm[-1] / bm[i] - 1) * 100, 2)
            break

    tail = 250
    return {
        "weights": {s: round(w * 100, 1) for s, w in weights.items()},
        "dates": dates[-tail:],
        "portfolio": [round(v, 2) for v in pf[-tail:]],
        "benchmark": [round(v, 2) for v in bm[-tail:]],
        "start": dates[0],
        "ytd": ytd, "m1": ret(pf, 21), "m3": ret(pf, 63),
        "y1": round((pf[-1] / 100 - 1) * 100, 2) if pf[0] == 100 else ret(pf, len(pf) - 1),
        "bench_ytd": bytd, "bench_m1": ret(bm, 21), "bench_m3": ret(bm, 63),
        "bench_y1": round((bm[-1] / 100 - 1) * 100, 2) if bm[0] == 100 else ret(bm, len(bm) - 1),
        "asof": dates[-1],
    }


HIST_SYMBOLS = ["SPY", "IEF", "DBC", "GLD", "BIL"]

SCENARIO_WINDOWS = [
    {"id": "2008", "title": "2008 金融危機", "emoji": "🏚",
     "start": "2007-10-01", "end": "2013-06-30",
     "desc": "雷曼倒閉引爆全球金融危機；美聯儲將利率降至零並啟動 QE。",
     "facts": ["標普500 自高點最大回撤約 -56%（2007-10 → 2009-03）",
               "回補前高耗時約 5 年（2013-03）", "避險資產勝出：美債、黃金大漲"]},
    {"id": "2020", "title": "2020 疫情崩盤", "emoji": "🦠",
     "start": "2020-01-01", "end": "2021-06-30",
     "desc": "新冠疫情全球擴散，市場一個月急跌；央行無限 QE 與財政刺激帶來 V 型反轉。",
     "facts": ["標普500 約 1 個月急跌 -34%", "回補前高僅約 5 個月（2020-08）",
               "商品與黃金同漲，現金回報趨零"]},
    {"id": "2022", "title": "2022 加息熊市", "emoji": "🏦",
     "start": "2021-12-01", "end": "2024-06-30",
     "desc": "通脹飆升，聯儲以四十年最快速度加息；股債雙殺。",
     "facts": ["標普500 全年 -19%，美債百年最差年份之一", "回補前高約 2 年（2024-01）",
               "股債同跌，傳統 60/40 失效；商品與現金跑贏"]},
]


def compute_scenarios(hist, targets):
    """歷史情景回測（模組 9）：以當前建議配置權重，回放 2008／2020／2022 三場危機
    （月頻、每月再平衡，全部用真實 ETF 月線計算，不臆造任何數字）。"""
    sym_map = {"股票": "SPY", "國債": "IEF", "商品": "DBC", "黃金": "GLD", "現金": "BIL"}
    weights = {}
    for t in targets:
        sym = sym_map.get(t["cls"])
        if sym and sym in hist:
            weights[sym] = t["pct"] / 100.0
    if not weights or "SPY" not in hist:
        return []

    def metrics(vals):
        vals = [v for v in vals if v is not None]
        if len(vals) < 2 or not vals[0]:
            return None
        vals = [v / vals[0] for v in vals]  # 歸一化為期初 1.0
        peak, maxdd, trough_i = vals[0], 0.0, 0
        for i, v in enumerate(vals):
            peak = max(peak, v)
            dd = v / peak - 1
            if dd < maxdd:
                maxdd, trough_i = dd, i
        rec = None
        for i in range(trough_i + 1, len(vals)):
            if vals[i] >= 1.0:
                rec = i - trough_i
                break
        return {"ret": round((vals[-1] - 1) * 100, 2),
                "maxdd": round(maxdd * 100, 2), "recover_months": rec}

    def slim(vals, n=40):
        vals = [v for v in vals if v is not None]
        step = max(1, len(vals) // n)
        return [round(v * 100, 1) for v in vals[::step]]

    out = []
    w_dates = hist["SPY"]["dates"]
    maps = {s: dict(zip(h["dates"], h["closes"])) for s, h in hist.items()}
    for sc in SCENARIO_WINDOWS:
        i0 = next((i for i, d in enumerate(w_dates) if d >= sc["start"]), None)
        if i0 is None:
            continue
        i1 = next((i for i, d in enumerate(w_dates) if d > sc["end"]), len(w_dates))
        axes = w_dates[i0:i1]
        lasts, fills = {s: None for s in maps}, []
        for d in axes:
            for s, m in maps.items():
                if d in m:
                    lasts[s] = m[d]
            fills.append(dict(lasts))

        def series_of(sym):
            return [f.get(sym) for f in fills]

        pf, base = [], None
        for f in fills:
            if any(f.get(s) is None for s in weights):
                pf.append(pf[-1] if pf else None)
                continue
            if base is None:
                base = {s: f[s] for s in weights}
            pf.append(sum(weights[s] * f[s] / base[s] for s in weights))

        assets = {s: metrics(series_of(s)) for s in sorted(weights)}
        assets = {s: m for s, m in assets.items() if m}
        # 模組 35：歸因——各資產貢獻 ≈ 權重 × 資產期間回報（月頻再平衡的近似分解）
        spy_m = metrics(series_of("SPY"))
        pf_m = metrics(pf)
        attr = []
        for s, w in weights.items():
            m = metrics(series_of(s))
            if m:
                attr.append({"sym": s, "label": RISK_LABELS.get(s, s),
                             "w": round(w * 100, 1), "ret": m["ret"],
                             "contrib": round(w * m["ret"], 2)})
        attr.sort(key=lambda a: -(a["contrib"] or -999))
        out.append({
            "id": sc["id"], "title": sc["title"], "emoji": sc["emoji"],
            "start": axes[0], "end": axes[-1], "desc": sc["desc"], "facts": sc["facts"],
            "weights": {s: round(w * 100, 1) for s, w in weights.items()},
            "assets": assets, "pf": pf_m, "spy": spy_m,
            "attr": attr,
            "excess": round((pf_m["ret"] - spy_m["ret"]), 2)
            if pf_m and spy_m else None,
            "pf_series": slim(pf), "spy_series": slim(series_of("SPY")),
            "n_months": len(axes),
        })
    return out


# ---------------------------------------------------------------------------
# 模組 7/8/10/18：風險儀表板（衰退概率／相關性矩陣／尾部風險／情緒指標）
# ---------------------------------------------------------------------------

RISK_ASSETS = ["SPY", "IEF", "DBC", "GLD", "BIL"]
RISK_LABELS = {"SPY": "股票", "IEF": "國債", "DBC": "商品", "GLD": "黃金", "BIL": "現金"}

# 情緒指標人工維護數據（模組 18）：AAII 週度調查與 CNN 恐懼貪婪指數公開報導，站長手動更新
SENTIMENT_MANUAL = [
    {"label": "AAII 散戶情緒：多空差", "value": -15.4, "unit": "百分點",
     "detail": "看多 32.7%／中性 19.2%／看空 48.1%；連續第 10 週低於歷史均值 +6.5%",
     "asof": "2026-09-24 當週", "source": "AAII 週度情緒調查"},
    {"label": "CNN 恐懼貪婪指數", "value": 38, "unit": "/ 100",
     "detail": "位於「恐懼」區間；自 9-16 低點 27 回升 11 點（大型科技股反彈），但廣度仍窄",
     "asof": "2026-09-25", "source": "CNN Fear & Greed Index"},
    {"label": "散戶現金配置偏高比例", "value": 19.1, "unit": "%",
     "detail": "AAII 調查回答現金配置「遠高於正常」的受訪者比例（防禦性配置訊號）",
     "asof": "2026-09-24 當週", "source": "AAII 週度情緒調查"},
]


def _month_end(vals):
    """日頻 [date, value] 降為月頻（取每月最後一個值）。"""
    by = {}
    for d, v in vals:
        by[d[:7]] = v
    return sorted(by.items())


def _returns_from_closes(closes):
    return [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes))
            if closes[i - 1]]


def _pearson(xs, ys):
    n = min(len(xs), len(ys))
    xs, ys = xs[:n], ys[:n]
    if n < 12:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if not sxx or not syy:
        return None
    return sxy / (sxx * syy) ** 0.5


def _pct_rank(v, vals, lo=None):
    if v is None or not vals:
        return None
    if lo is not None:
        vals = [x for x in vals if x >= lo]
    if not vals:
        return None
    vals = sorted(vals)
    return round(sum(1 for x in vals if x <= v) / len(vals) * 100, 1)


def _sigmoid(z):
    return 1.0 / (1.0 + math.exp(-z))


def build_recession_model(fred):
    """模組 7：10Y-3M 利差 vs 未來 12 個月是否衰退（NBER USREC）的邏輯迴歸模型。
    全部使用 FRED 真實歷史資料，樣本內擬合後給出當前利差對應的衰退概率。"""
    spread = _month_end(fred.get("T10Y3M") or [])
    rec_map = dict(_month_end(fred.get("USREC") or []))
    if len(spread) < 120:
        return {}
    months = [d for d, _ in spread]
    X, Y = [], []
    for i, (d, s) in enumerate(spread):
        future = months[i + 1:i + 13]
        if len(future) < 12:
            break
        y = 1.0 if any(rec_map.get(m, 0) > 0 for m in future) else 0.0
        X.append(s)
        Y.append(y)
    # 邏輯迴歸（梯度上升，無第三方庫）
    a, b, n = -2.0, -1.0, len(X)
    for _ in range(600):
        ga = gb = 0.0
        for s, y in zip(X, Y):
            p = _sigmoid(a + b * s)
            ga += y - p
            gb += (y - p) * s
        a += 0.05 * ga / n
        b += 0.05 * gb / n
    probs = [_sigmoid(a + b * s) * 100 for s in X]
    step = max(1, len(probs) // 40)
    series = [{"d": months[i], "p": round(probs[i], 1)}
              for i in range(len(X)) if i % step == 0]
    cur_d, cur_s = spread[-1]
    series.append({"d": cur_d, "p": round(_sigmoid(a + b * cur_s) * 100, 1)})
    # NBER 衰退月份壓縮成區間文字（供圖表標註）
    rec_m = sorted(d for d in months if rec_map.get(d, 0) > 0)
    ranges, lo, prev = [], None, None

    def _next_m(d):
        y, m = int(d[:4]), int(d[5:7])
        return f"{y + (m == 12)}-{(m % 12) + 1:02d}"

    for d in rec_m:
        if lo is None or d[:7] != _next_m(prev):
            if lo:
                ranges.append([lo, prev])
            lo = d
        prev = d
    if lo:
        ranges.append([lo, prev])
    return {
        "spread_now": round(cur_s, 2), "spread_date": cur_d,
        "prob_now": round(_sigmoid(a + b * cur_s) * 100, 1),
        "b": round(b, 4),
        "series": series,
        "rec_ranges": ranges,
        "n_months": n,
        "n_rec": int(sum(Y)),
        "train_end": months[len(X) - 1],
    }


def build_concentration(companies, fund_data):
    """模組 10：站內美股公司市值前十大集中度（Yahoo 市值快照，真實計算）。"""
    caps = []
    for c in companies:
        t = c.get("ticker") or ""
        # 只統計美國上市（無交易所後綴）的公司，市值同為美元口徑
        if not t or "." in t:
            continue
        fd = (fund_data or {}).get(t) or {}
        sd = ((fd.get("qs") or {}).get("summaryDetail") or {})
        mc = sd.get("marketCap")
        mc = mc.get("raw") if isinstance(mc, dict) else mc
        if isinstance(mc, (int, float)) and mc > 0:
            caps.append((c["name"], mc))
    caps.sort(key=lambda x: -x[1])
    total = sum(mc for _, mc in caps)
    if total <= 0:
        return None
    top10 = [{"name": n, "pct": round(mc / total * 100, 1)} for n, mc in caps[:10]]
    return {"top10": top10, "top10_sum": round(sum(x["pct"] for x in top10), 1),
            "n_companies": len(caps)}


def build_gepu(fred):
    vals = fred.get("GEPUCURRENT") or []
    if len(vals) < 60:
        return None
    cur = vals[-1][1]
    return {"now": round(cur, 1), "pct": _pct_rank(cur, [v for _, v in vals[-120:]]),
            "date": vals[-1][0]}


def compute_risk(fred, quotes, hist, fund_data, companies):
    """風險儀表板：衰退概率（模組 7）、相關性矩陣（模組 8）、尾部風險（模組 10）、
    情緒指標（模組 18）。全部由 FRED／Yahoo 真實歷史資料計算。"""
    risk = {"recession": build_recession_model(fred)}

    # 初請失業金（週頻）：4 週均線與環比／年比
    icsa = fred.get("ICSA") or []
    if len(icsa) >= 56:
        cur4 = sum(v for _, v in icsa[-4:]) / 4
        prev4 = sum(v for _, v in icsa[-5:-1]) / 4
        y4 = sum(v for _, v in icsa[-56:-52]) / 4
        risk["recession"]["icsa"] = {
            "now": icsa[-1][1], "ma4": round(cur4), "date": icsa[-1][0],
            "wo_prev": round((cur4 / prev4 - 1) * 100, 1) if prev4 else None,
            "yo_prev": round((cur4 / y4 - 1) * 100, 1) if y4 else None,
        }
    g = growth_score(fred)
    if g is not None:
        risk["recession"]["growth_now"] = round(g)

    # ---- 模組 8：相關性矩陣（月報酬，全樣本 vs 近 36 個月）----
    syms = [s for s in RISK_ASSETS if s in hist and len(hist[s]["closes"]) >= 40]
    if len(syms) >= 3:
        rets = {s: _returns_from_closes(hist[s]["closes"]) for s in syms}
        full = [[round(_pearson(rets[s1], rets[s2]), 2) for s2 in syms] for s1 in syms]
        recent = [[round(_pearson(rets[s1][-36:], rets[s2][-36:]), 2) for s2 in syms]
                  for s1 in syms]
        risk["corr"] = {
            "labels": [RISK_LABELS.get(s, s) for s in syms],
            "full": full, "recent": recent,
            "n_months": max(len(rets[s]) for s in syms), "window": 36,
        }

    # ---- 模組 10：尾部風險 ----
    tail_items = []
    for sid, label in [("BAMLH0A0HYM2", "高收益信用利差（OAS）"),
                       ("BAMLC0A0CM", "投資級信用利差（OAS）")]:
        vals = fred.get(sid) or []
        if len(vals) < 250:
            continue
        cur = vals[-1][1] * 100  # FRED 原生單位為百分點，轉基點
        hist10 = [v * 100 for _, v in vals[-2520:]]
        tail_items.append({
            "label": label, "now": round(cur), "unit": "基點",
            "pct": _pct_rank(cur, hist10),
            "lo10": round(min(hist10)), "hi10": round(max(hist10)),
            "date": vals[-1][0],
        })
    vix = fred.get("VIXCLS") or []
    vix_blk = None
    if len(vix) >= 250:
        cur = vix[-1][1]
        hist10 = [v for _, v in vix[-2520:]]
        vix_blk = {
            "now": round(cur, 2), "pct": _pct_rank(cur, hist10),
            "ma200": round(sum(v for _, v in vix[-200:]) / 200, 2),
            "date": vix[-1][0],
        }
    if tail_items or vix_blk:
        risk["tail"] = {
            "items": tail_items, "vix": vix_blk,
            "concentration": build_concentration(companies, fund_data),
            "gepu": build_gepu(fred),
        }

    # ---- 模組 18：情緒指標（VIX 恐慌指標 + 人工維護的 AAII／CNN 公開數據）----
    risk["sentiment"] = {"vix": vix_blk, "manual": SENTIMENT_MANUAL}
    return risk


# ---------------------------------------------------------------------------
# 模組 11/13/14/16/17/19/21：市場全景（資金流向／擴展資產／全球儀表板／盈利週期／
# 技術面／ETF 持倉穿透／再平衡提醒）
# ---------------------------------------------------------------------------

GLOBAL_INDICES = {
    "^GSPC": "標普500", "^IXIC": "納斯達克", "^HSI": "恒生指數", "000300.SS": "滬深300",
    "^N225": "日經225", "^GDAXI": "德國DAX", "^FTSE": "英國富時100",
    "^NSEI": "印度Nifty 50", "^BVSP": "巴西Bovespa", "EEM": "MSCI 新興市場",
}
EXTENDED_ASSETS = {
    "VNQ": "美國房地產 REITs", "BTC-USD": "比特幣", "ETH-USD": "以太幣",
    "DX-Y.NYB": "美元指數", "EEM": "MSCI 新興市場", "PSP": "全球上市私募股權",
}
ETF_HOLDING_SYMBOLS = ["SPY", "IEF", "DBC", "GLD", "BIL"]
INDEX_PERF_CACHE = os.path.join(SITE_DIR, "js", "index_perf_cache.json")
EARNINGS_CACHE = os.path.join(SITE_DIR, "js", "earnings_cache.json")
ETF_CACHE = os.path.join(SITE_DIR, "js", "etf_cache.json")

# 資金流向人工維護數據（模組 11）：LSEG Lipper／ICI 週度數據與 NAAIM 曝險的公開報導，
# 站長手動更新（NAAIM 2026-08-01 起轉訂閱制）
FUND_FLOWS_MANUAL = {
    "weeks": [
        {"week": "截至 2026-09-25", "global_eq": 44.1, "us_eq": 37.6, "us_bond": 5.93,
         "note": "全球股票基金 +441 億美元，7-08 以來最大單週流入；AI 樂觀情緒回歸＋油價回落。科技板塊 +48.9 億、金融 −25.3 億"},
        {"week": "截至 2026-09-16", "global_eq": -23.21, "us_eq": -31.44, "us_bond": None,
         "note": "全球股票基金 −232 億美元，九個月來最大單週流出（油價創四個月高點、聯儲加息前通脹擔憂）；亞洲基金逆勢 +62.6 億"},
    ],
    "ici": {"week": "截至 2026-08-27 當週", "equity": 12.34, "bond": -3.21,
            "note": "ICI 週度統計：股票基金 +123.4 億美元、債券基金 −32.1 億美元",
            "source": "ICI 週度統計"},
    "naaim": {"value": 89.6, "date": "2026-09-11", "median": 92.64,
              "note": "主動投資經理平均美股曝險（100=滿倉）；8-26 曾達 102.66（槓桿多頭）",
              "source": "NAAIM Exposure Index"},
    "source": "LSEG Lipper 週度基金流量（公開報導，站長手動維護）",
}


def fetch_earnings():
    """模組 16：標普 500 盈利歷史（multpl.com 公開表格，as-reported EPS）。"""
    url = "https://www.multpl.com/s-p-500-earnings/table/by-year"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            page = resp.read().decode("utf-8", "replace")
        m = re.search(r'<table id="datatable".*?</table>', page, re.S)
        if not m:
            return []
        rows = []
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", m.group(0), re.S):
            cells = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip()
                     .replace(" ", "").replace("\n", "")
                     for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]
            if len(cells) >= 2 and cells[1] and cells[0] != "Date":
                d = datetime.strptime(cells[0], "%b %d, %Y").strftime("%Y-%m-%d")
                rows.append({"date": d, "eps": float(cells[1])})
        return rows
    except Exception as e:
        print(f"  ✗ 標普500盈利 multpl {e}")
        return []


def fetch_etf_holdings(symbols):
    """模組 19：ETF 前十大持倉與行業權重（Yahoo quoteSummary topHoldings）。"""
    jar = http.cookiejar.CookieJar()
    crumb = _get_crumb(jar)
    if not crumb:
        print("  ✗ Yahoo crumb 取得失敗，ETF 持倉穿透跳過")
        return {}
    out = {}
    for sym in sorted(symbols):
        try:
            url = ("https://query1.finance.yahoo.com/v10/finance/quoteSummary/"
                   f"{urllib.parse.quote(sym)}?modules=topHoldings,fundProfile"
                   f"&crumb={urllib.parse.quote(crumb)}")
            d = _yahoo_json(url, jar)
            res = (d.get("quoteSummary", {}).get("result") or [None])[0]
            if not res:
                continue
            th = res.get("topHoldings") or {}
            fp = res.get("fundProfile") or {}
            holds = []
            for h in th.get("holdings") or []:
                s = h.get("symbol")
                p = (h.get("holdingPercent") or {}).get("raw")
                if s and p is not None:
                    holds.append({"sym": s, "pct": round(p * 100, 2)})
            secs = [(w.get("sectorName"), (w.get("sectorWeight") or {}).get("raw"))
                    for w in th.get("sectorWeightings") or []]
            out[sym] = {
                "category": fp.get("categoryName"),
                "holds": holds[:10],
                "sectors": [{"name": n, "pct": round(p * 100, 1)}
                            for n, p in secs if p is not None],
                "asof": th.get("dateShortFormat"),
            }
            print(f"  ✓ ETF 持倉 {sym}（前 {len(out[sym]['holds'])} 大）")
        except Exception as e:
            print(f"  ✗ ETF 持倉 {sym} {e}")
        time.sleep(0.25)
    return out


def _sma(closes, n):
    if not closes or len(closes) < n:
        return None
    return round(sum(closes[-n:]) / n, 2)


def _rsi(closes, n=14):
    if not closes or len(closes) < n + 1:
        return None
    gains = losses = 0.0
    for i in range(len(closes) - n, len(closes)):
        ch = closes[i] - closes[i - 1]
        gains += max(ch, 0.0)
        losses += max(-ch, 0.0)
    if losses == 0:
        return 100.0
    rs = (gains / n) / (losses / n)
    return round(100 - 100 / (1 + rs), 1)


def simulate_rebalance_drift(hist, targets):
    """模組 21：月頻模擬——每月以目標權重重平衡、持有 1 個月後的最大權重偏離分佈。"""
    sym_of = {"股票": "SPY", "國債": "IEF", "商品": "DBC", "黃金": "GLD", "現金": "BIL"}
    rets = {}
    for t in targets:
        sym = sym_of.get(t["cls"])
        if sym in hist:
            closes = hist[sym]["closes"]
            rets[sym] = [closes[i] / closes[i - 1] - 1
                         for i in range(1, len(closes)) if closes[i - 1]]
    if len(rets) < 3:
        return None
    n = min(len(r) for r in rets.values())
    over, maxdrs = 0, []
    for i in range(n):
        w = {}
        for t in targets:
            sym = sym_of.get(t["cls"])
            if sym in rets:
                w[sym] = t["pct"] * (1 + rets[sym][i])
        tot = sum(w.values())
        if tot <= 0:
            continue
        drifts = [abs(t["pct"] - w[sym_of[t["cls"]]] * 100 / tot)
                  for t in targets if sym_of[t["cls"]] in w]
        maxdrs.append(max(drifts))
        if max(drifts) > 5:
            over += 1
    return {"n_months": len(maxdrs),
            "avg_max_drift": round(sum(maxdrs) / len(maxdrs), 1) if maxdrs else None,
            "pct_over5": round(over / len(maxdrs) * 100, 1) if maxdrs else None,
            "threshold": 5}


def compute_market(fred, quotes, index_perf, asset_perf, hist, allocation,
                   earnings, etf_holds, companies):
    """市場全景：全球儀表板（14）、擴展資產（13）、盈利週期（16）、技術面（17）、
    持倉穿透（19）、再平衡提醒（21）、資金流向（11）。"""
    out = {"flows": FUND_FLOWS_MANUAL}

    # ---- 模組 14：全球市場儀表板 ----
    spy_y1 = (index_perf.get("^GSPC") or {}).get("y1")
    rows = []
    for sym, label in GLOBAL_INDICES.items():
        p = index_perf.get(sym) or {}
        q = quotes.get(sym) or {}
        if p.get("price") is None and q.get("price") is None:
            continue
        closes = p.get("closes") or []
        price = p.get("price") or q.get("price")
        ma50, ma200 = _sma(closes, 50), _sma(closes, 200)
        # 資料點太少時不展示期間報酬（避免單點資料出現 0.0% 誤導）
        ok = len(closes) >= 60
        y1 = p.get("y1") if ok else None
        ytd = p.get("ytd") if ok else None
        rows.append({
            "sym": sym, "label": label, "price": round(price, 2),
            "chg": q.get("change_pct"), "ytd": ytd, "y1": y1,
            "rs": round(y1 - spy_y1, 1) if (y1 is not None and spy_y1 is not None) else None,
            "ma50": ma50, "ma200": ma200,
            "trend": "50 日線上方" if (ma50 and price and price >= ma50) else
                     "50 日線下方" if (ma50 and price) else None,
        })
    out["global"] = rows

    # ---- 模組 17：主要指數技術面（50/200 日均線、RSI、52 週位置）----
    tech_rows = []
    for sym in ("^GSPC", "^IXIC", "^HSI", "000300.SS", "^N225"):
        p = index_perf.get(sym) or {}
        q = quotes.get(sym) or {}
        label = GLOBAL_INDICES.get(sym, sym)
        closes = p.get("closes") or []
        price = p.get("price") or q.get("price")
        if price is None:
            continue
        hi52, lo52 = p.get("high"), p.get("low")
        pos52 = round((price - lo52) / (hi52 - lo52) * 100, 1) if (hi52 and lo52 and hi52 != lo52) else None
        ma50, ma200 = _sma(closes, 50), _sma(closes, 200)
        tech_rows.append({
            "sym": sym, "label": label, "price": round(price, 2),
            "ma50": ma50, "ma200": ma200, "rsi": _rsi(closes), "pos52": pos52,
            "above200": None if (ma200 is None or price is None)
                        else price >= ma200,
        })
    out["technicals"] = tech_rows

    # ---- 模組 13：擴展資產類別 ----
    assets = []
    for sym, label in EXTENDED_ASSETS.items():
        p = index_perf.get(sym) or {}
        q = quotes.get(sym) or {}
        if p.get("price") is None and q.get("price") is None:
            continue
        assets.append({"sym": sym, "label": label,
                       "price": round(p.get("price") or q.get("price"), 2),
                       "chg": q.get("change_pct"), "ytd": p.get("ytd"), "y1": p.get("y1")})
    csh = fred.get("CSUSHPINSA") or []
    if len(csh) >= 13:
        now, yago = csh[-1][1], csh[-13][1]
        assets.append({"sym": "CSUSHPINSA", "label": "美國房價（20 城，季調）",
                       "price": round(now, 1), "chg": None, "ytd": None,
                       "y1": round((now / yago - 1) * 100, 1),
                       "note": f"Case-Shiller 指數（FRED，截至 {csh[-1][0]}）"})
    out["assets"] = assets

    # ---- 模組 16：盈利週期（標普 500 EPS：當前、同比、長期、盈利衰退段）----
    # multpl 表格為「當前 TTM（6-30）+ 歷年 12-31」，同比只用 12-31 行比較
    if earnings:
        year_rows = [r for r in earnings if r["date"][5:] == "12-31"]
        yago = {}
        for r in earnings:
            yago[(int(r["date"][5:7]), int(r["date"][:4]))] = r["eps"]
        e_series = []
        for r in year_rows:
            yy = yago.get((12, int(r["date"][:4]) - 1))
            e_series.append({"date": r["date"], "eps": r["eps"],
                             "yy": round((r["eps"] / yy - 1) * 100, 1) if yy else None})
        e_series = sorted(e_series, key=lambda x: x["date"])
        # 盈利衰退段（同比連續為負，僅展示 1990 年以後）
        declines, lo = [], None
        for e in e_series:
            if e["yy"] is not None and e["yy"] < 0 and e["date"] >= "1990-01-01":
                if lo is None:
                    lo = e["date"]
                prev_d = e["date"]
            elif lo:
                declines.append([lo, prev_d])
                lo = None
        if lo:
            declines.append([lo, e_series[-1]["date"]])
        spx = (quotes.get("^GSPC") or {}).get("price")
        eps_now = earnings[0] if earnings else None
        # 最近完整年度同比
        last_year = e_series[-1] if e_series else None
        cagr10 = None
        if eps_now and e_series:
            r10ago = None
            for r in reversed(e_series):
                if int(eps_now["date"][:4]) - int(r["date"][:4]) >= 10:
                    r10ago = r
                    break
            if r10ago and eps_now["eps"] and r10ago["eps"]:
                yrs = int(eps_now["date"][:4]) - int(r10ago["date"][:4])
                if yrs > 0:
                    cagr10 = round(((eps_now["eps"] / r10ago["eps"]) ** (1 / yrs) - 1) * 100, 1)
        step = max(1, len(e_series) // 40)
        series = [{"date": e["date"], "yy": e["yy"]}
                  for e in e_series[::step] if e["yy"] is not None]
        if e_series and (not series or series[-1]["date"] != e_series[-1]["date"]):
            series.append({"date": e_series[-1]["date"], "yy": e_series[-1]["yy"]})
        out["earnings"] = {
            "now": eps_now, "spx": spx,
            "pe": round(spx / eps_now["eps"], 1) if (spx and eps_now["eps"]) else None,
            "last_year": last_year, "cagr10": cagr10, "declines": declines,
            "series": series,
        }

    # ---- 模組 19：持倉穿透（建議配置 × ETF 前十大）----
    sym_of = {"股票": "SPY", "國債": "IEF", "商品": "DBC", "黃金": "GLD", "現金": "BIL"}
    targets = (allocation or {}).get("targets") or []
    weights = {t["cls"]: t["pct"] / 100.0 for t in targets}
    spy_h = (etf_holds.get("SPY") or {}).get("holds") or []
    spy_s = (etf_holds.get("SPY") or {}).get("sectors") or []
    # Yahoo 有時缺 SPY 行業權重 → 用站內公司的行業標籤聚合前十大持倉（標註口徑）
    sec_note = ""
    if not spy_s and spy_h:
        sec_by_ticker = {c["ticker"]: c["sector"] for c in companies if c.get("ticker")}
        agg = {}
        for h in spy_h:
            sec = sec_by_ticker.get(h["sym"])
            if sec:
                agg[sec] = agg.get(sec, 0) + h["pct"]
        spy_s = [{"name": k, "pct": round(v, 1)}
                 for k, v in sorted(agg.items(), key=lambda kv: -kv[1])]
        if spy_s:
            sec_note = "行業口徑＝SPY 前十大持倉按站內行業標籤聚合"
    eq_w = weights.get("股票")
    look_top = [{"sym": h["sym"], "pct": round(h["pct"] * eq_w, 2)}
                for h in spy_h[:10]] if eq_w and spy_h else []
    look_sec = [{"name": s["name"], "pct": round(s["pct"] * eq_w, 2)}
                for s in spy_s] if eq_w and spy_s else []
    out["lookthrough"] = {
        "top": look_top, "sectors": look_sec, "sec_note": sec_note,
        "eq_w": round(eq_w * 100, 1) if eq_w else None,
        "etfs": [dict({"sym": s}, **etf_holds.get(s, {}))
                 for s in ETF_HOLDING_SYMBOLS if s in etf_holds],
    }

    # ---- 模組 21：再平衡提醒（30 天不動作的權重漂移，用資產 1 年日線）----
    drifts = []
    for t in targets:
        sym = sym_of.get(t["cls"])
        p = (asset_perf or {}).get(sym) or index_perf.get(sym) or {}
        closes = p.get("closes") or []
        if len(closes) < 31 or not closes[-31]:
            continue
        rel = closes[-1] / closes[-31]
        drifts.append({"cls": t["cls"], "sym": sym, "target": t["pct"],
                       "rel": round((rel - 1) * 100, 1)})
    tot = sum(d["target"] * (1 + d["rel"] / 100) for d in drifts)
    if tot:
        for d in drifts:
            d["w30"] = round(d["target"] * (1 + d["rel"] / 100) * 100 / tot, 1)
            d["drift"] = round(d["w30"] - d["target"], 1)
    out["rebalance"] = {
        "now": drifts, "threshold": 5,
        "sim": simulate_rebalance_drift(hist, targets),
    }
    return out


# ---------------------------------------------------------------------------
# 模組 22-26：決策工具箱（前端交互 + 風險預算 + 規則透明日誌）
# ---------------------------------------------------------------------------

RULE_TEXTS = [
    "基準配置：股票 40 / 國債 20 / 商品 10 / 黃金 10 / 現金 20",
    "壓力 ≥ 60 → 股票 −10、現金 +10",
    "增長 < 45 → 股票 −10、國債 +10",
    "通脹 ≥ 70 → 黃金 +8、國債 −8",
    "流動性 < 45 → 現金 +5、商品 −5",
    "商品一年報酬 > +25% → 商品 +5、現金 −5",
    "下限保護：國債、現金均不低於 10%",
]


def build_rule_log(fred, hist):
    """模組 26：用 FRED 真實歷史逐月（月尾）重算四項評分與配置規則，
    記錄每次配置變化的日期、觸發條件與調整動作。"""
    # 信用利差用 BAA10Y（Moody's Baa−10Y，1986 起全歷史）：ICE 高收益 OAS 的
    # fredgraph 下載僅提供近三年，無法支持 2000 年起的逐月重算
    need = ["GDPC1", "UNRATE", "PAYEMS", "CPIAUCSL", "PCEPILFE",
            "DFF", "T10Y2Y", "BAA10Y", "VIXCLS"]
    if not all(s in fred for s in need):
        return []

    def ff(by, m):
        best = None
        for k in sorted(by):
            if k > m:
                break
            best = by[k]
        return best

    def madd(m, k):
        y, mo = int(m[:4]), int(m[5:7])
        mo += k
        y += (mo - 1) // 12
        mo = (mo - 1) % 12 + 1
        return f"{y:04d}-{mo:02d}"

    def yoy(m, by):
        v = ff(by, m)
        p = ff(by, madd(m, -12))
        return (v / p - 1) * 100 if (v and p) else None

    ms = {}
    for sid in need:
        by = {}
        for d, v in fred.get(sid) or []:
            by[d[:7]] = v
        ms[sid] = by
    dbc = hist.get("DBC") or {}
    dbc_m = dict(zip([d[:7] for d in dbc.get("dates", [])], dbc.get("closes", [])))

    axis = [m for m in sorted(ms["UNRATE"]) if m >= "2000-01"]
    prev_w, log = None, []
    for m in axis:
        gdp_y = yoy(m, ms["GDPC1"])
        un = ff(ms["UNRATE"], m)
        pay_y = yoy(m, ms["PAYEMS"])
        cpi_y = yoy(m, ms["CPIAUCSL"])
        pce_y = yoy(m, ms["PCEPILFE"])
        ffr = ff(ms["DFF"], m)
        sp = ff(ms["T10Y2Y"], m)
        oas = ff(ms["BAA10Y"], m)
        vix = ff(ms["VIXCLS"], m)
        dbc_y = yoy(m, dbc_m)
        if None in (gdp_y, un, pay_y, cpi_y, pce_y, ffr, sp, oas, vix):
            continue
        g = (0.4 * _clamp((gdp_y - 0.5) * 25)
             + 0.3 * _clamp(100 - (un - 3.5) * 22)
             + 0.3 * _clamp(50 + pay_y * 30))
        i = 0.6 * _clamp((cpi_y - 1.5) * 40) + 0.4 * _clamp((pce_y - 1.5) * 35)
        tight = _clamp((ffr - 1.0) * 22)
        curve = 8 if sp >= 0 else -12
        l = 0.75 * _clamp(100 - tight + curve) + 0.25 * _clamp(100 - (oas - 3.0) * 30)
        s = 0.5 * _clamp((vix - 12) * 6) + 0.5 * _clamp(50 + (oas - 3.2) * 25)
        w = {"股票": 40.0, "國債": 20.0, "商品": 10.0, "黃金": 10.0, "現金": 20.0}
        fired = []
        if s >= 60:
            w["股票"] -= 10
            w["現金"] += 10
            fired.append("壓力 ≥ 60 → 股票 −10、現金 +10")
        if g < 45:
            w["股票"] -= 10
            w["國債"] += 10
            fired.append("增長 < 45 → 股票 −10、國債 +10")
        if i >= 70:
            w["黃金"] += 8
            w["國債"] -= 8
            fired.append("通脹 ≥ 70 → 黃金 +8、國債 −8")
        if l < 45:
            w["現金"] += 5
            w["商品"] -= 5
            fired.append("流動性 < 45 → 現金 +5、商品 −5")
        if dbc_y is not None and dbc_y > 25:
            w["商品"] += 5
            w["現金"] -= 5
            fired.append("商品一年報酬 > +25% → 商品 +5、現金 −5")
        for k in ("國債", "現金"):
            if w[k] < 10:
                w["股票"] -= 10 - w[k]
                w[k] = 10
        w_now = tuple(round(w[k], 1) for k in ("股票", "國債", "商品", "黃金", "現金"))
        if prev_w != w_now:
            log.append({
                "date": m,
                "scores": {"增長": round(g), "通脹": round(i),
                           "流動性": round(l), "壓力": round(s)},
                "fired": fired,
                "w": {k: round(w[k], 1) for k in w},
            })
            prev_w = w_now
    return log


def compute_market_review(quotes, allocation):
    """模組 29：本週市場回顧（自動彙總）——指數與核心資產一週變動、
    宏觀評分變動、未來 30 天關注事件。"""
    syms = ["^GSPC", "^IXIC", "^HSI", "000300.SS", "^N225", "^GDAXI", "^FTSE",
            "^NSEI", "^BVSP", "EEM", "SPY", "IEF", "DBC", "GLD", "BIL", "TLT"]
    rows = []
    for s in syms:
        q = quotes.get(s) or {}
        c = q.get("closes") or []
        if len(c) >= 5 and c[-1]:
            prev = c[-6] if len(c) >= 6 else c[0]
            if prev:
                rows.append({"sym": s, "label": q.get("label") or s,
                             "w": round((c[-1] / prev - 1) * 100, 2)})
    rows.sort(key=lambda r: -(r["w"] if r["w"] is not None else -999))
    macro = (allocation or {}).get("macro") or []
    moves = [{"label": m.get("label", ""), "score": m.get("score"),
              "change": m.get("change"), "up_good": m.get("up_good")}
             for m in macro if m.get("change")]
    events = (allocation or {}).get("events") or {}
    asof = quotes.get("^GSPC", {}).get("asof", "")
    upcoming = []
    try:
        d0 = datetime.strptime(asof, "%Y-%m-%d").date()
    except Exception:
        d0 = None
    if d0:
        for e in (events.get("fixed") or []):
            try:
                de = datetime.strptime(e.get("date", ""), "%Y-%m-%d").date()
            except Exception:
                de = None
            if de and d0 <= de <= d0 + timedelta(days=30):
                upcoming.append({"date": e["date"], "label": e.get("label", ""),
                                 "note": e.get("note", ""), "kind": "fixed"})
        for e in (events.get("earnings") or []):
            try:
                de = datetime.strptime(e.get("date", ""), "%Y-%m-%d").date()
            except Exception:
                de = None
            if de and d0 <= de <= d0 + timedelta(days=30):
                upcoming.append({"date": e["date"], "label": e.get("name", ""),
                                 "ticker": e.get("ticker", ""), "kind": "earnings"})
        upcoming.sort(key=lambda e: e["date"])
    best = rows[0] if rows else None
    worst = rows[-1] if rows else None
    summary = ""
    if best and worst:
        summary = (f"本週最佳：{best['label']} {best['w']:+.2f}%；"
                   f"最弱：{worst['label']} {worst['w']:+.2f}%。")
    return {"asof": asof, "rows": rows, "moves": moves,
            "upcoming": upcoming[:12], "summary": summary}


def compute_tools(fred, hist, allocation):
    """決策工具箱：風險預算（25）＋規則透明日誌（26）。22-24 為前端交互，
    以當前評分與目標權重為預設值。"""
    tools = {"rules": RULE_TEXTS}
    targets = (allocation or {}).get("targets") or []
    sym_of = {"股票": "SPY", "國債": "IEF", "商品": "DBC", "黃金": "GLD", "現金": "BIL"}
    weights = {}
    for t in targets:
        sym = sym_of.get(t["cls"])
        if sym and sym in hist:
            weights[sym] = t["pct"] / 100.0

    # ---- 模組 25：風險預算（月報酬協方差 → 波動貢獻；歷史最大回撤）----
    if len(weights) >= 3 and "SPY" in hist:
        rets = {}
        for s in weights:
            closes = hist[s]["closes"]
            rets[s] = [closes[i] / closes[i - 1] - 1
                       for i in range(1, len(closes)) if closes[i - 1]]
        n = min(len(r) for r in rets.values())
        R = {s: r[-n:] for s, r in rets.items()}
        means = {s: sum(R[s]) / n for s in R}
        cov = {}
        for a in R:
            for b in R:
                cov[(a, b)] = (sum((R[a][i] - means[a]) * (R[b][i] - means[b])
                                  for i in range(n)) / (n - 1))
        var_p = sum(weights[a] * weights[b] * cov[(a, b)] for a in R for b in R)
        contrib = {}
        for a in R:
            marg = weights[a] * sum(weights[b] * cov[(a, b)] for b in R)
            contrib[a] = marg / var_p * 100 if var_p > 0 else 0.0
        maps = {s: dict(zip(hist[s]["dates"], hist[s]["closes"])) for s in R}
        lasts, base, pf = {s: None for s in R}, None, []
        for d in hist["SPY"]["dates"]:
            for s, m in maps.items():
                if d in m:
                    lasts[s] = m[d]
            if any(lasts[s] is None for s in R):
                continue
            if base is None:
                base = dict(lasts)
            pf.append(sum(weights[s] * lasts[s] / base[s] for s in R))
        peak, maxdd = pf[0], 0.0
        for v in pf:
            peak = max(peak, v)
            maxdd = min(maxdd, v / peak - 1)
        tools["riskbudget"] = {
            "assets": [{
                "sym": s, "label": RISK_LABELS.get(s, s),
                "w": round(weights[s] * 100, 1),
                "vol_ann": round((sum((x - means[s]) ** 2 for x in R[s])
                                  / (n - 1)) ** 0.5 * 12 ** 0.5 * 100, 1),
                "contrib": round(contrib[s], 1),
            } for s in sorted(weights)],
            "pf_vol_ann": round(var_p ** 0.5 * 12 ** 0.5 * 100, 1) if var_p > 0 else None,
            "maxdd": round(maxdd * 100, 1) if pf else None,
            "n_months": n,
        }

    # ---- 模組 26：規則透明日誌 ----
    log = build_rule_log(fred, hist)
    tools["log"] = log
    tools["log_note"] = (
        "歷史重算的信用利差以 Moody's Baa − 10Y 國債利差（FRED BAA10Y，1986 年起全歷史）"
        "代替 ICE 高收益 OAS——後者的 fredgraph 下載僅提供近三年；"
        "評分公式與現行頁面相同（信用錨點 3.0／3.2 百分點）。")
    return tools


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

_GITHUB_BASE = "https://github.com/aliu29775-bot/ai-berkshire/blob/main/"


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
                    return f'<img src="https://raw.githubusercontent.com/aliu29775-bot/ai-berkshire/main/{relp}" alt="{m.group(1)}">'
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
        # 網站更名：報告正文中的舊站名/舊倉庫名統一改寫
        text = text.replace("AI Berkshire", "AIShan+")
        text = text.replace("xbtlin/ai-berkshire", "aliu29775-bot/ai-berkshire")
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
    ap.add_argument("--quick", action="store_true",
                    help="快速更新（小更新）：只重抓行情/FRED/資產 1Y 並重建 data.js；不重渲染報告與個股頁")
    args = ap.parse_args()

    quick = args.quick
    REPORTS_CACHE = os.path.join(SITE_DIR, "js", "reports_cache.json")
    t_start = time.time()

    repo = os.path.abspath(args.repo)
    if quick:
        # 快速模式：公司/專題/報告索引取自大更新寫入的快取（無需源 repo）
        if not os.path.exists(REPORTS_CACHE):
            sys.exit("快速模式需要 js/reports_cache.json（由完整建站寫入），請先跑一次大更新")
        rc = json.load(open(REPORTS_CACHE, encoding="utf-8"))
        idx = rc["idx"]
        companies = rc["companies"]
        topics = rc["topics"]
        extra = rc.get("extra", [])
        reports = [r for r in idx["reports"] if r.get("path")]
        in_combo_names = set()
        print(f"== 快速更新（小更新）：報告快取 {len(companies)} 家 / {len(topics)} 專題 / {len(reports)} 份 ==")
    elif not os.path.exists(os.path.join(repo, "reports", "index.json")):
        sys.exit(f"找不到 repo: {repo}")

    if not quick:
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

        # 上游 index 偶爾把專題系列誤標為公司（group 以 -YYYYMMDD 結尾且無 ticker），
        # 歸入專題桶，避免出現在公司清單。
        for r in reports:
            if r["bucket"] == "公司" and not r.get("ticker") and re.search(r"-\d{8}$", r["group"]):
                r["bucket"] = "专题"
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
                "sector": sector_of(name, titles),
                "ticker": ticker,
                "count": len(rs),
                "latest": latest,
                "score": score,
                "verdict": verdict,
                "verdict_class": classify_verdict(verdict),
                "summary": summary,
                "page": "stocks/" + slugify(name) + ".html",
                "reports": [
                    {"title": r["title"], "date": r["date"], "type": r["type"],
                     "path": site_path(r["path"])}
                    for r in reversed(rs)
                ],
            })

        # 個股分析系統：補充監測公司（無研報，僅行情＋基本面監測），覆蓋擴至 300 家
        have_tickers = {c["ticker"] for c in companies}
        have_names = {c["name"] for c in companies}
        for x in EXTRA_COMPANIES:
            if not x["ticker"] or x["ticker"] in have_tickers or x["name"] in have_names:
                continue
            companies.append({
                "name": x["name"], "sector": x["sector"], "ticker": x["ticker"],
                "region": x["region"], "count": 0, "latest": "",
                "score": None, "verdict": None, "verdict_class": None,
                "summary": None, "page": "stocks/" + slugify(x["name"]) + ".html",
                "reports": [],
            })
            have_tickers.add(x["ticker"])

        # 選定公司組合（與 app.js selectedCombo 同規則：結論正面且評分最高的 8 家）
        pos = [c for c in companies
               if c.get("score") and c["score"].get("value") is not None
               and c.get("verdict_class") == "positive"]
        pos.sort(key=lambda c: -c["score"]["value"])
        in_combo_names = {c["name"] for c in pos[:8]}

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

    asset_symbols = list(ASSET_PROXIES.values()) + [s for _, s, _ in COMMODITY_FUTURES]
    quotes = {}
    cache_file = os.path.join(SITE_DIR, "js", "market_cache.json")
    if not args.no_market:
        print(f"== 3/4 並行抓取行情（{len([t for t in tickers if t])} 個代碼）==")
        quotes = fetch_quotes(tickers + list(MARKET_INDICES) + list(GLOBAL_INDICES)
                              + list(EXTENDED_ASSETS) + asset_symbols)
        for sym, label in MARKET_INDICES.items():
            if sym in quotes:
                quotes[sym]["label"] = label
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(quotes, f, ensure_ascii=False)
    elif os.path.exists(cache_file):
        quotes = json.load(open(cache_file, encoding="utf-8"))
        print(f"== 3/4 使用行情快取（{len(quotes)} 檔，{cache_file}）==")

    # 個股基本面（Yahoo quoteSummary + 1y 日線，供個股分析頁；快速模式用快取）
    fund_data = load_or_fetch_fundamentals(tickers, args.no_market or quick)

    # 首頁市場總覽用：主要指數行情（取得到幾個就顯示幾個）
    indices = [{"sym": s, "label": l} for s, l in MARKET_INDICES.items() if s in quotes]

    # 宏觀評分與資產配置（FRED + 資產 1 年報酬）
    alloc_cache = os.path.join(SITE_DIR, "js", "allocation_cache.json")
    allocation = None
    # 資產 1Y 行情一次抓齊（資產配置 + 市場全景共用，避免重複抓取）
    union_perf_symbols = list(GLOBAL_INDICES) + list(EXTENDED_ASSETS) + asset_symbols
    if not args.no_market:
        print("== 3.5/4 抓取宏觀與資產配置資料（FRED + Yahoo 1Y，並行）==")
        fred = fetch_fred(FRED_SERIES, FRED_CACHE)
        asset_perf = fetch_asset_perf(union_perf_symbols)
        if fred:
            allocation = compute_allocation(fred, quotes, asset_perf)
            print(f"  ✓ 資產配置已計算（通脹 {allocation['macro'][1]['score']} 分 / "
                  f"壓力 {allocation['macro'][3]['score']} 分）")
        else:
            print("  ✗ FRED 全數失敗，資產配置跳過")
    if allocation is not None and (not args.no_market or "valuation" not in allocation):
        fred_for_val = fred if not args.no_market else {}
        allocation["valuation"] = compute_valuation(fred_for_val, companies, fund_data)
        if not args.no_market:
            with open(alloc_cache, "w", encoding="utf-8") as f:
                json.dump(allocation, f, ensure_ascii=False)
        print(f"  ✓ 估值儀表板（巴菲特指標 + 行業估值中位數，"
              f"{allocation['valuation'].get('n_valued', 0)} 家有 PE）")
    if allocation is not None and (not args.no_market or "events" not in allocation):
        allocation["events"] = compute_events({}, companies, fund_data)
        if not args.no_market:
            with open(alloc_cache, "w", encoding="utf-8") as f:
                json.dump(allocation, f, ensure_ascii=False)
        print(f"  ✓ 政策事件日曆（未來 60 天財報 {len(allocation['events']['earnings'])} 條）")
    elif os.path.exists(alloc_cache):
        allocation = json.load(open(alloc_cache, encoding="utf-8"))
        print("== 3.5/4 使用資產配置快取 ==")

    # 歷史情景回測（20 年月頻行情：網路建站抓取，快取建站讀取 js/hist_cache.json）
    hist_cache = os.path.join(SITE_DIR, "js", "hist_cache.json")
    hist = {}
    if not args.no_market and not quick:
        print("== 3.6/4 抓取 20 年歷史行情（情景回測）==")
        hist = fetch_asset_history(HIST_SYMBOLS)
        if hist:
            with open(hist_cache, "w", encoding="utf-8") as f:
                json.dump(hist, f, ensure_ascii=False)
    if not hist and os.path.exists(hist_cache):
        hist = json.load(open(hist_cache, encoding="utf-8"))
        print(f"== 3.6/4 歷史行情使用快取（{len(hist)} 檔）==")
    scenarios = compute_scenarios(hist, (allocation or {}).get("targets") or []) if hist else []
    if scenarios:
        print(f"  ✓ 歷史情景回測 {len(scenarios)} 個情景（2008／2020／2022）")

    # 風險儀表板（模組 7 衰退概率／8 相關性／10 尾部風險／18 情緒）
    risk = None
    if hist and companies:
        fred_for_risk = fred if not args.no_market else {}
        if args.no_market and os.path.exists(FRED_CACHE):
            fred_for_risk = json.load(open(FRED_CACHE, encoding="utf-8"))
        if fred_for_risk:
            risk = compute_risk(fred_for_risk, quotes, hist, fund_data, companies)
            r = risk.get("recession") or {}
            print(f"  ✓ 風險儀表板（衰退概率 {r.get('prob_now', '—')}% · "
                  f"相關性 {len((risk.get('corr') or {}).get('labels', []))} 資產 · "
                  f"尾部風險 {len((risk.get('tail') or {}).get('items', []))} 指標）")

    # 市場全景（模組 11/13/14/16/17/19/21）
    marketview = None
    tools = None
    review = None
    if quotes:
        index_perf, earnings, etf_holds = {}, [], {}
        if not args.no_market and not quick:
            print("== 3.7/4 抓取市場全景資料（標普盈利 + ETF 持倉）==")
            index_perf = asset_perf  # 全球指數 1Y 已在 3.5 併入 union 抓取
            with open(INDEX_PERF_CACHE, "w", encoding="utf-8") as f:
                json.dump(index_perf, f, ensure_ascii=False)
            earnings = fetch_earnings()
            with open(EARNINGS_CACHE, "w", encoding="utf-8") as f:
                json.dump(earnings, f, ensure_ascii=False)
            etf_holds = fetch_etf_holdings(ETF_HOLDING_SYMBOLS)
            with open(ETF_CACHE, "w", encoding="utf-8") as f:
                json.dump(etf_holds, f, ensure_ascii=False)
        elif not args.no_market:
            # 快速模式：標普盈利與 ETF 持倉用快取（全球指數 1Y 已在 3.5 抓齊）
            index_perf = asset_perf
            with open(INDEX_PERF_CACHE, "w", encoding="utf-8") as f:
                json.dump(index_perf, f, ensure_ascii=False)
            if os.path.exists(EARNINGS_CACHE):
                earnings = json.load(open(EARNINGS_CACHE, encoding="utf-8"))
            if os.path.exists(ETF_CACHE):
                etf_holds = json.load(open(ETF_CACHE, encoding="utf-8"))
        else:
            if os.path.exists(INDEX_PERF_CACHE):
                index_perf = json.load(open(INDEX_PERF_CACHE, encoding="utf-8"))
            if os.path.exists(EARNINGS_CACHE):
                earnings = json.load(open(EARNINGS_CACHE, encoding="utf-8"))
            if os.path.exists(ETF_CACHE):
                etf_holds = json.load(open(ETF_CACHE, encoding="utf-8"))
        fred_for_mv = fred if not args.no_market else {}
        if args.no_market and os.path.exists(FRED_CACHE):
            fred_for_mv = json.load(open(FRED_CACHE, encoding="utf-8"))
        mv_asset_perf = asset_perf if not args.no_market else {}
        marketview = compute_market(fred_for_mv, quotes, index_perf, mv_asset_perf, hist,
                                    allocation, earnings, etf_holds, companies)
        e_now = (marketview.get("earnings") or {}).get("now") or {}
        print(f"  ✓ 市場全景（全球 {len(marketview['global'])} 指數 · "
              f"標普盈利 {e_now.get('eps', '—')} · "
              f"穿透 ETF {len(marketview['lookthrough']['etfs'])}）")
        # 決策工具箱（模組 22-26）：風險預算＋規則透明日誌
        tools = compute_tools(fred_for_mv, hist, allocation)
        rb = (tools or {}).get("riskbudget") or {}
        print(f"  ✓ 決策工具箱（規則日誌 {len((tools or {}).get('log', []))} 條 · "
              f"風險預算 {len(rb.get('assets', []))} 資產）")
        # 本週市場回顧（模組 29）：一週變動＋宏觀評分變動＋下月關注
        review = compute_market_review(quotes, allocation)
        print(f"  ✓ 市場回顧（一週變動 {len(review['rows'])} 標的 · "
              f"下月關注 {len(review['upcoming'])} 項）")

    if not quick:
        print(f"== 4/4 預渲染 {len(reports)} + {len(extra)} 份報告 ==")
        render_reports(repo, reports + extra)
        print(f"   完成，輸出至 {os.path.relpath(os.path.join(SITE_DIR, 'reports'))}")
    else:
        print("== 4/4 快速模式：報告頁與個股頁不重渲染 ==")

    # 全球前五大基金資產配置動態（公開披露數據，按各基金最新年報／政策區間，站長手動維護）
    # delta 為較上一披露期的百分點變化（數字）或文字說明；min/max 為政策區間（ADIA）
    FUNDS = [
        {
            "rank": 1,
            "name": "挪威政府全球養老基金（GPFG）",
            "mgr": "挪威央行投資管理 NBIM · 全球最大主權基金",
            "country": "挪威",
            "aum": "≈2.0 萬億美元",
            "asof": "2025-12-31",
            "source": "NBIM 2025 年度報告",
            "note": "政策目標：股票 70%／債券 30%；2025 年回報 +15.1%，其中股票 +19.3%、債券 +5.4%。",
            "alloc": [
                {"cls": "股票", "pct": 71.3, "delta": "高於政策目標 70%"},
                {"cls": "債券", "pct": 26.5},
                {"cls": "不動產", "pct": 1.7},
                {"cls": "另類", "pct": 0.4, "sub": "未上市可再生能源基建"},
            ],
        },
        {
            "rank": 2,
            "name": "日本政府養老投資基金（GPIF）",
            "mgr": "全球最大養老基金",
            "country": "日本",
            "aum": "≈299.8 萬億日元（約 2.0 萬億美元）",
            "asof": "2026-03-31",
            "source": "GPIF 2025 財年年報摘要（2026-07-03 發布）",
            "note": "政策基準四等分各 25%；實際：國内債券 26.91%／外國債券 24.48%／國内股票 23.81%／外國股票 24.80%。",
            "alloc": [
                {"cls": "債券", "pct": 51.4, "delta": 0.9, "sub": "國内 26.91% · 外國 24.48%"},
                {"cls": "股票", "pct": 48.6, "delta": -0.9, "sub": "國内 23.81% · 外國 24.80%"},
            ],
        },
        {
            "rank": 3,
            "name": "中國投資有限責任公司（中投 CIC）",
            "mgr": "中國主權財富基金",
            "country": "中國",
            "aum": "≈1.57 萬億美元（總資產）",
            "asof": "2024-12-31",
            "source": "中投 2024 年度報告（2025-12-09 發布）",
            "note": "境外組合另類資產為第一大類；公開市場股票中信息科技佔 25.9%、金融 16.4%。",
            "alloc": [
                {"cls": "另類", "pct": 48.5, "delta": 0.2, "sub": "對沖基金、私募股權、私募信用、房地產等"},
                {"cls": "股票", "pct": 34.7, "delta": 1.5},
                {"cls": "債券", "pct": 15.5, "delta": -0.9},
                {"cls": "現金", "pct": 1.3, "delta": -0.8},
            ],
        },
        {
            "rank": 4,
            "name": "阿布扎比投資局（ADIA）",
            "mgr": "阿聯酋主權財富基金（第三方估算規模）",
            "country": "阿聯酋",
            "aum": "≈1.1 萬億美元",
            "asof": "2025 年度回顧",
            "source": "ADIA 2025 Annual Review（長期政策區間）",
            "note": "只披露長期政策區間：2025 年上調私募股權 12–17%→15–20% 與金融另類 5–10%→7–12%，下調房地產 5–10%→2–7%。",
            "alloc": [
                {"cls": "股票", "pct": 51.0, "min": 40, "max": 62, "sub": "發達 32–42% · 新興 7–15% · 小盤 1–5%"},
                {"cls": "另類", "pct": 31.5, "min": 24, "max": 39, "delta": "區間上調 ↑", "sub": "私募 15–20% · 金融另類 7–12% · 基建 2–7%"},
                {"cls": "債券", "pct": 15.5, "min": 9, "max": 22, "sub": "國債 7–15% · 信貸 2–7%"},
                {"cls": "不動產", "pct": 4.5, "min": 2, "max": 7, "delta": "區間下調 ↓"},
                {"cls": "現金", "pct": 2.5, "min": 0, "max": 5},
            ],
        },
        {
            "rank": 5,
            "name": "科威特投資局（KIA）",
            "mgr": "全球歷史最悠久的主權基金（1953 年成立）",
            "country": "科威特",
            "aum": "≈1.0 萬億美元",
            "asof": "—",
            "source": "—",
            "note": "不公開披露資產配置明細，故無法列出具體權重。",
            "alloc": [],
        },
    ]

    # 前五大對沖基金配置動態（SEC 13F 美股多頭口徑，只含美股多頭、不含空頭/衍生品/非美資產）
    # 規模為淨 AUM（2026 年公開估算）；delta 為較上期變化的文字說明，含「減」或「↓」時按下調著色
    HEDGE_FUNDS = [
        {
            "rank": 1,
            "name": "橋水 Bridgewater Associates",
            "mgr": "全球最大對沖基金 · 宏觀／全天候策略",
            "country": "美國",
            "aum": "淨 AUM ≈780 億美元",
            "asof": "2026-03-31（13F Q1）",
            "source": "13F 披露（13radar／Growin 等）",
            "note": "全天候策略公開目標權重：股票 30／長期國債 40／中期國債 15／黃金 7.5／大宗商品 7.5；13F 僅反映美股多頭。Q1 大幅減持 IVV，清倉或減持 Salesforce、Workday、ServiceNow 等軟件股。",
            "alloc": [
                {"cls": "科技", "pct": 38.7, "delta": "加倉 AI 芯片", "sub": "新建倉台積電 ~2.2%，加倉 AMZN／NVDA／AVGO／MU"},
                {"cls": "工業", "pct": 11.6},
                {"cls": "消費", "pct": 10.1},
                {"cls": "金融", "pct": 8.9},
                {"cls": "醫療", "pct": 8.1},
                {"cls": "材料", "pct": 6.6},
                {"cls": "通訊", "pct": 6.5},
                {"cls": "能源", "pct": 3.3},
            ],
            "tops": ["SPY＋IVV ≈21%", "AMZN 5.4%", "NVDA 4.8%", "GOOGL 4.1%", "AVGO 3.4%"],
        },
        {
            "rank": 2,
            "name": "千禧年 Millennium Management",
            "mgr": "多策略·多經理平台（約 330 個投資團隊）",
            "country": "美國",
            "aum": "淨 AUM ≈835 億美元",
            "asof": "2026-06-30（13F Q2）",
            "source": "13F 披露（StockDrifts 等）",
            "note": "科技風險由個股直投轉為指數化；2025 年旗艦基金回報約 +10.5%。",
            "alloc": [
                {"cls": "指數ETF", "pct": 36.5, "delta": "指數化核心", "sub": "標普／納指 ETF"},
                {"cls": "科技", "pct": 20.6, "delta": "較上期 30.3% 減 ~9.7pp", "sub": "傾斜 AI 基建：NVDA／MSFT／CRDO／STX／SNOW／ORCL"},
                {"cls": "其他", "pct": 42.9, "sub": "分散於醫療、工業等多行業（Q3 2025 曾超配工業與醫療）"},
            ],
            "tops": ["NVDA", "MSFT", "CRDO", "STX", "SNOW", "ORCL"],
        },
        {
            "rank": 3,
            "name": "城堡 Citadel Advisors",
            "mgr": "多策略 · 史上累計盈利最高的對沖基金",
            "country": "美國",
            "aum": "淨 AUM ≈660–680 億美元",
            "asof": "2026-06-30（13F Q2）",
            "source": "13F 披露（SmartMoneyDB／StockDrifts 等）",
            "note": "由集中押注 AI 芯片龍頭轉向「三引擎」組合；另持 NVDA 期權名義值：約 122 億美元看漲 + 92 億美元看跌。Wellington 基金 2025 年回報約 +10.2%。",
            "alloc": [
                {"cls": "科技", "pct": 24.6, "delta": "集中度減：前 50 大科技權重 54.1%→32.3%", "sub": "含期權口徑；純多頭口徑 16.6–33.1% 依分類方法而異"},
                {"cls": "指數ETF", "pct": 7.6, "sub": "IVV（iShares 標普500 ETF）"},
                {"cls": "其他", "pct": 67.8, "sub": "分散於 6,354 個持倉"},
            ],
            "tops": ["IVV 7.6%", "AMZN 1.49%", "NVDA 1.36%", "AAPL 1.21%", "MSFT 0.81%"],
        },
        {
            "rank": 4,
            "name": "Man Group",
            "mgr": "全球最大上市對沖基金集團（AHL／GLG／Numeric，量化為主）",
            "country": "英國",
            "aum": "集團 AUM 1,933 億美元（對沖 sleeve ≈665 億）",
            "asof": "2026（13F）",
            "source": "13F 披露（MarketBeat／HedgeTrack）",
            "note": "13F 美股多頭僅約 2.1 億美元（佔集團 AUM 約 0.1%），行業配置不具代表性；代表性持倉為分散的半導體個股（LRCX 0.62%／KEYS 0.59%／QCOM 0.56%／MU 0.55%）。",
            "alloc": [],
            "tops": [],
        },
        {
            "rank": 5,
            "name": "D.E. Shaw & Co.",
            "mgr": "量化＋多策略",
            "country": "美國",
            "aum": "淨 AUM ≈600–660 億美元",
            "asof": "2026-06-30（13F Q2）",
            "source": "13F 披露（QWResearch 等）",
            "note": "2025 年 Composite 回報約 +18.5%、Oculus 約 +28.2%。",
            "alloc": [
                {"cls": "科技", "pct": 28.0, "sub": "GICS 行業口徑"},
                {"cls": "其他", "pct": 72.0, "sub": "高度分散的量化組合"},
            ],
            "tops": ["NVDA 1.54%", "MSFT 1.37%", "AVGO 1.21%", "AAPL 1.07%"],
        },
    ]

    # 知名家族辦公室（模組 12，SEC 13F 美股多頭口徑，站長手動維護）
    FAMILY_OFFICES = [
        {
            "name": "蓋茨基金會信託（Bill & Melinda Gates Foundation Trust）",
            "mgr": "比爾·蓋茨家族慈善信託 · 全球最大慈善基金會",
            "country": "美國",
            "aum": "13F 持倉 ≈344 億美元（24 檔）",
            "asof": "2026-06-30（13F Q2，2026-08-14 申報）",
            "source": "SEC 13F 披露（13radar／PortfolioSavvy）",
            "note": "前十大集中度 94.9%，季度換手僅 1.6%。Q2 新建倉 Home Depot（+3.5 億美元），減持 BRK-B −13.8%、WM −3.3%。",
            "alloc": [
                {"cls": "工業", "pct": 65.0, "sub": "CAT 19.7% · CNI 18.0% · WM 17.3% · DE 6.6% · FDX 2.2%"},
                {"cls": "金融", "pct": 21.4, "sub": "主要為 BRK-B 21.4%"},
                {"cls": "消費", "pct": 5.4, "sub": "WMT 2.8% · KOF 1.9%"},
                {"cls": "材料", "pct": 4.2, "sub": "ECL 4.2%"},
            ],
            "tops": ["BRK-B 21.4%", "CAT 19.7%", "CNI 18.0%", "WM 17.3%", "DE 6.6%"],
        },
        {
            "name": "巴菲特家族辦公室（波克夏 13F）",
            "mgr": "華倫·巴菲特 · 波克夏海瑟威（家族辦公室口徑）",
            "country": "美國",
            "aum": "13F 持倉約 29 檔",
            "asof": "2026-06-30（13F Q2）",
            "source": "SEC 13F 披露（13radar 等）",
            "note": "Q2 大增持 Alphabet +83%（兩類股合計），市值 166→378 億美元，躍居第三大持倉（12.6%），為其 AI 敞口的主要途徑；前兩大為 Apple 與美國運通。組合 0% AI 基建（半導體／電力）。",
            "alloc": [],
            "tops": ["Apple（第一大）", "美國運通（第二大）", "Alphabet 12.6%（第三大，Q2 +83%）"],
        },
        {
            "name": "索羅斯基金管理（Soros Fund Management）",
            "mgr": "喬治·索羅斯家族辦公室 · 全球宏觀策略",
            "country": "美國",
            "aum": "13F 持倉 ≈81.4 億美元（266 檔）",
            "asof": "2026-06-30（13F Q2，2026-08-14 申報）",
            "source": "SEC 13F 披露（13radar）",
            "note": "季度換手 28.2%，前十大集中度 30.8%。Q2 新建倉 84 檔，主題為 AI 基建：最大新買 SMCI（≈1.1 億美元）、AEP（≈1.05 億美元）、NBIS（≈0.86 億美元）；最大加倉 Entergy +1,084%、Digital Realty +840%；大減 Amazon −39.2%。",
            "alloc": [],
            "tops": ["AMZN 3.5%（−39.2%）", "TSM 3.1%", "GPN 2.7%", "GOOG 2.6%", "NVDA 2.6%", "EA 2.4%"],
        },
    ]

    # 大學捐贈基金（模組 12，FY2025 年報口徑，站長手動維護）
    ENDOWMENTS = [
        {
            "name": "耶魯大學捐贈基金（Yale Endowment）",
            "mgr": "美國第二大捐贈基金 · David Swensen 模式開創者",
            "country": "美國",
            "aum": "≈441 億美元",
            "asof": "FY2025（截至 2025-06-30）",
            "source": "耶魯投資辦公室年報（Yale Daily News／Forbes 報導）",
            "note": "FY2025 回報 +11.1%（上一年 +5.7%），投資收益 45 億美元，向學校撥款 21 億美元（逾營運收入三分之一）；10 年年化 9.4%。2026-07-01 起聯邦捐贈稅升至 8%（每年估計最高 ~3 億美元）。",
            "alloc": [
                {"cls": "私募/風投", "pct": 48.0, "sub": "常春藤中最高（範圍 29–48%）"},
                {"cls": "公開市場", "pct": 17.0, "sub": "發達＋新興"},
                {"cls": "另類", "pct": 16.0, "sub": "對沖基金等"},
                {"cls": "房地產", "pct": 12.0},
                {"cls": "其他", "pct": 7.0},
            ],
            "tops": [],
        },
        {
            "name": "哈佛大學捐贈基金（Harvard Management Company）",
            "mgr": "全球最大大學捐贈基金",
            "country": "美國",
            "aum": "≈569 億美元",
            "asof": "FY2025（截至 2025-06-30）",
            "source": "HMC 年報（Forbes 報導）",
            "note": "FY2025 回報 +11.9%（FY2024 +9.6%），向學校撥款 25 億美元（約佔預算四成）；8 年年化 9.6%。校方自認「公開股票太少、私募太多」拖累表現；2026-07-01 起聯邦捐贈稅升至 8%（每年估計最高 ~3 億美元）。",
            "alloc": [
                {"cls": "私募/風投", "pct": 41.0},
                {"cls": "實物資產", "pct": 8.0},
                {"cls": "公開市場等", "pct": 51.0, "sub": "公開股票＋其他（年報未細分）"},
            ],
            "tops": [],
        },
    ]

    # 大型養老基金（模組 12，最新年報口徑，站長手動維護）
    PENSIONS = [
        {
            "name": "加拿大養老金計劃投資委員會（CPP Investments）",
            "mgr": "2,200 萬加拿大人養老金 · 全球最大養老基金之一",
            "country": "加拿大",
            "aum": "淨資產 7,933 億加元",
            "asof": "FY2026（截至 2026-03-31）",
            "source": "CPP Investments FY2026 年報",
            "note": "FY2026 淨回報 +7.8%，跑輸基準組合 +13.2%（主因刻意低配美國公開股票以分散風險）；公開股票為回報主引擎（美國 +6.0%／歐洲 +8.3%／亞太 +6.5%／拉美 +22.0%）。",
            "alloc": [
                {"cls": "公開股票", "pct": 36.0},
                {"cls": "私募股權", "pct": 22.0},
                {"cls": "實物資產", "pct": 20.0, "sub": "房地產＋基建＋能源"},
                {"cls": "政府債", "pct": 13.0},
                {"cls": "信貸", "pct": 9.0},
            ],
            "tops": [],
        },
        {
            "name": "新加坡政府投資公司（GIC）",
            "mgr": "新加坡主權財富基金 · 管理國家外匯儲備",
            "country": "新加坡",
            "aum": "管理規模不公開披露",
            "asof": "FY2025/26（截至 2026-03-31）",
            "source": "GIC Report 2025/26",
            "note": "20 年年化實質回報 +3.4%（名目 +5.6% 美元），較上年 3.8% 下滑、六年最低；5 年年化名目 3.6%。全權主動管理的全球委託。",
            "alloc": [
                {"cls": "股票", "pct": 56.0},
                {"cls": "固定收益", "pct": 22.0},
                {"cls": "實物資產", "pct": 22.0},
            ],
            "tops": [],
        },
        {
            "name": "韓國國民年金（National Pension Service）",
            "mgr": "全球第三大養老基金",
            "country": "韓國",
            "aum": "≈1,458 兆韓元",
            "asof": "2025 曆年末（2025-12-31）",
            "source": "NPS／韓國保健福祉部 2025 年報",
            "note": "2025 年回報 +18.82%——1988 年成立以來最高，收益 231.6 兆韓元；成立以來年化 8.04%。2025 年優於挪威 GPFG +15.1%、日本 GPIF +12.3%、加拿大 CPPIB +7.7%、荷蘭 ABP −1.6%。",
            "alloc": [
                {"cls": "海外股票", "pct": 37.8},
                {"cls": "國內債券", "pct": 20.9},
                {"cls": "國內股票", "pct": 18.1},
                {"cls": "另類", "pct": 16.0},
                {"cls": "海外債券", "pct": 6.9},
                {"cls": "短期資金", "pct": 0.3},
            ],
            "tops": [],
        },
    ]

    # 13F 反向持倉（公司 → 持有該股的頂級基金）與法定申報日曆
    fund_holdings = build_fund_holdings(HEDGE_FUNDS, companies)
    f13f = build_13f_calendar()

    # 政要交易反向匹配（公司 → 涉及該股的政要披露記錄）
    polit_holdings = build_polit_holdings(POLITICIAN_DISCLOSURES, companies)

    # 中國資產專區（港股／A股／中概股聚合 + 宏觀常量）
    china = compute_china(companies, quotes, fund_data)

    # 個股獨立分析頁（stocks/，每家公司一頁，內嵌估值模型；帶反向持倉引用）
    if quick:
        st_stats = {"pages": rc.get("stocks_pages", 0), "with_data": 0}
        print(f"   ✓ 快速模式：個股分析頁沿用既有 {st_stats['pages']} 頁（不重渲染）")
    else:
        st_stats = render_stock_pages(companies, quotes, fund_data, in_combo_names,
                                      fund_holdings, polit_holdings)
        print(f"   ✓ 個股分析頁 {st_stats['pages']} 頁（含基本面數據 {st_stats['with_data']} 頁，"
              f"頂級基金持倉引用 {sum(len(v) for v in fund_holdings.values())} 條，"
              f"政要交易引用 {sum(len(v) for v in polit_holdings.values())} 條）")

    # 網站資料（報告、公司、行情、配置、基金與對沖基金公開披露）
    data = {
        "stats": {
            "reports": idx["count"], "companies": len(companies),
            "topics": len(topics), "updated": max(r["date"] for r in reports),
            "stocks": st_stats["pages"],
        },
        # 全球前五大基金資產配置（公開披露數據，按最新年報／政策區間，站長手動維護）
        "funds": FUNDS,
        # 前五大對沖基金配置動態（SEC 13F 美股多頭口徑，站長手動維護）
        "hedgefunds": HEDGE_FUNDS,
        # 模組 12 擴展：家族辦公室（13F）／大學捐贈基金（年報）／養老基金（年報）
        "familyoffices": FAMILY_OFFICES,
        "endowments": ENDOWMENTS,
        "pensions": PENSIONS,
        # 13F 反向持倉映射與法定申報日曆（模組 6）
        "fund_holdings": fund_holdings,
        "f13f": f13f,
        # 政要交易追蹤（模組 7）：披露整理 + 國會動態 + 反向匹配
        "politician": build_politician(companies),
        "polit_holdings": polit_holdings,
        # 中國資產專區（模組 8）
        "china": {
            "macro": CHINA_MACRO, "indices": CHINA_INDICES,
            "timeline": CHINA_TRADE_TIMELINE,
            "stocks": china,
        },
        # 歷史情景回測（模組 9）
        "scenarios": scenarios,
        # 風險儀表板（模組 7/8/10/18）
        "risk": risk,
        # 市場全景（模組 11/13/14/16/17/19/21）
        "marketview": marketview,
        # 決策工具箱（模組 22-26）：風險預算＋規則透明日誌＋規則文字
        "tools": tools,
        # 本週市場回顧（模組 29）
        "review": review,
        "companies": companies,
        "topics": topics,
        "latest_reports": [
            {"title": r["title"], "date": r["date"], "type": r["type"],
             "group": r["group"], "bucket": r["bucket"],
             "path": site_path(r["path"])}
            for r in all_reports[:30]
        ],
        "market": quotes,
        "indices": indices,
        "market_asof": max((q.get("asof", "") for q in quotes.values()), default=""),
        "allocation": allocation,
        "sectors": [{"name": n, "count": c}
                    for n, c in sorted(Counter(c["sector"] for c in companies).items(),
                                       key=lambda kv: -kv[1])],
    }

    # 寫 js/data.js
    with open(os.path.join(SITE_DIR, "js", "data.js"), "w", encoding="utf-8") as f:
        f.write("// 由 build_site.py 自動生成，勿手動編輯\n")
        f.write("window.SITE_DATA = ")
        json.dump(data, f, ensure_ascii=False)
        f.write(";\n")
    print(f"✓ js/data.js 已生成（{os.path.getsize(os.path.join(SITE_DIR, 'js', 'data.js'))/1024:.0f} KB）")

    if not quick:
        # 寫報告快取：快速更新（小更新）從這裡取公司/專題/索引，免重讀 repo、免重渲染
        with open(REPORTS_CACHE, "w", encoding="utf-8") as f:
            json.dump({"idx": idx, "companies": companies, "topics": topics,
                       "extra": extra, "stocks_pages": st_stats["pages"]},
                      f, ensure_ascii=False)
        print("✓ js/reports_cache.json 已寫入（供小更新使用）")
    print(f"✓ 完成，耗時 {time.time() - t_start:.0f} 秒")


def render_reports(repo, reports):
    """把全部報告預渲染成獨立 HTML 頁面。"""
    out_root = os.path.join(SITE_DIR, "reports")
    # 複製 repo 的 assets（報告內圖片會用到）
    repo_assets = os.path.join(repo, "assets")
    if os.path.isdir(repo_assets):
        shutil.copytree(repo_assets, os.path.join(out_root, "assets"),
                        dirs_exist_ok=True)
        # 網站更名：資源檔（SVG 內嵌文字）中的舊站名/舊倉庫名一併改寫
        for root, __dirs, files in os.walk(os.path.join(out_root, "assets")):
            for f in files:
                if not f.lower().endswith(".svg"):
                    continue
                p = os.path.join(root, f)
                try:
                    s = open(p, encoding="utf-8").read()
                except (OSError, UnicodeDecodeError):
                    continue
                s2 = s.replace("AI Berkshire", "AIShan+").replace(
                    "xbtlin/ai-berkshire", "aliu29775-bot/ai-berkshire")
                if s2 != s:
                    open(p, "w", encoding="utf-8").write(s2)
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
<title>{_esc(title)} — AIShan+ 投研網站</title>
<link rel="stylesheet" href="{rel}css/style.css">
<link rel="stylesheet" href="{rel}css/report.css">
</head>
<body data-page="report">
<header class="site-nav">
  <a class="brand" href="{rel}index.html">◆ AIShan+ <span>投研網站</span></a>
  <nav>
    <a href="{rel}index.html">首頁</a>
    <a href="{rel}companies.html">公司</a>
    <a href="{rel}reports.html">報告</a>
    <a href="{rel}trackrecord.html">組合</a>
    <a href="{rel}allocation.html">配置</a>
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
    <p>資料來源：<a href="https://github.com/aliu29775-bot/ai_investment_tool_aliu" target="_blank" rel="noopener">GitHub：AIShan+</a>
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
