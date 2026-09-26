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
import subprocess
import sys
import time
import urllib.parse
from datetime import datetime
import urllib.request
from collections import Counter, defaultdict

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
                    "closes": [round(c, 2) for c in valid[-5:]],
                }
                if verbose:
                    print(f"  ✓ {sym:14s} {price:>10.2f} {meta.get('currency','')}")
        except Exception as e:
            if verbose:
                print(f"  ✗ {sym:14s} {e}")
        time.sleep(0.25)
    return quotes


# ---------------------------------------------------------------------------
# 3.5 宏觀數據與資產配置（FRED + Yahoo 資產行情）
# ---------------------------------------------------------------------------

FRED_SERIES = ["CPIAUCSL", "PCEPILFE", "UNRATE", "DGS2", "DGS10", "DGS30",
               "DFF", "BAMLH0A0HYM2", "BAMLH0A0HYM2EY", "BAMLC0A0CM", "BAMLC0A0CMEY",
               "DFII10", "GDPC1", "PAYEMS", "T10Y2Y"]

ASSET_PROXIES = {"股票": "SPY", "國債": "IEF", "長期國債": "TLT",
                 "商品": "DBC", "黃金": "GLD", "現金": "BIL"}

COMMODITY_FUTURES = [("黃金", "GC=F", "美元/盎司"), ("白銀", "SI=F", "美元/盎司"),
                     ("原油WTI", "CL=F", "美元/桶"), ("銅", "HG=F", "美元/磅")]


def fetch_fred(series_ids, cache_file):
    """用 curl -4 抓 FRED fredgraph.csv（部分網絡 urllib 走 IPv6 會超時）。"""
    fred = {}
    for sid in series_ids:
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
                fred[sid] = vals
                print(f"  ✓ FRED {sid:16s} 最新 {vals[-1][1]:>10.2f} ({vals[-1][0]})")
            else:
                print(f"  ✗ FRED {sid:16s} 空資料")
        except Exception as e:
            print(f"  ✗ FRED {sid:16s} {e}")
        time.sleep(0.2)
    if not fred and os.path.exists(cache_file):
        fred = json.load(open(cache_file, encoding="utf-8"))
        print("  網路不可用，使用宏觀快取")
    elif fred:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(fred, f, ensure_ascii=False)
    return fred


def fetch_asset_perf(symbols):
    """抓 1 年（日線）行情，計算 YTD/1Y 報酬、52 周高低，並保留日期序列供組合實時收益計算。"""
    perf = {}
    for sym in sorted(set(symbols)):
        url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
               f"{urllib.parse.quote(sym)}?range=1y&interval=1d")
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
                continue
            price = meta.get("regularMarketPrice") or pairs[-1][1]
            first = pairs[0][1]
            cur_year = datetime.fromtimestamp(pairs[-1][0]).year
            jan = next((c for t, c in pairs
                        if datetime.fromtimestamp(t).year == cur_year), None)
            ytd = (price / jan - 1) * 100 if jan else None
            y1 = (price / first - 1) * 100 if first else None
            perf[sym] = {
                "price": round(price, 2),
                "ytd": round(ytd, 2) if ytd is not None else None,
                "y1": round(y1, 2) if y1 is not None else None,
                "high": meta.get("fiftyTwoWeekHigh"),
                "low": meta.get("fiftyTwoWeekLow"),
                "closes": [round(c, 2) for _, c in pairs],
                # 組合實時收益用：全精度收盤 + 日期（YYYY-MM-DD）
                "series": [round(c, 4) for _, c in pairs],
                "dates": [datetime.fromtimestamp(t).strftime("%Y-%m-%d") for t, _ in pairs],
            }
            print(f"  ✓ 資產 {sym:8s} {price:>10.2f} | YTD {ytd:>7.2f}% | 1Y {y1:>7.2f}%")
        except Exception as e:
            print(f"  ✗ 資產 {sym:8s} {e}")
        time.sleep(0.25)
    return perf


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

    return {
        "asof": max((q.get("asof", "") for q in quotes.values()), default=""),
        "macro": macro,
        "targets": targets,
        "judgment": judgment,
        "rules": rules,
        "bonds": bonds,
        "commodities": commodities,
        "assets": assets,
        "portfolio": compute_portfolio(asset_perf, targets),
        "sources": ["FRED 聯儲經濟數據（fredgraph.csv）", "Yahoo Finance 公開行情",
                    "ICE/COMEX 期貨報價"],
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

    asset_symbols = list(ASSET_PROXIES.values()) + [s for _, s, _ in COMMODITY_FUTURES]
    quotes = {}
    cache_file = os.path.join(SITE_DIR, "js", "market_cache.json")
    if not args.no_market:
        print(f"== 3/4 抓取行情（{len([t for t in tickers if t])} 個代碼，約 40 秒）==")
        quotes = fetch_quotes(tickers + list(MARKET_INDICES) + asset_symbols)
        for sym, label in MARKET_INDICES.items():
            if sym in quotes:
                quotes[sym]["label"] = label
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(quotes, f, ensure_ascii=False)
    elif os.path.exists(cache_file):
        quotes = json.load(open(cache_file, encoding="utf-8"))
        print(f"== 3/4 使用行情快取（{len(quotes)} 檔，{cache_file}）==")

    # 首頁市場總覽用：主要指數行情（取得到幾個就顯示幾個）
    indices = [{"sym": s, "label": l} for s, l in MARKET_INDICES.items() if s in quotes]

    # 宏觀評分與資產配置（FRED + 資產 1 年報酬）
    alloc_cache = os.path.join(SITE_DIR, "js", "allocation_cache.json")
    allocation = None
    if not args.no_market:
        print("== 3.5/4 抓取宏觀與資產配置資料（FRED + Yahoo 1Y）==")
        fred = fetch_fred(FRED_SERIES, os.path.join("/tmp", "fred_macro_cache.json"))
        asset_perf = fetch_asset_perf(asset_symbols)
        if fred:
            allocation = compute_allocation(fred, quotes, asset_perf)
            with open(alloc_cache, "w", encoding="utf-8") as f:
                json.dump(allocation, f, ensure_ascii=False)
            print(f"  ✓ 資產配置已計算（通脹 {allocation['macro'][1]['score']} 分 / "
                  f"壓力 {allocation['macro'][3]['score']} 分）")
        else:
            print("  ✗ FRED 全數失敗，資產配置跳過")
    elif os.path.exists(alloc_cache):
        allocation = json.load(open(alloc_cache, encoding="utf-8"))
        print("== 3.5/4 使用資產配置快取 ==")

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
        "indices": indices,
        "market_asof": max((q.get("asof", "") for q in quotes.values()), default=""),
        "allocation": allocation,
        "sectors": [{"name": n, "count": c}
                    for n, c in sorted(Counter(c["sector"] for c in companies).items(),
                                       key=lambda kv: -kv[1])],
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
