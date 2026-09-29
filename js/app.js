/* AIShan+ 投研網站 — 共用邏輯 */
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
      if (window.renderTrackRecord) window.renderTrackRecord();
    });
  }

  /* ---------- 工具 ---------- */
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  /* 簡→繁 兼容：頁面 chip 用繁體，數據用簡體，比較前統一轉簡體 */
  var SIMP_MAP = {
    "專": "专", "題": "题", "師": "师", "篩": "筛", "選": "选", "財": "财",
    "報": "报", "倉": "仓", "橫": "横", "對": "对", "組": "组", "織": "织",
    "眾": "众", "號": "号", "層": "层", "觀": "观", "價": "价", "團": "团"
  };
  function simp(s) {
    return String(s == null ? "" : s).replace(/[專題師篩選財報倉橫對組織眾號層觀價團]/g, function (ch) {
      return SIMP_MAP[ch] || ch;
    });
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

  function stockLink(c) {
    return c.page || ("stocks/" + encodeURIComponent(c.name) + ".html");
  }

  /* 資產類別統一色板：所有棒形圖按類別取色，同一類別全站同色 */
  var FUND_COLORS = {
    "股票": "#3b89e3", "債券": "#8a6fd1", "不動產": "#2e9e6b",
    "另類": "#c25ec0", "商品": "#e08c3a", "黃金": "#d9a514", "現金": "#98a2b3",
  };
  /* 行業統一色板：公司組合／持倉棒形圖按行業取色 */
  var SECTOR_COLORS = {
    "科技": "#3b89e3", "互聯網": "#17b2a0", "金融": "#8a6fd1", "消費": "#e08c3a",
    "材料": "#c2543a", "醫藥": "#2e9e6b", "能源": "#5a6b8c", "債券": "#a58fd1",
    "工業": "#6c7a89", "汽車": "#d95f8c", "公用事業": "#d9a514", "房地產": "#b07a3a",
  };
  function sectorColor(s) {
    return SECTOR_COLORS[s] || "#98a2b3";
  }

  /* ---------- 首頁 ---------- */
  function renderHome() {
    var hs = document.getElementById("hero-stats");
    if (hs && D.stats) {
      var nums = hs.querySelectorAll(".num");
      if (nums[0]) nums[0].textContent = D.stats.reports.toLocaleString();
      if (nums[1]) nums[1].textContent = D.stats.companies.toLocaleString();
      if (nums[2]) nums[2].textContent = D.stats.topics.toLocaleString();
    }
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

    renderMarket();
    renderHomeAlloc();
    renderScoreDist();
  }

  /* ---------- 首頁：市場總覽（指數報價條＋近 5 日走勢線） ---------- */
  function sparklineSVG(vals, up) {
    if (!vals || vals.length < 2) return "";
    var W = 64, H = 22, P = 2;
    var mn = Math.min.apply(null, vals);
    var mx = Math.max.apply(null, vals);
    var rng = mx - mn || 1;
    var pts = vals.map(function (v, i) {
      var x = P + i * (W - 2 * P) / (vals.length - 1);
      var y = H - P - (v - mn) / rng * (H - 2 * P);
      return x.toFixed(1) + "," + y.toFixed(1);
    });
    return '<svg class="spark" viewBox="0 0 ' + W + " " + H + '" aria-hidden="true">' +
      '<polyline points="' + pts.join(" ") + '" fill="none" stroke="' +
      (up ? "var(--good)" : "var(--crit)") +
      '" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/></svg>';
  }

  function renderMarket() {
    var strip = document.getElementById("market-strip");
    if (!strip || !D.indices) return;
    strip.innerHTML = D.indices.map(function (it) {
      var q = D.market[it.sym];
      if (!q) return "";
      var up = q.change_pct >= 0;
      return '<div class="ticker-card">' +
        '<div class="tk-name">' + esc(it.label) + "</div>" +
        '<div class="tk-price">' + q.price.toLocaleString() + "</div>" +
        '<div class="tk-chg ' + (up ? "up" : "down") + '">' +
        (up ? "▲" : "▼") + Math.abs(q.change_pct).toFixed(2) + "%</div>" +
        sparklineSVG(q.closes, up) + "</div>";
    }).join("");
    var f = document.getElementById("market-asof");
    if (f && D.market_asof) f.textContent = "⏱ 行情更新於 " + D.market_asof;
  }

  /* ---------- 首頁：推薦配置組合 · 實時業績 ---------- */
  function renderHomeAlloc() {
    var A = D.allocation;
    var allocColors = {
      "股票": "#3b89e3", "國債": "#8a6fd1", "商品": "#e08c3a",
      "黃金": "#d9a514", "現金": "#98a2b3",
    };
    if (!A) {
      var fa = document.getElementById("home-alloc");
      if (fa) fa.innerHTML = '<div class="empty">資產配置資料暫不可用（建站時宏觀數據抓取失敗）</div>';
      return;
    }
    /* Hero 兩項：推薦配置中的股票與黃金權重 */
    var byCls = {};
    A.targets.forEach(function (t) { byCls[t.cls] = t; });
    var eq = document.getElementById("hero-alloc-equity");
    if (eq && byCls["股票"]) eq.textContent = byCls["股票"].pct + "%";
    var gd = document.getElementById("hero-alloc-gold");
    if (gd && byCls["黃金"]) gd.textContent = byCls["黃金"].pct + "%";

    /* 目標權重＋實時行情 */
    var box = document.getElementById("home-alloc");
    if (box) {
      var maxT = Math.max.apply(null, A.targets.map(function (t) { return t.pct; }));
      box.innerHTML = A.targets.map(function (t) {
        var w = Math.round(t.pct / maxT * 100);
        var q = D.market && D.market[t.proxy];
        var pr = q ? q.price.toLocaleString() : "—";
        var chg = q && q.change_pct != null ?
          '<span class="c ' + (q.change_pct >= 0 ? "up" : "down") + '">' +
          (q.change_pct >= 0 ? "▲ +" : "▼ ") + Math.abs(q.change_pct).toFixed(2) + "%</span>" : "";
        return '<div class="al-block">' +
          '<div class="al-line"><span class="al-name">' + esc(t.cls) + "</span>" +
          '<div class="track"><div class="fill" style="width:' + w + "%;background:" +
          (allocColors[t.cls] || "var(--sector-fill)") + '"></div></div>' +
          '<span class="al-val">' + t.pct + "%</span></div>" +
          '<div class="al-proxy">' + esc(t.proxy) + " · " + pr + " " + chg + "</div></div>";
      }).join("");
    }

    /* 組合加權當日表現 */
    var combo = document.getElementById("home-alloc-combo");
    if (combo) {
      var total = 0, weightSum = 0;
      A.targets.forEach(function (t) {
        var q = D.market && D.market[t.proxy];
        if (q && q.change_pct != null) { total += t.pct * q.change_pct; weightSum += t.pct; }
      });
      if (weightSum) {
        var v = total / weightSum;
        combo.textContent = (v >= 0 ? "+" : "") + v.toFixed(2) + "%";
        combo.className = "home-combo " + (v >= 0 ? "up" : "down");
      } else {
        combo.textContent = "—";
      }
    }
    /* 宏觀儀錶（精簡版） */
    var mg = document.getElementById("home-macro");
    if (mg) {
      mg.innerHTML = A.macro.map(function (m) {
        var w = Math.max(0, Math.min(100, m.score || 0));
        var chg = "";
        if (m.change != null && m.change !== 0) {
          var good = m.change > 0 ? m.up_good : !m.up_good;
          chg = ' <span class="m-change ' + (good ? "good" : "bad") + '">' +
            (m.change > 0 ? "▲+" : "▼") + Math.abs(m.change) + "</span>";
        }
        return '<div class="dist-row">' +
          '<span class="dist-label">' + esc(m.label) + chg + "</span>" +
          '<div class="track"><div class="fill" style="width:' + w + "%;background:" +
          macroColor(m.score, m.up_good) + '"></div></div>' +
          '<span class="dist-num">' + (m.score == null ? "—" : m.score) + "</span></div>";
      }).join("");
      var mn = document.getElementById("home-macro-note");
      if (mn) mn.textContent = "⏱ 更新於 " + A.asof + " · 完整邏輯見配置頁";
    }
  }

  /* ---------- 首頁：覆蓋公司評分分佈 ---------- */
  function renderScoreDist() {
    var box = document.getElementById("score-dist");
    if (!box) return;
    var buckets = [
      { label: "4★ 及以上", min: 4, color: "var(--good)" },
      { label: "3 ~ 4★", min: 3, color: "var(--s3)" },
      { label: "3★ 以下", min: 0, color: "var(--warn)" },
      { label: "未評分", min: null, color: "var(--text-muted)" },
    ];
    var counts = [0, 0, 0, 0];
    D.companies.forEach(function (c) {
      if (!c.score) counts[3]++;
      else if (c.score.value >= 4) counts[0]++;
      else if (c.score.value >= 3) counts[1]++;
      else counts[2]++;
    });
    var total = D.companies.length || 1;
    box.innerHTML = buckets.map(function (b, i) {
      var w = Math.round(counts[i] / total * 100);
      return '<div class="dist-row">' +
        '<span class="dist-label">' + b.label + "</span>" +
        '<div class="track"><div class="fill" style="width:' + w + "%;background:" + b.color +
        '"></div></div>' +
        '<span class="dist-num">' + counts[i] + " 家</span></div>";
    }).join("");
    var v = { positive: 0, neutral: 0, negative: 0 };
    D.companies.forEach(function (c) {
      if (c.verdict_class && v[c.verdict_class] != null) v[c.verdict_class]++;
    });
    box.innerHTML += '<div class="dist-verdict">結論分佈：✅ 通過 ' + v.positive +
      " 家 · ❓ 灰色地帶 " + v.neutral + " 家 · ❌ 不通過 " + v.negative + " 家</div>";
    var sect = D.sectors || [];
    if (sect.length) {
      var maxS = Math.max.apply(null, sect.map(function (s) { return s.count; }));
      box.innerHTML += '<div class="dist-sector-title">行業分佈（前 6）</div>' +
        sect.slice(0, 6).map(function (s) {
          var w2 = Math.round(s.count / maxS * 100);
          return '<div class="dist-row dist-sector"><span class="dist-label">' + esc(s.name) +
            "</span>" +
            '<div class="track"><div class="fill" style="width:' + w2 +
            "%;background:var(--sector-fill)\"></div></div>" +
            '<span class="dist-num">' + s.count + "</span></div>";
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
    var watched = getWatch().indexOf(c.name) >= 0;
    return '<div class="card co-card" data-name="' + esc(c.name) + '" tabindex="0">' +
      '<div class="co-top"><h3 class="co-name">' + esc(c.name) +
      '<span class="co-sector">' + esc(c.sector || "") + "</span></h3>" +
      priceCell(c) + "</div>" +
      '<div class="co-mid">' + score + verdictBadge(c) + "</div>" +
      sum +
      '<div class="co-foot"><span>📄 ' + c.count + " 份報告</span>" +
      "<span>🕐 " + (c.latest ? "最近 " + c.latest : "監測中（無研報）") + "</span></div>" +
      '<a class="co-stock-link" href="' + stockLink(c) + '">📈 個股分析 →</a>' +
      '<div class="co-actions">' +
        '<button class="watch-btn' + (watched ? " on" : "") + '" data-watch="' + esc(c.name) +
          '" aria-pressed="' + watched + '">' + (watched ? "⭐" : "☆") + " 關注</button>" +
        '<button class="cmp-btn" data-cmp="' + esc(c.name) + '">＋ 比較</button>' +
      "</div>" +
      '<div class="co-reports"><ol>' + reports + more + "</ol></div>" +
      "</div>";
  }

  /* ---------- 我的關注（localStorage） ---------- */
  function getWatch() {
    try { return JSON.parse(localStorage.getItem("aiberkshire-watch") || "[]"); }
    catch (e) { return []; }
  }
  function setWatch(list) {
    try { localStorage.setItem("aiberkshire-watch", JSON.stringify(list)); } catch (e) {}
  }

  function exchangeOf(c) {
    var t = c.ticker || "";
    if (/\.HK$/i.test(t)) return "hk";
    if (/\.(SS|SZ)$/i.test(t) || /^\d{6}\./.test(t)) return "cn";
    if (t && t.indexOf(".") === -1) return "us";
    return "other";
  }

  function initCompanies() {
    var grid = document.getElementById("co-grid");
    if (!grid) return;
    var q = document.getElementById("co-search");
    var sortSel = document.getElementById("co-sort");
    var counter = document.getElementById("co-count");
    var state = { filter: "all", q: "", min: 0, exch: "all", watch: false, sort: "score", sector: "all" };
    var cmpList = [];
    var sectorSel = document.getElementById("co-sector");
    if (sectorSel && D.sectors) {
      var opts = ["<option value='all'>全部行業</option>"];
      D.sectors.forEach(function (s) {
        opts.push("<option value='" + esc(s.name) + "'>" + esc(s.name) + " (" + s.count + ")</option>");
      });
      sectorSel.innerHTML = opts.join("");
    }

    function apply() {
      var list = D.companies.slice();
      var watch = getWatch();
      if (state.q) {
        // 忽略空格與間隔號：「space x」也能命中「SpaceX」、「台 積 電」命中「台積電」
        var s = state.q.toLowerCase().replace(/[\s·]+/g, "");
        list = list.filter(function (c) {
          return c.name.toLowerCase().replace(/[\s·]+/g, "").indexOf(s) >= 0 ||
            (c.ticker && c.ticker.toLowerCase().replace(/[\s·]+/g, "").indexOf(s) >= 0) ||
            (c.summary && c.summary.toLowerCase().replace(/[\s·]+/g, "").indexOf(s) >= 0);
        });
      }
      if (state.filter === "scored") list = list.filter(function (c) { return c.score; });
      if (state.filter === "positive") list = list.filter(function (c) { return c.verdict_class === "positive"; });
      if (state.filter === "neutral") list = list.filter(function (c) { return c.verdict_class === "neutral"; });
      if (state.filter === "negative") list = list.filter(function (c) { return c.verdict_class === "negative"; });
      if (state.min) list = list.filter(function (c) { return c.score && c.score.value >= state.min; });
      if (state.exch !== "all") list = list.filter(function (c) { return exchangeOf(c) === state.exch; });
      if (state.sector !== "all") list = list.filter(function (c) { return c.sector === state.sector; });
      if (state.watch) list = list.filter(function (c) { return watch.indexOf(c.name) >= 0; });
      list.sort(function (a, b) {
        if (state.sort === "latest") return a.latest < b.latest ? 1 : -1;
        if (state.sort === "count") return b.count - a.count;
        return (b.score ? b.score.value : -1) - (a.score ? a.score.value : -1);
      });
      if (counter) counter.textContent = list.length + " / " + D.companies.length + " 家";
      grid.innerHTML = list.length ? list.map(coCardHTML).join("") :
        '<div class="empty">沒有符合條件的公司</div>';
      grid.querySelectorAll(".cmp-btn").forEach(function (b) {
        var n = b.getAttribute("data-cmp");
        if (cmpList.indexOf(n) >= 0) {
          b.classList.add("on");
          b.textContent = "✓ 已加入";
        }
      });
    }

    grid.addEventListener("click", function (e) {
      var wBtn = e.target.closest(".watch-btn");
      if (wBtn) {
        var name = wBtn.getAttribute("data-watch");
        var watch = getWatch();
        var i = watch.indexOf(name);
        if (i >= 0) watch.splice(i, 1); else watch.push(name);
        setWatch(watch);
        apply();
        return;
      }
      var cBtn = e.target.closest(".cmp-btn");
      if (cBtn) {
        var n2 = cBtn.getAttribute("data-cmp");
        var j = cmpList.indexOf(n2);
        if (j >= 0) cmpList.splice(j, 1);
        else if (cmpList.length < 3) cmpList.push(n2);
        else { alert("最多同時比較 3 家公司"); return; }
        updateCmpBar();
        apply();
        return;
      }
      var card = e.target.closest(".co-card");
      if (card && !e.target.closest("a")) card.classList.toggle("open");
    });

    grid.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") {
        var card = e.target.closest(".co-card");
        if (card && !e.target.closest("button") && !e.target.closest("a")) {
          e.preventDefault(); card.classList.toggle("open");
        }
      }
    });

    /* ---------- 比較列與彈窗 ---------- */
    function updateCmpBar() {
      var bar = document.getElementById("cmp-bar");
      if (!bar) return;
      document.getElementById("cmp-n").textContent = cmpList.length;
      document.getElementById("cmp-chips").innerHTML = cmpList.map(function (name) {
        return '<span class="cmp-chip">' + esc(name) +
          '<button class="cmp-rm" data-rm="' + esc(name) + '" aria-label="移除">✕</button></span>';
      }).join("");
      bar.hidden = cmpList.length === 0;
    }

    function openCompare() {
      var modal = document.getElementById("cmp-modal");
      if (!modal) return;
      if (cmpList.length < 2) { alert("請先選至少 2 家公司"); return; }
      var cos = cmpList.map(function (name) {
        return D.companies.filter(function (c) { return c.name === name; })[0];
      });
      var rows = [
        ["評分", function (c) {
          return c.score ? stars(c.score.stars) + " " + c.score.value.toFixed(1) + " / 5" : "—";
        }],
        ["結論", function (c) { return verdictBadge(c) || "—"; }],
        ["代碼", function (c) { return esc(c.ticker || "—"); }],
        ["股價", function (c) {
          var q = c.ticker && D.market ? D.market[c.ticker] : null;
          if (!q) return "—";
          var up = q.change_pct >= 0;
          return esc(q.price.toLocaleString()) + ' <span class="c ' + (up ? "up" : "down") + '">' +
            (up ? "▲" : "▼") + Math.abs(q.change_pct).toFixed(2) + "%</span>";
        }],
        ["報告數", function (c) { return c.count + " 份"; }],
        ["最近更新", function (c) { return c.latest; }],
        ["摘要", function (c) { return c.summary ? esc(c.summary) : "—"; }],
      ];
      document.getElementById("cmp-table").innerHTML =
        "<thead><tr><th>指標</th>" +
        cos.map(function (c) { return "<th>" + esc(c.name) + "</th>"; }).join("") +
        "</tr></thead><tbody>" +
        rows.map(function (row) {
          return "<tr><td class='cmp-metric'>" + row[0] + "</td>" +
            cos.map(function (c) { return "<td>" + row[1](c) + "</td>"; }).join("") + "</tr>";
        }).join("") + "</tbody>";
      modal.hidden = false;
    }

    var barEl = document.getElementById("cmp-bar");
    if (barEl) {
      barEl.addEventListener("click", function (e) {
        var rm = e.target.closest(".cmp-rm");
        if (rm) {
          cmpList.splice(cmpList.indexOf(rm.getAttribute("data-rm")), 1);
          updateCmpBar(); apply();
        }
      });
      document.getElementById("cmp-clear").addEventListener("click", function () {
        cmpList = []; updateCmpBar(); apply();
      });
      document.getElementById("cmp-go").addEventListener("click", openCompare);
      document.getElementById("cmp-close").addEventListener("click", function () {
        document.getElementById("cmp-modal").hidden = true;
      });
      document.getElementById("cmp-modal").addEventListener("click", function (e) {
        if (e.target === this) this.hidden = true;
      });
      document.addEventListener("keydown", function (e) {
        if (e.key === "Escape" && document.getElementById("cmp-modal")) {
          document.getElementById("cmp-modal").hidden = true;
        }
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
    document.querySelectorAll("[data-exch]").forEach(function (chip) {
      chip.addEventListener("click", function () {
        document.querySelectorAll("[data-exch]").forEach(function (c) { c.classList.remove("on"); });
        chip.classList.add("on");
        state.exch = chip.getAttribute("data-exch");
        apply();
      });
    });
    document.querySelectorAll("[data-min]").forEach(function (chip) {
      chip.addEventListener("click", function () {
        document.querySelectorAll("[data-min]").forEach(function (c) { c.classList.remove("on"); });
        chip.classList.add("on");
        state.min = Number(chip.getAttribute("data-min"));
        apply();
      });
    });
    document.querySelectorAll("[data-watch]").forEach(function (chip) {
      chip.addEventListener("click", function () {
        state.watch = !state.watch;
        chip.classList.toggle("on", state.watch);
        apply();
      });
    });
    if (sortSel) sortSel.addEventListener("change", function () {
      state.sort = sortSel.value;
      apply();
    });
    if (sectorSel) sectorSel.addEventListener("change", function () {
      state.sector = sectorSel.value;
      apply();
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

    /* 每個類型／分類 chip 標註報告數 */
    var typeCnt = {}, bucketCnt = {};
    all.forEach(function (x) {
      typeCnt[x.r.type] = (typeCnt[x.r.type] || 0) + 1;
      bucketCnt[x.b] = (bucketCnt[x.b] || 0) + 1;
    });
    document.querySelectorAll("[data-type]").forEach(function (chip) {
      var v = chip.getAttribute("data-type");
      var n = v === "all" ? all.length : typeCnt[v] || typeCnt[simp(v)] || 0;
      chip.textContent += " · " + n;
    });
    document.querySelectorAll("[data-bucket]").forEach(function (chip) {
      var v = chip.getAttribute("data-bucket");
      var n = v === "all" ? all.length : bucketCnt[v] || bucketCnt[simp(v)] || 0;
      chip.textContent += " · " + n;
    });

    function apply() {
      var s = state.q.toLowerCase();
      var items = all.filter(function (x) {
        if (state.type !== "all" && simp(x.r.type) !== simp(state.type)) return false;
        if (state.bucket !== "all" && simp(x.b) !== simp(state.bucket)) return false;
        if (s && (x.r.title.toLowerCase().indexOf(s) < 0 &&
            x.g.toLowerCase().indexOf(s) < 0 &&
            simp(x.r.title).toLowerCase().indexOf(s) < 0 &&
            simp(x.g).toLowerCase().indexOf(s) < 0)) return false;
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

  /* ---------- 組合頁：選定公司組合（當前持倉） ---------- */
  function selectedCombo() {
    var pos = D.companies.filter(function (c) {
      return c.verdict_class === "positive" && c.score && c.score.value != null;
    }).sort(function (a, b) { return b.score.value - a.score.value; });
    var combo = pos.slice(0, 8);
    var tot = 0;
    combo.forEach(function (c) { tot += c.score.value; });
    combo.forEach(function (c) { c._w = c.score.value / tot; });
    return combo;
  }

  function renderSelectedCombo() {
    var combo = selectedCombo();
    if (!combo.length) return;
    var tot = 0;
    combo.forEach(function (c) { tot += c.score.value; });
    var avg = tot / combo.length;
    var secs = {};
    combo.forEach(function (c) { secs[c.sector] = (secs[c.sector] || 0) + 1; });

    var st = document.getElementById("rec-combo-stats");
    if (st) {
      st.innerHTML = [
        ["組合公司數", combo.length + " 家"],
        ["平均評分", avg.toFixed(2) + " / 5"],
        ["覆蓋行業", Object.keys(secs).length + " 個"],
        ["最高評分", esc(combo[0].name) + " " + combo[0].score.value],
      ].map(function (kv) {
        return '<div class="mini-stat"><div class="num">' + kv[1] +
          '</div><div class="label">' + kv[0] + "</div></div>";
      }).join("");
    }
    var lg = document.getElementById("rec-combo-legend");
    if (lg) {
      lg.innerHTML = Object.keys(secs).map(function (s) {
        return '<span class="item"><span class="sw" style="background:' + sectorColor(s) +
          '"></span>' + esc(s) + "</span>";
      }).join("");
    }
    var box = document.getElementById("rec-combo");
    if (box) {
      box.innerHTML = combo.map(function (c) {
        var w = Math.round(c._w * 100);
        var r0 = c.reports && c.reports[0];
        var nm = r0 ? '<a class="cb-link" href="' + reportLink(r0) + '" target="_blank" rel="noopener">' +
          esc(c.name) + "</a>" : esc(c.name);
        return '<div class="cb-row">' +
          '<span class="cb-name">' + nm + "</span>" +
          '<div class="track"><div class="fill" style="width:' + w + "%;background:" +
          sectorColor(c.sector) + '" aria-hidden="true"></div></div>' +
          '<span class="cb-val">' + c.score.value + " 分 · " + (c._w * 100).toFixed(1) + "%</span>" +
          '<span class="cb-sector" style="color:' + sectorColor(c.sector) + '">' + esc(c.sector) + "</span></div>";
      }).join("") +
      '<p class="disclaimer">權重按評分歸一化（評分 ÷ 總分），僅作示意；投資決策請回看各公司研報結論。</p>';
    }
  }

  /* ---------- 組合頁：選定組合 vs 大盤指數 ---------- */
  function comboPerf() {
    var combo = selectedCombo();
    var wDay = 0, w5 = 0, sDay = 0, s5 = 0;
    combo.forEach(function (c) {
      var q = D.market[c.ticker];
      if (q && q.change_pct != null) { wDay += c._w * q.change_pct; sDay += c._w; }
      if (q && q.closes && q.closes.length >= 2) {
        var cs = q.closes;
        w5 += c._w * ((cs[cs.length - 1] / cs[0]) - 1) * 100;
        s5 += c._w;
      }
    });
    return { day: sDay ? wDay / sDay : null, five: s5 ? w5 / s5 : null };
  }

  function renderComboVsIndex() {
    var pf = comboPerf();
    var rows = [{ label: "選定組合", day: pf.day, five: pf.five }];
    ["^GSPC", "^IXIC", "^HSI", "000300.SS"].forEach(function (sym) {
      var q = D.market[sym];
      if (!q) return;
      var five = null;
      if (q.closes && q.closes.length >= 2) {
        var cs = q.closes;
        five = ((cs[cs.length - 1] / cs[0]) - 1) * 100;
      }
      var label = { "^GSPC": "標普500", "^IXIC": "納斯達克", "^HSI": "恒生指數", "000300.SS": "滬深300" }[sym];
      rows.push({ label: label, day: q.change_pct, five: five });
    });

    function bars(rows, key) {
      var vals = rows.map(function (r) { return r[key]; });
      var maxAbs = Math.max.apply(null, vals.map(function (v) { return Math.abs(v); }));
      return rows.map(function (r) {
        var v = r[key];
        if (v == null) return "";
        var w = Math.round(Math.abs(v) / maxAbs * 100);
        var up = v >= 0;
        return '<div class="vs-row">' +
          '<span class="vs-name">' + esc(r.label) + "</span>" +
          '<div class="track"><div class="fill" style="width:' + w + "%;background:" +
          (up ? "var(--good)" : "var(--crit)") + '" aria-hidden="true"></div></div>' +
          '<span class="vs-val ' + (up ? "up" : "down") + '">' + (up ? "+" : "") + v.toFixed(2) + "%</span></div>";
      }).join("");
    }
    var bd = document.getElementById("vs-day");
    if (bd) bd.innerHTML = bars(rows, "day");
    var b5 = document.getElementById("vs-5d");
    if (b5) b5.innerHTML = bars(rows, "five");
    var tb = document.getElementById("vs-table");
    if (tb) {
      tb.innerHTML = "<thead><tr><th>標的</th><th>今日漲跌</th><th>近 5 個交易日</th></tr></thead><tbody>" +
        rows.map(function (r) {
          return "<tr><td>" + esc(r.label) + "</td><td>" + fmtPct(r.day) + "</td><td>" +
            fmtPct(r.five) + "</td></tr>";
        }).join("") + "</tbody>";
    }
    var asof = document.getElementById("vs-asof");
    if (asof && D.market_asof) asof.textContent = "⏱ 行情更新於 " + D.market_asof;
  }

  /* ---------- 組合頁：前五大對沖基金配置動態 ---------- */
  var HF_COLORS = {
    "科技": "#3b89e3", "金融": "#8a6fd1", "醫療": "#2e9e6b", "工業": "#6c7a89",
    "消費": "#e08c3a", "材料": "#c2543a", "通訊": "#17b2a0", "能源": "#5a6b8c",
    "指數ETF": "#98a2b3", "其他": "#b0b8c4",
  };
  function hedgeFundCardHTML(f) {
    var maxP = 1;
    f.alloc.forEach(function (a) { if (a.pct > maxP) maxP = a.pct; });
    var rows = f.alloc.length ? f.alloc.map(function (a) {
      var w = Math.round(a.pct / maxP * 100);
      var dlt = a.delta != null ?
        '<span class="f-delta' + (a.delta.indexOf("↓") !== -1 || a.delta.indexOf("減") !== -1 ? " down" : "") + '">' +
        esc(a.delta) + "</span>" : "";
      return '<div class="f-row">' +
        '<span class="f-cls">' + esc(a.cls) + "</span>" +
        '<div class="track"><div class="fill" style="width:' + w + "%;background:" +
        (HF_COLORS[a.cls] || "#98a2b3") + '" aria-hidden="true"></div></div>' +
        '<span class="f-val">' + a.pct + "%</span>" + dlt + "</div>" +
        (a.sub ? '<div class="f-sub">' + esc(a.sub) + "</div>" : "");
    }).join("") :
      '<div class="empty" style="padding:14px 0;">13F 美股多頭規模過小，行業配置不具代表性（見備註）</div>';
    var tops = f.tops && f.tops.length ?
      '<div class="fund-note">重倉：' + esc(f.tops.join(" · ")) + "</div>" : "";
    return '<div class="card fund-card">' +
      '<div class="fund-head"><span class="fund-rank">' + f.rank + "</span>" +
      '<div class="fund-title"><h3>' + esc(f.name) + "</h3>" +
      '<div class="fund-meta">' + esc(f.mgr) + " · " + esc(f.country) + " · " +
      esc(f.aum) + " · 截至 " + esc(f.asof) + "</div></div></div>" +
      rows + tops +
      '<div class="fund-note">' + esc(f.note) + ' · 來源：' + esc(f.source) + "</div></div>";
  }

  function renderHedgeFunds() {
    var host = document.getElementById("hedge-list");
    if (!host || !D.hedgefunds || !D.hedgefunds.length) return;
    var lg = document.getElementById("hedge-legend");
    if (lg) {
      lg.innerHTML = Object.keys(HF_COLORS).map(function (k) {
        return '<span class="item"><span class="sw" style="background:' + HF_COLORS[k] +
          '"></span>' + k + "</span>";
      }).join("");
    }
    host.innerHTML = D.hedgefunds.map(hedgeFundCardHTML).join("");
  }

  /* ---------- 模組 12：家族辦公室／捐贈基金／養老基金 ---------- */
  function fundGroupCard(f, i) {
    var maxP = 1;
    (f.alloc || []).forEach(function (a) { if (a.pct > maxP) maxP = a.pct; });
    var rows = (f.alloc || []).length ? f.alloc.map(function (a) {
      var w = Math.round(a.pct / maxP * 100);
      return '<div class="f-row">' +
        '<span class="f-cls">' + esc(a.cls) + "</span>" +
        '<div class="track"><div class="fill" style="width:' + w + "%;background:" +
        (HF_COLORS[a.cls] || "#98a2b3") + '" aria-hidden="true"></div></div>' +
        '<span class="f-val">' + a.pct + "%</span></div>" +
        (a.sub ? '<div class="f-sub">' + esc(a.sub) + "</div>" : "");
    }).join("") : '<div class="empty" style="padding:14px 0;">未披露行業配置（見備註）</div>';
    var tops = f.tops && f.tops.length ?
      '<div class="fund-note">重倉：' + esc(f.tops.join(" · ")) + "</div>" : "";
    return '<div class="card fund-card">' +
      '<div class="fund-head"><span class="fund-rank">' + (i + 1) + "</span>" +
      '<div class="fund-title"><h3>' + esc(f.name) + "</h3>" +
      '<div class="fund-meta">' + esc(f.mgr) + " · " + esc(f.country) + " · " +
      esc(f.aum) + " · 截至 " + esc(f.asof) + "</div></div></div>" +
      rows + tops +
      '<div class="fund-note">' + esc(f.note) + ' · 來源：' + esc(f.source) + "</div></div>";
  }

  function renderFundGroup(hostId, list) {
    var host = document.getElementById(hostId);
    if (!host || !list || !list.length) return;
    host.innerHTML = list.map(fundGroupCard).join("");
  }

  /* ---------- 13F 頂級基金追蹤頁（模組 6） ---------- */
  function renderF13F() {
    if (document.body.getAttribute("data-page") !== "funds") return;
    renderHedgeFunds();
    renderFundGroup("familyoffice-list", D.familyoffices);
    renderFundGroup("endowment-list", D.endowments);
    renderFundGroup("pension-list", D.pensions);
    renderF13FCalendar();
    renderFundHeat();
  }

  function renderF13FCalendar() {
    var host = document.getElementById("f13f-cal");
    var nextEl = document.getElementById("f13f-next");
    if (!host || !D.f13f) return;
    var next = null;
    D.f13f.forEach(function (r) { if (r.status === "next") next = r; });
    if (nextEl && next) {
      nextEl.textContent = "下一次申報截止：" + next.deadline + "（" +
        (next.days_left <= 0 ? "今日截止" : "還有 " + next.days_left + " 天") + "）";
    }
    host.innerHTML = '<table class="s-table"><thead><tr>' +
      "<th>季度</th><th>季末</th><th>申報截止</th><th>狀態</th></tr></thead><tbody>" +
      D.f13f.map(function (r) {
        var st = r.status === "past" ? '<span class="s-chip off">已截止</span>'
          : r.status === "next" ? '<span class="s-chip on">下一次</span>'
          : '<span class="s-chip off">未來</span>';
        var d = r.days_left <= 0 ? "—" : (r.days_left + " 天後");
        return "<tr" + (r.status === "next" ? ' style="background:var(--brand-tint);"' : "") + ">" +
          "<td>" + esc(r.quarter) + "</td><td>" + esc(r.period_end) + "</td><td>" +
          esc(r.deadline) + "</td><td>" + st + " " + d + "</td></tr>";
      }).join("") + "</tbody></table>" +
      '<p class="s-note">SEC 規則：管理超 1 億美元美股資產的機構須於季末後 45 天內申報 13F（慣例截止日如上）。僅美股多頭；空頭、衍生品與非美資產不披露。13D/G 大股東變動則須 10 天內申報。</p>';
  }

  function renderFundHeat() {
    var host = document.getElementById("fund-heat");
    if (!host || !D.fund_holdings || !D.companies) return;
    var agg = {};
    (D.companies || []).forEach(function (c) {
      var ms = D.fund_holdings[c.ticker];
      if (ms && ms.length) {
        var funds = {};
        ms.forEach(function (m) { funds[m.fund] = true; });
        agg[c.ticker] = { c: c, n: Object.keys(funds).length, funds: Object.keys(funds) };
      }
    });
    var rows = Object.keys(agg).map(function (k) { return agg[k]; })
      .sort(function (a, b) { return b.n - a.n || (a.c.name < b.c.name ? -1 : 1); });
    if (!rows.length) {
      host.innerHTML = "<p>暫無匹配（基金披露文本與本站覆蓋公司無交集）。</p>";
      return;
    }
    host.innerHTML = rows.slice(0, 15).map(function (r) {
      return '<div class="f-row">' +
        '<a class="f-cls" href="' + stockLink(r.c) + '">' + esc(r.c.name) +
        " · " + esc(r.c.ticker) + "</a>" +
        '<span class="f-sub">' + r.funds.map(function (fn) {
          return '<span class="s-chip on">' + esc(fn) + "</span>";
        }).join(" ") + "</span></div>";
    }).join("") +
      (rows.length > 15 ? '<p class="s-note">… 另有 ' + (rows.length - 15) + " 家公司在各基金披露中被提及（詳見個股頁「頂級基金持倉」）。</p>" : "");
  }

  /* ---------- 政要交易追蹤頁（模組 7） ---------- */
  function renderPolitician() {
    if (document.body.getAttribute("data-page") !== "politician") return;
    renderPolitRules();
    renderPolitDisclosures();
    renderPolitCongress();
  }

  function renderPolitRules() {
    var host = document.getElementById("pol-rules");
    if (!host) return;
    var dl = new Date(Date.now() + 45 * 86400000);
    var dstr = dl.getFullYear() + "-" + String(dl.getMonth() + 1).padStart(2, "0") + "-" +
      String(dl.getDate()).padStart(2, "0");
    host.innerHTML = '<div class="s-grid2" style="gap:12px;">' +
      '<div class="s-kv"><span class="s-n">國會議員（STOCK Act）</span><span class="s-v">交易後 45 天內申報</span></div>' +
      '<div class="s-kv"><span class="s-n">申報門檻</span><span class="s-v">單筆 &gt; 1,000 美元</span></div>' +
      '<div class="s-kv"><span class="s-n">披露精度</span><span class="s-v">僅金額區間（如 100–500 萬）</span></div>' +
      '<div class="s-kv"><span class="s-n">逾期申報罰款</span><span class="s-v">標準 200 美元／次</span></div>' +
      '<div class="s-kv"><span class="s-n">若今日交易</span><span class="s-v">最遲申報日：' + dstr + '</span></div>' +
      '<div class="s-kv"><span class="s-n">總統／高官</span><span class="s-v">OGE 年度／季度申報；總統豁免利益衝突禁令</span></div>' +
      "</div>" +
      '<p class="s-note">STOCK Act（2012）：議員及其配偶、受扶養子女的交易須在知悉後 30 天內、且不晚於交易後 45 天申報，由眾院書記官與參院秘書對外公開。法律並不禁止議員炒股——公開披露是主要監督機制。</p>';
  }

  function renderPolitDisclosures() {
    var host = document.getElementById("pol-disclosures");
    var P = D.politician;
    if (!host || !P || !P.disclosures) return;
    host.innerHTML = P.disclosures.map(function (p) {
      var items = function (side, icon) {
        return (p[side] || []).map(function (it) {
          var nm = it.page
            ? '<a href="' + esc(it.page) + '">' + esc(it.name) +
              (it.ticker ? " (" + esc(it.ticker) + ")" : "") + "</a>"
            : esc(it.name) + (it.ticker ? " (" + esc(it.ticker) + ")" : "");
          return "<li>" + nm + (it.range ? ' <span class="s-n">' + esc(it.range) + "</span>" : "") + "</li>";
        }).join("");
      };
      return '<div class="card" style="margin-top:12px;">' +
        '<div class="fund-head"><div class="fund-title"><h3>🪑 ' + esc(p.person) + "</h3>" +
        '<div class="fund-meta">' + esc(p.role) + " · " + esc(p.period) + " · " +
        esc(p.disclosed) + " · " + esc(p.stats) + "</div></div></div>" +
        '<div class="s-bullbear" style="gap:14px;margin-top:8px;">' +
        '<div><h4 class="s-h3" style="color:var(--good);">🟢 買入／增持</h4><ul class="s-reports">' +
        items("buys") + "</ul></div>" +
        '<div><h4 class="s-h3" style="color:var(--crit);">🔴 賣出／減持</h4><ul class="s-reports">' +
        items("sells") + "</ul></div></div>" +
        (p.note ? '<div class="fund-note">' + esc(p.note) + "</div>" : "") +
        '<div class="fund-note">來源：' + esc(p.source) + "</div></div>";
    }).join("");
  }

  function renderPolitCongress() {
    var host = document.getElementById("pol-congress");
    var P = D.politician;
    if (!host || !P || !P.congress) return;
    var C = P.congress;
    var table = function (rows, isDetail) {
      return '<table class="s-table"><thead><tr><th>人物</th><th>黨派</th>' +
        (isDetail ? "<th>內容</th>" : "<th>買入區間</th>") + "</tr></thead><tbody>" +
        rows.map(function (r) {
          return "<tr><td>" + esc(r.name) + "</td><td>" + esc(r.party) + "</td><td>" +
            esc(r.detail != null ? r.detail : r.range) + "</td></tr>";
        }).join("") + "</tbody></table>";
    };
    host.innerHTML =
      '<div class="card" style="margin-top:12px;"><h3>🚀 ' + esc(C.spacex.title) + "</h3>" +
      '<p class="s-note" style="margin:6px 0;">' + esc(C.spacex.note) + "</p>" +
      table(C.spacex.rows, false) +
      '<p class="s-note">來源：' + esc(C.spacex.source) + "</p></div>" +
      '<div class="card" style="margin-top:12px;"><h3>⚠️ ' + esc(C.violations.title) + "</h3>" +
      '<p class="s-note" style="margin:6px 0;">' + esc(C.violations.note) + "</p>" +
      table(C.violations.rows, true) +
      '<p class="s-note">來源：' + esc(C.violations.source) + "</p></div>" +
      '<div class="card" style="margin-top:12px;"><h3>🔎 ' + esc(C.overlap.title) + "</h3>" +
      '<p class="s-note" style="margin:6px 0;">' + esc(C.overlap.note) + "</p>" +
      table(C.overlap.rows, true) +
      '<p class="s-note">來源：' + esc(C.overlap.source) + "</p></div>";
  }

  /* ---------- 中國資產專區（模組 8） ---------- */
  function renderChina() {
    if (document.body.getAttribute("data-page") !== "china") return;
    renderChinaMacro();
    renderChinaIndices();
    renderChinaTimeline();
    renderChinaStocks();
  }

  function renderChinaMacro() {
    var host = document.getElementById("cn-macro");
    var C = D.china;
    if (!host || !C) return;
    var M = C.macro;
    var pmi = M.pmi.map(function (p) {
      var up = p.v >= 50;
      return '<span class="s-chip ' + (up ? "on" : "down") + '">' + esc(p.m) + " " +
        p.v.toFixed(1) + "</span>";
    }).join(" ");
    host.innerHTML = '<div class="s-grid2" style="gap:12px;">' +
      '<div class="s-kv"><span class="s-n">LPR 1 年期</span><span class="s-v">' +
      M.lpr_1y.toFixed(1) + '%</span></div>' +
      '<div class="s-kv"><span class="s-n">LPR 5 年期以上</span><span class="s-v">' +
      M.lpr_5y.toFixed(1) + '%</span></div>' +
      '<div class="s-kv"><span class="s-n">上半年 GDP 同比</span><span class="s-v">+' +
      M.gdp_h1.toFixed(1) + '%</span><span class="s-n">Q1 ' + M.gdp_q1.toFixed(1) +
      "% · Q2 " + M.gdp_q2.toFixed(1) + "% · " + esc(M.gdp_target) + "</span></div>" +
      '<div class="s-kv"><span class="s-n">製造業 PMI（近 3 個月）</span><span class="s-v">' +
      pmi + "</span></div></div>" +
      '<p class="s-note">' + esc(M.lpr_note) + "；" + esc(M.gdp_note) + "；" +
      esc(M.pmi_note) + "。來源：" + esc(M.source) + "</p>";
  }

  function renderChinaIndices() {
    var host = document.getElementById("cn-indices");
    var C = D.china;
    if (!host || !C) return;
    host.innerHTML = C.indices.map(function (ix) {
      var up = ix.chg >= 0;
      return '<div class="card" style="margin:0;"><div class="fund-head">' +
        '<div class="fund-title"><h3>' + esc(ix.name) + " · " + esc(ix.ticker) + "</h3>" +
        '<div class="fund-meta">截至 ' + esc(ix.asof) + " · " + esc(ix.note) + "</div></div>" +
        '<span class="s-v" style="font-size:22px;color:' + (up ? "var(--good)" : "var(--crit)") +
        ';">' + ix.price.toLocaleString() + "</span></div>" +
        '<div class="f-row" style="margin-top:8px;">' +
        '<span class="f-cls">當日</span>' +
        '<span class="f-val" style="color:' + (up ? "var(--good)" : "var(--crit)") + ';">' +
        (up ? "+" : "") + ix.chg.toLocaleString() + "</span>" +
        '<span class="f-cls">今年以來</span>' +
        '<span class="f-val" style="color:' + (ix.ytd >= 0 ? "var(--good)" : "var(--crit)") +
        ';">' + (ix.ytd >= 0 ? "+" : "") + ix.ytd.toFixed(2) + "%</span></div></div>";
    }).join("");
  }

  function renderChinaTimeline() {
    var host = document.getElementById("cn-timeline");
    var C = D.china;
    if (!host || !C) return;
    host.innerHTML = C.timeline.map(function (ev) {
      return '<div class="f-row" style="display:flex;align-items:flex-start;gap:10px;margin:10px 0;">' +
        '<span class="s-chip on">' + esc(ev.date) + "</span>" +
        '<div><strong>' + esc(ev.title) + "</strong>" +
        '<div class="s-n">' + esc(ev.detail) + "</div></div></div>";
    }).join("");
  }

  function renderChinaStocks() {
    var host = document.getElementById("cn-stocks");
    var C = D.china;
    if (!host || !C) return;
    var S = C.stocks;
    if (!S || !S.stats) { host.innerHTML = "<p>暫無數據。</p>"; return; }
    var link = function (r) {
      return '<a href="' + (r.page || ("stocks/" + encodeURIComponent(r.name) + ".html")) + '">' +
        esc(r.name) + "</a>";
    };
    var pct = function (v) {
      if (v == null) return "—";
      return '<span style="color:' + (v >= 0 ? "var(--good)" : "var(--crit)") + ';">' +
        (v >= 0 ? "+" : "") + v.toFixed(2) + "%</span>";
    };
    var rankTable = function (rows) {
      return '<table class="s-table"><thead><tr><th>公司</th><th>代碼</th><th>板塊</th>' +
        "<th>現價</th><th>漲跌幅</th></tr></thead><tbody>" +
        rows.map(function (r) {
          return "<tr><td>" + link(r) + "</td><td>" + esc(r.ticker) + "</td><td>" +
            esc(r.sector) + "</td><td>" + (r.price != null ? r.price : "—") +
            "</td><td>" + pct(r.change_pct) + "</td></tr>";
        }).join("") + "</tbody></table>";
    };
    var uscno = S.rows.filter(function (r) { return r.region === "中概股"; });
    var cap = S.cap_top.map(function (r) {
      var mc = r.mktcap >= 1e12 ? (r.mktcap / 1e12).toFixed(2) + " 萬億"
        : r.mktcap >= 1e8 ? (r.mktcap / 1e8).toFixed(0) + " 億" : r.mktcap;
      return "<tr><td>" + link(r) + "</td><td>" + esc(r.ticker) + "</td><td>" +
        esc(r.region) + "</td><td>" + mc + "</td></tr>";
    }).join("");
    var sectors = S.sectors.length ? '<table class="s-table"><thead><tr><th>行業</th>' +
      "<th>公司數</th><th>PE 中位數</th></tr></thead><tbody>" +
      S.sectors.map(function (s) {
        var col = s.pe_median < 15 ? "var(--good)" : s.pe_median <= 30 ? "var(--warn)" : "var(--crit)";
        return "<tr><td>" + esc(s.sector) + "</td><td>" + s.n + "</td><td style='color:" +
          col + ";'>" + s.pe_median.toFixed(1) + "×</td></tr>";
      }).join("") + "</tbody></table>" : "";
    host.innerHTML =
      '<p class="s-note">站內覆蓋 ' + S.stats.n + " 家中國相關公司：港股 " + S.stats.hk +
      " · A股 " + S.stats.a + " · 中概股 " + S.stats.uscno + "；有行情 " +
      S.stats.with_price + " 家" + (S.stats.pe_median != null ?
        "；PE 中位數 " + S.stats.pe_median.toFixed(1) + "×" : "") + "。</p>" +
      '<div class="s-bullbear" style="gap:16px;">' +
      '<div class="card" style="margin:0;"><h3 style="color:var(--good);">🟢 漲幅榜</h3>' +
      rankTable(S.gainers) + "</div>" +
      '<div class="card" style="margin:0;"><h3 style="color:var(--crit);">🔴 跌幅榜</h3>' +
      rankTable(S.losers) + "</div></div>" +
      '<div class="s-bullbear" style="gap:16px;margin-top:16px;">' +
      '<div class="card" style="margin:0;"><h3>🏆 市值前 10</h3><table class="s-table">' +
      "<thead><tr><th>公司</th><th>代碼</th><th>板塊</th><th>市值（美元）</th></tr></thead><tbody>" +
      cap + "</tbody></table></div>" +
      '<div class="card" style="margin:0;"><h3>🏭 行業估值（PE 中位數）</h3>' +
      (sectors || '<p class="s-note">行業樣本不足。</p>') + "</div></div>" +
      (uscno.length ? '<div class="card" style="margin-top:16px;"><h3>🌐 中概股（美股上市）</h3>' +
        rankTable(uscno) + "</div>" : "");
  }

  /* ---------- 歷史情景回測（模組 9） ---------- */
  function renderScenarios() {
    if (document.body.getAttribute("data-page") !== "scenarios") return;
    var host = document.getElementById("sc-list");
    var S = D.scenarios;
    if (!host || !S || !S.length) {
      if (host) host.innerHTML = "<p>歷史行情資料暫缺（建站時 20 年月線抓取失敗），請重新觸發更新。</p>";
      return;
    }
    var fmt = function (v) {
      return v == null ? "—" : (v >= 0 ? "+" : "") + v.toFixed(1) + "%";
    };
    var col = function (v) { return v == null ? "" : v >= 0 ? "var(--good)" : "var(--crit)"; };
    host.innerHTML = S.map(function (sc) {
      var assetRows = Object.keys(sc.assets).map(function (k) {
        var a = sc.assets[k];
        return "<tr><td>" + esc(k) + "（代理 ETF）</td>" +
          '<td style="color:' + col(a.ret) + ';">' + fmt(a.ret) + "</td>" +
          '<td style="color:' + col(a.maxdd) + ';">' + fmt(a.maxdd) + "</td>" +
          "<td>" + (a.recover_months != null ? a.recover_months + " 個月" : "—") + "</td></tr>";
      }).join("");
      var pair = function (v) { return v.map(function (x, i) { return [i, x]; }); };
      var chart = '<div class="s-bullbear" style="gap:14px;margin-top:10px;">' +
        '<div><h4 class="s-h3">建議配置組合</h4>' + fedLineSVG(pair(sc.pf_series), "#0e6b4f") + "</div>" +
        '<div><h4 class="s-h3">純股票（SPY）</h4>' + fedLineSVG(pair(sc.spy_series), "#3b89e3") + "</div></div>" +
        '<p class="s-note">縱軸為期初 100 的指數化價值（' + esc(sc.start) + " – " + esc(sc.end) +
        "，共 " + sc.n_months + " 個月，月頻、每月再平衡）。</p>";
      var pf = sc.pf || {}, spy = sc.spy || {};
      /* 模組 35：報酬歸因——各資產貢獻 ≈ 平均權重 × 區間報酬 */
      var attrRows = (sc.attr || []).map(function (a) {
        return "<tr><td>" + esc(a.label) + "（" + esc(a.sym) + "）</td>" +
          '<td style="font-variant-numeric:tabular-nums;">' + a.w + "%</td>" +
          '<td style="color:' + col(a.ret) + ';">' + fmt(a.ret) + "</td>" +
          '<td style="color:' + col(a.contrib) + ';">' + fmt(a.contrib) + "</td></tr>";
      }).join("");
      var attrTable = (sc.attr && sc.attr.length
        ? '<h4 class="s-h3" style="margin-top:14px;">🔍 報酬歸因（近似：平均權重 × 資產區間報酬）</h4>' +
          '<table class="s-table"><thead><tr><th>資產</th><th>平均權重</th><th>區間報酬</th>' +
          "<th>貢獻</th></tr></thead><tbody>" + attrRows + "</tbody></table>" +
          (sc.excess != null
            ? '<p class="s-note">組合相對 SPY：<b style="color:' +
              (sc.excess >= 0 ? "var(--good)" : "var(--crit)") + ';">' +
              (sc.excess >= 0 ? "+" : "") + sc.excess + "%</b>（組合 " + fmt(pf.ret) +
              " vs SPY " + fmt(spy.ret) + "；月頻再平衡下各資產貢獻之和 ≈ 組合報酬）</p>"
            : "")
        : "");
      return '<div class="card" style="margin-top:12px;">' +
        "<h3>" + sc.emoji + " " + esc(sc.title) + ' <span class="s-chip off">' +
        esc(sc.start) + " – " + esc(sc.end) + "</span></h3>" +
        '<p class="s-note" style="margin:6px 0;">' + esc(sc.desc) + "</p>" +
        '<ul class="s-reports">' + sc.facts.map(function (f) {
          return "<li><span class='s-note'>" + esc(f) + "</span></li>";
        }).join("") + "</ul>" +
        '<table class="s-table"><thead><tr><th>組合／資產</th><th>區間報酬</th>' +
        "<th>最大回撤</th><th>回補期初所需月數</th></tr></thead><tbody>" +
        '<tr style="background:var(--brand-tint);"><td>🏗 建議配置組合（' +
        Object.keys(sc.weights).map(function (k) {
          return esc(k) + " " + sc.weights[k].toFixed(0) + "%";
        }).join("／") + "）</td>" +
        '<td style="color:' + col(pf.ret) + ';">' + fmt(pf.ret) + "</td>" +
        '<td style="color:' + col(pf.maxdd) + ';">' + fmt(pf.maxdd) + "</td>" +
        "<td>" + (pf.recover_months != null ? pf.recover_months + " 個月" : "—") + "</td></tr>" +
        '<tr><td>SPY（純股票對照）</td>' +
        '<td style="color:' + col(spy.ret) + ';">' + fmt(spy.ret) + "</td>" +
        '<td style="color:' + col(spy.maxdd) + ';">' + fmt(spy.maxdd) + "</td>" +
        "<td>" + (spy.recover_months != null ? spy.recover_months + " 個月" : "—") + "</td></tr>" +
        assetRows + "</tbody></table>" + chart + attrTable + "</div>";
    }).join("");
  }

  /* ---------- 組合頁：總渲染 ---------- */
  function renderTrackRecord() {
    if (document.body.getAttribute("data-page") !== "trackrecord") return;
    renderSelectedCombo();
    renderComboVsIndex();
    renderHedgeFunds();
  }

  /* ---------- 資產配置頁 ---------- */
  function fmtPct(v) {
    return v == null ? "—" : (v >= 0 ? "+" : "") + v.toFixed(1) + "%";
  }

  function macroColor(s, upGood) {
    if (s == null) return "var(--text-muted)";
    var v = upGood ? s : 100 - s;
    if (v >= 65) return "var(--good)";
    if (v >= 40) return "var(--warn)";
    return "var(--crit)";
  }

  function renderAllocation() {
    var A = D.allocation;
    if (!A) {
      var host = document.querySelector("main.container");
      if (host) {
        host.insertAdjacentHTML("afterbegin",
          '<div class="card" style="padding:16px;margin-top:16px;">' +
          "⚠️ 資產配置資料暫不可用（建站時宏觀數據抓取失敗）。</div>");
      }
      return;
    }
    var i;
    var asofEls = document.querySelectorAll("#alloc-asof, #macro-asof");
    for (i = 0; i < asofEls.length; i++) {
      asofEls[i].textContent = "⏱ 更新於 " + A.asof;
    }

    /* 宏觀儀錶板 */
    var mg = document.getElementById("alloc-macro");
    if (mg) {
      mg.innerHTML = A.macro.map(function (m) {
        var chg = "";
        if (m.change != null && m.change !== 0) {
          var good = m.change > 0 ? m.up_good : !m.up_good;
          chg = '<span class="m-change ' + (good ? "good" : "bad") + '">' +
            (m.change > 0 ? "▲ +" : "▼ ") + Math.abs(m.change) + "</span>";
        }
        var w = Math.max(0, Math.min(100, m.score || 0));
        return '<div class="card macro-card">' +
          '<div class="macro-head"><span class="macro-label">' + esc(m.label) + "</span>" +
          chg + "</div>" +
          '<div class="macro-score">' + (m.score == null ? "—" : m.score) +
          '<span class="macro-unit">/100</span></div>' +
          '<div class="track"><div class="fill" style="width:' + w + "%;background:" +
          macroColor(m.score, m.up_good) + '"></div></div>' +
          '<div class="macro-note">' + esc(m.note) + "</div></div>";
      }).join("");
    }

    /* 建議配置 */
    var allocColors = {
      "股票": "#3b89e3", "國債": "#8a6fd1", "商品": "#e08c3a",
      "黃金": "#d9a514", "現金": "#98a2b3",
    };
    var tg = document.getElementById("alloc-targets");
    if (tg) {
      var maxT = Math.max.apply(null, A.targets.map(function (t) { return t.pct; }));
      tg.innerHTML = '<div class="dash-head"><h3>🎯 目標權重</h3></div>' +
        A.targets.map(function (t) {
          var w = Math.round(t.pct / maxT * 100);
          var q = D.market && D.market[t.proxy];
          var pr = q ? q.price.toLocaleString() : "";
          return '<div class="al-block">' +
            '<div class="al-line"><span class="al-name">' + esc(t.cls) + "</span>" +
            '<div class="track"><div class="fill" style="width:' + w + "%;background:" +
            (allocColors[t.cls] || "var(--sector-fill)") + '"></div></div>' +
            '<span class="al-val">' + t.pct + "%</span></div>" +
            '<div class="al-proxy">ETF 代理 ' + esc(t.proxy) + (pr ? " · " + pr : "") +
            "</div></div>";
        }).join("");
    }

    /* 當前判斷 */
    var jl = document.getElementById("alloc-judgment");
    if (jl) {
      jl.innerHTML = A.judgment.map(function (line) {
        return "<li>" + esc(line) + "</li>";
      }).join("");
    }

    /* 資產類別表現 */
    var ag = document.getElementById("alloc-assets");
    if (ag) {
      ag.innerHTML = A.assets.map(function (a) {
        var up = a.y1 >= 0;
        return '<div class="card asset-card">' +
          '<div class="asset-top"><span class="asset-label">' + esc(a.label) + "</span>" +
          '<span class="asset-sym">' + esc(a.sym) + "</span></div>" +
          '<div class="asset-price">' + a.price.toLocaleString() + "</div>" +
          '<div class="asset-ret">' +
          '<span class="c ' + (a.ytd >= 0 ? "up" : "down") + '">YTD ' + fmtPct(a.ytd) + "</span>" +
          '<span class="c ' + (a.y1 >= 0 ? "up" : "down") + '">1Y ' + fmtPct(a.y1) + "</span>" +
          "</div>" + sparklineSVG(a.closes, up) +
          '<div class="asset-range">52周 ' + (a.low == null ? "—" : a.low.toLocaleString()) +
          " – " + (a.high == null ? "—" : a.high.toLocaleString()) + "</div></div>";
      }).join("");
    }

    /* 債券市場 */
    var bt = document.getElementById("bonds-table");
    if (bt && A.bonds) {
      var b = A.bonds;
      bt.innerHTML = "<thead><tr><th>指標</th><th>數值</th><th>說明</th></tr></thead><tbody>" +
        "<tr><td>2年期國債殖利率</td><td class='hl'>" + b.dgs2 + "%</td><td>短端定價「利率高位持續」</td></tr>" +
        "<tr><td>10年期國債殖利率</td><td class='hl'>" + b.dgs10 + "%</td><td>全球資產定價之錨</td></tr>" +
        "<tr><td>30年期國債殖利率</td><td class='hl'>" + b.dgs30 + "%</td><td>期限溢價顯著</td></tr>" +
        "<tr><td>10Y-2Y 利差</td><td class='hl'>" + (b.spread >= 0 ? "+" : "") + b.spread +
        "%</td><td>正斜率：曲線已正常化</td></tr>" +
        "<tr><td>聯邦基金利率</td><td>" + b.ffr + "%</td><td>美聯儲政策利率</td></tr>" +
        "<tr><td>10年期實際利率（TIPS）</td><td>" + b.real10 + "%</td><td>長債的真實回報</td></tr>" +
        "<tr><td>高收益債利差（OAS）</td><td>" + b.hy_oas + "%</td><td>信用利差極窄＝市場無懼</td></tr>" +
        "<tr><td>投資級債利差（IG OAS）</td><td>" +
        (b.ig_oas == null ? "—" : b.ig_oas + "%") + "</td><td>歷史低位，信用溢價極薄</td></tr>" +
        "<tr><td>投資級債有效收益率</td><td class='hl'>" +
        (b.ig_yield == null ? "—" : b.ig_yield + "%") + "</td><td>IG 到期收益（LQD 之錨）</td></tr>" +
        "<tr><td>高收益債有效收益率</td><td class='hl'>" +
        (b.hy_yield == null ? "—" : b.hy_yield + "%") + "</td><td>HY 到期收益（HYG 之錨）</td></tr>" +
        "</tbody>";
      var ba = document.getElementById("bonds-asof");
      if (ba) ba.textContent = "⏱ FRED 數據截至 " + b.asof;
    }

    /* 大宗商品 */
    var cg = document.getElementById("alloc-commodities");
    if (cg) {
      cg.innerHTML = A.commodities.map(function (c) {
        var up = c.y1 >= 0;
        var chgHtml = c.chg == null ? "" :
          '<span class="c ' + (c.chg >= 0 ? "up" : "down") + '">' +
          (c.chg >= 0 ? "▲" : "▼") + Math.abs(c.chg).toFixed(2) + "%</span>";
        return '<div class="card asset-card">' +
          '<div class="asset-top"><span class="asset-label">' + esc(c.name) + "</span>" +
          '<span class="asset-sym">' + esc(c.unit) + "</span></div>" +
          '<div class="asset-price">' + c.price.toLocaleString() + "</div>" +
          '<div class="asset-ret">' + chgHtml +
          '<span class="c ' + (c.ytd >= 0 ? "up" : "down") + '">YTD ' + fmtPct(c.ytd) + "</span>" +
          '<span class="c ' + (c.y1 >= 0 ? "up" : "down") + '">1Y ' + fmtPct(c.y1) + "</span>" +
          "</div>" + sparklineSVG(c.closes, up) + "</div>";
      }).join("");
    }

    /* 建議組合實時收益 */
    renderPortfolioPerf();

    /* 方法論 */
    var frm = document.getElementById("alloc-formulas");
    if (frm) {
      frm.innerHTML = A.macro.map(function (m) {
        return "<li><strong>" + esc(m.label) + "</strong>：" + esc(m.formula) + "</li>";
      }).join("");
    }
    var rl = document.getElementById("alloc-rules");
    if (rl) {
      rl.innerHTML = A.rules.map(function (r) { return "<li>" + esc(r) + "</li>"; }).join("");
    }
    var src = document.getElementById("alloc-sources");
    if (src) src.textContent = "資料來源：" + A.sources.join(" · ");
  }

  /* ---------- 配置頁：全球前五大基金資產配置動態 ---------- */
  function renderFunds() {
    var host = document.getElementById("funds-list");
    if (!host || !D.funds || !D.funds.length) return;
    var lg = document.getElementById("funds-legend");
    if (lg) {
      lg.innerHTML = Object.keys(FUND_COLORS).map(function (k) {
        return '<span class="item"><span class="sw" style="background:' + FUND_COLORS[k] +
          '"></span>' + k + "</span>";
      }).join("");
    }
    host.innerHTML = D.funds.map(function (f) {
      var maxP = 1;
      f.alloc.forEach(function (a) { if (a.pct > maxP) maxP = a.pct; });
      var rows = f.alloc.length ? f.alloc.map(function (a) {
        var w = Math.round(a.pct / maxP * 100);
        var dlt = "";
        if (a.delta != null) {
          if (typeof a.delta === "number") {
            dlt = '<span class="f-delta' + (a.delta < 0 ? " down" : "") + '">' +
              (a.delta >= 0 ? "▲ +" : "▼ ") + Math.abs(a.delta).toFixed(1) + "pp</span>";
          } else {
            dlt = '<span class="f-delta' + (a.delta.indexOf("↓") !== -1 ? " down" : "") + '">' +
              esc(a.delta) + "</span>";
          }
        }
        return '<div class="f-row">' +
          '<span class="f-cls">' + esc(a.cls) + "</span>" +
          '<div class="track"><div class="fill" style="width:' + w + "%;background:" +
          (FUND_COLORS[a.cls] || "#98a2b3") + '" aria-hidden="true"></div></div>' +
          '<span class="f-val">' + a.pct + "%" +
          (a.min != null ? ' <em class="f-rng">區間 ' + a.min + "–" + a.max + "%</em>" : "") +
          "</span>" + dlt + "</div>" +
          (a.sub ? '<div class="f-sub">' + esc(a.sub) + "</div>" : "");
      }).join("") :
        '<div class="empty" style="padding:14px 0;">不公開披露資產配置明細</div>';
      return '<div class="card fund-card">' +
        '<div class="fund-head"><span class="fund-rank">' + f.rank + "</span>" +
        '<div class="fund-title"><h3>' + esc(f.name) + "</h3>" +
        '<div class="fund-meta">' + esc(f.mgr) + " · " + esc(f.country) + " · " +
        esc(f.aum) + " · 截至 " + esc(f.asof) + "</div></div></div>" +
        rows +
        '<div class="fund-note">' + esc(f.note) + ' · 來源：' + esc(f.source) + "</div></div>";
    }).join("");
  }

  function renderPortfolioPerf() {
    var A = D.allocation;
    var pf = A && A.portfolio;
    var card = document.getElementById("pf-card");
    if (!card) return;
    if (!pf || !pf.portfolio || pf.portfolio.length < 2) {
      card.innerHTML = '<div class="dash-head"><h3>📈 組合淨值走勢</h3></div>' +
        '<p class="disclaimer" style="padding:0 16px 12px;">組合收益資料暫不可用（建站時資產序列抓取失敗）。</p>';
      return;
    }
    var asofEl = document.getElementById("pf-asof");
    if (asofEl) asofEl.textContent = "⏱ 回測截至 " + pf.asof;

    var rets = [
      ["YTD", pf.ytd, pf.bench_ytd],
      ["近1月", pf.m1, pf.bench_m1],
      ["近3月", pf.m3, pf.bench_m3],
      ["近1年", pf.y1, pf.bench_y1],
    ];
    var statHtml = "";
    for (var i = 0; i < rets.length; i++) {
      var r = rets[i][1], b = rets[i][2];
      var ex = (r == null || b == null) ? null : r - b;
      statHtml += '<div class="pf-stat">' +
        '<div class="pf-stat-label">' + rets[i][0] + "</div>" +
        '<div class="pf-stat-val ' + (r == null ? "" : (r >= 0 ? "up" : "down")) + '">' +
        fmtPct(r) + "</div>" +
        '<div class="pf-stat-ex">vs SPY ' +
        (ex == null ? "—" : (ex >= 0 ? "跑贏 <b>+" + ex.toFixed(1) : "跑輸 <b>" + Math.abs(ex).toFixed(1)) + "%</b>") +
        "</div></div>";
    }

    /* SVG 折線圖（組合 vs SPY，共用同一坐標系） */
    var W = 720, H = 240, PL = 8, PR = 8, PT = 14, PB = 24;
    var n = pf.portfolio.length;
    var mn = Math.min.apply(null, pf.portfolio.concat(pf.benchmark));
    var mx = Math.max.apply(null, pf.portfolio.concat(pf.benchmark));
    if (mx - mn < 0.5) { mx += 0.5; mn -= 0.5; }
    function pts(series) {
      var s = "";
      for (var i = 0; i < n; i++) {
        var x = PL + (W - PL - PR) * i / (n - 1);
        var y = PT + (H - PT - PB) * (1 - (series[i] - mn) / (mx - mn));
        s += (i ? " " : "") + x.toFixed(1) + "," + y.toFixed(1);
      }
      return s;
    }
    var wKey = Object.keys(pf.weights || {});
    var wLabel = wKey.length ? wKey.map(function (s) {
      return esc(s) + " " + pf.weights[s] + "%";
    }).join(" · ") : "";

    card.innerHTML =
      '<div class="dash-head"><h3>📈 組合淨值走勢（起始 = 100，自 ' + esc(pf.start) + "）</h3>" +
      '<span class="pf-legend"><span class="pf-dot pf-dot-a"></span>建議組合' +
      '<span class="pf-dot pf-dot-b"></span>SPY 基準</span></div>' +
      '<div class="pf-stats">' + statHtml + "</div>" +
      '<div class="pf-chart">' +
      '<svg viewBox="0 0 ' + W + " " + H + '" preserveAspectRatio="none" role="img" aria-label="建議組合與SPY淨值走勢對比">' +
      '<line class="pf-axis" x1="' + PL + '" y1="' + (H - PB) + '" x2="' + (W - PR) +
      '" y2="' + (H - PB) + '"></line>' +
      '<polyline class="pf-line-b" points="' + pts(pf.benchmark) + '"></polyline>' +
      '<polyline class="pf-line-a" points="' + pts(pf.portfolio) + '"></polyline>' +
      "</svg>" +
      '<div class="pf-axis-labels"><span>' + esc(pf.dates[0]) + "</span><span>" +
      esc(pf.dates[n - 1]) + "</span></div>" +
      '<div class="pf-weights">配置權重：' + wLabel +
      "（每日以目標權重再平衡，未計費用與稅，僅為框架演示）</div>" +
      "</div>";
  }

  /* ---------- 更新數據按鈕 ----------
   * 有觸發憑證（gh-trigger.js）：直接 API 觸發工作流 + 狀態輪詢；
   * 無憑證（默認）：打開 GitHub Actions 頁面，手動點 Run workflow。 */
  function initUpdateButton() {
    var btn = document.getElementById("btn-update-data");
    if (!btn) return;
    var status = document.getElementById("update-status");
    var TOKEN = (typeof window.GH_TRIGGER_TOKEN === "string" && window.GH_TRIGGER_TOKEN) || "";
    var REPO = "aliu29775-bot/ai_investment_tool_aliu";
    var WF = "update-data.yml";
    var COOLDOWN_MS = 10 * 60 * 1000; // 單一瀏覽器 10 分鐘冷卻
    var POLL_MS = 15000;
    var MAX_POLL = 24; // 最多輪詢約 6 分鐘

    function setMsg(text, cls) {
      if (!status) return;
      status.hidden = false;
      status.textContent = text;
      status.className = "update-status" + (cls ? " " + cls : "");
    }

    function pollRun(attempt) {
      if (attempt > MAX_POLL) { setMsg("⏳ 仍在進行中，稍後刷新頁面即可看到更新", "warn"); return; }
      var xhr = new XMLHttpRequest();
      xhr.open("GET", "https://api.github.com/repos/" + REPO + "/actions/runs?event=workflow_dispatch&per_page=1", true);
      xhr.onload = function () {
        if (xhr.status !== 200) { setTimeout(function () { pollRun(attempt + 1); }, POLL_MS); return; }
        var runs = [];
        try { runs = (JSON.parse(xhr.responseText).workflow_runs) || []; } catch (e) {}
        if (!runs.length) { setTimeout(function () { pollRun(attempt + 1); }, POLL_MS); return; }
        var run = runs[0];
        if (run.status === "completed") {
          if (run.conclusion === "success") setMsg("✅ 更新完成！頁面正在重新發佈，約 1 分鐘後刷新即可看到新數據", "ok");
          else setMsg("❌ 更新失敗（" + run.conclusion + "），可稍後重試", "err");
        } else if (run.status === "in_progress" || run.status === "queued") {
          setMsg("⏳ 更新進行中…（" + (run.status === "queued" ? "排隊中" : "抓取行情 + 重建報告") + "）", "warn");
          setTimeout(function () { pollRun(attempt + 1); }, POLL_MS);
        } else {
          setTimeout(function () { pollRun(attempt + 1); }, POLL_MS);
        }
      };
      xhr.onerror = function () { setTimeout(function () { pollRun(attempt + 1); }, POLL_MS); };
      xhr.send();
    }

    btn.addEventListener("click", function () {
      if (!TOKEN) {
        window.open("https://github.com/" + REPO + "/actions/workflows/" + WF, "_blank", "noopener");
        setMsg("已打開 GitHub Actions 頁面，點擊 Run workflow 觸發更新；完成後約 1 分鐘刷新本頁即可看到新數據", "ok");
        return;
      }
      var last = 0;
      try { last = parseInt(localStorage.getItem("lastUpdateTrigger"), 10) || 0; } catch (e) {}
      var now = Date.now();
      if (now - last < COOLDOWN_MS) {
        setMsg("⏱ 冷卻中，約 " + Math.ceil((COOLDOWN_MS - (now - last)) / 60000) + " 分鐘後可再次更新", "warn");
        return;
      }
      // 預設小更新（關鍵數據，約 30 秒）；取消則改為大更新（全部數據 + 重渲染全部報告）
      var mode = "small";
      if (!window.confirm("進行「小更新」？\n\n小更新：只重抓行情與宏觀等關鍵數據（約 30 秒）\n\n點「取消」改為「大更新」：重抓全部數據並重渲染全部報告（約 5 分鐘）")) {
        mode = "big";
      }
      btn.disabled = true;
      setMsg("⏳ 正在觸發" + (mode === "small" ? "小更新" : "大更新") + "…", "warn");
      var xhr = new XMLHttpRequest();
      xhr.open("POST", "https://api.github.com/repos/" + REPO + "/actions/workflows/" + WF + "/dispatches", true);
      xhr.setRequestHeader("Accept", "application/vnd.github+json");
      xhr.setRequestHeader("Authorization", "Bearer " + TOKEN);
      xhr.onload = function () {
        btn.disabled = false;
        if (xhr.status === 204) {
          try { localStorage.setItem("lastUpdateTrigger", String(Date.now())); } catch (e) {}
          setMsg("✅ 已觸發！工作流開始運行…", "warn");
          setTimeout(function () { pollRun(0); }, 8000);
        } else if (xhr.status === 401 || xhr.status === 403) {
          setMsg("⚠ 觸發憑證無效或過期，請站長更新 PAT", "err");
        } else if (xhr.status === 404) {
          setMsg("⚠ 未找到工作流 update-data.yml", "err");
        } else if (xhr.status === 422) {
          // 舊版工作流沒有 mode 輸入：回退為無參數觸發（全量更新）
          var x2 = new XMLHttpRequest();
          x2.open("POST", "https://api.github.com/repos/" + REPO + "/actions/workflows/" + WF + "/dispatches", true);
          x2.setRequestHeader("Accept", "application/vnd.github+json");
          x2.setRequestHeader("Authorization", "Bearer " + TOKEN);
          x2.onload = function () {
            btn.disabled = false;
            if (x2.status === 204) {
              try { localStorage.setItem("lastUpdateTrigger", String(Date.now())); } catch (e) {}
              setMsg("✅ 已觸發全量更新（工作流尚未支援大小更新）…", "warn");
              setTimeout(function () { pollRun(0); }, 8000);
            } else {
              setMsg("⚠ 觸發失敗（HTTP " + x2.status + "），可到 GitHub Actions 頁面手動運行", "err");
            }
          };
          x2.onerror = function () { btn.disabled = false; setMsg("⚠ 網絡錯誤，請稍後重試", "err"); };
          x2.send("{}");
        } else {
          setMsg("⚠ 觸發失敗（HTTP " + xhr.status + "），請稍後重試", "err");
        }
      };
      xhr.onerror = function () { btn.disabled = false; setMsg("⚠ 網絡錯誤，請稍後重試", "err"); };
      xhr.send(JSON.stringify({ ref: "main", inputs: { mode: mode } }));
    });
  }

  /* ---------- 美聯儲追蹤器 ---------- */
  function fedLineSVG(series, color) {
    if (!series || series.length < 2) return "";
    var W = 640, H = 150, P = 10;
    var vals = series.map(function (p) { return p[1]; });
    var mn = Math.min.apply(null, vals), mx = Math.max.apply(null, vals);
    var rng = (mx - mn) || 1;
    var pts = vals.map(function (v, i) {
      var x = P + i * (W - 2 * P) / (vals.length - 1);
      var y = H - P - (v - mn) / rng * (H - 2 * P);
      return x.toFixed(1) + "," + y.toFixed(1);
    });
    return '<svg viewBox="0 0 ' + W + " " + H + '" style="width:100%;height:auto;" aria-hidden="true">' +
      '<polyline points="' + pts.join(" ") + '" fill="none" stroke="' + color +
      '" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/></svg>';
  }

  function renderFed() {
    var F = D.allocation && D.allocation.fed;
    var host = document.querySelector("main.container");
    if (!host) return;
    if (!F) {
      host.insertAdjacentHTML("afterbegin",
        '<div class="card" style="padding:16px;margin-top:16px;">' +
        "⚠️ 美聯儲追蹤資料暫不可用（建站時 FRED 宏觀數據抓取失敗）。</div>");
      return;
    }
    var i;
    var asofEls = document.querySelectorAll("#fed-asof");
    for (i = 0; i < asofEls.length; i++) asofEls[i].textContent = "⏱ 更新於 " + F.asof;

    /* 政策利率 */
    var el = document.getElementById("fed-rate");
    if (el && F.eff != null) {
      var tgt = F.target_upper != null && F.target_lower != null
        ? F.target_upper.toFixed(2) + "% – " + F.target_lower.toFixed(2) + "%" : "—";
      var next = null;
      (F.fomc || []).forEach(function (m) { if (m.status === "next") next = m; });
      el.innerHTML =
        '<div class="fed-big">' + F.eff.toFixed(2) + '<span>%</span></div>' +
        '<div class="fed-sub">聯邦基金有效利率 · 目標區間 ' + tgt + "</div>" +
        (next ? '<div class="fed-next">🔜 下次 FOMC：' + esc(next.dates) + "（2026）</div>" : "");
    }

    /* 利率走勢（1 年：有效利率 + 目標上限） */
    var ch = document.getElementById("fed-rate-chart");
    if (ch) {
      var effSvg = fedLineSVG(F.eff_hist, "#3b89e3");
      var tgtSvg = fedLineSVG(F.target_hist, "#c2543a");
      if (effSvg) {
        ch.innerHTML = (tgtSvg ? '<p class="fed-legend">' +
          '<span style="color:#c2543a;">▬ 目標上限</span>' +
          '<span style="color:#3b89e3;margin-left:14px;">▬ 有效利率</span></p>' : "") +
          tgtSvg + effSvg +
          '<p class="s-note" style="margin-top:6px;">近 1 年日頻（FRED）。</p>';
      } else {
        ch.innerHTML = "<p>利率走勢數據暫缺。</p>";
      }
    }

    /* 通脹追蹤 */
    var inf = document.getElementById("fed-inflation");
    if (inf) {
      var rows = [["CPI 同比", F.cpi_yoy], ["核心 CPI 同比", F.core_cpi_yoy],
        ["PCE 同比", F.pce_yoy], ["核心 PCE 同比", F.core_pce_yoy]];
      inf.innerHTML = rows.map(function (r) {
        var v = r[1];
        if (v == null) return "";
        var gap = v - 0.02;
        var cls = v > 0.025 ? "down" : "up";
        return '<div class="card macro-card">' +
          '<div class="macro-head"><span class="macro-label">' + r[0] + "</span></div>" +
          '<div class="macro-score">' + (v * 100).toFixed(1) +
          '<span class="macro-unit">%</span></div>' +
          '<div class="macro-note">距 2% 目標 ' + (gap >= 0 ? "+" : "") +
          (gap * 100).toFixed(1) + " 個百分點</div></div>";
      }).join("") + (F.unrate != null
        ? '<div class="card macro-card"><div class="macro-head"><span class="macro-label">失業率</span></div>' +
          '<div class="macro-score">' + F.unrate.toFixed(1) +
          '<span class="macro-unit">%</span></div><div class="macro-note">勞動市場冷熱參考</div></div>'
        : "");
    }

    /* 資產負債表 */
    var bs = document.getElementById("fed-bs");
    if (bs && F.walcl != null) {
      var y1 = F.walcl_1y != null && F.walcl_1y
        ? (F.walcl / F.walcl_1y - 1) * 100 : null;
      bs.innerHTML = '<div class="s-grid2">' +
        '<div class="s-kv"><span class="s-k">資產負債表規模</span><span class="s-v">' +
        (F.walcl / 1000).toFixed(2) + " 兆美元</span></div>" +
        (y1 != null ? '<div class="s-kv"><span class="s-k">近 1 年變化</span><span class="s-v ' +
          (y1 > 0 ? "up" : "down") + '">' + (y1 > 0 ? "▲" : "▼") + " " +
          Math.abs(y1).toFixed(1) + "%</span></div>" : "") +
        "</div>" +
        (fedLineSVG(F.walcl_hist, "#8a6fd1") || "<p>資產負債表走勢暫缺。</p>") +
        '<p class="s-note">近 60 週（FRED WALCL，單位：十億美元）。</p>';
    }

    /* FOMC 日曆 */
    var fc = document.getElementById("fed-fomc");
    if (fc && (F.fomc || []).length) {
      var statLabel = { past: "已召開", next: "🔜 下次會議", future: "待召開" };
      fc.innerHTML = '<table class="s-table"><thead><tr><th>會議</th><th>狀態</th>' +
        "<th>會後目標區間</th></tr></thead><tbody>" +
        F.fomc.map(function (m) {
          var tgt2 = m.upper != null && m.lower != null
            ? m.lower.toFixed(2) + "% – " + m.upper.toFixed(2) + "%" : "—";
          return "<tr" + (m.status === "next" ? ' style="background:var(--brand-tint);"' : "") + ">" +
            "<td>" + esc(m.dates) + "</td><td>" + (statLabel[m.status] || m.status) + "</td>" +
            "<td>" + tgt2 + "</td></tr>";
        }).join("") + "</tbody></table>" +
        '<p class="s-note">目標區間由 FRED 目標上限/下限序列按決議日取值；日程為聯儲官網預先公佈。</p>';
    }

    /* 收益率曲線 */
    var yc = document.getElementById("fed-yc");
    if (yc) {
      var B = D.allocation.bonds || {};
      var yvals = [["2 年期", B.dgs2], ["10 年期", B.dgs10], ["30 年期", B.dgs30]];
      yc.innerHTML = '<div class="s-grid2">' +
        yvals.map(function (r) {
          return r[1] != null ? '<div class="s-kv"><span class="s-k">' + r[0] +
            "</span><span class='s-v'>" + r[1].toFixed(2) + "%</span></div>" : "";
        }).join("") +
        (B.spread != null ? '<div class="s-kv"><span class="s-k">10Y−2Y 利差</span><span class="s-v ' +
          (B.spread > 0 ? "up" : "down") + '">' + (B.spread > 0 ? "+" : "") +
          B.spread.toFixed(2) + "%</span></div>" : "") +
        (B.real10 != null ? '<div class="s-kv"><span class="s-k">10Y 實際利率</span><span class="s-v">' +
          B.real10.toFixed(2) + "%</span></div>" : "") +
        (B.hy_oas != null ? '<div class="s-kv"><span class="s-k">高收益利差</span><span class="s-v">' +
          B.hy_oas.toFixed(2) + "%</span></div>" : "") +
        "</div>" +
        '<p class="s-note">利差為負（倒掛）時市場預期衰退；數據源 FRED。</p>';
    }
    renderTreasury(F.treasury);
  }

  /* ---------- 國債交易台 ---------- */
  function renderTreasury(T) {
    var host = document.getElementById("fed-treasury");
    if (!host) return;
    if (!T || !T.rates) {
      host.innerHTML = "<p>國債交易台數據暫缺。</p>";
      return;
    }
    var R = T.rates;
    function bp(v) {
      if (v == null) return '<span class="s-note">—</span>';
      var s = (v > 0 ? "▲ +" : (v < 0 ? "▼ " : "± ")) + Math.abs(v).toFixed(0) + "bp";
      return '<span class="' + (v > 0 ? "up" : v < 0 ? "down" : "") + '">' + s + "</span>";
    }
    function kv(k, v, note) {
      return '<div class="s-kv"><span class="s-k">' + k + "</span><span class='s-v'>" +
        v + "</span>" + (note ? '<span class="s-note">' + note + "</span>" : "") + "</div>";
    }
    var ch = T.changes || {};

    /* 關鍵利率（FFR/3M/2Y/5Y/10Y/30Y，帶 1M/1Y 變化） */
    var heads = [
      ["聯邦基金有效利率", R.ffr != null ? R.ffr.toFixed(2) + "%" : "—", "DFF"],
      ["3 個月國庫券", R.dgs3m != null ? R.dgs3m.toFixed(2) + "%" : "—", "DGS3MO"],
      ["2 年期殖利率", R.dgs2 != null ? R.dgs2.toFixed(2) + "%" : "—",
        bp(ch["2Y"] ? ch["2Y"].m1 : null) + " 1M / " + bp(ch["2Y"] ? ch["2Y"].y1 : null) + " 1Y"],
      ["5 年期殖利率", R.dgs5 != null ? R.dgs5.toFixed(2) + "%" : "—",
        bp(ch["5Y"] ? ch["5Y"].m1 : null) + " 1M / " + bp(ch["5Y"] ? ch["5Y"].y1 : null) + " 1Y"],
      ["10 年期殖利率", R.dgs10 != null ? R.dgs10.toFixed(2) + "%" : "—",
        bp(ch["10Y"] ? ch["10Y"].m1 : null) + " 1M / " + bp(ch["10Y"] ? ch["10Y"].y1 : null) + " 1Y"],
      ["30 年期殖利率", R.dgs30 != null ? R.dgs30.toFixed(2) + "%" : "—",
        bp(ch["30Y"] ? ch["30Y"].m1 : null) + " 1M / " + bp(ch["30Y"] ? ch["30Y"].y1 : null) + " 1Y"],
    ];
    var html = '<div class="s-grid2">' +
      heads.map(function (h) { return kv(h[0], h[1], h[2]); }).join("") + "</div>";

    /* 殖利率曲線快照（FFR→30Y，按到期年限橫軸） */
    html += '<div class="card" style="margin-top:10px;"><h4 style="margin:0 0 6px;">殖利率曲線快照（FFR / 3M / 2Y / 5Y / 10Y / 30Y）</h4>' +
      '<div class="chart-scroll"><div style="min-width:600px;">' +
      curveSVG(T.curve || []) +
      '</div></div>' +
      '<p class="s-note">曲線形狀即第一層「形態」的直觀呈現；數據源 FRED。</p></div>';

    /* ---- 第一層：形態 ---- */
    var S = T.shape || {};
    html += '<h3 style="margin:18px 0 8px;">📐 第一層・形態：當前「' + esc(S.name || "—") +
      '」，近一年「' + esc(S.trend || "—") + '」</h3>' +
      '<div class="card" style="margin:0;">' +
      (S.text ? '<p style="margin:0 0 6px;">' + S.text + "</p>" : "") +
      (S.trend_text ? '<p style="margin:0 0 6px;">' + S.trend_text + "</p>" : "") +
      (S.hump ? '<p style="margin:0;">' + S.hump + "</p>" : "") + "</div>";
    /* 牛陡/熊陡/牛平/熊平速查表 */
    if (S.trend_table && S.trend_table.length) {
      html += '<div class="card" style="margin-top:10px;"><h4 style="margin:0 0 6px;">牛陡／熊陡／牛平／熊平速查表</h4>' +
        '<table class="s-table"><thead><tr><th>類型</th><th>定義</th><th>利差</th><th>曲線交易</th><th></th></tr></thead><tbody>' +
        S.trend_table.map(function (t) {
          return "<tr><td><b>" + esc(t.name) + "</b></td><td>" + esc(t.def) + "</td><td>" +
            esc(t.spread) + "</td><td>" + esc(t.trade) + "</td><td>" +
            (t.now ? '<span class="chip">當前</span>' : "") + "</td></tr>";
        }).join("") + "</tbody></table></div>";
    }
    /* 四種基本形態速查卡 */
    if (S.cards && S.cards.length) {
      html += '<h4 style="margin:14px 0 6px;">利率曲線四種基本形態</h4><div class="s-grid2">' +
        S.cards.map(function (c) {
          return '<div class="card"><h4 style="margin:0 0 4px;">' + esc(c.name) + "</h4>" +
            shapeSketch(c.kind) +
            '<p class="s-note" style="margin:4px 0;">' + esc(c.desc) + "</p>" +
            '<p style="margin:0;"><b>' + esc(c.trade) + "</b></p></div>";
        }).join("") + "</div>";
    }

    /* ---- 第二層：驅動因素 ---- */
    if (T.drivers && T.drivers.length) {
      html += '<h3 style="margin:18px 0 8px;">🔍 第二層・驅動因素</h3><div class="s-grid2">' +
        T.drivers.map(function (d) {
          return '<div class="card"><h4 style="margin:0 0 4px;">' + esc(d.title) + "</h4>" +
            '<p class="s-note" style="margin:0;">' + d.txt + "</p></div>";
        }).join("") + "</div>";
    }

    /* ---- 利差總表 ---- */
    if (T.spreads && T.spreads.length) {
      html += '<div class="card" style="margin-top:14px;"><h4 style="margin:0 0 6px;">📊 利差總表（期限利差＋信用利差＋盈虧平衡）</h4>' +
        '<table class="s-table"><thead><tr><th>利差</th><th>現值</th><th>解讀</th></tr></thead><tbody>' +
        T.spreads.map(function (s) {
          return "<tr><td>" + esc(s.name) + "</td><td><b>" + esc(s.val) + "</b></td><td>" +
            esc(s.note) + "</td></tr>";
        }).join("") + "</tbody></table></div>";
    }

    /* ---- 圖：近 2 年 2Y/5Y/10Y/30Y 殖利率 ---- */
    var h = T.hist || {};
    var svg2 = fedLineSVG(h.dgs2, "#3b89e3");
    var svg5 = fedLineSVG(h.dgs5, "#7f5bd6");
    var svg10 = fedLineSVG(h.dgs10, "#e58c2e");
    var svg30 = fedLineSVG(h.dgs30, "#c2543a");
    if (svg2 && svg10 && svg30) {
      html += '<div class="card" style="margin-top:10px;"><h4 style="margin:0 0 6px;">近 2 年：2Y／5Y／10Y／30Y 殖利率（日頻）</h4>' +
        '<p class="fed-legend" style="margin:0 0 4px;">' +
        '<span style="color:#3b89e3;">▬ 2Y</span>' +
        '<span style="color:#7f5bd6;margin-left:14px;">▬ 5Y</span>' +
        '<span style="color:#e58c2e;margin-left:14px;">▬ 10Y</span>' +
        '<span style="color:#c2543a;margin-left:14px;">▬ 30Y</span></p>' +
        svg2 + (svg5 || "") + svg10 + svg30 +
        '<p class="s-note">四線的相對移動即牛陡／熊陡／牛平／熊平的圖形化；數據源 FRED DGS。</p></div>';
    }
    var spr = fedLineSVG(h.spread2s10s, (R.spread2s10s_bp || 0) >= 0 ? "#2e9e6b" : "#c2543a");
    var spr5 = fedLineSVG(h.spread5s30s, (R.spread5s30s_bp || 0) >= 0 ? "#2e9e6b" : "#c2543a");
    if (spr || spr5) {
      html += '<div class="card" style="margin-top:10px;"><h4 style="margin:0 0 6px;">近 2 年：2s10s 與 5s30s 利差（bp）</h4>' +
        '<div style="display:flex;gap:12px;flex-wrap:wrap;">' +
        (spr ? '<div style="flex:1 1 300px;"><p class="fed-legend" style="margin:0 0 4px;">' +
          '<span style="color:#2e9e6b;">▬ 2s10s</span></p>' + spr +
          '<p class="s-note">> 0 陡峭、< 0 倒掛；當前 ' +
          esc(R.spread2s10s_bp != null ? (R.spread2s10s_bp > 0 ? "+" : "") + R.spread2s10s_bp + "bp" : "—") +
          "</p></div>" : "") +
        (spr5 ? '<div style="flex:1 1 300px;"><p class="fed-legend" style="margin:0 0 4px;">' +
          '<span style="color:#7f5bd6;">▬ 5s30s</span></p>' + spr5 +
          '<p class="s-note">長端陡峭度；當前 ' +
          esc(R.spread5s30s_bp != null ? (R.spread5s30s_bp > 0 ? "+" : "") + R.spread5s30s_bp + "bp" : "—") +
          "</p></div>" : "") +
        "</div></div>";
    }

    /* ---- 第三層：交易策略（具體場景） ---- */
    if (T.strategies && T.strategies.length) {
      html += '<h3 style="margin:18px 0 8px;">🎯 第三層・交易策略（具體場景）</h3><div class="s-grid2">' +
        T.strategies.map(function (s) {
          return '<div class="card"><h4 style="margin:0 0 4px;">' + esc(s.name) + "</h4>" +
            '<div class="s-chip" style="margin-bottom:6px;">' + esc(s.setup) + "</div>" +
            '<p class="s-note" style="margin:0;">' + s.scenario + "</p></div>";
        }).join("") + "</div>";
    }

    /* Treasury 產品工具表 */
    var trow = function (n, d, dv, u) {
      return "<tr><td>" + n + "</td><td>" + d + "</td><td>" + dv + "</td><td>" + u + "</td></tr>";
    };
    html += '<div class="card" style="margin-top:14px;"><h4 style="margin:0 0 6px;">🧰 Treasury 產品工具箱（久期/DV01 為近似值）</h4>' +
      '<table class="s-table"><thead><tr><th>標的</th><th>到期／久期（約）</th><th>DV01（約）</th><th>用途</th></tr></thead><tbody>' +
      trow("ZT（2Y 期貨）", "2 年", "$41", "短端 carry 核心工具") +
      trow("ZF（5Y 期貨）", "5 年", "$77", "中短端曲線腿") +
      trow("ZN（10Y 期貨）", "10 年", "$80", "久期調整主力") +
      trow("TN（超長期 10Y）", "10 年+", "$119", "10Y 區間交易") +
      trow("ZB（30Y 期貨）", "30 年", "$150", "長端分批建倉") +
      trow("UB（Ultra Bond）", "30 年+", "$228", "超長久期對沖") +
      trow("Micro 2Y/10Y/30Y", "同上 1/10 規模", "1/10", "小倉位精細調整") +
      trow("BIL（0-3M T-Bill ETF）", "≈0.1 年", "≈$0.4", "現金管理") +
      trow("SHY（1-3Y ETF）", "≈1.9 年", "≈$2.3", "短端配置替代") +
      trow("IEI（3-7Y ETF）", "≈4.5 年", "≈$5.4", "曲線中段") +
      trow("IEF（7-10Y ETF）", "≈7.3 年", "≈$8.8", "10Y 配置型") +
      trow("TLT（20Y+ ETF）", "≈16 年", "≈$16", "長端／避險") +
      trow("EDV（零息長債 ETF）", "≈24 年", "≈$24", "超長久期衛星倉") +
      trow("TIP（TIPS ETF）", "≈6.7 年（實質）", "≈$8", "通脹保護腿") +
      "</tbody></table>" +
      '<p class="s-note">CME 國債期貨為保證金交易、內含槓桿，DV01 會隨價格與殖利率變化；ETF 久期以發行商披露為準。以上為工具列舉，非推薦個別產品。</p></div>';

    host.innerHTML = html +
      (T.ref ? '<p class="s-note" style="margin-top:10px;">📚 ' + esc(T.ref) + "</p>" : "");
  }

  /* 殖利率曲線快照（到期年限橫軸） */
  function curveSVG(points) {
    if (!points || !points.length) return "";
    var W = 640, H = 180, PAD = 40;
    var ys = points.map(function (p) { return p[2]; }).filter(function (v) { return v != null; });
    if (!ys.length) return "";
    var ymin = Math.min.apply(null, ys), ymax = Math.max.apply(null, ys);
    var pad = Math.max((ymax - ymin) * 0.3, 0.25);
    ymin -= pad; ymax += pad;
    var X = function (x) { return PAD + x / 30 * (W - PAD - 14); };
    var Y = function (y) { return H - 18 - (y - ymin) / (ymax - ymin) * (H - 18 - 14); };
    var pts = points.filter(function (p) { return p[2] != null; })
      .map(function (p) { return X(p[1]).toFixed(1) + "," + Y(p[2]).toFixed(1); }).join(" ");
    /* 標籤防重疊：距上一標籤 <48px 的點只畫圓點不標字；首點左對齊、末點右對齊；奇偶上下錯開 */
    var lastLx = -1e9;
    var dots = points.filter(function (p) { return p[2] != null; }).map(function (p, i, arr) {
      var x = X(p[1]), y = Y(p[2]);
      var dot = '<circle cx="' + x.toFixed(1) + '" cy="' + y.toFixed(1) + '" r="3.5" fill="#3b89e3"/>';
      if (x - lastLx < 48) return dot;
      lastLx = x;
      var anchor = i === 0 ? "start" : (i === arr.length - 1 ? "end" : "middle");
      var tx = i === 0 ? x + 6 : (i === arr.length - 1 ? x - 6 : x);
      var ty = (i % 2 === 0) ? y - 7 : y + 17;
      return dot + '<text x="' + tx.toFixed(1) + '" y="' + ty.toFixed(1) + '" text-anchor="' + anchor +
        '" font-size="12" fill="#4b5563">' + esc(p[0]) + " " + p[2].toFixed(2) + "%</text>";
    }).join("");
    var grid = "", i, gy, gx;
    for (i = 0; i <= 4; i++) {
      gy = 14 + (H - 18 - 14) * i / 4;
      grid += '<line x1="' + PAD + '" y1="' + gy.toFixed(1) + '" x2="' + (W - 14) + '" y2="' + gy.toFixed(1) +
        '" stroke="#e5e7eb" stroke-width="1"/>';
    }
    for (i = 0; i <= 6; i++) {
      gx = PAD + i / 6 * (W - PAD - 14);
      grid += '<line x1="' + gx.toFixed(1) + '" y1="14" x2="' + gx.toFixed(1) + '" y2="' + (H - 18) +
        '" stroke="#eef0f3" stroke-width="1"/>';
    }
    return '<svg viewBox="0 0 ' + W + ' ' + H + '" style="width:100%;height:auto;" role="img" aria-label="國債殖利率曲線">' +
      grid + '<polyline points="' + pts + '" fill="none" stroke="#3b89e3" stroke-width="2.5"/>' + dots + "</svg>";
  }

  /* 四種形態小圖 */
  function shapeSketch(kind) {
    var paths = {
      steep: "12,44 40,36 70,24 104,8",
      flat: "12,28 40,30 70,32 104,34",
      invert: "12,10 40,24 70,36 104,46",
      hump: "12,40 40,12 76,12 104,40"
    };
    return '<svg viewBox="0 0 116 56" style="width:100%;height:auto;" role="img" aria-label="' + esc(kind) + '">' +
      '<line x1="12" y1="46" x2="104" y2="46" stroke="#d1d5db"/>' +
      '<polyline points="' + (paths[kind] || paths.flat) + '" fill="none" stroke="#3b89e3" stroke-width="2.5" stroke-linecap="round"/>' +
      "</svg>";
  }

  /* ---------- 估值儀表板 ---------- */
  function renderValuation() {
    var V = D.allocation && D.allocation.valuation;
    var host = document.querySelector("main.container");
    if (!host) return;
    if (!V) {
      host.insertAdjacentHTML("afterbegin",
        '<div class="card" style="padding:16px;margin-top:16px;">' +
        "⚠️ 估值儀表板資料暫不可用（建站時宏觀數據抓取失敗）。</div>");
      return;
    }
    var i;
    var asofEls = document.querySelectorAll("#val-asof");
    for (i = 0; i < asofEls.length; i++) asofEls[i].textContent = "⏱ 更新於 " + (V.asof || D.market_asof);

    /* 巴菲特指標 */
    var el = document.getElementById("val-buffett");
    if (el && V.buffett) {
      var r = V.buffett.ratio, pct = Math.round(r * 100);
      var cls = pct >= 130 ? "down" : pct <= 70 ? "up" : "mid";
      var note = pct >= 130 ? "偏高區（>130%）" : pct <= 70 ? "偏低區（<70%）" : "中間區（70–130%）";
      el.innerHTML = '<div class="fed-big">' + pct + '<span>%</span></div>' +
        '<div class="fed-sub">美股企業股權市值 / GDP（Z.1 金融帳戶代理，季度）· ' + note + "</div>" +
        (fedLineSVG(V.buffett.hist.map(function (p) { return [p[0], p[1] * 100]; }), "#e08c3a") || "") +
        (V.buffett.asof ? '<p class="s-note">最新 ' + esc(V.buffett.asof) + "；歷史為近 40 季。</p>" : "");
    } else if (el) {
      el.innerHTML = "<p>巴菲特指標數據暫缺（FRED 未提供 Wilshire/GDP）。</p>";
    }

    /* 市場估值概覽 */
    var ov = document.getElementById("val-overview");
    if (ov) {
      var rows = [];
      if (V.pe_median_all != null)
        rows.push(['全站 PE 中位數（' + (V.n_valued || 0) + " 家）", V.pe_median_all + "×", ""]);
      if (V.earn_yield_median != null)
        rows.push(["全站 PE 中位數對應盈餘收益率", (V.earn_yield_median * 100).toFixed(2) + "%", ""]);
      if (V.dgs10 != null)
        rows.push(["10 年期國債收益率", V.dgs10 + "%", ""]);
      if (V.erp != null) {
        var e = V.erp * 100;
        rows.push(["股權風險溢價（盈餘收益率 − 10Y）", (e > 0 ? "+" : "") + e.toFixed(2) + "%",
          e < 1 ? "偏低：股票相對債券吸引力下降" : "股票風險補償充分"]);
      }
      ov.innerHTML = rows.length
        ? '<div class="s-grid2">' + rows.map(function (r2) {
            return '<div class="s-kv"><span class="s-k">' + r2[0] + "</span><span class='s-v'>" +
              r2[1] + "</span>" + (r2[2] ? '<span class="s-n">' + r2[2] + "</span>" : "") + "</div>";
          }).join("") + "</div>"
        : "<p>全市場估值數據暫缺。</p>";
    }

    /* 行業估值中位數 */
    var sec = document.getElementById("val-sectors");
    if (sec && (V.sectors || []).length) {
      sec.innerHTML = '<table class="s-table"><thead><tr><th>行業</th><th>公司數</th>' +
        "<th>PE 中位</th><th>PE 區間</th><th>估值帶</th></tr></thead><tbody>" +
        V.sectors.map(function (x) {
          var band = x.pe_median < 15 ? "低估" : x.pe_median <= 30 ? "合理" : "偏高";
          var color = x.pe_median < 15 ? "#15803d" : x.pe_median <= 30 ? "#8a6d00" : "#b02a37";
          return "<tr><td>" + esc(x.sector) + "</td><td>" + x.n + "</td><td><b>" +
            x.pe_median + "×</b></td><td>" + x.pe_low + " – " + x.pe_high + "×</td><td>" +
            '<span class="s-chip" style="background:' + color + '18;color:' + color + '">' +
            band + "</span></td></tr>";
        }).join("") + "</tbody></table>" +
        '<p class="s-note">行業 PE 中位數：全站有 PE 數據的公司按行業聚合（≥3 家才顯示）；PE 缺時以價格/每股收益估算。</p>';
    }

    /* 高估 / 低估榜 */
    function rankTable(items, clsLabel) {
      return '<table class="s-table"><thead><tr><th>公司</th><th>代碼</th><th>PE</th></tr></thead><tbody>' +
        items.map(function (r3) {
          return "<tr><td>" + esc(r3.name) + "</td><td>" + esc(r3.ticker || "") + "</td><td>" +
            r3.pe + "×</td></tr>";
        }).join("") + "</tbody></table>";
    }
    var exp = document.getElementById("val-expensive");
    if (exp && (V.expensive || []).length) exp.innerHTML = rankTable(V.expensive);
    var chp = document.getElementById("val-cheap");
    if (chp && (V.cheap || []).length) chp.innerHTML = rankTable(V.cheap);
  }

  /* ---------- 政策事件日曆 ---------- */
  function renderEvents() {
    var EV = D.allocation && D.allocation.events;
    var F = D.allocation && D.allocation.fed;
    var host = document.querySelector("main.container");
    if (!host) return;
    if (!EV) {
      host.insertAdjacentHTML("afterbegin",
        '<div class="card" style="padding:16px;margin-top:16px;">' +
        "⚠️ 事件日曆資料暫不可用（建站時數據抓取失敗）。</div>");
      return;
    }
    /* 財報日曆（未來 60 天） */
    var er = document.getElementById("ev-earnings");
    if (er) {
      if ((EV.earnings || []).length) {
        var rows = EV.earnings.map(function (e) {
          var link = e.page ? '<a href="' + esc(e.page) + '">' + esc(e.name) + "</a>" : esc(e.name);
          return "<tr><td>" + esc(e.date) + "</td><td>" + link + "</td><td>" +
            esc(e.ticker || "") + "</td><td>" + esc(e.sector || "") + "</td></tr>";
        }).join("");
        er.innerHTML = '<table class="s-table"><thead><tr><th>日期</th><th>公司</th>' +
          "<th>代碼</th><th>行業</th></tr></thead><tbody>" + rows + "</tbody></table>" +
          '<p class="s-note">僅含覆蓋公司中已公佈財報日的（Yahoo calendarEvents）；財報日可能臨時調整。</p>';
      } else {
        er.innerHTML = "<p>未來 60 天暫無已公佈的財報日。</p>";
      }
    }
    /* FOMC 日程 */
    var fm = document.getElementById("ev-fomc");
    if (fm && F && (F.fomc || []).length) {
      var statLabel = { past: "已召開", next: "🔜 下次會議", future: "待召開" };
      fm.innerHTML = '<table class="s-table"><thead><tr><th>會議</th><th>狀態</th>' +
        "<th>會後目標區間</th></tr></thead><tbody>" +
        F.fomc.map(function (m) {
          var tgt = m.upper != null && m.lower != null
            ? m.lower.toFixed(2) + "% – " + m.upper.toFixed(2) + "%" : "—";
          return "<tr" + (m.status === "next" ? ' style="background:var(--brand-tint);"' : "") + ">" +
            "<td>" + esc(m.dates) + "</td><td>" + (statLabel[m.status] || m.status) + "</td>" +
            "<td>" + tgt + "</td></tr>";
        }).join("") + "</tbody></table>";
    }
    /* 固定事件 */
    var fx = document.getElementById("ev-fixed");
    if (fx && (EV.fixed || []).length) {
      fx.innerHTML = '<table class="s-table"><thead><tr><th>日期</th><th>事件</th>' +
        "<th>影響</th></tr></thead><tbody>" +
        EV.fixed.map(function (e) {
          return "<tr><td>" + esc(e.date) + "</td><td><b>" + esc(e.label) + "</b></td><td>" +
            esc(e.note || "") + "</td></tr>";
        }).join("") + "</tbody></table>";
    }
    /* 每月例行 */
    var mo = document.getElementById("ev-monthly");
    if (mo && (EV.monthly || []).length) {
      mo.innerHTML = "<ul class='s-reports'>" + EV.monthly.map(function (m) {
        return "<li>" + esc(m) + "</li>";
      }).join("") + "</ul>";
    }
  }

  /* ================= 風險儀表板（模組 7/8/10/18） ================= */
  function renderRisk() {
    if (document.body.getAttribute("data-page") !== "risk") return;
    renderRiskRecession();
    renderRiskCorr();
    renderRiskTail();
    renderRiskSentiment();
  }

  function pctBar(p, color) {
    var w = p == null ? 0 : Math.max(2, Math.min(100, p));
    return '<div style="background:var(--chip);border-radius:6px;height:9px;width:100%;overflow:hidden;margin-top:6px;">' +
      '<div style="width:' + w + '%;height:100%;background:' + (color || "var(--brand)") + ';"></div></div>';
  }

  function renderRiskRecession() {
    var host = document.getElementById("r-recession");
    var R = (D.risk || {}).recession;
    if (!host) return;
    if (!R || R.prob_now == null) {
      host.innerHTML = "<p>衰退模型資料暫缺（FRED 抓取失敗），請重新觸發更新。</p>";
      return;
    }
    var prob = R.prob_now, spread = R.spread_now;
    var pcls = prob >= 50 ? "down" : prob >= 30 ? "mid" : "on";
    var pcol = prob >= 50 ? "var(--crit)" : prob >= 30 ? "#b3542e" : "var(--good)";
    var kv = [];
    kv.push('<div class="s-kv"><span class="s-n">10Y-3M 利差（' + esc(R.spread_date) + '）</span>' +
      '<span class="s-v">' + (spread >= 0 ? "+" : "") + spread.toFixed(2) + '%</span>' +
      '<span class="s-n">利差 &lt; 0 為倒掛，歷史為衰退先行訊號</span></div>');
    kv.push('<div class="s-kv"><span class="s-n">未來 12 個月衰退概率（模型）</span>' +
      '<span class="s-v" style="color:' + pcol + ';">' + prob.toFixed(1) + "%</span>" +
      pctBar(prob, pcol) + '<span class="s-n">樣本內邏輯迴歸 · ' +
      esc(R.n_months) + ' 個月 · 衰退月份 ' + esc(R.n_rec) + ' 個</span></div>');
    if (R.growth_now != null) {
      kv.push('<div class="s-kv"><span class="s-n">增長評分（交叉驗證）</span>' +
        '<span class="s-v">' + R.growth_now + " / 100</span>" +
        '<span class="s-n">配置頁宏觀評分；評分低與模型高概率同向時需警惕</span></div>');
    }
    if (R.icsa) {
      var i = R.icsa;
      kv.push('<div class="s-kv"><span class="s-n">初請失業金（' + esc(i.date) + '）</span>' +
        '<span class="s-v">' + i.now.toLocaleString() + " 人</span>" +
        '<span class="s-n">4 週均線 ' + i.ma4.toLocaleString() + " · 較前一週 " +
        (i.wo_prev >= 0 ? "+" : "") + i.wo_prev + "% · 較去年 " +
        (i.yo_prev >= 0 ? "+" : "") + i.yo_prev + "%</span></div>");
    }
    var pts = (R.series || []).map(function (x, idx) { return [idx, x.p]; });
    var ranges = (R.rec_ranges || []).map(function (rg) {
      return '<span class="s-chip down">NBER 衰退 ' + esc(rg[0]) + " – " + esc(rg[1]) + "</span>";
    }).join(" ");
    host.innerHTML = '<div class="card">' +
      '<h3>🌡 10Y-3M 利差衰退模型 <span class="s-chip ' + pcls + '">' +
      prob.toFixed(0) + "% 概率</span></h3>" +
      '<div class="s-grid2" style="gap:12px;margin-top:8px;">' + kv.join("") + "</div>" +
      '<div style="margin-top:14px;"><h4 class="s-h3">模型歷史概率（月頻，' +
      esc((R.series || [])[0] ? (R.series[0].d) : "") + " 起）</h4>" +
      fedLineSVG(pts, "#0e6b4f") + "</div>" +
      '<p class="s-note">縱軸為模型給出的「未來 12 個月落入衰退」概率（%）。' +
      ranges + "</p>" +
      '<p class="s-note">模型：FRED T10Y3M 月頻利差 × NBER USREC 衰退標記擬合邏輯迴歸' +
      "（係數 b=" + esc(R.b) + "；樣本至 " + esc(R.train_end) + "）。" +
      "單一變量為粗糙先行指標：樣本內峰值（2007 年）也僅約四成，低概率不代表無風險，" +
      "只是與增長評分的交叉驗證工具。</p></div>";
  }

  function renderRiskCorr() {
    var host = document.getElementById("r-corr");
    var C = (D.risk || {}).corr;
    if (!host) return;
    if (!C || !C.labels) {
      host.innerHTML = "<p>相關性矩陣暫缺（20 年月線快取缺失），請重新觸發更新。</p>";
      return;
    }
    var tbl = function (labels, mat, title, note) {
      var tint = function (v) {
        if (v == null) return "";
        var a = Math.min(0.25, Math.abs(v) * 0.3);
        var c = v >= 0 ? "16,110,79" : "196,54,54";
        return "background:rgba(" + c + "," + a.toFixed(2) + ");";
      };
      return '<div style="min-width:320px;flex:1;"><h4 class="s-h3">' + esc(title) + "</h4>" +
        '<table class="s-table"><thead><tr><th></th>' +
        labels.map(function (l) { return "<th>" + esc(l) + "</th>"; }).join("") +
        "</tr></thead><tbody>" +
        mat.map(function (row, i) {
          return "<tr><th>" + esc(labels[i]) + "</th>" +
            row.map(function (v, j) {
              var txt = i === j ? "1" : v == null ? "—" : v.toFixed(2);
              return '<td style="text-align:right;font-variant-numeric:tabular-nums;' +
                (i === j ? "" : tint(v)) + '">' + txt + "</td>";
            }).join("") + "</tr>";
        }).join("") + "</tbody></table>" +
        (note ? '<p class="s-note">' + esc(note) + "</p>" : "") + "</div>";
    };
    var stk_bnd = [0, 1];
    var sb_full = C.full.length > 1 ? C.full[stk_bnd[0]][stk_bnd[1]] : null;
    var sb_recent = C.recent.length > 1 ? C.recent[stk_bnd[0]][stk_bnd[1]] : null;
    host.innerHTML = '<div class="card">' +
      '<h3>🔗 股／債／商品／黃金／現金月報酬相關性</h3>' +
      '<div class="s-bullbear" style="gap:18px;align-items:flex-start;">' +
      tbl(C.labels, C.full, "全樣本（" + C.n_months + " 個月，20 年）") +
      tbl(C.labels, C.recent, "近 " + C.window + " 個月滾動") +
      "</div>" +
      '<p class="s-note">皮爾遜相關係數（真實 ETF 月報酬：SPY／IEF／DBC／GLD／BIL）。' +
      "正相關著綠、負相關著紅。" +
      (sb_full != null && sb_recent != null
        ? " 股票-國債相關性由全樣本 " + sb_full.toFixed(2) + " 變為近 " + C.window +
          " 個月 " + sb_recent.toFixed(2) +
          (sb_recent > 0 ? "——正值意味股債同漲同跌，「股債雙殺」風險高於歷史常態（2022 年情景即是）。"
                         : "——負值意味國債仍能對沖股票下跌。")
        : "") +
      "</p></div>";
  }

  function renderRiskTail() {
    var host = document.getElementById("r-tail");
    var T = (D.risk || {}).tail;
    if (!host) return;
    if (!T) {
      host.innerHTML = "<p>尾部風險資料暫缺（FRED 抓取失敗），請重新觸發更新。</p>";
      return;
    }
    var statusOf = function (pct) {
      return pct == null ? ["off", "—"] : pct >= 75 ? ["down", "偏高"]
        : pct <= 25 ? ["on", "偏緊"] : ["mid", "中性"];
    };
    var cards = [];
    (T.items || []).forEach(function (it) {
      var st = statusOf(it.pct);
      cards.push('<div class="card" style="flex:1;min-width:240px;">' +
        '<h4 class="s-h3">' + esc(it.label) + ' <span class="s-chip ' + st[0] + '">' +
        st[1] + "</span></h4>" +
        '<div class="s-kv" style="margin-top:6px;"><span class="s-v">' +
        it.now + ' <span class="s-n">' + esc(it.unit) + "</span></span>" +
        '<span class="s-n">10 年百分位 ' + it.pct + "% · 區間 " + it.lo10 + " – " +
        it.hi10 + " · " + esc(it.date) + "</span>" +
        pctBar(it.pct, st[0] === "down" ? "var(--crit)" : st[0] === "on" ? "var(--good)" : "#b3542e") +
        "</div></div>");
    });
    if (T.vix) {
      var st = statusOf(T.vix.pct);
      cards.push('<div class="card" style="flex:1;min-width:240px;">' +
        '<h4 class="s-h3">VIX 恐慌指數 <span class="s-chip ' + st[0] + '">' + st[1] + "</span></h4>" +
        '<div class="s-kv" style="margin-top:6px;"><span class="s-v">' + T.vix.now + "</span>" +
        '<span class="s-n">10 年百分位 ' + T.vix.pct + "% · 200 日均值 " + T.vix.ma200 +
        " · " + esc(T.vix.date) + "</span>" +
        pctBar(T.vix.pct, st[0] === "down" ? "var(--crit)" : st[0] === "on" ? "var(--good)" : "#b3542e") +
        "</div></div>");
    }
    if (T.gepu) {
      var st = statusOf(T.gepu.pct);
      cards.push('<div class="card" style="flex:1;min-width:240px;">' +
        '<h4 class="s-h3">全球經濟政策不確定性 <span class="s-chip ' + st[0] + '">' + st[1] + "</span></h4>" +
        '<div class="s-kv" style="margin-top:6px;"><span class="s-v">' + T.gepu.now + "</span>" +
        '<span class="s-n">10 年百分位 ' + T.gepu.pct + "% · " + esc(T.gepu.date) + "</span>" +
        pctBar(T.gepu.pct, "#b3542e") +
        "</div></div>");
    }
    var conc = T.concentration;
    var concHtml = "";
    if (conc && conc.top10 && conc.top10.length) {
      concHtml = '<div class="card" style="flex:1;min-width:260px;">' +
        '<h4 class="s-h3">市場集中度（站內美股覆蓋）</h4>' +
        '<div class="s-kv" style="margin-top:6px;"><span class="s-v">' + conc.top10_sum +
        "%</span><span class=\"s-n\">前十大市值佔比 · " + conc.n_companies +
        " 家美股公司（Yahoo 市值快照）</span></div>" +
        "<ul class='s-reports' style='margin-top:6px;'>" +
        conc.top10.map(function (x) {
          return "<li><b>" + esc(x.name) + "</b> " + x.pct + "%</li>";
        }).join("") + "</ul></div>";
    }
    host.innerHTML = '<div class="s-bullbear" style="gap:12px;align-items:stretch;flex-wrap:wrap;">' +
      cards.join("") + concHtml + "</div>" +
      '<p class="s-note">信用利差與 VIX 百分位越低代表市場風險偏好越高（利差收緊）。' +
      "信用利差資料：ICE BofA 指數 OAS（FRED）；VIX：CBOE（FRED VIXCLS）。</p>";
  }

  function renderRiskSentiment() {
    var host = document.getElementById("r-sentiment");
    var S = (D.risk || {}).sentiment;
    if (!host) return;
    if (!S) {
      host.innerHTML = "<p>情緒指標資料暫缺。</p>";
      return;
    }
    var rows = (S.manual || []).map(function (m) {
      var cls = "off";
      if (m.unit === "百分點") cls = m.value >= 0 ? "on" : "down";
      if (m.unit === "/ 100") cls = m.value <= 25 ? "down" : m.value >= 75 ? "on" : "mid";
      return "<tr><td>" + esc(m.label) + "</td>" +
        '<td><span class="s-chip ' + cls + '">' + m.value + " " + esc(m.unit) + "</span></td>" +
        "<td>" + esc(m.detail) + "</td>" +
        '<td><span class="s-note">' + esc(m.asof) + " · " + esc(m.source) + "</span></td></tr>";
    }).join("");
    host.innerHTML = '<div class="card">' +
      "<h3>😨 散戶與市場情緒</h3>" +
      '<table class="s-table"><thead><tr><th>指標</th><th>數值</th><th>解讀</th><th>資料</th></tr></thead><tbody>' +
      rows + "</tbody></table>" +
      '<p class="s-note">VIX 見上方尾部風險卡片（當前 ' +
      (S.vix ? S.vix.now + "，10 年百分位 " + S.vix.pct + "%" : "—") +
      "）。AAII 與 CNN 指數為公開報導整理、站長人工維護，每週更新；歷史均值：AAII 多空差 +6.5%、看空 31.5%。" +
      "散戶極度看空時常為反向訊號，但不作投資依據。</p></div>";
  }

  /* ================= 市場全景（模組 11/13/14/16/17/19/21） ================= */
  function renderMarketPage() {
    if (document.body.getAttribute("data-page") !== "market") return;
    renderMarketFlows();
    renderMarketGlobal();
    renderMarketEarnings();
    renderMarketTechnicals();
    renderMarketAssets();
    renderMarketLookthrough();
    renderMarketRebalance();
  }

  function pctTxt(v) {
    if (v == null) return "—";
    return (v >= 0 ? "+" : "") + v.toFixed(1) + "%";
  }
  function pctClr(v) {
    if (v == null) return "";
    return ' style="color:' + (v >= 0 ? "var(--good)" : "var(--crit)") + ';"';
  }

  function renderMarketFlows() {
    var host = document.getElementById("m-flows");
    var F = (D.marketview || {}).flows;
    if (!host) return;
    if (!F) {
      host.innerHTML = "<p>資金流向資料暫缺。</p>";
      return;
    }
    var wkCards = (F.weeks || []).map(function (w) {
      var g = w.global_eq, u = w.us_eq, b = w.us_bond;
      return '<div class="card" style="flex:1;min-width:260px;">' +
        "<h4 class='s-h3'>" + esc(w.week) + "</h4>" +
        '<div class="s-grid2" style="gap:8px;margin-top:6px;">' +
        '<div class="s-kv"><span class="s-n">全球股票基金</span><span class="s-v"' +
        pctClr(g) + ">" + (g >= 0 ? "+" : "") + g.toFixed(1) + " 億美元</span></div>" +
        '<div class="s-kv"><span class="s-n">美國股票基金</span><span class="s-v"' +
        pctClr(u) + ">" + (u >= 0 ? "+" : "") + u.toFixed(1) + " 億美元</span></div>" +
        (b != null ? '<div class="s-kv"><span class="s-n">美國債券基金</span><span class="s-v"' +
          pctClr(b) + ">" + (b >= 0 ? "+" : "") + b.toFixed(1) + " 億美元</span></div>" : "") +
        "</div><p class='s-note' style='margin-top:6px;'>" + esc(w.note) + "</p></div>";
    }).join("");
    var ici = F.ici || {};
    var na = F.naaim || {};
    var naCls = na.value == null ? "" : na.value >= 100 ? "on" : na.value <= 40 ? "down" : "mid";
    host.innerHTML = '<div class="s-bullbear" style="gap:12px;align-items:stretch;flex-wrap:wrap;">' +
      wkCards +
      '<div class="card" style="flex:1;min-width:240px;"><h4 class="s-h3">機構倉位（NAAIM）</h4>' +
      '<div class="s-kv" style="margin-top:6px;"><span class="s-v">' +
      (na.value != null ? na.value : "—") + ' <span class="s-n">/ 100 平均曝險</span></span>' +
      '<span class="s-n">' + esc(na.date || "") + " · 歷史中位數 " + (na.median != null ? na.median : "—") +
      " · 100=滿倉</span></div>" +
      '<p class="s-note" style="margin-top:6px;">' + esc(na.note || "") + "</p></div>" +
      '<div class="card" style="flex:1;min-width:240px;"><h4 class="s-h3">ICI 週度統計</h4>' +
      '<div class="s-kv" style="margin-top:6px;"><span class="s-v"' + pctClr(ici.equity) + ">" +
      (ici.equity != null ? (ici.equity >= 0 ? "+" : "") + ici.equity.toFixed(2) + " 億美元" : "—") +
      "</span><span class=\"s-n\">股票基金 · " + esc(ici.week || "") + "</span></div>" +
      '<div class="s-kv"><span class="s-v"' + pctClr(ici.bond) + ">" +
      (ici.bond != null ? (ici.bond >= 0 ? "+" : "") + ici.bond.toFixed(2) + " 億美元" : "—") +
      "</span><span class=\"s-n\">債券基金</span></div>" +
      '<p class="s-note" style="margin-top:6px;">' + esc(ici.note || "") + "</p></div></div>" +
      '<p class="s-note">來源：' + esc(F.source || "") + "；ICI：ICH 週度統計；NAAIM：" +
      esc(na.source || "") + "。散戶情緒見風險儀表板（AAII）。</p>";
  }

  function renderMarketGlobal() {
    var host = document.getElementById("m-global");
    var G = (D.marketview || {}).global;
    if (!host) return;
    if (!G || !G.length) {
      host.innerHTML = "<p>全球指數資料暫缺（行情抓取失敗），請重新觸發更新。</p>";
      return;
    }
    var rows = G.map(function (r) {
      return "<tr><td><b>" + esc(r.label) + "</b></td>" +
        '<td style="font-variant-numeric:tabular-nums;">' +
        (r.price != null ? r.price.toLocaleString() : "—") + "</td>" +
        "<td" + pctClr(r.chg) + ">" + pctTxt(r.chg) + "</td>" +
        "<td" + pctClr(r.ytd) + ">" + pctTxt(r.ytd) + "</td>" +
        "<td" + pctClr(r.y1) + ">" + pctTxt(r.y1) + "</td>" +
        "<td" + pctClr(r.rs) + ">" + pctTxt(r.rs) + "</td>" +
        "<td>" + (r.ma50 != null ? r.ma50.toLocaleString() : "—") + "</td>" +
        "<td>" + (r.ma200 != null ? r.ma200.toLocaleString() : "—") + "</td>" +
        "<td>" + (r.trend ? (r.trend.indexOf("上方") >= 0
          ? '<span class="s-chip on">' : '<span class="s-chip down">') + esc(r.trend) + "</span>" : "—") +
        "</td></tr>";
    }).join("");
    host.innerHTML = '<div class="card"><h3>🌍 全球主要指數</h3>' +
      '<table class="s-table"><thead><tr><th>指數</th><th>價格</th><th>日漲跌</th>' +
      "<th>YTD</th><th>1 年</th><th>相對標普500（1 年）</th><th>50 日均線</th><th>200 日均線</th>" +
      "<th>趨勢</th></tr></thead><tbody>" + rows + "</tbody></table>" +
      '<p class="s-note">價格為最近收盤（Yahoo 1 年日線）；相對強弱＝該指數 1 年報酬 − 標普 500 1 年報酬。' +
      "資料點不足的指數不展示期間報酬（如滬深 300 的 Yahoo 日線僅有最新點）。</p></div>";
  }

  function renderMarketEarnings() {
    var host = document.getElementById("m-earnings");
    var E = (D.marketview || {}).earnings;
    if (!host) return;
    if (!E || !E.now) {
      host.innerHTML = "<p>標普 500 盈利資料暫缺（multpl 抓取失敗），請重新觸發更新。</p>";
      return;
    }
    var pts = (E.series || []).map(function (x, i) { return [i, x.yy]; });
    var chips = (E.declines || []).map(function (rg) {
      return '<span class="s-chip down">盈利衰退 ' + esc(rg[0].slice(0, 4)) +
        (rg[0] !== rg[1] ? " – " + esc(rg[1].slice(0, 4)) : "") + "</span>";
    }).join(" ");
    var ly = E.last_year || {};
    host.innerHTML = '<div class="card"><h3>💹 標普 500 盈利（as-reported EPS）</h3>' +
      '<div class="s-grid2" style="gap:12px;margin-top:8px;">' +
      '<div class="s-kv"><span class="s-n">TTM EPS（' + esc(E.now.date) + "）</span><span class=\"s-v\">" +
      E.now.eps.toFixed(2) + "</span></div>" +
      '<div class="s-kv"><span class="s-n">後視市盈率</span><span class="s-v">' +
      (E.pe != null ? E.pe.toFixed(1) + "×" : "—") +
      "<span class=\"s-n\">指數 " + (E.spx != null ? E.spx.toFixed(2) : "—") + " ÷ TTM EPS</span></div>" +
      '<div class="s-kv"><span class="s-n">最近完整年度（' + esc(ly.date || "") + "）</span><span class=\"s-v\"" +
      pctClr(ly.yy) + ">" + pctTxt(ly.yy) + "</span><span class=\"s-n\">EPS " +
      (ly.eps != null ? ly.eps.toFixed(2) : "—") + "</span></div>" +
      '<div class="s-kv"><span class="s-n">10 年複合增速</span><span class="s-v">' +
      (E.cagr10 != null ? "+" + E.cagr10 + "% / 年" : "—") + "</span></div></div>" +
      '<div style="margin-top:14px;"><h4 class="s-h3">年度 EPS 同比增速（%，1971 年起，降採樣）</h4>' +
      fedLineSVG(pts, "#0e6b4f") + "</div>" +
      '<p class="s-note">' + chips + "</p>" +
      '<p class="s-note">資料：multpl.com 標普 500 盈利（1871 年起）；同比只比較每年 12-31 的年度 EPS。' +
      "盈利衰退＝年度 EPS 同比轉負（1990 年後）。EPS 為標普公司公佈的 as-reported 值。</p></div>";
  }

  function renderMarketTechnicals() {
    var host = document.getElementById("m-technicals");
    var T = (D.marketview || {}).technicals;
    if (!host) return;
    if (!T || !T.length) {
      host.innerHTML = "<p>技術面資料暫缺（1 年日線抓取失敗）。</p>";
      return;
    }
    var rows = T.map(function (t) {
      var rsiCls = t.rsi == null ? "" : t.rsi >= 70 ? "down" : t.rsi <= 30 ? "on" : "mid";
      return "<tr><td><b>" + esc(t.label) + "</b></td>" +
        '<td style="font-variant-numeric:tabular-nums;">' +
        (t.price != null ? t.price.toLocaleString() : "—") + "</td>" +
        "<td>" + (t.ma50 != null ? t.ma50.toLocaleString() : "—") + "</td>" +
        "<td>" + (t.ma200 != null ? t.ma200.toLocaleString() : "—") + "</td>" +
        "<td>" + (t.above200 == null ? "—" : t.above200
          ? '<span class="s-chip on">200 日線上方</span>'
          : '<span class="s-chip down">200 日線下方</span>') + "</td>" +
        "<td>" + (t.rsi != null
          ? '<span class="s-chip ' + rsiCls + '">' + t.rsi + "</span>" : "—") + "</td>" +
        "<td>" + (t.pos52 != null ? t.pos52 + "%" : "—") + "</td></tr>";
    }).join("");
    host.innerHTML = '<div class="card"><h3>📈 50/200 日均線、RSI、52 週位置</h3>' +
      '<table class="s-table"><thead><tr><th>指數</th><th>價格</th><th>50 日均線</th>' +
      "<th>200 日均線</th><th>長期趨勢</th><th>RSI-14</th><th>52 週區間位置</th></tr></thead><tbody>" +
      rows + "</tbody></table>" +
      '<p class="s-note">RSI ≥ 70 超買、≤ 30 超賣；52 週位置＝（現價 − 52 週低）÷（52 週高 − 52 週低）。' +
      "由 Yahoo 1 年日線真實計算。</p></div>";
  }

  function renderMarketAssets() {
    var host = document.getElementById("m-assets");
    var A = (D.marketview || {}).assets;
    if (!host) return;
    if (!A || !A.length) {
      host.innerHTML = "<p>擴展資產資料暫缺。</p>";
      return;
    }
    var cards = A.map(function (a) {
      return '<div class="card" style="flex:1;min-width:180px;">' +
        "<h4 class='s-h3'>" + esc(a.label) + "</h4>" +
        '<div class="s-kv" style="margin-top:6px;"><span class="s-v">' +
        (a.price != null ? a.price.toLocaleString() : "—") + "</span>" +
        '<span class="s-n">YTD <span' + pctClr(a.ytd) + ">" + pctTxt(a.ytd) +
        "</span> · 1 年 <span" + pctClr(a.y1) + ">" + pctTxt(a.y1) + "</span></span>" +
        (a.note ? '<span class="s-n">' + esc(a.note) + "</span>" : "") +
        "</div></div>";
    }).join("");
    host.innerHTML = '<div class="s-bullbear" style="gap:12px;align-items:stretch;flex-wrap:wrap;">' +
      cards + "</div>" +
      '<p class="s-note">REITs＝VNQ、上市私募股權＝PSP、新興市場＝EEM（均為 ETF 代理）；' +
      "比特幣／以太幣為加密市場價；房價為 Case-Shiller 20 城季調指數。私募／風投直接數據無公開免費來源，" +
      "故用上市私募股權 ETF 代理。行情由 Yahoo 1 年日線真實計算。</p>";
  }

  function renderMarketLookthrough() {
    var host = document.getElementById("m-lookthrough");
    var L = (D.marketview || {}).lookthrough;
    if (!host) return;
    if (!L) {
      host.innerHTML = "<p>持倉穿透資料暫缺（ETF 持倉抓取失敗），請重新觸發更新。</p>";
      return;
    }
    var topRows = (L.top || []).map(function (h) {
      return "<tr><td>" + esc(h.sym) + "</td><td>" + h.pct.toFixed(2) + "%</td></tr>";
    }).join("");
    var secRows = (L.sectors || []).map(function (s) {
      return "<tr><td>" + esc(s.name) + "</td><td>" + s.pct.toFixed(2) + "%</td></tr>";
    }).join("");
    var etfCards = (L.etfs || []).map(function (e) {
      var hs = (e.holds || []).slice(0, 6).map(function (h) {
        return esc(h.sym) + " " + h.pct.toFixed(1) + "%";
      }).join("、");
      return '<div class="card" style="flex:1;min-width:200px;">' +
        "<h4 class='s-h3'>" + esc(e.sym) + "</h4>" +
        '<p class="s-note">' + esc(e.category || "") +
        (e.asof ? " · 截至 " + esc(e.asof) : "") + "</p>" +
        (hs ? '<p class="s-note">前十大：' + hs + "</p>"
            : '<p class="s-note">持倉為國債／實物資產，無個股符號。</p>') +
        "</div>";
    }).join("");
    host.innerHTML = '<div class="card"><h3>🔍 建議配置的穿透視角</h3>' +
      '<p class="s-note">把建議配置中股票權重（' + (L.eq_w != null ? L.eq_w + "%" : "—") +
      "）乘進 SPY 前十大持倉，得到整個組合對個股的隱含暴露：</p>" +
      '<div class="s-bullbear" style="gap:18px;align-items:flex-start;">' +
      '<div style="flex:1;min-width:220px;"><h4 class="s-h3">穿透後前十大個股暴露</h4>' +
      '<table class="s-table"><thead><tr><th>代碼</th><th>組合內權重</th></tr></thead><tbody>' +
      (topRows || "<tr><td colspan='2'>暫缺</td></tr>") + "</tbody></table></div>" +
      '<div style="flex:1;min-width:220px;"><h4 class="s-h3">穿透後行業暴露</h4>' +
      '<table class="s-table"><thead><tr><th>行業</th><th>組合內權重</th></tr></thead><tbody>' +
      (secRows || "<tr><td colspan='2'>暫缺</td></tr>") + "</tbody></table>" +
      (L.sec_note ? '<p class="s-note">' + esc(L.sec_note) + "</p>" : "") + "</div></div>" +
      '<h4 class="s-h3" style="margin-top:12px;">各代理 ETF 前十大持倉</h4>' +
      '<div class="s-bullbear" style="gap:10px;align-items:stretch;flex-wrap:wrap;">' +
      etfCards + "</div>" +
      '<p class="s-note">ETF 持倉資料：Yahoo quoteSummary topHoldings（建站時抓取）。' +
      "穿透計算＝建議配置的資產權重 × ETF 持倉權重，反映「整個組合買到了什麼」。</p></div>";
  }

  function renderMarketRebalance() {
    var host = document.getElementById("m-rebalance");
    var R = (D.marketview || {}).rebalance;
    if (!host) return;
    if (!R || !R.now || !R.now.length) {
      host.innerHTML = "<p>再平衡資料暫缺（資產 1 年日線缺失）。</p>";
      return;
    }
    var rows = R.now.map(function (d) {
      var over = Math.abs(d.drift) >= (R.threshold || 5);
      return "<tr" + (over ? ' style="background:var(--brand-tint);"' : "") + ">" +
        "<td>" + esc(d.cls) + "（" + esc(d.sym) + "）</td>" +
        '<td style="font-variant-numeric:tabular-nums;">' + d.target.toFixed(1) + "%</td>" +
        "<td" + pctClr(d.rel) + ">" + pctTxt(d.rel) + "</td>" +
        '<td style="font-variant-numeric:tabular-nums;">' + d.w30.toFixed(1) + "%</td>" +
        "<td" + pctClr(d.drift) + ">" + (d.drift >= 0 ? "+" : "") + d.drift.toFixed(1) + " 百分點</td>" +
        "<td>" + (over ? '<span class="s-chip mid">⚠ 建議檢視</span>' : '<span class="s-chip on">正常</span>') +
        "</td></tr>";
    }).join("");
    var sim = R.sim || {};
    host.innerHTML = '<div class="card"><h3>⚖️ 目標權重 vs 30 天不動作後的實際權重</h3>' +
      '<table class="s-table"><thead><tr><th>資產</th><th>目標權重</th><th>近 30 天報酬</th>' +
      "<th>當前隱含權重</th><th>偏離</th><th>狀態（閾值 ±" + (R.threshold || 5) +
      " 百分點）</th></tr></thead><tbody>" + rows + "</tbody></table>" +
      '<p class="s-note">假設 30 天前按目標權重買入後完全不動作：各資產漲跌使實際權重偏離目標。' +
      (sim.n_months
        ? "歷史模擬（20 年月線，每月重平衡後持有 1 個月，共 " + sim.n_months +
          " 個月）：平均最大偏離 " + sim.avg_max_drift +
          " 百分點，超過閾值的月份佔 " + sim.pct_over5 +
          "%。月頻再平衡下偏離極少超過 5 百分點——若網站月更，5pp 閾值足夠。"
        : "") +
      " 實際操作請以自身持倉金額計算（見決策工具箱的再平衡計算器）。</p></div>";
  }

  /* ---------- 決策工具箱（模組 22-26） ---------- */
  var TOOL_CLS = ["股票", "國債", "商品", "黃金", "現金"];
  var TOOL_COLOR = {"股票": "#2563eb", "國債": "#16a34a", "商品": "#d97706",
                    "黃金": "#f59e0b", "現金": "#64748b"};
  var TOOL_W = null;        // 模擬器目前權重（與再平衡計算器共享）
  var TOOL_CURRENT = {};    // 目前總資產與五類持倉（再平衡計算器）

  function toolWeightsFromScores(g, i, l, s, dbcY) {
    var w = {股票: 40, 國債: 20, 商品: 10, 黃金: 10, 現金: 20};
    var fired = [];
    if (s >= 60) { w["股票"] -= 10; w["現金"] += 10; fired.push("壓力 ≥ 60 → 股票 −10、現金 +10"); }
    if (g < 45) { w["股票"] -= 10; w["國債"] += 10; fired.push("增長 < 45 → 股票 −10、國債 +10"); }
    if (i >= 70) { w["黃金"] += 8; w["國債"] -= 8; fired.push("通脹 ≥ 70 → 黃金 +8、國債 −8"); }
    if (l < 45) { w["現金"] += 5; w["商品"] -= 5; fired.push("流動性 < 45 → 現金 +5、商品 −5"); }
    if (dbcY > 25) { w["商品"] += 5; w["現金"] -= 5; fired.push("商品一年報酬 > +25% → 商品 +5、現金 −5"); }
    if (w["國債"] < 10) { w["股票"] -= 10 - w["國債"]; w["國債"] = 10; }
    if (w["現金"] < 10) { w["股票"] -= 10 - w["現金"]; w["現金"] = 10; }
    return {w: w, fired: fired};
  }

  function toolCurrentScores() {
    var macro = ((D.allocation || {}).macro) || [];
    var sc = {growth: 50, inflation: 50, liquidity: 50, stress: 50};
    macro.forEach(function (m) {
      if (m && m.key && typeof m.score === "number") sc[m.key] = m.score;
    });
    var dbcY = 0;
    (((D.allocation || {}).assets) || []).concat(
      ((D.marketview || {}).assets) || []).forEach(function (a) {
      if (a && a.sym === "DBC" && typeof a.y1 === "number") dbcY = a.y1;
    });
    return {g: sc.growth, i: sc.inflation, l: sc.liquidity, s: sc.stress, dbc: dbcY};
  }

  function toolSimResult() {
    var g = +document.getElementById("tool-g").value;
    var i = +document.getElementById("tool-i").value;
    var l = +document.getElementById("tool-l").value;
    var s = +document.getElementById("tool-s").value;
    var dbc = +document.getElementById("tool-dbc").value;
    var r = toolWeightsFromScores(g, i, l, s, dbc);
    TOOL_W = r.w;
    var seg = TOOL_CLS.map(function (c) {
      return '<div style="flex:' + r.w[c] + ' 1 0%;background:' + TOOL_COLOR[c] +
             ';height:22px;" title="' + c + " " + r.w[c] + '%"></div>';
    }).join("");
    var legend = TOOL_CLS.map(function (c) {
      return '<span style="white-space:nowrap;"><span style="display:inline-block;width:10px;height:10px;' +
             "border-radius:2px;background:" + TOOL_COLOR[c] + ';margin-right:4px;"></span>' +
             c + " <b>" + r.w[c] + "%</b></span>";
    }).join('<span style="margin:0 8px;color:var(--mid);">·</span>');
    var firedHtml = r.fired.length
      ? "<ul>" + r.fired.map(function (f) {
          return '<li><span class="s-chip mid">規則觸發</span> ' + esc(f) + "</li>";
        }).join("") + "</ul>"
      : '<p class="s-note">未觸發任何調整規則 → 維持基準配置 40/20/10/10/20。</p>';
    document.getElementById("tool-result").innerHTML =
      '<div style="display:flex;gap:2px;border-radius:6px;overflow:hidden;">' + seg + "</div>" +
      '<p style="margin:8px 0 4px;">' + legend + "</p>" + firedHtml;
    toolCalcRender();
    return r;
  }

  function toolSliderRow(id, label, val, min, max, unit, desc) {
    return '<div class="s-kv"><div><span class="s-n">' + label + "</span>" +
      '<span class="s-v" id="' + id + '-v" style="font-variant-numeric:tabular-nums;">' +
      val + unit + "</span></div>" +
      '<input type="range" id="' + id + '" min="' + min + '" max="' + max +
      '" step="1" value="' + val + '" style="width:100%;margin-top:6px;">' +
      '<p class="s-note" style="margin:2px 0 0;">' + desc + "</p></div>";
  }

  function renderToolsSim() {
    var host = document.getElementById("t-sim");
    if (!host) return;
    var cur = toolCurrentScores();
    var macro = ((D.allocation || {}).macro) || [];
    var labelOf = {"growth": "增長", "inflation": "通脹", "liquidity": "流動性", "stress": "壓力"};
    var noteOf = {
      growth: "GDP 同比、失業率與薪資成長（越高越強）",
      inflation: "CPI 與核心 PCE（越高壓力越大）",
      liquidity: "利率鬆緊、利差曲線與信用利差（越高越寬鬆）",
      stress: "VIX 與高收益利差（越高越緊張）",
    };
    var defs = {g: cur.g, i: cur.i, l: cur.l, s: cur.s, dbc: Math.round(cur.dbc)};
    host.innerHTML = '<div class="card">' +
      '<div class="s-grid2">' +
      toolSliderRow("tool-g", "增長評分", defs.g, 0, 100, "", noteOf.growth) +
      toolSliderRow("tool-i", "通脹評分", defs.i, 0, 100, "", noteOf.inflation) +
      toolSliderRow("tool-l", "流動性評分", defs.l, 0, 100, "", noteOf.liquidity) +
      toolSliderRow("tool-s", "壓力評分", defs.s, 0, 100, "", noteOf.stress) +
      toolSliderRow("tool-dbc", "商品一年報酬", defs.dbc, -40, 60, "%",
                    "DBC 過去 12 個月報酬（目前 " + (cur.dbc >= 0 ? "+" : "") +
                    cur.dbc.toFixed(1) + "%）") +
      '</div><div id="tool-result" style="margin-top:14px;"></div>' +
      '<p class="s-note" style="margin-top:10px;">規則與評分公式同配置頁：增長＝0.4×GDP＋0.3×就業＋0.3×薪資；' +
      "通脹＝0.6×CPI＋0.4×核心 PCE；流動性＝0.75×利率鬆緊與曲線＋0.25×信用利差；壓力＝0.5×VIX＋0.5×信用利差。</p></div>";
    ["tool-g", "tool-i", "tool-l", "tool-s", "tool-dbc"].forEach(function (id) {
      document.getElementById(id).addEventListener("input", function () {
        document.getElementById(id + "-v").textContent =
          id === "tool-dbc" ? (this.value >= 0 ? "+" : "") + this.value + "%" : this.value;
        toolSimResult();
        renderToolsSensitivity();
      });
    });
    toolSimResult();
  }

  function renderToolsScenarios() {
    var host = document.getElementById("t-scenarios");
    if (!host) return;
    var presets = [
      {n: "通脹回落至 2%", d: "CPI／核心 PCE 回到目標，其他評分維持現狀。",
       g: 60, i: 25, l: 58, s: 33, dbc: 0},
      {n: "衰退來臨", d: "GDP 轉負、失業率升、VIX 飆升、曲線重新陡峭化。",
       g: 25, i: 35, l: 40, s: 75, dbc: -10},
      {n: "地緣衝突升級", d: "能源價格飆升、避險情緒高漲、商品大漲。",
       g: 40, i: 75, l: 35, s: 85, dbc: 40},
      {n: "2022 重演：股債雙殺", d: "高通脹＋聯儲快速加息，股債同跌、信用利差擴大。",
       g: 45, i: 80, l: 25, s: 70, dbc: 15},
      {n: "全面中性（基準）", d: "四項評分均中性、商品平淡：回到基準 40/20/10/10/20。",
       g: 60, i: 30, l: 60, s: 30, dbc: 0},
    ];
    host.innerHTML = '<div class="card"><div style="display:flex;flex-wrap:wrap;gap:8px;">' +
      presets.map(function (p, k) {
        return '<button class="s-chip up" data-scen="' + k + '" style="cursor:pointer;border:none;" ' +
          'title="' + esc(p.d) + '">' + esc(p.n) + "</button>";
      }).join("") + "</div>" +
      '<p id="t-scen-desc" class="s-note" style="margin-top:8px;">點選情景 → 上方模擬器的滑桿自動代入該假設，配置隨即重算。</p></div>';
    host.querySelectorAll("[data-scen]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var p = presets[+this.getAttribute("data-scen")];
        [["tool-g", p.g], ["tool-i", p.i], ["tool-l", p.l],
         ["tool-s", p.s], ["tool-dbc", p.dbc]].forEach(function (kv) {
          var el = document.getElementById(kv[0]);
          el.value = kv[1];
          document.getElementById(kv[0] + "-v").textContent =
            kv[0] === "tool-dbc" ? (kv[1] >= 0 ? "+" : "") + kv[1] + "%" : kv[1];
        });
        document.getElementById("t-scen-desc").textContent = "已代入「" + p.n + "」：" + p.d;
        toolSimResult();
      });
    });
  }

  function toolCalcRender() {
    var host = document.querySelector("#t-calc-table tbody");
    if (!host || !TOOL_W) return;
    var total = parseFloat(document.getElementById("tool-total").value) || 0;
    var rows = TOOL_CLS.map(function (c) {
      var curAmt = parseFloat(document.getElementById("tool-cur-" + c).value) || 0;
      var tgt = total * TOOL_W[c] / 100;
      var diff = tgt - curAmt;
      var act = Math.abs(diff) < Math.max(1, total * 0.001) ? "—"
        : (diff > 0 ? '<span style="color:var(--good);">買入 ' +
          Math.round(diff).toLocaleString() + "</span>"
          : '<span style="color:var(--crit);">賣出 ' +
          Math.round(-diff).toLocaleString() + "</span>");
      return "<tr><td><span style='display:inline-block;width:10px;height:10px;" +
        "border-radius:2px;background:" + TOOL_COLOR[c] + ";margin-right:6px;'></span>" +
        c + "</td>" +
        '<td style="font-variant-numeric:tabular-nums;">' + Math.round(curAmt).toLocaleString() + "</td>" +
        '<td style="font-variant-numeric:tabular-nums;">' + TOOL_W[c] + "% → " +
        Math.round(tgt).toLocaleString() + "</td><td>" + act + "</td></tr>";
    }).join("");
    host.innerHTML = rows;
  }

  function renderToolsCalc() {
    var host = document.getElementById("t-calc");
    if (!host) return;
    var cur = toolCurrentScores();
    host.innerHTML = '<div class="card">' +
      '<div class="s-grid2">' +
      '<div><span class="s-n">總資產（元）</span><br>' +
      '<input type="number" id="tool-total" min="0" step="10000" value="1000000" ' +
      'style="width:100%;padding:6px 8px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg);"></div>' +
      TOOL_CLS.map(function (c) {
        return '<div><span class="s-n">目前 ' + c + " 持倉（元）</span><br>" +
          '<input type="number" id="tool-cur-' + c + '" min="0" step="10000" value="0" ' +
          'style="width:100%;padding:6px 8px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg);"></div>';
      }).join("") + "</div>" +
      '<p class="s-note" style="margin:8px 0;">目標權重＝上方模擬器目前結果（股票 ' +
      (TOOL_W ? TOOL_W["股票"] : "—") + "%／國債 " + (TOOL_W ? TOOL_W["國債"] : "—") +
      "%／商品 " + (TOOL_W ? TOOL_W["商品"] : "—") + "%／黃金 " + (TOOL_W ? TOOL_W["黃金"] : "—") +
      "%／現金 " + (TOOL_W ? TOOL_W["現金"] : "—") + "%），拖動滑桿後此表自動更新；|調整| 小於總資產 0.1% 顯示「—」。</p>" +
      '<table class="s-table" id="t-calc-table"><thead><tr><th>資產</th><th>目前金額</th>' +
      "<th>目標金額</th><th>動作</th></tr></thead><tbody></tbody></table></div>";
    ["tool-total"].concat(TOOL_CLS.map(function (c) { return "tool-cur-" + c; }))
      .forEach(function (id) {
        document.getElementById(id).addEventListener("input", toolCalcRender);
      });
    toolCalcRender();
  }

  function renderToolsBudget() {
    var host = document.getElementById("t-riskbudget");
    var rb = ((D.tools || {}).riskbudget) || null;
    if (!host) return;
    if (!rb || !rb.assets || !rb.assets.length) {
      host.innerHTML = "<p>風險預算資料暫缺（組合月報酬序列缺失）。</p>";
      return;
    }
    var rows = rb.assets.map(function (a) {
      return "<tr><td>" + esc(a.label) + "（" + esc(a.sym) + "）</td>" +
        '<td style="font-variant-numeric:tabular-nums;">' + a.w + "%</td>" +
        '<td style="font-variant-numeric:tabular-nums;">' + a.vol_ann + "%</td>" +
        '<td><div style="display:flex;align-items:center;gap:8px;">' +
        '<div style="flex:1;height:8px;border-radius:4px;background:var(--bg2);overflow:hidden;">' +
        '<div style="height:100%;width:' + Math.min(100, Math.max(0, a.contrib)) +
        '%;background:var(--brand);"></div></div>' +
        '<span style="font-variant-numeric:tabular-nums;white-space:nowrap;">' +
        a.contrib + "%</span></div></td></tr>";
    }).join("");
    host.innerHTML = '<div class="card">' +
      '<div class="s-grid2">' +
      '<div class="s-kv"><span class="s-n">組合年化波動</span>' +
      '<span class="s-v" style="font-variant-numeric:tabular-nums;">' + rb.pf_vol_ann + "%</span></div>" +
      '<div class="s-kv"><span class="s-n">歷史最大回撤（按目前權重每月再平衡）</span>' +
      '<span class="s-v" style="font-variant-numeric:tabular-nums;color:var(--crit);">' +
      rb.maxdd + "%</span></div>" +
      "</div>" +
      '<table class="s-table"><thead><tr><th>資產</th><th>權重</th><th>年化波動</th>' +
      "<th>波動貢獻（佔組合方差）</th></tr></thead><tbody>" + rows + "</tbody></table>" +
      '<p class="s-note">樣本：' + rb.n_months +
      " 個月真實月報酬（SPY／IEF／DBC／GLD／BIL）。波動貢獻＝權重 × 資產與組合的協方差 ÷ 組合方差，" +
      "各資產加總為 100%——權重大的資產不一定貢獻最多的風險。</p></div>";
  }

  function renderToolsLog() {
    var host = document.getElementById("t-log");
    var log = ((D.tools || {}).log) || [];
    if (!host) return;
    if (!log.length) {
      host.innerHTML = "<p>規則日誌暫缺（FRED 歷史序列未載入）。</p>";
      return;
    }
    var rows = log.slice().reverse().map(function (e, k) {
      var sc = e.scores;
      return "<tr" + (k === 0 ? ' style="background:var(--brand-tint);"' : "") + ">" +
        '<td style="font-variant-numeric:tabular-nums;">' + e.date + "</td>" +
        '<td style="font-variant-numeric:tabular-nums;">' + sc["增長"] + " / " + sc["通脹"] +
        " / " + sc["流動性"] + " / " + sc["壓力"] + "</td>" +
        "<td>" + (e.fired.length ? e.fired.map(esc).join("<br>")
          : '<span class="s-chip on">無觸發</span>') + "</td>" +
        '<td style="font-variant-numeric:tabular-nums;">' + TOOL_CLS.map(function (c) {
          return c + " " + e.w[c] + "%";
        }).join(" · ") + "</td></tr>";
    }).join("");
    var span = log[0].date + " → " + log[log.length - 1].date;
    host.innerHTML = '<div class="card">' +
      '<p class="s-note" style="margin:0 0 8px;">僅記錄配置發生變化的月份：共 ' + log.length +
      " 條，範圍 " + span +
      "（FRED 歷史逐月重算評分並執行同一套規則；最新一列高亮）。" +
      esc((D.tools || {}).log_note || "") + "</p>" +
      '<table class="s-table"><thead><tr><th>月份</th><th>評分（增/通/流/壓）</th>' +
      "<th>觸發規則</th><th>調整後配置</th></tr></thead><tbody>" + rows +
      "</tbody></table></div>";
  }

  function renderTools() {
    renderToolsSim();
    renderToolsScenarios();
    renderToolsCalc();
    renderToolsBudget();
    renderToolsLog();
    renderToolsSensitivity();
    applyToolsHash();
  }

  /* ---------- 模組 36：規則敏感性 ---------- */
  function renderToolsSensitivity() {
    var host = document.getElementById("t-sensitivity");
    if (!host) return;
    var base = ["tool-g", "tool-i", "tool-l", "tool-s", "tool-dbc"].map(function (id) {
      var el = document.getElementById(id);
      return el ? +el.value : null;
    });
    if (base.some(function (v) { return v == null || isNaN(v); })) {
      host.innerHTML = "<p>模擬器尚未載入。</p>";
      return;
    }
    var baseW = toolWeightsFromScores(base[0], base[1], base[2], base[3], base[4]).w;
    var names = [["tool-g", "增長評分"], ["tool-i", "通脹評分"], ["tool-l", "流動性評分"],
                 ["tool-s", "壓力評分"], ["tool-dbc", "商品一年報酬"]];
    var unit = function (id, v) { return id === "tool-dbc" ? (v >= 0 ? "+" : "") + v + "%" : v; };
    var rows = names.map(function (nm, k) {
      var cells = [-10, +10].map(function (d) {
        var v = base.slice();
        v[k] += d;
        var w = toolWeightsFromScores(v[0], v[1], v[2], v[3], v[4]).w;
        var deltas = TOOL_CLS.filter(function (c) { return w[c] !== baseW[c]; })
          .map(function (c) {
            return c + " " + (w[c] > baseW[c] ? "+" : "") + (w[c] - baseW[c]);
          });
        return '<td style="font-variant-numeric:tabular-nums;">' + unit(nm[0], v[k]) +
          (deltas.length
            ? '<br><span style="color:var(--mid);">' + deltas.join("、") + "</span>"
            : '<br><span class="s-note">配置無變化</span>') + "</td>";
      });
      return "<tr><td>" + esc(nm[1]) + "（基準 " + unit(nm[0], base[k]) + "）</td>" +
        cells.join("") + "</tr>";
    }).join("");
    host.innerHTML = '<div class="card">' +
      '<p class="s-note" style="margin:0 0 8px;">基準＝目前滑桿值（股票 ' + baseW["股票"] +
      "／國債 " + baseW["國債"] + "／商品 " + baseW["商品"] + "／黃金 " + baseW["黃金"] +
      "／現金 " + baseW["現金"] + '）。每個評分單獨 ±10、其餘不變，重跑全部規則；只列出發生變化的資產。</p>' +
      '<table class="s-table"><thead><tr><th>變動的評分</th><th>−10 後的配置變化</th>' +
      "<th>+10 後的配置變化</th></tr></thead><tbody>" + rows + "</tbody></table></div>";
  }

  /* ---------- 模組 33：匯出與分享 ---------- */
  function csvCell(c) {
    c = String(c == null ? "" : c);
    return /[",\n]/.test(c) ? '"' + c.replace(/"/g, '""') + '"' : c;
  }
  function downloadCsv(filename, lines) {
    var blob = new Blob(["﻿" + lines.map(csvCell).join("\r\n")],
                        {type: "text/csv;charset=utf-8"});
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 500);
  }
  function copyText(t, done) {
    var fallback = function () {
      var ta = document.createElement("textarea");
      ta.value = t;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand("copy"); } catch (e) {}
      ta.remove();
      done();
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(t).then(done, fallback);
    } else {
      fallback();
    }
  }
  function shareLinkFor(vals) {
    return "tools.html#tools=" + vals.map(function (v) { return Math.round(v); }).join(",");
  }
  function toolsExportState() {
    return ["tool-g", "tool-i", "tool-l", "tool-s", "tool-dbc"].map(function (id) {
      var el = document.getElementById(id);
      return el ? +el.value : null;
    });
  }
  function exportToolsCsv() {
    var v = toolsExportState();
    if (!v[0] && v[0] !== 0) return;
    var r = toolWeightsFromScores(v[0], v[1], v[2], v[3], v[4]);
    var lines = [["AIShan+ 決策工具箱匯出"], ["匯出時間", new Date().toISOString()], [""],
      ["評分", "數值"],
      ["增長", v[0]], ["通脹", v[1]], ["流動性", v[2]], ["壓力", v[3]],
      ["商品一年報酬（%）", v[4]], [""],
      ["資產", "權重（%）"]];
    TOOL_CLS.forEach(function (c) { lines.push([c, r.w[c]]); });
    lines.push([""]);
    lines.push(["觸發規則", r.fired.length ? r.fired.join("；") : "無（維持基準 40/20/10/10/20）"]);
    downloadCsv("aishan-tools-" + new Date().toISOString().slice(0, 10) + ".csv", lines);
  }
  function exportAllocCsv() {
    var A = D.allocation || {};
    var macro = A.macro || [];
    var targets = A.targets || [];
    var lines = [["AIShan+ 資產配置匯出"], ["匯出時間", new Date().toISOString()],
      ["資料截至", D.market_asof || "—"], [""],
      ["宏觀評分", "分數", "月變動"]];
    macro.forEach(function (m) {
      lines.push([m.label, m.score, m.change != null ? (m.change >= 0 ? "+" : "") + m.change : "—"]);
    });
    lines.push([""]);
    lines.push(["目標配置", "權重（%）", "代理 ETF"]);
    targets.forEach(function (t) { lines.push([t.cls, t.pct, t.proxy || "—"]); });
    lines.push([""]);
    lines.push(["觸發的規則"]);
    var rules = (D.tools || {}).rules || [];
    if (rules.length) {
      rules.forEach(function (rd) { lines.push([rd]); });
    } else {
      lines.push(["無（維持基準配置）"]);
    }
    downloadCsv("aishan-allocation-" + new Date().toISOString().slice(0, 10) + ".csv", lines);
  }
  function initExportButtons() {
    var allocHost = document.getElementById("alloc-export");
    if (allocHost) {
      allocHost.innerHTML =
        '<button class="btn primary" id="btn-alloc-csv">⬇ 匯出 CSV（評分＋配置）</button>' +
        '<button class="btn" id="btn-alloc-share">🔗 複製分享連結</button>' +
        '<span class="s-note" id="alloc-export-msg" style="align-self:center;"></span>';
      document.getElementById("btn-alloc-csv").addEventListener("click", exportAllocCsv);
      document.getElementById("btn-alloc-share").addEventListener("click", function () {
        var cur = toolCurrentScores();
        var link = shareLinkFor([cur.g, cur.i, cur.l, cur.s, Math.round(cur.dbc)]);
        copyText(link, function () {
          document.getElementById("alloc-export-msg").textContent = "已複製：" + link;
        });
      });
    }
    var toolsHost = document.getElementById("t-export");
    if (toolsHost) {
      toolsHost.innerHTML =
        '<button class="btn primary" id="btn-tools-csv">⬇ 匯出 CSV（模擬器狀態）</button>' +
        '<button class="btn" id="btn-tools-share">🔗 複製分享連結</button>' +
        '<span class="s-note" id="tools-export-msg" style="align-self:center;"></span>';
      document.getElementById("btn-tools-csv").addEventListener("click", exportToolsCsv);
      document.getElementById("btn-tools-share").addEventListener("click", function () {
        var link = shareLinkFor(toolsExportState());
        copyText(link, function () {
          document.getElementById("tools-export-msg").textContent = "已複製：" + link;
        });
      });
    }
  }
  function applyToolsHash() {
    var m = /#tools=(-?\d+(?:,-?\d+)*)/.exec(location.hash || "");
    if (!m) return;
    var v = m[1].split(",").map(function (x) { return +x; });
    if (v.length !== 5 || v.some(function (x) { return isNaN(x); })) return;
    [["tool-g", v[0], 0, 100], ["tool-i", v[1], 0, 100], ["tool-l", v[2], 0, 100],
     ["tool-s", v[3], 0, 100], ["tool-dbc", v[4], -40, 60]].forEach(function (kv) {
      var el = document.getElementById(kv[0]);
      if (!el) return;
      el.value = Math.min(kv[3], Math.max(kv[2], kv[1]));
      document.getElementById(kv[0] + "-v").textContent =
        kv[0] === "tool-dbc" ? (el.value >= 0 ? "+" : "") + el.value + "%" : el.value;
    });
    toolSimResult();
    toolCalcRender();
    renderToolsSensitivity();
    var d = document.getElementById("t-scen-desc");
    if (d) d.textContent = "已由分享連結代入評分（見上方滑桿）。";
  }

  /* ---------- 模組 29：本週市場回顧（首頁） ---------- */
  function renderMarketReview() {
    var host = document.getElementById("home-review");
    var R = D.review;
    if (!host) return;
    if (!R || !R.rows || !R.rows.length) {
      host.innerHTML = "<p>本週回顧資料暫缺（行情未抓取，請觸發更新）。</p>";
      return;
    }
    var bars = R.rows.map(function (r) {
      var w = r.w;
      return '<div style="flex:1;min-width:130px;">' +
        '<div style="display:flex;justify-content:space-between;gap:8px;">' +
        '<span class="s-n" style="font-size:12px;">' + esc(r.label) +
        ' <span class="s-note">' + esc(r.sym) + "</span></span>" +
        '<span class="s-v" style="font-size:12px;"' + pctClr(w) + ">" + pctTxt(w) + "</span></div>" +
        '<div style="height:6px;border-radius:3px;background:var(--bg2);overflow:hidden;margin-top:3px;">' +
        '<div style="height:100%;width:' + Math.min(100, Math.max(0, 50 + w * 6)) +
        "%;background:" + (w >= 0 ? "var(--good)" : "var(--crit)") + ';"></div></div></div>';
    }).join("");
    var movesHtml = R.moves.length
      ? '<ul class="judgment-list">' + R.moves.map(function (m) {
          var good = m.up_good ? (m.change >= 0) : (m.change <= 0);
          var arrow = m.change > 0 ? "▲ +" + m.change
            : m.change < 0 ? "▼ " + m.change : "＝ 0";
          return "<li><b>" + esc(m.label) + "</b> " + m.score +
            ' <span style="color:' + (m.change === 0 ? "var(--mid)"
              : good ? "var(--good)" : "var(--crit)") + ';">' + arrow +
            "</span>（較上月）</li>";
        }).join("") + "</ul>"
      : '<p class="s-note">本月四項評分無變動。</p>';
    var upHtml = R.upcoming.length
      ? '<table class="s-table"><thead><tr><th>日期</th><th>事件</th></tr></thead><tbody>' +
        R.upcoming.map(function (e) {
          var badge = e.kind === "earnings"
            ? '<span class="s-chip on">財報</span>'
            : '<span class="s-chip mid">事件</span>';
          return '<tr><td style="font-variant-numeric:tabular-nums;white-space:nowrap;">' +
            esc(e.date) + "</td><td>" + badge + " " + esc(e.label) +
            (e.ticker ? "（" + esc(e.ticker) + "）" : "") +
            (e.note ? ' <span class="s-note">' + esc(e.note) + "</span>" : "") + "</td></tr>";
        }).join("") + "</tbody></table>"
      : '<p class="s-note">未來 30 天暫無已收錄事件。</p>';
    host.innerHTML = '<div class="card" style="margin-bottom:14px;">' +
      '<div class="dash-head"><h3>📊 一週變動（核心指數與資產）</h3>' +
      '<span class="freshness">資料截至 ' + esc(R.asof || "—") + "</span></div>" +
      '<div style="display:flex;flex-wrap:wrap;gap:14px 18px;">' + bars + "</div>" +
      '<p class="s-note" style="margin-top:10px;margin-bottom:0;">' +
      esc(R.summary || "") + "走勢條為相對零軸的位置示意（非數值軸）。</p></div>" +
      '<div class="dash-grid">' +
      '<div class="card"><div class="dash-head"><h3>🌡 宏觀評分變動</h3>' +
      '<a class="more" href="allocation.html">配置 →</a></div>' + movesHtml + "</div>" +
      '<div class="card"><div class="dash-head"><h3>🗓 未來 30 天關注</h3>' +
      '<a class="more" href="events.html">事件 →</a></div>' + upHtml + "</div></div>";
  }

  /* ---------- 模組 37：評分映射說明（配置頁） ---------- */
  function renderAllocationMapping() {
    var host = document.getElementById("a-mapping");
    var M = ((D.allocation || {}).mapping) || [];
    if (!host) return;
    if (!M.length) {
      host.innerHTML = "<p>評分映射資料暫缺。</p>";
      return;
    }
    var gloss = {growth: "growth-score", inflation: "inflation-score",
                 liquidity: "liquidity-score", stress: "stress-score"};
    host.innerHTML = M.map(function (m) {
      var partRows = (m.parts || []).map(function (p) {
        return "<tr><td>" + esc(p.name) + "</td>" +
          '<td style="font-variant-numeric:tabular-nums;">' +
          (p.value == null ? "—" : p.value) + "</td>" +
          '<td style="font-variant-numeric:tabular-nums;">× ' + p.weight.toFixed(1) + "</td>" +
          '<td style="font-variant-numeric:tabular-nums;"><b>' + p.contrib + "</b></td></tr>";
      }).join("");
      return '<div class="card" style="margin-top:12px;">' +
        '<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px;">' +
        '<h3 style="margin:0;">' + esc(m.label) + " 評分" +
        ' <a href="glossary.html#' + (gloss[m.key] || "clamp") +
        '" style="font-size:12px;text-decoration:none;" title="術語表">ⓘ</a></h3>' +
        '<span class="s-chip on">總分 ' + m.score + " / 100</span></div>" +
        '<p class="s-note" style="margin:6px 0;">公式：' + esc(m.formula) + "</p>" +
        '<table class="s-table"><thead><tr><th>原始輸入</th><th>目前值</th><th>權重</th>' +
        "<th>貢獻分</th></tr></thead><tbody>" + partRows + "</tbody></table></div>";
    }).join("");
  }

  /* ---------- 模組 27：數據更新時間戳 ---------- */
  function stampPage() {
    var asof = D.market_asof;
    if (!asof) return;
    // 頁面已有任何日期徽章就不再追加，避免同一節出現兩條日期
    if (document.querySelector(".freshness")) return;
    var d = document.querySelector(".section-desc");
    if (!d) return;
    if (/資料截至|截至/.test(d.textContent || "")) return;
    var sp = document.createElement("span");
    sp.className = "freshness";
    sp.textContent = "資料截至 " + asof;
    d.appendChild(document.createTextNode(" "));
    d.appendChild(sp);
  }

  /* ---------- 啟動 ---------- */
  document.addEventListener("DOMContentLoaded", function () {
    initThemeToggle();
    initUpdateButton();
    var page = document.body.getAttribute("data-page");
    if (page === "home") { renderHome(); renderMarketReview(); }
    if (page === "companies") { initCompanies(); initTopics(); }
    if (page === "reports") initReports();
    if (page === "trackrecord") renderTrackRecord();
    if (page === "allocation") { renderAllocation(); renderFunds(); renderAllocationMapping(); initExportButtons(); }
    if (page === "fed") renderFed();
    if (page === "valuation") renderValuation();
    if (page === "events") renderEvents();
    if (page === "funds") renderF13F();
    if (page === "politician") renderPolitician();
    if (page === "china") renderChina();
    if (page === "scenarios") renderScenarios();
    if (page === "risk") renderRisk();
    if (page === "market") renderMarketPage();
    if (page === "tools") { renderTools(); initExportButtons(); }
    stampPage();
  });
  window.renderTrackRecord = renderTrackRecord;  // 主題切換時重繪

})();
