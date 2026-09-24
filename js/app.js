/* AI Berkshire 投研網站 — 共用邏輯 */
(function () {
  "use strict";

  var D = window.SITE_DATA;
  if (!D) return;

  /* ---------- 主題切換 ---------- */
  var saved = null;
  try { saved = localStorage.getItem("aiberkshire-theme"); } catch (e) {}
  var prefersDark = window.matchMedia &&
    window.matchMedia("(prefers-color-scheme: dark)").matches;
  var theme = saved || (prefersDark ? "dark" : "light");
  document.documentElement.setAttribute("data-theme", theme);

  function initThemeToggle() {
    var btn = document.querySelector(".theme-toggle");
    if (!btn) return;
    var cur = document.documentElement.getAttribute("data-theme") === "dark";
    btn.textContent = cur ? "☀ 亮色" : "🌙 暗色";
    btn.addEventListener("click", function () {
      var nowDark = document.documentElement.getAttribute("data-theme") === "dark";
      var next = nowDark ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      btn.textContent = next === "dark" ? "☀ 亮色" : "🌙 暗色";
      try { localStorage.setItem("aiberkshire-theme", next); } catch (e) {}
      if (window.renderReturnsChart) window.renderReturnsChart();
    });
  }

  /* ---------- 工具 ---------- */
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function stars(n) {
    var full = "★".repeat(Math.max(1, Math.min(5, n)));
    return '<span class="stars" aria-label="' + n + ' 分（滿分 5）">' + full + "</span>";
  }

  function verdictBadge(c) {
    if (!c.verdict) return "";
    var cls = c.verdict_class || "";
    var icon = cls === "positive" ? "✅" : cls === "negative" ? "❌" : "❓";
    return '<span class="badge ' + cls + '">' + icon + " " + esc(c.verdict) + "</span>";
  }

  function priceCell(c) {
    var q = c.ticker && D.market ? D.market[c.ticker] : null;
    if (!q) return '<span class="co-ticker">' + esc(c.ticker || "") + "</span>";
    var chg = q.change_pct == null ? "" :
      '<div class="c ' + (q.change_pct >= 0 ? "up" : "down") + '">' +
      (q.change_pct >= 0 ? "▲" : "▼") + Math.abs(q.change_pct).toFixed(2) + "%</div>";
    return '<div class="co-price"><div class="p">' + esc(q.price.toLocaleString()) +
      '</div>' + chg + "</div>" +
      '<span class="co-ticker">' + esc(c.ticker) + "</span>";
  }

  function reportLink(r) {
    return "reports/" + r.path;
  }

  /* ---------- 首頁 ---------- */
  function renderHome() {
    var feats = D.companies
      .filter(function (c) { return c.score; })
      .sort(function (a, b) { return b.score.value - a.score.value; })
      .slice(0, 6);
    var grid = document.getElementById("featured-grid");
    if (grid) grid.innerHTML = feats.map(coCardHTML).join("");

    var latest = document.getElementById("latest-list");
    if (latest) {
      latest.innerHTML = D.latest_reports.slice(0, 10).map(function (r) {
        return '<div class="report-row">' +
          '<span class="d">' + r.date + "</span>" +
          '<span class="type-badge">' + esc(r.type) + "</span>" +
          '<a class="t" href="' + reportLink(r) + '">' + esc(r.title) + "</a>" +
          '<span class="g">' + esc(r.group) + "</span>" +
          "</div>";
      }).join("");
    }
  }

  /* ---------- 公司卡片 ---------- */
  function coCardHTML(c) {
    var score = c.score ? stars(c.score.stars) +
      '<span class="score-num">' + c.score.value.toFixed(1) + " / 5</span>" : "";
    var sum = c.summary ? '<p class="co-summary">' + esc(c.summary) + "</p>" : "";
    var reports = c.reports.slice(0, 40).map(function (r) {
      return "<li><span class='d'>" + r.date + "</span>" +
        "<span class='t'>" + esc(r.type) + "</span>" +
        '<a href="' + reportLink(r) + '">' + esc(r.title) + "</a></li>";
    }).join("");
    var more = c.reports.length > 40 ? "<li>… 另有 " + (c.reports.length - 40) + " 份報告</li>" : "";
    return '<div class="card co-card" data-name="' + esc(c.name) + '" tabindex="0">' +
      '<div class="co-top"><h3 class="co-name">' + esc(c.name) + "</h3>" +
      priceCell(c) + "</div>" +
      '<div class="co-mid">' + score + verdictBadge(c) + "</div>" +
      sum +
      '<div class="co-foot"><span>📄 ' + c.count + " 份報告</span>" +
      "<span>🕐 最近 " + c.latest + "</span></div>" +
      '<div class="co-reports"><ol>' + reports + more + "</ol></div>" +
      "</div>";
  }

  function initCompanies() {
    var grid = document.getElementById("co-grid");
    if (!grid) return;
    var q = document.getElementById("co-search");
    var state = { filter: "all", q: "" };

    function apply() {
      var list = D.companies.slice();
      if (state.q) {
        var s = state.q.toLowerCase();
        list = list.filter(function (c) {
          return c.name.toLowerCase().indexOf(s) >= 0 ||
            (c.ticker && c.ticker.toLowerCase().indexOf(s) >= 0) ||
            (c.summary && c.summary.toLowerCase().indexOf(s) >= 0);
        });
      }
      if (state.filter === "scored") list = list.filter(function (c) { return c.score; });
      if (state.filter === "positive") list = list.filter(function (c) { return c.verdict_class === "positive"; });
      if (state.filter === "neutral") list = list.filter(function (c) { return c.verdict_class === "neutral"; });
      if (state.filter === "negative") list = list.filter(function (c) { return c.verdict_class === "negative"; });
      list.sort(function (a, b) {
        return (b.score ? b.score.value : -1) - (a.score ? a.score.value : -1);
      });
      grid.innerHTML = list.length ? list.map(coCardHTML).join("") :
        '<div class="empty">沒有符合條件的公司</div>';
      grid.querySelectorAll(".co-card").forEach(function (card) {
        card.addEventListener("click", function () { card.classList.toggle("open"); });
        card.addEventListener("keydown", function (e) {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault(); card.classList.toggle("open");
          }
        });
      });
    }

    q.addEventListener("input", function () { state.q = q.value.trim(); apply(); });
    document.querySelectorAll("[data-filter]").forEach(function (chip) {
      chip.addEventListener("click", function () {
        document.querySelectorAll("[data-filter]").forEach(function (c) { c.classList.remove("on"); });
        chip.classList.add("on");
        state.filter = chip.getAttribute("data-filter");
        apply();
      });
    });
    apply();
  }

  /* ---------- 報告總覽 ---------- */
  function initReports() {
    var list = document.getElementById("report-list");
    if (!list) return;
    var q = document.getElementById("rp-search");
    var state = { q: "", type: "all", bucket: "all", shown: 0 };
    var PAGE = 100;

    function rows() {
      var out = [];
      D.companies.forEach(function (c) {
        c.reports.forEach(function (r) { out.push({ r: r, g: c.name, b: "公司" }); });
      });
      D.topics.forEach(function (t) {
        t.reports.forEach(function (r) { out.push({ r: r, g: t.name, b: t.bucket }); });
      });
      out.sort(function (a, b) { return a.r.date < b.r.date ? 1 : -1; });
      return out;
    }

    var all = rows();

    function apply() {
      var s = state.q.toLowerCase();
      var items = all.filter(function (x) {
        if (state.type !== "all" && x.r.type !== state.type) return false;
        if (state.bucket !== "all" && x.b !== state.bucket) return false;
        if (s && (x.r.title.toLowerCase().indexOf(s) < 0 &&
            x.g.toLowerCase().indexOf(s) < 0)) return false;
        return true;
      });
      state.shown = 0;
      var btn = document.getElementById("load-more");
      var counter = document.getElementById("rp-count");
      counter.textContent = items.length + " 份報告";

      function renderChunk() {
        var chunk = items.slice(state.shown, state.shown + PAGE);
        state.shown += chunk.length;
        chunk.forEach(function (x) {
          var row = document.createElement("div");
          row.className = "report-row";
          row.innerHTML = '<span class="d">' + x.r.date + "</span>" +
            '<span class="type-badge">' + esc(x.r.type) + "</span>" +
            '<a class="t" href="' + reportLink(x.r) + '">' + esc(x.r.title) + "</a>" +
            '<span class="g">' + esc(x.g) + "</span>";
          list.appendChild(row);
        });
        btn.style.display = state.shown >= items.length ? "none" : "block";
      }

      list.innerHTML = "";
      renderChunk();
      btn.onclick = renderChunk;
      if (!items.length) {
        list.innerHTML = '<div class="empty">沒有符合條件的報告</div>';
        btn.style.display = "none";
      }
    }

    q.addEventListener("input", function () { state.q = q.value.trim(); apply(); });
    document.querySelectorAll("[data-type]").forEach(function (chip) {
      chip.addEventListener("click", function () {
        document.querySelectorAll("[data-type]").forEach(function (c) { c.classList.remove("on"); });
        chip.classList.add("on");
        state.type = chip.getAttribute("data-type");
        apply();
      });
    });
    document.querySelectorAll("[data-bucket]").forEach(function (chip) {
      chip.addEventListener("click", function () {
        document.querySelectorAll("[data-bucket]").forEach(function (c) { c.classList.remove("on"); });
        chip.classList.add("on");
        state.bucket = chip.getAttribute("data-bucket");
        apply();
      });
    });
    apply();
  }

  /* ---------- 專題（公司頁第二個 tab） ---------- */
  function initTopics() {
    var grid = document.getElementById("topic-grid");
    if (!grid) return;
    var byBucket = {};
    D.topics.forEach(function (t) {
      (byBucket[t.bucket] = byBucket[t.bucket] || []).push(t);
    });
    grid.innerHTML = D.topics.map(function (t) {
      return '<div class="card topic-card" data-name="' + esc(t.name) + '">' +
        '<h3 class="tname">' + esc(t.name) + "</h3>" +
        '<div class="tmeta">' + esc(t.bucket) + " · " + t.count + " 份報告 · 最近 " + t.latest + "</div>" +
        '<div class="co-reports"><ol>' + t.reports.slice(0, 40).map(function (r) {
          return "<li><span class='d'>" + r.date + "</span>" +
            "<span class='t'>" + esc(r.type) + "</span>" +
            '<a href="' + reportLink(r) + '">' + esc(r.title) + "</a></li>";
        }).join("") + "</ol></div>" +
        "</div>";
    }).join("");
    grid.querySelectorAll(".topic-card").forEach(function (card) {
      card.addEventListener("click", function () { card.classList.toggle("open"); });
    });
  }

  /* ---------- 實盤：年度收益分組長條圖（SVG，經 CVD 驗證色板） ---------- */
  function renderReturnsChart() {
    var wrap = document.getElementById("returns-chart");
    if (!wrap) return;
    var td = D.trackrecord;
    var W = Math.min(wrap.clientWidth || 660, 660);
    var H = 300;
    var padL = 46, padR = 16, padT = 18, padB = 34;
    var maxV = Math.max.apply(null, td.returns.map(function (s) {
      return Math.max.apply(null, s.values);
    })) * 1.12;

    var g = Math.max(0, W - padL - padR);
    var ph = H - padT - padB;
    var groupW = g / td.years.length;
    var n = td.returns.length;
    var gap = 2;                          // 相鄰長條 2px 表面間隙
    var bw = Math.min(46, (groupW - 40) / n);
    var step = bw + gap;
    var x0 = (groupW - (step * n - gap)) / 2;

    var svg = '<svg viewBox="0 0 ' + W + " " + H + '" role="img" ' +
      'aria-label="2024 與 2025 年度收益對比長條圖（數據見下方表格）">';
    // 網格與 y 軸（退居次要）
    for (var v = 0; v <= 70; v += 10) {
      var y = padT + ph - (v / maxV) * ph;
      svg += '<line x1="' + padL + '" y1="' + y + '" x2="' + (W - padR) + '" y2="' + y +
        '" stroke="var(--gridline)" stroke-width="1"/>';
      svg += '<text x="' + (padL - 8) + '" y="' + (y + 4) + '" text-anchor="end" ' +
        'fill="var(--text-muted)" font-size="11">' + v + "%</text>";
    }
    // 基線
    svg += '<line x1="' + padL + '" y1="' + (padT + ph) + '" x2="' + (W - padR) +
      '" y2="' + (padT + ph) + '" stroke="var(--baseline)" stroke-width="1"/>';

    var seriesOrder = td.returns.map(function (_, i) { return i; });
    td.years.forEach(function (yr, yi) {
      var cx = padL + yi * groupW;
      td.returns.forEach(function (s, si) {
        var val = s.values[yi];
        var h = (val / maxV) * ph;
        var x = cx + x0 + si * step;
        var y = padT + ph - h;
        var color = "var(--series-" + (si + 1) + ")";
        var label = si === 0  // 只對本框架實盤直接標值
          ? '<text x="' + (x + bw / 2) + '" y="' + (y - 6) + '" text-anchor="middle" ' +
            'fill="var(--text-primary)" font-size="11.5" font-weight="600">' +
            val.toFixed(1) + "%</text>"
          : "";
        svg += label +
          '<rect class="bar" x="' + x + '" y="' + y + '" width="' + bw +
          '" height="' + Math.max(h, 0) + '" rx="4" ry="4" fill="' + color + '"' +
          (h < 8 ? ' clip-path="inset(0 0 ' + (8 - h) + 'px 0)"' : "") +
          ' data-tip="' + s.name + " " + yr + "：" + val.toFixed(2) + '%"/>' +
          '<rect class="bar-hit" x="' + x + '" y="' + (y - 8) + '" width="' + bw +
          '" height="' + (h + 8) + '" data-tip="' + s.name + " " + yr + "：" + val.toFixed(2) + '%"/>';
      });
      svg += '<text x="' + (cx + groupW / 2) + '" y="' + (H - 10) + '" text-anchor="middle" ' +
        'fill="var(--text-secondary)" font-size="12.5">' + yr + "</text>";
    });
    svg += "</svg>";

    var tip = document.createElement("div");
    tip.className = "tooltip";
    document.body.appendChild(tip);
    wrap.innerHTML = svg;
    wrap.querySelectorAll(".bar-hit").forEach(function (el) {
      el.addEventListener("mousemove", function (e) {
        tip.textContent = el.getAttribute("data-tip");
        tip.style.opacity = "1";
        tip.style.left = (e.pageX + 12) + "px";
        tip.style.top = (e.pageY - 30) + "px";
      });
      el.addEventListener("mouseleave", function () { tip.style.opacity = "0"; });
    });
  }

  /* ---------- 實盤：持倉 ---------- */
  function renderPortfolio() {
    var box = document.getElementById("holdings-bars");
    if (!box) return;
    var p = D.portfolio;
    var maxW = Math.max.apply(null, p.holdings.map(function (h) { return h.weight; }));
    // 順序色階（藍 100→700）：以權重排序顯示
    var seq = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec"];
    var sorted = p.holdings.slice().sort(function (a, b) { return b.weight - a.weight; });
    box.innerHTML = sorted.map(function (h, i) {
      var w = Math.round(h.weight / maxW * 100);
      return '<div class="hbar-row">' +
        '<span class="hname">' + esc(h.name) + "</span>" +
        '<div class="track"><div class="fill" style="width:' + w + "%;background:" + seq[i] +
        " aria-hidden=\"true\"></div></div>" +
        '<span class="hval">' + h.weight + "% · " +
        (h.pnl >= 0 ? '<span class="pnl-up">+' : '<span class="pnl-down">') +
        h.pnl.toFixed(1) + "%</span></span>" +
        "</div>";
    }).join("");
  }

  /* ---------- 啟動 ---------- */
  document.addEventListener("DOMContentLoaded", function () {
    initThemeToggle();
    var page = document.body.getAttribute("data-page");
    if (page === "home") renderHome();
    if (page === "companies") { initCompanies(); initTopics(); }
    if (page === "reports") initReports();
    if (page === "trackrecord") { renderReturnsChart(); renderPortfolio(); }
  });
  window.renderReturnsChart = renderReturnsChart;  // 主題切換時重繪
})();
