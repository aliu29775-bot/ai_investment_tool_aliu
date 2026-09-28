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
    var asof = document.getElementById("home-alloc-asof");
    if (asof) {
      var d0 = D.market_asof || (D.market && D.market.SPY && D.market.SPY.asof) || A.asof;
      if (d0) asof.textContent = "⏱ 行情更新於 " + d0;
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

  /* ---------- 13F 頂級基金追蹤頁（模組 6） ---------- */
  function renderF13F() {
    if (document.body.getAttribute("data-page") !== "funds") return;
    renderHedgeFunds();
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
      btn.disabled = true;
      setMsg("⏳ 正在觸發更新…", "warn");
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
        } else {
          setMsg("⚠ 觸發失敗（HTTP " + xhr.status + "），請稍後重試", "err");
        }
      };
      xhr.onerror = function () { btn.disabled = false; setMsg("⚠ 網絡錯誤，請稍後重試", "err"); };
      xhr.send();
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

  /* ---------- 啟動 ---------- */
  document.addEventListener("DOMContentLoaded", function () {
    initThemeToggle();
    initUpdateButton();
    var page = document.body.getAttribute("data-page");
    if (page === "home") renderHome();
    if (page === "companies") { initCompanies(); initTopics(); }
    if (page === "reports") initReports();
    if (page === "trackrecord") renderTrackRecord();
    if (page === "allocation") { renderAllocation(); renderFunds(); }
    if (page === "fed") renderFed();
    if (page === "valuation") renderValuation();
    if (page === "events") renderEvents();
    if (page === "funds") renderF13F();
  });
  window.renderTrackRecord = renderTrackRecord;  // 主題切換時重繪
})();
