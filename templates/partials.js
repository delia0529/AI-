/* ============================================================
   AI DAILY DIGEST — interactions & live sync
   1. 氛围光斑跟随指针缓慢漂移
   2. 标签过滤 / 锚点高亮
   3. 归档抽屉 + 日期快速跳转
   4. 数据驱动同步：读取 data/index.json，自动对齐最新一期
      （标题、日期、正文、归档列表全部自动更新，无需重新构建）
   ============================================================ */
(function () {
  "use strict";

  var body = document.body;
  var BASE = body.getAttribute("data-base") || "";
  var PAGE = body.getAttribute("data-page") || "";
  var CURRENT = body.getAttribute("data-date") || "";
  var LIVE = body.getAttribute("data-live") === "1"; // 仅首页会自动跟随最新一期

  var PRIO = { high: "高优先", mid: "常规", low: "观察" };

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c];
    });
  }

  function loadJSON(url) {
    if (location.protocol === "file:") return Promise.resolve(null);
    return fetch(url, { cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .catch(function () { return null; });
  }

  /* ---------------------------------------------------------- 渲染器 */

  function itemHTML(mod, it, i) {
    var tags = it.tags || [];
    return (
      '<article class="item" id="' + esc(it.id || mod.id + "-" + i) + '" data-tags="' + esc(tags.join("|")) + '">' +
        '<div class="item-top">' +
          '<span class="item-no">' + esc(mod.index) + "·" + ("0" + i).slice(-2) + "</span>" +
          '<span class="item-prio" data-level="' + esc(it.priority || "mid") + '">' + esc(PRIO[it.priority] || "常规") + "</span>" +
        "</div>" +
        '<h3 class="item-title">' + esc(it.title) + "</h3>" +
        '<div class="item-cat">' + esc(it.category) + "</div>" +
        '<div class="item-body">' +
          '<div class="field"><div class="field-k">核心事实</div><p class="field-v">' + esc(it.facts) + "</p></div>" +
          '<div class="field field-insight"><div class="field-k">深度洞察</div><p class="field-v">' + esc(it.insight) + "</p></div>" +
        "</div>" +
        '<div class="item-foot">' +
          '<div class="item-tags">' + tags.map(function (t) { return '<span class="tag">' + esc(t) + "</span>"; }).join("") + "</div>" +
          '<div class="item-entities">关联：' + esc((it.entities || []).join("、")) + "</div>" +
          '<div class="item-sources">' + (it.sources || []).map(function (s) {
            return '<a href="' + esc(s.url) + '" target="_blank" rel="noopener">' + esc(s.name) + "</a>";
          }).join("") + "</div>" +
        "</div>" +
      "</article>"
    );
  }

  function moduleHTML(m) {
    return (
      '<section class="module" id="' + esc(m.id) + '">' +
        '<div class="module-head">' +
          '<span class="module-index">' + esc(m.index) + "</span>" +
          '<h2 class="module-name">' + esc(m.name) + "</h2>" +
          '<span class="module-en">' + esc(m.en) + "</span>" +
        "</div>" +
        '<p class="module-note">' + esc(m.note) + "</p>" +
        (m.items || []).map(function (it, i) { return itemHTML(m, it, i + 1); }).join("") +
        '<div class="watch">' +
          '<div class="watch-title">长期观察 Watchlist · ' + esc(m.en) + "</div>" +
          (m.watchlist || []).map(function (w) {
            return '<div class="watch-row"><b>' + esc(w.k) + "</b><span>" + esc(w.v) + "</span></div>";
          }).join("") +
        "</div>" +
      "</section>"
    );
  }

  function drawerHTML(issues) {
    return issues.map(function (it) {
      return '<a class="drawer-item" href="' + BASE + "archive/" + esc(it.date) + '.html">' +
        '<div class="d1">' + esc(it.date) + " · " + esc(it.weekday) + " · " + esc(it.items) + " 条</div>" +
        '<div class="d2">' + esc(it.headline) + "</div>" +
        '<div class="d3">' + esc(it.deck) + "</div>" +
      "</a>";
    }).join("");
  }

  function archiveRowsHTML(issues) {
    return issues.map(function (it) {
      var hay = [it.date, it.weekday, it.headline, it.deck, (it.tags || []).join(" ")].join(" ");
      return '<a class="arch-row" href="' + BASE + esc(it.url) + '"' +
        ' data-tags="' + esc((it.tags || []).join("|")) + '"' +
        ' data-month="' + esc(it.date.slice(0, 7)) + '"' +
        ' data-hay="' + esc(hay) + '">' +
        '<div class="arch-date">' + esc(it.date) + "<small>" + esc(it.weekday) + " · " + esc(it.issue) + "</small></div>" +
        "<div><h2 class=\"arch-h\">" + esc(it.headline) + "</h2><p class=\"arch-d\">" + esc(it.deck) + "</p></div>" +
        '<div class="arch-stat">' + esc(it.items) + " 条 / " + esc(it.sources) + " 源</div>" +
      "</a>";
    }).join("");
  }

  /* ---------------------------------------------------------- 交互绑定 */

  function bindTagFilter() {
    var cloud = document.querySelector("[data-tag-cloud]");
    var items = Array.prototype.slice.call(document.querySelectorAll(".item[data-tags]"));
    if (!cloud || !items.length) return;
    var counter = document.querySelector("[data-filter-count]");
    var active = null;

    function apply() {
      var shown = 0;
      items.forEach(function (el) {
        var tags = (el.getAttribute("data-tags") || "").split("|");
        var hit = !active || tags.indexOf(active) > -1;
        el.classList.toggle("is-hidden", !hit);
        if (hit) shown++;
      });
      if (counter) counter.textContent = active ? shown + " / " + items.length : String(items.length);
    }

    cloud.addEventListener("click", function (e) {
      var btn = e.target.closest(".tag");
      if (!btn) return;
      var tag = btn.getAttribute("data-tag");
      active = active === tag ? null : tag;
      Array.prototype.forEach.call(cloud.querySelectorAll(".tag"), function (b) {
        b.classList.toggle("is-on", b.getAttribute("data-tag") === active);
      });
      apply();
    });

    var reset = document.querySelector("[data-tag-reset]");
    if (reset) {
      reset.addEventListener("click", function () {
        active = null;
        Array.prototype.forEach.call(cloud.querySelectorAll(".tag"), function (b) { b.classList.remove("is-on"); });
        apply();
      });
    }
    apply();
  }

  function bindScrollSpy() {
    var links = Array.prototype.slice.call(document.querySelectorAll(".anchor-list a[href^='#']"));
    if (!links.length || !("IntersectionObserver" in window)) return;
    var map = {};
    links.forEach(function (a) { map[a.getAttribute("href").slice(1)] = a; });
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) {
          links.forEach(function (a) { a.classList.remove("is-active"); });
          var a = map[en.target.id];
          if (a) a.classList.add("is-active");
        }
      });
    }, { rootMargin: "-96px 0px -68% 0px", threshold: 0 });
    Object.keys(map).forEach(function (id) {
      var el = document.getElementById(id);
      if (el) io.observe(el);
    });
  }

  /* ---------------------------------------------------------- 应用最新一期 */

  function applyDigest(day) {
    var stream = document.querySelector(".stream");
    if (!stream || !day || !day.modules) return;

    stream.innerHTML = day.modules.slice().sort(function (a, b) {
      return String(a.index).localeCompare(String(b.index));
    }).map(moduleHTML).join("");

    var eyebrow = document.querySelector(".hero-eyebrow span");
    if (eyebrow) eyebrow.textContent = day.date.replace(/^(\d{4})-(\d{2})-(\d{2})$/, "$1年$2月$3日") +
      (day.weekday ? " · " + day.weekday : "");
    var title = document.querySelector(".hero-title");
    if (title) title.textContent = day.headline;
    var deck = document.querySelector(".hero-deck");
    if (deck) deck.textContent = day.deck;

    var stats = day.stats || {};
    var nums = document.querySelectorAll(".hero-meta b");
    if (nums.length >= 5) {
      nums[0].textContent = stats.sources || 0;
      nums[1].textContent = stats.raw || 0;
      nums[2].textContent = stats.clusters || 0;
      nums[3].textContent = stats.items || 0;
      nums[4].textContent = stats.dedupe_rate || "—";
    }

    // 左侧目录与标签云跟随最新一期重建
    var anchorList = document.querySelector(".anchor-list");
    if (anchorList) {
      anchorList.innerHTML = day.modules.map(function (m) {
        return '<li><a href="#' + esc(m.id) + '"><i>' + esc(m.index) + "</i><span>" + esc(m.name) + "</span></a></li>";
      }).join("");
    }
    var cloud = document.querySelector("[data-tag-cloud]");
    if (cloud) {
      var seen = [];
      day.modules.forEach(function (m) {
        (m.items || []).forEach(function (it) {
          (it.tags || []).forEach(function (t) { if (seen.indexOf(t) === -1) seen.push(t); });
        });
      });
      cloud.innerHTML = seen.map(function (t) {
        return '<button class="tag" data-tag="' + esc(t) + '">' + esc(t) + "</button>";
      }).join("");
    }

    document.title = day.date + " · AI 趋势日报 " + (day.issue || "");
    body.setAttribute("data-date", day.date);

    bindTagFilter();
    bindScrollSpy();
  }

  function syncJumper(issues) {
    var jumper = document.querySelector("[data-jumper]");
    if (!jumper) return;
    var value = jumper.value;
    jumper.innerHTML = issues.map(function (it) {
      return '<option value="' + esc(it.date) + '"' + (it.date === (value || CURRENT) ? " selected" : "") +
        ">" + esc(it.date) + " · " + esc(it.weekday) + "</option>";
    }).join("");
  }

  function syncDrawer(issues) {
    var box = document.querySelector("#drawer .drawer-body");
    if (box) box.innerHTML = drawerHTML(issues);
    var foot = document.querySelector("#drawer .drawer-foot");
    if (foot) foot.innerHTML = '共 ' + issues.length + ' 期 · <a href="' + BASE + 'archive.html" style="color:inherit">查看全部归档 →</a>';
  }

  /* ---------------------------------------------------------- 归档页：自动累积 */

  function renderArchive(issues) {
    var list = document.getElementById("arch-list");
    if (!list) return;
    var empty = document.getElementById("arch-empty");
    if (empty) list.appendChild(empty);
    var rows = archiveRowsHTML(issues);
    var holder = document.getElementById("arch-rows");
    if (!holder) {
      holder = document.createElement("div");
      holder.id = "arch-rows";
      list.insertBefore(holder, list.firstChild);
    }
    holder.innerHTML = rows;
    var spans = document.querySelectorAll(".hero-eyebrow span");
    if (spans.length > 1) spans[1].textContent = "共 " + issues.length + " 期";

    // 月份下拉跟随数据重建
    var month = document.querySelector("[data-arch-month]");
    if (month) {
      var keep = month.value;
      var months = [];
      issues.forEach(function (it) {
        var m = it.date.slice(0, 7);
        if (months.indexOf(m) === -1) months.push(m);
      });
      months.sort().reverse();
      month.innerHTML = '<option value="">全部月份</option>' + months.map(function (m) {
        return '<option value="' + m + '">' + m.slice(0, 4) + " 年 " + parseInt(m.slice(5), 10) + " 月</option>";
      }).join("");
      month.value = keep;
    }
    // 标签云跟随数据重建
    var cloud = document.querySelector("[data-arch-tags]");
    if (cloud) {
      var tags = [];
      issues.forEach(function (it) {
        (it.tags || []).forEach(function (t) { if (tags.indexOf(t) === -1) tags.push(t); });
      });
      cloud.innerHTML = tags.map(function (t) {
        return '<button class="tag" data-tag="' + esc(t) + '">' + esc(t) + "</button>";
      }).join("");
    }
    bindArchiveFilters();
  }

  /* ---------------------------------------------------------- 归档页筛选 */

  function bindArchiveFilters() {
    var list = document.getElementById("arch-list");
    if (!list) return;
    var search = document.querySelector("[data-arch-search]");
    var month = document.querySelector("[data-arch-month]");
    var cloud = document.querySelector("[data-arch-tags]");
    var empty = document.getElementById("arch-empty");
    var active = null;

    function apply() {
      var rows = Array.prototype.slice.call(list.querySelectorAll(".arch-row"));
      var q = (search && search.value ? search.value : "").trim().toLowerCase();
      var m = month && month.value ? month.value : "";
      var shown = 0;
      rows.forEach(function (row) {
        var hay = (row.getAttribute("data-hay") || "").toLowerCase();
        var ok = true;
        if (q && hay.indexOf(q) === -1) ok = false;
        if (ok && m && row.getAttribute("data-month") !== m) ok = false;
        if (ok && active && (row.getAttribute("data-tags") || "").split("|").indexOf(active) === -1) ok = false;
        row.classList.toggle("is-hidden", !ok);
        if (ok) shown++;
      });
      if (empty) empty.style.display = shown ? "none" : "block";
    }

    if (search) { search.oninput = apply; }
    if (month) { month.onchange = apply; }
    if (cloud) {
      cloud.onclick = function (e) {
        var btn = e.target.closest(".tag");
        if (!btn) return;
        var tag = btn.getAttribute("data-tag");
        active = active === tag ? null : tag;
        Array.prototype.forEach.call(cloud.querySelectorAll(".tag"), function (b) {
          b.classList.toggle("is-on", b.getAttribute("data-tag") === active);
        });
        apply();
      };
    }
    apply();
  }

  /* ---------------------------------------------------------- 探测未收录的新期次 */

  function probeNewIssues(index) {
    var issues = (index && index.issues) ? index.issues.slice() : [];
    if (!issues.length) return Promise.resolve(issues);
    var latest = issues[0].date;
    var start = new Date(latest + "T00:00:00");
    var today = new Date();
    var probes = [];
    var d = new Date(start.getTime());
    while (probes.length < 7) {
      d.setDate(d.getDate() + 1);
      if (d > today) break;
      probes.push(d.toISOString().slice(0, 10));
    }
    if (!probes.length) return Promise.resolve(issues);

    return Promise.all(probes.map(function (date) {
      return loadJSON(BASE + "data/" + date + ".json").then(function (day) {
        if (!day || !day.date) return null;
        var tags = [];
        var items = 0;
        (day.modules || []).forEach(function (m) {
          (m.items || []).forEach(function (it) {
            items++;
            (it.tags || []).forEach(function (t) { if (tags.indexOf(t) === -1) tags.push(t); });
          });
        });
        return {
          date: day.date, issue: day.issue || "", weekday: day.weekday || "",
          headline: day.headline || "", deck: day.deck || "", items: items,
          sources: (day.stats || {}).sources || 0,
          url: "archive/" + day.date + ".html", tags: tags
        };
      });
    })).then(function (found) {
      var added = found.filter(Boolean);
      if (!added.length) return issues;
      var map = {};
      added.concat(issues).forEach(function (it) { map[it.date] = it; });
      return Object.keys(map).sort().reverse().map(function (k) { return map[k]; });
    });
  }

  /* ---------------------------------------------------------- 启动同步 */

  function boot() {
    loadJSON(BASE + "data/index.json").then(function (index) {
      if (!index || !index.issues) return null;
      return probeNewIssues(index).then(function (issues) {
        index.issues = issues;
        return index;
      });
    }).then(function (index) {
      if (!index || !index.issues || !index.issues.length) return;

      syncJumper(index.issues);
      syncDrawer(index.issues);

      if (PAGE === "archive") {
        renderArchive(index.issues);
        return;
      }

      // 历史快照页保持原样，只同步跳转器与归档抽屉
      if (!LIVE) return;

      document.title = index.latest + " · AI 趋势日报";
      if (index.latest === CURRENT) {
        var current = index.issues.filter(function (i) { return i.date === CURRENT; })[0];
        if (current) document.title = current.date + " · AI 趋势日报 " + (current.issue || "");
        return;
      }
      // 有更新的期次：直接在本页渲染最新一期，保证「打开即最新」
      loadJSON(BASE + "data/" + index.latest + ".json").then(function (day) {
        if (day && day.modules) applyDigest(day);
        else window.location.href = BASE + "archive/" + index.latest + ".html";
      });
    });
  }

  /* ---------------------------------------------------------- 氛围光斑 */

  (function () {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    var shell = document.querySelector(".page-shell");
    if (!shell) return;
    var raf = null, tx = 0, ty = 0;
    window.addEventListener("pointermove", function (e) {
      tx = (e.clientX / window.innerWidth - 0.62) * -34;
      ty = (e.clientY / window.innerHeight - 0.5) * -26;
      if (raf) return;
      raf = requestAnimationFrame(function () {
        shell.style.setProperty("--gx", tx.toFixed(2) + "px");
        shell.style.setProperty("--gy", ty.toFixed(2) + "px");
        raf = null;
      });
    }, { passive: true });
  })();

  /* ---------------------------------------------------------- 抽屉与跳转器 */

  (function () {
    var drawer = document.getElementById("drawer");
    var mask = document.getElementById("drawer-mask");
    var openBtn = document.querySelector("[data-drawer-open]");
    var closeBtn = document.querySelector("[data-drawer-close]");
    if (!drawer || !mask || !openBtn) return;

    function open() { drawer.classList.add("is-open"); mask.classList.add("is-open"); drawer.setAttribute("aria-hidden", "false"); }
    function close() { drawer.classList.remove("is-open"); mask.classList.remove("is-open"); drawer.setAttribute("aria-hidden", "true"); }
    openBtn.addEventListener("click", open);
    if (closeBtn) closeBtn.addEventListener("click", close);
    mask.addEventListener("click", close);
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") close(); });

    var jumper = document.querySelector("[data-jumper]");
    if (jumper) {
      jumper.addEventListener("change", function () {
        if (jumper.value) window.location.href = BASE + "archive/" + jumper.value + ".html";
      });
    }
  })();

  bindTagFilter();
  bindScrollSpy();
  bindArchiveFilters();
  boot();
})();
