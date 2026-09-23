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
        '<div class="item-shots">' + (it.images || []).filter(function (im) { return im.url; }).map(function (im) {
          return '<figure class="shot">' +
            '<a href="' + esc(im.link || im.url) + '" target="_blank" rel="noopener">' +
            '<img src="' + esc(im.url) + '" alt="' + esc(im.caption || "") + '" loading="lazy" ' +
            'onerror="this.closest(\'.shot\').style.display=\'none\'"></a>' +
            "<figcaption>" + esc(im.caption || "") + "<span> · 图源 " + esc(im.credit || "") + "</span></figcaption>" +
          "</figure>";
        }).join("") + "</div>" +
        '<div class="item-foot">' +
          '<div class="item-tags">' + tags.map(function (t) { return '<span class="tag">' + esc(t) + "</span>"; }).join("") + "</div>" +
          '<div class="item-entities">关联：' + esc((it.entities || []).join("、")) + "</div>" +
          '<div class="item-sources"><span class="foot-label">来源</span>' + (it.sources || []).map(function (s) {
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
          '<button class="mod-read" data-read-module="' + esc(m.id) + '" aria-label="朗读本模块">朗读本节</button>' +
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

  function domainOf(url) {
    try {
      return new URL(url).hostname.replace(/^www\./, "");
    } catch (e) {
      return String(url || "").replace(/^https?:\/\//, "").split("/")[0];
    }
  }

  /* 本期信源清单：把当天所有引用去重汇总，保证每条内容都能回溯到原文 */
  function renderSources(day) {
    var grid = document.querySelector("[data-sources-grid]");
    if (!grid) return;
    var map = {};
    (day.modules || []).forEach(function (m) {
      (m.items || []).forEach(function (it) {
        (it.sources || []).forEach(function (s) {
          if (!s.url) return;
          if (!map[s.url]) {
            map[s.url] = { name: s.name || domainOf(s.url), url: s.url, domain: domainOf(s.url), count: 0 };
          }
          map[s.url].count++;
        });
      });
    });
    var list = Object.keys(map).map(function (k) { return map[k]; });
    list.sort(function (a, b) {
      return b.count - a.count || a.domain.localeCompare(b.domain);
    });
    var section = document.getElementById("sources");
    if (section) section.style.display = list.length ? "" : "none";
    grid.innerHTML = list.map(function (s) {
      return '<a class="src-item" href="' + esc(s.url) + '" target="_blank" rel="noopener">' +
        "<b>" + esc(s.name) + "</b><span>" + esc(s.domain) + " · 引用 " + s.count + " 次</span></a>";
    }).join("");
  }

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

    renderSources(day);
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

  /* ---------------------------------------------------------- 朗读播报 */
  /* 使用浏览器内置 Web Speech API 在本地合成，不调用任何外部服务，也没有预生成音频。 */

  (function () {
    if (!("speechSynthesis" in window) || !("SpeechSynthesisUtterance" in window)) return;

    var bar = document.getElementById("reader");
    if (!bar) return;
    var stateEl = bar.querySelector("[data-read-state]");
    var progEl = bar.querySelector("[data-read-progress]");
    var toggleBtn = bar.querySelector("[data-read-toggle]");
    var stopBtn = bar.querySelector("[data-read-stop]");
    var rateSel = bar.querySelector("[data-read-rate]");
    var seekEl = bar.querySelector("[data-read-seek]");
    var previewEl = bar.querySelector("[data-read-preview]");
    var ticksEl = bar.querySelector("[data-read-ticks]");
    var chapterEl = bar.querySelector("[data-read-chapter]");

    var queue = [];
    var idx = -1;
    var stopped = true;
    var paused = false;
    var lastEl = null;
    var voice = null;
    var chapters = [];

    /* 统一挑选「标准普通话 · 女声」，PC 与移动端尽量一致 */
    var FEMALE_HINT = [
      "tingting", "婷婷", "meijia", "美佳", "huihui", "慧慧", "yaoyao", "yaoyi",
      "xiaoxiao", "晓晓", "xiaoyi", "晓伊", "xiaoqi", "female", "女声", "普通话（中国大陆）",
      "google 普通话", "chinese (simplified)", "mandarin"
    ];
    var MALE_HINT = [
      "kangkang", "康康", "yunxi", "云希", "yunyang", "云扬", "yunye", "liang",
      "daniel", "male", "男声"
    ];
    var DIALECT_HINT = ["yue", "cantonese", "粤语", "台湾", "tw", "hk", "hakka", "minnan"];

    function scoreVoice(v) {
      var name = String(v.name || "").toLowerCase();
      var lang = String(v.lang || "").toLowerCase().replace("_", "-");
      var score = 0;

      if (/^zh-cn|^cmn-hans-cn|^zh-hans/.test(lang)) score += 6;
      else if (/^zh-tw|^zh-hk|^cmn-hant/.test(lang)) score += 2;
      else if (/^zh|^cmn/.test(lang)) score += 3;
      else if (/chinese|普通话|中文/.test(name)) score += 2;
      else score -= 8; // 非中文音色直接淘汰

      for (var i = 0; i < FEMALE_HINT.length; i++) {
        if (name.indexOf(FEMALE_HINT[i]) !== -1) { score += 5; break; }
      }
      for (var j = 0; j < MALE_HINT.length; j++) {
        if (name.indexOf(MALE_HINT[j]) !== -1) { score -= 6; break; }
      }
      for (var k = 0; k < DIALECT_HINT.length; k++) {
        if (name.indexOf(DIALECT_HINT[k]) !== -1 || lang.indexOf(DIALECT_HINT[k]) !== -1) {
          score -= 4;
          break;
        }
      }
      if (v.localService) score += 1;
      return score;
    }

    function pickVoice() {
      var vs = window.speechSynthesis.getVoices() || [];
      if (!vs.length) return null;
      var best = null;
      var bestScore = -Infinity;
      vs.forEach(function (v) {
        var s = scoreVoice(v);
        if (s > bestScore) {
          bestScore = s;
          best = v;
        }
      });
      return best;
    }

    function refreshVoice() {
      voice = pickVoice();
    }
    refreshVoice();
    if (typeof window.speechSynthesis.onvoiceschanged !== "undefined") {
      window.speechSynthesis.onvoiceschanged = refreshVoice;
    }

    /* 标点符号不朗读：去掉中英文标点与装饰符号，保留字母、数字、小数点和连字符
       （GPT-6 / Opus 5.5 / $0.10 这类需要保留原形） */
    /* 保留 . - $ % 与字母数字，保证 Opus 5.5 / GPT-6 / $0.10 / 42% 读得出来 */
    var PUNCT = /[，。、；：！？…～·ˉˇ¨‘’“”〝〞（）【】《》〈〉「」『』〔〕｛｝［］﹃﹄〖〗＃＠＆＊＝＋／＼｜~^_*&@#<>{}\[\]\/\\'"!?,;:]/g;

    function clean(text) {
      return String(text || "")
        .replace(PUNCT, " ")
        .replace(/\s+/g, " ")
        .trim();
    }

    function chunk(text) {
      var src = String(text || "").replace(/\s+/g, " ").trim();
      var out = [];
      var buf = "";
      for (var i = 0; i < src.length; i++) {
        buf += src.charAt(i);
        if (/[。！？；;!?]/.test(src.charAt(i)) && buf.length >= 30) {
          out.push(clean(buf));
          buf = "";
        } else if (buf.length >= 170) {
          out.push(clean(buf));
          buf = "";
        }
      }
      if (buf.trim()) out.push(clean(buf));
      return out.filter(function (t) { return t.length > 0; });
    }

    function push(el, text) {
      chunk(text).forEach(function (piece) {
        queue.push({ text: piece, el: el });
      });
    }

    function txtOf(el) {
      return el ? String(el.textContent || "").replace(/\s+/g, " ").trim() : "";
    }

    /* 严格按页面 DOM 的可见顺序取文本，保证朗读内容与正文一一对应 */
    function buildQueue(scope) {
      queue = [];
      chapters = [];

      if (!scope) {
        chapters.push({ start: 0, label: "今日综述", num: "00" });
        var eyebrow = document.querySelector(".hero-eyebrow");
        var title = document.querySelector(".hero-title");
        var deck = document.querySelector(".hero-deck");
        if (txtOf(eyebrow)) push(eyebrow, txtOf(eyebrow));
        if (txtOf(title)) push(title, txtOf(title));
        if (txtOf(deck)) push(deck, txtOf(deck));
      }

      var modules = scope
        ? [scope]
        : Array.prototype.slice.call(document.querySelectorAll(".module"));

      modules.forEach(function (m) {
        var name = m.querySelector(".module-name");
        var index = m.querySelector(".module-index");
        chapters.push({
          start: queue.length,
          label: ((index && txtOf(index) ? txtOf(index) + " " : "") +
                  (name ? txtOf(name) : "模块")),
          num: (index && txtOf(index) ? txtOf(index) : "00")
        });

        if (txtOf(name)) push(m, txtOf(name));
        var note = m.querySelector(".module-note");
        if (txtOf(note)) push(m, txtOf(note));

        Array.prototype.forEach.call(m.querySelectorAll(".item"), function (it) {
          var t = it.querySelector(".item-title");
          if (txtOf(t)) push(it, txtOf(t));
          var cat = it.querySelector(".item-cat");
          if (txtOf(cat)) push(it, txtOf(cat));
          // 核心事实 / 深度洞察：标题来自页面上的字段名，顺序与页面一致
          Array.prototype.forEach.call(it.querySelectorAll(".field"), function (f) {
            var k = f.querySelector(".field-k");
            var v = f.querySelector(".field-v");
            if (txtOf(v)) push(it, (txtOf(k) ? txtOf(k) + " " : "") + txtOf(v));
          });
          var ent = it.querySelector(".item-entities");
          if (txtOf(ent)) push(it, txtOf(ent));
        });

        // 模块底部的长期观察清单也纳入朗读
        var watch = m.querySelector(".watch");
        if (watch) {
          var wt = watch.querySelector(".watch-title");
          if (txtOf(wt)) push(m, txtOf(wt));
          Array.prototype.forEach.call(watch.querySelectorAll(".watch-row"), function (row) {
            var k = row.querySelector("b");
            var v = row.querySelector("span");
            push(m, (txtOf(k) ? txtOf(k) + " " : "") + txtOf(v));
          });
        }
      });
    }

    function clearMarks() {
      var marked = document.querySelectorAll(".is-reading");
      Array.prototype.forEach.call(marked, function (el) { el.classList.remove("is-reading"); });
    }

    /* 把某个分片对应的正文锚定到视口中央并高亮 */
    function mark(i, force) {
      var q = queue[i];
      if (!q || !q.el) return;
      if (q.el !== lastEl || force) {
        clearMarks();
        q.el.classList.add("is-reading");
        lastEl = q.el;
      }
      try {
        q.el.scrollIntoView({ block: "center", behavior: "smooth" });
      } catch (e) {
        q.el.scrollIntoView();
      }
    }

    function updateUI() {
      var total = queue.length;
      if (progEl) progEl.textContent = total ? Math.min(idx + 1, total) + " / " + total : "";
      if (stateEl) stateEl.textContent = paused ? "已暂停" : "朗读中";
      if (toggleBtn) toggleBtn.textContent = paused ? "▶" : "❚❚";
      if (seekEl) {
        seekEl.max = Math.max(0, total - 1);
        seekEl.value = Math.max(0, Math.min(idx, Math.max(0, total - 1)));
      }
      if (previewEl) {
        var cur = queue[idx];
        var text = cur ? cur.text.replace(/\s+/g, " ") : "";
        previewEl.textContent = text.length > 34 ? text.slice(0, 34) + "…" : text;
        if (cur) previewEl.title = text;
      }

      // 当前所属章节：高亮对应锚点并显示章节名
      var curChapter = 0;
      for (var c = 0; c < chapters.length; c++) {
        if (chapters[c].start <= idx) curChapter = c;
      }
      if (chapterEl) chapterEl.textContent = chapters.length ? chapters[curChapter].label : "";
      if (ticksEl) {
        var ticks = ticksEl.children;
        for (var t = 0; t < ticks.length; t++) {
          var on = parseInt(ticks[t].getAttribute("data-chapter"), 10) === curChapter;
          ticks[t].classList.toggle("is-current", on);
        }
      }
    }

    /* 在进度条上渲染章节锚点：编号与左侧目录一致，位置按滑块可移动区间换算 */
    function renderTicks() {
      if (!ticksEl) return;
      ticksEl.innerHTML = "";
      var last = Math.max(1, queue.length - 1);
      chapters.forEach(function (ch, i) {
        var ratio = Math.min(1, ch.start / last);
        var tick = document.createElement("button");
        tick.type = "button";
        tick.className = "reader-tick";
        tick.setAttribute("data-chapter", String(i));
        tick.setAttribute("data-start", String(ch.start));
        tick.setAttribute("aria-label", "跳转到 " + ch.label);
        tick.title = ch.label;
        tick.style.left = "calc(8px + " + ratio.toFixed(4) + " * (100% - 16px))";
        tick.innerHTML =
          '<span class="tick-line"></span><span class="tick-num">' + esc(ch.num || "") + "</span>";
        ticksEl.appendChild(tick);
      });
    }

    function speakAt(i) {
      if (stopped) return;
      if (i >= queue.length) {
        stop();
        return;
      }
      idx = i;
      mark(i);
      var q = queue[i];
      var u = new window.SpeechSynthesisUtterance(q.text);
      u.lang = (voice && voice.lang) ? voice.lang : "zh-CN";
      if (voice) u.voice = voice;
      u.rate = parseFloat((rateSel && rateSel.value) || "1");
      u.onend = function () {
        if (!stopped) speakAt(i + 1);
      };
      u.onerror = function () {
        if (!stopped) speakAt(i + 1);
      };
      window.speechSynthesis.speak(u);
      updateUI();
    }

    function start(scope) {
      refreshVoice(); // 移动端音色列表常异步到达，每次开读前重新挑一次
      if (stateEl) {
        var ok = voice && scoreVoice(voice) >= 0;
        stateEl.title = voice
          ? (ok ? voice.name : "未检测到中文音色：" + voice.name + "（建议在系统里安装普通话语音）")
          : "未检测到可用音色";
        if (!ok && window.console && console.warn) {
          console.warn("[AI 日报] 未找到中文女声音色，请在系统中安装「普通话」语音包");
        }
      }
      window.speechSynthesis.cancel();
      buildQueue(scope || null);
      if (!queue.length) return;
      renderTicks();
      stopped = false;
      paused = false;
      lastEl = null;
      bar.hidden = false;
      speakAt(0);
    }

    /* 跳转到第 i 段：朗读中则继续读，暂停/停止则只锚定 */
    function seekTo(i) {
      if (!queue.length) return;
      idx = Math.max(0, Math.min(i, queue.length - 1));
      if (stopped) {
        mark(idx, true);
        updateUI();
        return;
      }
      window.speechSynthesis.cancel();
      paused = false;
      speakAt(idx);
    }

    function stop() {
      stopped = true;
      paused = false;
      window.speechSynthesis.cancel();
      clearMarks();
      lastEl = null;
      bar.hidden = true;
      updateUI();
    }

    if (toggleBtn) {
      toggleBtn.addEventListener("click", function () {
        if (stopped) return;
        if (paused) {
          window.speechSynthesis.resume();
          paused = false;
        } else {
          window.speechSynthesis.pause();
          paused = true;
        }
        updateUI();
      });
    }
    if (stopBtn) stopBtn.addEventListener("click", stop);

    /* 拖动进度条：拖动过程中暂停并实时锚定正文，松手后从新位置继续朗读 */
    if (seekEl) {
      seekEl.addEventListener("input", function () {
        var v = parseInt(seekEl.value, 10) || 0;
        if (!queue.length) return;
        idx = Math.max(0, Math.min(v, queue.length - 1));
        if (!stopped) window.speechSynthesis.pause();
        mark(idx, true);
        updateUI();
      });
      seekEl.addEventListener("change", function () {
        seekTo(parseInt(seekEl.value, 10) || 0);
      });
    }

    /* 点击章节锚点直接跳到该章节开头 */
    if (ticksEl) {
      ticksEl.addEventListener("click", function (e) {
        var tick = e.target.closest(".reader-tick");
        if (!tick) return;
        seekTo(parseInt(tick.getAttribute("data-start"), 10) || 0);
      });
    }
    if (rateSel) {
      rateSel.addEventListener("change", function () {
        if (stopped) return;
        // 变速需要重读当前段
        var at = Math.max(0, idx);
        window.speechSynthesis.cancel();
        stopped = false;
        paused = false;
        speakAt(at);
      });
    }

    document.addEventListener("click", function (e) {
      if (e.target.closest("[data-read-start]")) {
        start(null);
        return;
      }
      var mod = e.target.closest("[data-read-module]");
      if (mod) {
        var el = document.getElementById(mod.getAttribute("data-read-module"));
        if (el) start(el);
      }
    });

    window.addEventListener("pagehide", stop);
    window.addEventListener("beforeunload", stop);
  })();

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
