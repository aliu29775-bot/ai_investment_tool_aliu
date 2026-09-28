/* AIShan+ 個股獨立分析頁渲染（讀取 #stock-data 內嵌 JSON） */
(function () {
  "use strict";
  var root = document.getElementById("stock-root");
  var dataEl = document.getElementById("stock-data");
  if (!root || !dataEl) return;
  var S = JSON.parse(dataEl.textContent);

  var SECTOR_COLORS = {科技: "#3b89e3", 互聯網: "#17b2a0", 金融: "#8a6fd1", 消費: "#e08c3a",
    材料: "#c2543a", 醫藥: "#2e9e6b", 能源: "#5a6b8c", 工業: "#6c7a89", 汽車: "#d95f8c",
    公用事業: "#d9a514", 房地產: "#b07a3a", 電信: "#a58fd1", 債券: "#a58fd1", 商品: "#98a2b3",
    黃金: "#c9a227"};
  var REC = [[1.5, "強力買入"], [2.5, "買入"], [3.5, "持有"], [4.5, "減持"], [99, "賣出"]];

  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function fmtPct(v, d) { return v == null ? "—" : (v * 100).toFixed(d == null ? 1 : d) + "%"; }
  function fmtNum(v) {
    if (v == null || isNaN(v)) return "—";
    var a = Math.abs(v);
    if (a >= 1e12) return (v / 1e12).toFixed(2) + " 兆";
    if (a >= 1e8) return (v / 1e8).toFixed(1) + " 億";
    if (a >= 1e6) return (v / 1e6).toFixed(1) + " 百萬";
    if (a >= 1e3) return (v / 1e3).toFixed(1) + " K";
    return v.toFixed(2);
  }
  function cls(v) { return v == null ? "" : (v > 0 ? "up" : v < 0 ? "down" : "mid"); }
  function chip(v, suffix) {
    var c = cls(v);
    return '<span class="s-chip ' + c + '">' + (v > 0 ? "▲" : v < 0 ? "▼" : "·") +
      " " + fmtPct(v) + (suffix || "") + "</span>";
  }
  function card(title, body, icon) {
    return '<section class="s-card"><h2>' + (icon || "") + " " + title + "</h2>" +
      '<div class="s-body">' + body + "</div></section>";
  }
  function kv(label, value, note) {
    return '<div class="s-kv"><span class="s-k">' + label + "</span>" +
      '<span class="s-v">' + value + "</span>" +
      (note ? '<span class="s-n">' + note + "</span>" : "") + "</div>";
  }

  var q = S.quote || {}, f = S.finance || {}, m = S.multiples || {},
      dcf = S.dcf || {}, ta = S.ta || {}, an = S.analyst || {};

  /* ---------- 頁首 ---------- */
  var badges = "";
  if (S.hot) badges += '<span class="s-badge hot">⭐ 熱門深研</span>';
  if (S.in_combo) badges += '<span class="s-badge combo">✓ 在選定組合中</span>';
  if (S.region) badges += '<span class="s-badge">' + esc(S.region) + "</span>";
  if (S.sector) badges += '<span class="s-badge" style="background:' +
    (SECTOR_COLORS[S.sector] || "#888") + '20;color:' + (SECTOR_COLORS[S.sector] || "#888") +
    '">' + esc(S.sector) + "</span>";
  var stars = "", sv = S.score && S.score.value;
  if (sv != null) {
    stars = '<span class="s-stars" title="四維評分">' +
      "★★★★★".slice(0, Math.round(sv)).split("").map(function () { return "★"; }).join("") +
      '<span class="s-stars-dim">' + "★★★★★".slice(0, 5 - Math.round(sv)) + "</span>" +
      " " + sv.toFixed(1) + "/5</span>";
  }
  var vd = S.verdict ? '<span class="s-verdict ' + (S.verdict_class || "") + '">' +
    esc(S.verdict) + "</span>" : "";
  var chg = q.change_pct != null ? chip(q.change_pct / 100) : "";
  var head = '<div class="s-head">' +
    '<div class="s-title-row"><h1>' + esc(S.name) + "</h1>" +
    (S.ticker ? '<span class="s-ticker">' + esc(S.ticker) + "</span>" : "") + "</div>" +
    '<div class="s-badges">' + badges + "</div>" +
    '<div class="s-quote">' +
    '<span class="s-price">' + (q.price != null ? q.price : "—") +
    (q.currency ? ' <small>' + esc(q.currency) + "</small>" : "") + "</span>" + chg +
    (q.asof ? '<span class="s-asof">行情截至 ' + esc(q.asof) + "</span>" : "") +
    "</div>" +
    '<div class="s-meta">' + stars + vd + "</div></div>";

  /* ---------- 一句話總結 ---------- */
  var sum = S.summary || (sv != null
    ? "研報四維評分 " + sv.toFixed(1) + "/5" + (S.verdict ? "，結論「" + esc(S.verdict) + "」" : "") + "。" +
      (dcf.premium != null ? "DCF 中性情景較現價" + (dcf.premium >= 0 ? "折價" : "溢價") + " " +
        fmtPct(Math.abs(dcf.premium)) + "。" : "") +
      (ta.ma200 != null && q.price != null ? "價格" + (q.price >= ta.ma200 ? "位於" : "低於") + " 200 日均線。" : "")
    : "尚無研報覆蓋，僅監測行情與公開財務數據。");

  /* ---------- 公司概況 ---------- */
  var prof = S.profile || {};
  var profileBody = "";
  if (prof.biz) {
    var biz = prof.biz.length > 420 ? prof.biz.slice(0, 420) + "…" : prof.biz;
    profileBody = "<p class='s-biz'>" + esc(biz) + "</p>";
    if (prof.industry || prof.country || prof.website)
      profileBody += '<div class="s-grid2">' +
        (prof.industry ? kv("行業", esc(prof.industry)) : "") +
        (prof.country ? kv("總部", esc(prof.country)) : "") +
        (prof.website ? kv("官網", esc(prof.website)) : "") + "</div>";
  } else {
    profileBody = "<p>公司概況簡介暫缺（Yahoo 未提供）；最新研報見頁末列表。</p>";
  }

  /* ---------- 熱門深研加厚 ---------- */
  var relPe = S.relative && S.relative.pe;
  var deepBody = "";
  if (S.hot) {
    if ((S.officers || []).length) {
      deepBody += '<h3 class="s-h3">👔 管理層</h3><table class="s-table">' +
        "<thead><tr><th>姓名</th><th>年齡</th><th>職位</th></tr></thead><tbody>" +
        S.officers.map(function (o) {
          return "<tr><td>" + esc(o.name) + "</td><td>" + (o.age != null ? o.age : "—") +
            "</td><td>" + esc(o.title) + "</td></tr>";
        }).join("") + "</tbody></table>";
    }
    if ((S.income_hist || []).length) {
      deepBody += '<h3 class="s-h3">💵 近 4 年營收與利潤</h3><table class="s-table">' +
        "<thead><tr><th>年度</th><th>營收</th><th>毛利</th><th>毛利率</th><th>淨利</th><th>淨利率</th></tr></thead><tbody>" +
        S.income_hist.map(function (r) {
          var gm = r.revenue != null && r.gross != null && r.revenue ? r.gross / r.revenue : null;
          var nm = r.revenue != null && r.net_income != null && r.revenue
            ? r.net_income / r.revenue : null;
          return "<tr><td>" + esc(r.year) + "</td><td>" + fmtNum(r.revenue) + "</td><td>" +
            fmtNum(r.gross) + "</td><td>" + (gm != null ? fmtPct(gm) : "—") + "</td><td>" +
            (r.net_income != null
              ? (r.net_income < 0 ? "−" : "") + fmtNum(Math.abs(r.net_income)) : "—") +
            "</td><td>" + (nm != null ? fmtPct(nm) : "—") + "</td></tr>";
        }).join("") + "</tbody></table>";
    }
    var shr = S.shr || {};
    if (shr.dps != null || shr.ocf != null) {
      deepBody += '<h3 class="s-h3">💸 股東回報（TTM）</h3><div class="s-grid2">' +
        (shr.dps != null ? kv("每股股息", shr.dps.toFixed(2) + (q.currency ? " " + esc(q.currency) : "")) : "") +
        (shr.dy != null ? kv("股息率", fmtPct(shr.dy)) : "") +
        (shr.payout != null ? kv("派息率", fmtPct(shr.payout)) : "") +
        (shr.ocf != null ? kv("經營現金流", fmtNum(shr.ocf) + (q.currency ? " " + esc(q.currency) : "")) : "") +
        (shr.fcf != null ? kv("自由現金流", fmtNum(shr.fcf) + (q.currency ? " " + esc(q.currency) : "")) : "") +
        "</div>";
    }
    if ((S.earn_trend || []).length) {
      deepBody += '<h3 class="s-h3">📐 盈利預測趨勢（分析師）</h3><div class="s-grid2">' +
        S.earn_trend.map(function (t) {
          return kv(esc(t.period), t.growth != null ? fmtPct(t.growth) : "—");
        }).join("") + "</div>";
    }
    var moat = [], comp = [];
    if (f.roe != null && f.roe > 0.25) moat.push("ROE " + fmtPct(f.roe) + "，資本回報遠高於市場平均");
    else if (f.roe != null && f.roe > 0.15) moat.push("ROE " + fmtPct(f.roe) + "，資本回報穩健");
    if (f.margins != null && f.margins > 0.2) moat.push("淨利率 " + fmtPct(f.margins) + "，具備定價能力");
    if (f.margins != null && f.margins < 0.05) comp.push("淨利率僅 " + fmtPct(f.margins) + "，行業競爭激烈");
    if (m.beta != null && m.beta < 0.8) moat.push("Beta " + m.beta.toFixed(2) + "，業務具防禦性");
    if (relPe && relPe.premium > 0.5) comp.push("PE 較同業溢價 " + fmtPct(relPe.premium) + "，市場定價已反映樂觀預期");
    if (f.debt_equity != null && f.debt_equity > 150) comp.push("負債/權益 " + f.debt_equity.toFixed(0) + "%，槓桿偏高");
    if (!moat.length) moat.push("暫無突出護城河數據，需結合研報定性判斷");
    if (!comp.length) comp.push("暫無明顯競爭劣勢數據");
    deepBody += '<div class="s-bullbear"><div class="s-bull"><h3>🏰 護城河觀察</h3><ul>' +
      moat.map(function (x) { return "<li>" + x + "</li>"; }).join("") + "</ul></div>" +
      '<div class="s-bear"><h3>⚔️ 競爭壓力</h3><ul>' +
      comp.map(function (x) { return "<li>" + x + "</li>"; }).join("") + "</ul></div></div>" +
      "<p class='s-note'>深研加厚基於公開財務與分析師數據自動生成；管理層變動、監管與行業事件見研報原文。</p>";
  }

  /* ---------- 財務分析 ---------- */
  var finRows = [["淨利率", f.margins != null ? fmtPct(f.margins) : "—"],
    ["營業利潤率", f.op_margins != null ? fmtPct(f.op_margins) : "—"],
    ["ROE", f.roe != null ? fmtPct(f.roe) : "—"],
    ["營收增速", f.rev_growth != null ? fmtPct(f.rev_growth) : "—"],
    ["盈利增速", f.earn_growth != null ? fmtPct(f.earn_growth) : "—"],
    ["自由現金流", fmtNum(f.fcf) + (q.currency ? " " + esc(q.currency) : "")],
    ["負債/權益", f.debt_equity != null ? f.debt_equity.toFixed(0) + "%" : "—"],
    ["現金", fmtNum(f.cash) + (q.currency ? " " + esc(q.currency) : "")],
    ["總債務", fmtNum(f.debt) + (q.currency ? " " + esc(q.currency) : "")],
    ["營收(TTM)", fmtNum(f.revenue) + (q.currency ? " " + esc(q.currency) : "")],
    ["EBITDA", fmtNum(f.ebitda) + (q.currency ? " " + esc(q.currency) : "")],
    ["EPS(TTM)", f.eps != null ? f.eps.toFixed(2) : "—"]];
  var finBody = f.margins == null && f.fcf == null && f.revenue == null
    ? "<p>財務數據暫缺（Yahoo 未提供該市場數據）。</p>"
    : '<div class="s-grid2">' + finRows.map(function (r) { return kv(r[0], r[1]); }).join("") +
      '<p class="s-note">數據源：Yahoo Finance（TTM）。</p></div>';

  /* ---------- 估值建模 ---------- */
  var valBody = "";
  // 倍數
  var multRows = [["PE(TTM)", m.pe != null ? m.pe.toFixed(1) + "×" : "—"],
    ["前瞻 PE", m.fwd_pe != null ? m.fwd_pe.toFixed(1) + "×" : "—"],
    ["PB", m.pb != null ? m.pb.toFixed(2) + "×" : "—"],
    ["PS", m.ps != null ? m.ps.toFixed(2) + "×" : "—"],
    ["EV/EBITDA", m.evebitda != null ? m.evebitda.toFixed(1) + "×" : "—"],
    ["PEG", m.peg != null ? m.peg.toFixed(2) : "—"],
    ["股息率", m.dy != null ? fmtPct(m.dy) : "—"],
    ["Beta", m.beta != null ? m.beta.toFixed(2) : "—"],
    ["市值", fmtNum(m.mktcap) + (q.currency ? " " + esc(q.currency) : "")]];
  valBody += '<h3 class="s-h3">💠 估值倍數</h3><div class="s-grid2">' +
    multRows.map(function (r) { return kv(r[0], r[1]); }).join("") + "</div>";

  // DCF
  if (dcf.value != null) {
    var prem = dcf.premium != null ? chip(dcf.premium, " 對現價") : "";
    valBody += '<h3 class="s-h3">💠 DCF 模型（兩階段自由現金流折現）</h3>' +
      '<div class="s-grid2">' +
      kv("基期 FCF(TTM)", fmtNum(dcf.fcf) + (q.currency ? " " + esc(q.currency) : "")) +
      kv("增長假設 g", fmtPct(dcf.g)) +
      kv("折現率 r", fmtPct(dcf.r, 1)) +
      kv("終值增速", "2.5%") +
      kv("中性內在價值", dcf.neutral != null ? dcf.neutral.toFixed(2) : "—", "每股") +
      kv("現價", q.price != null ? q.price + (q.currency ? " " + esc(q.currency) : "") : "—",
        prem ? "" : "") + "</div>" +
      '<div class="s-prem">內在價值 vs 現價：' + prem +
      (dcf.premium != null && dcf.premium < 0 ? "（高估）" : "（低估）") + "</div>" +
      '<h3 class="s-h3">💠 敏感性分析（每股內在價值）</h3>' +
      '<table class="s-matrix"><thead><tr><th>g＼r</th>' +
      (dcf.gs || []).map(function (x) { return "<th>g=" + fmtPct(x) + "</th>"; }).join("") +
      "</tr></thead><tbody>" +
      (dcf.matrix || []).map(function (row) {
        return "<tr><th>r=" + fmtPct(row.r, 1) + "</th>" +
          row.cells.map(function (v) {
            return "<td" + (v == null ? "" : (v > (q.price || 0) ? ' class="m-good"' : ' class="m-bad"')) +
              ">" + (v == null ? "—" : v.toFixed(0)) + "</td>";
          }).join("") + "</tr>";
      }).join("") + "</tbody></table>" +
      '<div class="s-grid3">' +
      kv("悲觀情景", dcf.pessimistic != null ? dcf.pessimistic.toFixed(2) : "—") +
      kv("中性情景", dcf.neutral != null ? dcf.neutral.toFixed(2) : "—") +
      kv("樂觀情景", dcf.optimistic != null ? dcf.optimistic.toFixed(2) : "—") + "</div>";
  } else {
    valBody += "<p>DCF 暫缺：自由現金流數據不足（Yahoo 未提供或公司 FCF 為負）。</p>";
  }
  // DDM
  if (S.ddm) {
    valBody += '<h3 class="s-h3">💠 股息折現模型（Gordon DDM）</h3><div class="s-grid2">' +
      kv("每股股息", S.ddm.dps.toFixed(2) + (q.currency ? " " + esc(q.currency) : "")) +
      kv("股息增速 g", fmtPct(S.ddm.g)) +
      kv("DDM 價值", S.ddm.value.toFixed(2), "每股") +
      kv("對現價", S.ddm.premium != null ? fmtPct(S.ddm.premium) : "—") + "</div>";
  }
  // 相對估值
  var relKeys = { pe: "PE", pb: "PB", ps: "PS", evebitda: "EV/EBITDA" };
  var relRows = Object.keys(relKeys).filter(function (k) { return S.relative && S.relative[k]; });
  if (relRows.length) {
    valBody += '<h3 class="s-h3">💠 相對估值 vs 同業中位數</h3>' +
      '<table class="s-table"><thead><tr><th>指標</th><th>本公司</th><th>同業中位</th><th>折溢價</th></tr></thead><tbody>' +
      relRows.map(function (k) {
        var r = S.relative[k];
        return "<tr><td>" + relKeys[k] + "</td><td>" + r.own.toFixed(2) + "×</td><td>" +
          r.median.toFixed(2) + "×</td><td>" + chip(r.premium) + "</td></tr>";
      }).join("") + "</tbody></table>" +
      '<p class="s-note">同業 = 全站同行業公司（' + (S.rel_peers_n || 0) + " 家）。</p>";
  }

  /* ---------- 技術面 ---------- */
  var taBody = "";
  if (ta.n >= 50) {
    var pos50 = q.price != null && ta.ma50 != null ? (q.price >= ta.ma50 ? "之上" : "之下") : "";
    var pos200 = q.price != null && ta.ma200 != null ? (q.price >= ta.ma200 ? "之上" : "之下") : "";
    taBody = '<div class="s-grid2">' +
      (ta.ma50 != null ? kv("50 日均線", ta.ma50.toFixed(2), q.price != null ? "現價" + pos50 : "") : "") +
      (ta.ma200 != null ? kv("200 日均線", ta.ma200.toFixed(2), q.price != null ? "現價" + pos200 : "") : "") +
      (ta.ret_1y != null ? kv("近 1 年漲跌", fmtPct(ta.ret_1y)) : "") +
      (ta.rs != null ? kv("相對強弱 vs 標普500", fmtPct(ta.rs), "跑贏為正") : "") +
      (ta.support != null ? kv("支撐位（近 3 月低點）", ta.support.toFixed(2)) : "") +
      (ta.resistance != null ? kv("阻力位（近 3 月高點）", ta.resistance.toFixed(2)) : "") +
      (ta["52w_high"] != null ? kv("52 週區間", ta["52w_low"].toFixed(2) + " – " + ta["52w_high"].toFixed(2)) : "") +
      (ta.vol_trend != null ? kv("成交量趨勢", chip(ta.vol_trend), "近 10 日 vs 前 2 月") : "") +
      "</div><p class='s-note'>基於近 1 年日線（" + ta.n + " 個交易日）。</p>";
  } else {
    taBody = "<p>技術面數據暫缺。</p>";
  }

  /* ---------- 機構持倉與分析師 ---------- */
  var instBody = "";
  if ((S.holders || []).length) {
    instBody = '<table class="s-table"><thead><tr><th>機構</th><th>持股比例</th><th>持倉市值</th></tr></thead><tbody>' +
      S.holders.map(function (h) {
        return "<tr><td>" + esc(h.org) + "</td><td>" +
          (h.pct != null ? h.pct.toFixed(2) + "%" : "—") + "</td><td>" + fmtNum(h.value) + "</td></tr>";
      }).join("") + "</tbody></table>" +
      '<p class="s-note">數據源：SEC 13F 匯總（Yahoo institutionOwnership）；僅美股多頭口徑。</p>';
  } else {
    instBody = "<p>機構持倉數據暫缺（非美股或 Yahoo 未提供）。</p>";
  }
  var recLabel = "—";
  if (an.rec != null) {
    for (var i = 0; i < REC.length; i++) if (an.rec <= REC[i][0]) { recLabel = REC[i][1]; break; }
  }
  var anBody = '<div class="s-grid2">' +
    (S.inst_pct != null ? kv("機構持股比例", fmtPct(S.inst_pct)) : "") +
    kv("分析師評級", recLabel, an.n ? an.n + " 位分析師" : "") +
    (an.target != null ? kv("目標價均值", an.target.toFixed(2) + (q.currency ? " " + esc(q.currency) : ""),
      q.price != null && an.target ? chip((an.target / q.price) - 1, " 對現價") : "") : "") +
    (an.low != null && an.high != null ? kv("目標價區間", an.low.toFixed(0) + " – " + an.high.toFixed(0)) : "") +
    "</div>";

  /* ---------- 催化劑與風險 ---------- */
  var catBody = '<div class="s-grid2">' +
    (S.earnings_date ? kv("📅 下次財報", esc(S.earnings_date)) : kv("📅 下次財報", "未知")) +
    (m.beta != null ? kv("宏觀關聯 · Beta", m.beta.toFixed(2),
      m.beta > 1.3 ? "對利率/大盤敏感" : m.beta < 0.8 ? "防禦性強" : "中等") : "") +
    "</div>" +
    "<p class='s-note'>近期催化劑：財報、產品發佈與政策事件（深度版將逐家梳理）。" +
    "主要風險：業績不及預期、估值回調、行業監管與競爭、利率上行（依 Beta 高低而異）。</p>";

  /* ---------- AI 投資論點 ---------- */
  var bull = [], bear = [];
  if (sv != null) {
    if (S.verdict_class === "positive") bull.push("研報結論正面：「" + esc(S.verdict) + "」，四維評分 " + sv.toFixed(1) + "/5");
    if (S.verdict_class === "negative") bear.push("研報結論負面：「" + esc(S.verdict) + "」");
    if (S.verdict_class === "neutral" || !S.verdict_class) bull.push("研報結論中性/未定：「" + esc(S.verdict || "灰色地帶") + "」，需等待更好價格");
  } else {
    bull.push("尚未有研報覆蓋，暫按公開財務與估值數據監測");
  }
  if (dcf.premium != null && dcf.premium > 0.1) bull.push("DCF 中性情景較現價折價 " + fmtPct(dcf.premium) + "，安全邊際較大");
  if (dcf.premium != null && dcf.premium < -0.1) bear.push("DCF 中性情景較現價溢價 " + fmtPct(-dcf.premium) + "，估值偏貴");
  if (relPe && relPe.premium < -0.3) bear.push("PE 較同業溢價 " + fmtPct(-relPe.premium));
  if (relPe && relPe.premium > 0.3) bull.push("PE 較同業折價 " + fmtPct(relPe.premium));
  if (ta.ma200 != null && q.price != null) {
    if (q.price >= ta.ma200) bull.push("價格位於 200 日均線之上，中期趨勢偏多");
    else bear.push("價格跌破 200 日均線，中期趨勢偏空");
  }
  if (ta.rs != null && ta.rs > 0.05) bull.push("近 1 年跑贏標普 500 達 " + fmtPct(ta.rs));
  if (ta.rs != null && ta.rs < -0.05) bear.push("近 1 年跑輸標普 500 達 " + fmtPct(-ta.rs));
  if (an.target != null && q.price != null && an.target / q.price > 1.15) bull.push("分析師目標價較現價高 " + fmtPct(an.target / q.price - 1));
  if (m.dy && m.dy > 0.03) bull.push("股息率 " + fmtPct(m.dy) + "，現金回報穩健");
  if (f.debt_equity != null && f.debt_equity > 200) bear.push("負債/權益比偏高（" + f.debt_equity.toFixed(0) + "%）");
  if (f.roe != null && f.roe > 0.2) bull.push("ROE 達 " + fmtPct(f.roe) + "，資本回報優秀");
  if (!bull.length) bull.push("暫無明顯看多信號，等待催化劑");
  if (!bear.length) bear.push("暫無明顯看空信號，主要風險在宏觀與行業層面");
  var comboLine = S.in_combo
    ? "✅ 目前在網站的「選定公司組合」（當前持倉）中，權重按評分歸一化。"
    : "➖ 目前不在選定組合中" + (S.score ? "（組合按結論正面且評分最高的 8 家選取）" : "（尚無研報評分）。");
  var aiBody = '<div class="s-bullbear"><div class="s-bull"><h3>🐂 看多理由</h3><ul>' +
    bull.map(function (x) { return "<li>" + x + "</li>"; }).join("") + "</ul></div>" +
    '<div class="s-bear"><h3>🐻 看空理由</h3><ul>' +
    bear.map(function (x) { return "<li>" + x + "</li>"; }).join("") + "</ul></div></div>" +
    "<p class='s-combo'>" + comboLine + "</p>";

  /* ---------- 頂級基金持倉（13F 反向匹配） ---------- */
  var fmBody = "";
  if ((S.fund_mentions || []).length) {
    fmBody = '<table class="s-table"><thead><tr><th>基金</th><th>披露內容</th></tr></thead><tbody>' +
      S.fund_mentions.map(function (m) {
        return "<tr><td>" + esc(m.fund) + "</td><td>" + esc(m.detail) + "</td></tr>";
      }).join("") + "</tbody></table>" +
      '<p class="s-note">來源：各基金最新 SEC 13F 披露（僅美股多頭口徑）的機械匹配，僅供參考。</p>';
  }

  /* ---------- 研報 ---------- */
  var repBody = "";
  if ((S.reports || []).length) {
    repBody = "<ol class='s-reports'>" + S.reports.slice(0, 30).map(function (r) {
      return "<li><a href='" + esc("../reports/" + r.path) + "'>" + esc(r.title) + "</a>" +
        '<span class="s-rep-date">' + esc(r.date) + "</span></li>";
    }).join("") + "</ol>";
    if (S.reports.length > 30) repBody += "<p class='s-note'>… 另有 " + (S.reports.length - 30) + " 份報告</p>";
  } else {
    repBody = "<p>暫無研報（監測中）。</p>";
  }

  root.innerHTML = head +
    card("📌 一句話總結", "<p class='s-summary'>" + sum + "</p>") +
    card("🏢 公司概況", profileBody) +
    (S.hot ? card("🔍 熱門深研加厚", deepBody) : "") +
    card("📊 財務分析", finBody) +
    card("💰 估值建模", valBody) +
    card("📈 技術面與動量", taBody) +
    card("🏦 機構持倉與分析師", instBody + '<h3 class="s-h3">🎯 分析師</h3>' + anBody) +
    (fmBody ? card("🏰 頂級基金持倉", fmBody) : "") +
    card("🎯 催化劑與風險", catBody) +
    card("🤖 AI 投資論點", aiBody) +
    card("📄 研究報告", repBody);
})();
