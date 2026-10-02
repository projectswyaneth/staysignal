/* StaySignal console
   The risk score on this page is not pre-computed. models/model.json holds the
   weights learned by ml/train.py, and the four functions below run that model
   in the browser for whichever customer you click. */

(function () {
  "use strict";

  const DATA = window.STAYSIGNAL;
  const M = DATA.model;
  const CUSTOMERS = DATA.customers;
  const TOWN_XY = DATA.townXY;

  const MAP_PATH = "M67.4,47.2L51.7,49.9L38.8,32.8L36.0,25.2L38.8,20.2L42.5,17.5L47.1,18.4L52.7,34.6L67.4,47.2ZM43.4,197.3L50.8,216.6L29.6,203.6L15.7,192.4L10.2,183.4L39.7,193.3L43.4,197.3ZM71.1,0.0L95.1,1.3L121.9,0.4L140.4,4.0L171.8,44.0L257.7,115.5L304.8,188.3L308.5,204.0L315.0,217.5L326.1,221.6L336.2,227.9L382.4,298.0L388.0,311.9L387.0,327.2L389.8,338.4L402.7,344.3L417.5,347.0L427.7,357.8L440.6,413.5L440.6,431.0L443.4,438.7L502.5,525.4L506.2,536.2L505.3,544.3L507.1,551.0L518.2,566.3L536.7,607.6L545.0,617.1L556.1,653.5L557.0,722.7L553.3,753.7L542.2,791.5L529.3,827.9L514.5,854.4L495.1,876.9L429.5,924.5L410.1,934.4L324.2,964.0L261.4,992.4L202.3,1000.0L144.1,984.7L99.8,947.4L77.6,892.6L61.9,835.5L38.8,772.1L22.2,576.6L13.9,521.8L0.0,452.1L1.8,422.0L11.1,393.3L11.1,456.6L19.4,464.3L25.9,456.2L32.3,390.6L36.9,362.7L60.0,290.3L61.0,277.3L56.3,249.9L57.3,236.4L92.4,185.6L100.7,156.0L105.3,125.8L103.5,93.0L97.0,60.7L125.6,71.0L141.3,82.2L157.0,89.9L170.0,85.8L184.7,85.8L174.6,68.3L141.3,52.1L86.8,42.2L70.2,29.2L63.7,18.0L66.5,4.9L71.1,0.0Z";
  const MAP_W = 557, MAP_H = 1000;

  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  const fmt = (n) => Math.round(n).toLocaleString("en-US");

  /* ---------------------------------------------------------------- model */

  /* The 24 feature values come from ml/features.py, the same module that
     trained the model — they are not recomputed here. A second implementation
     of a feature definition, written in a different language, is how a working
     model silently starts scoring two different things in training and in
     production. So the browser is given the vector and runs the MODEL on it:
     the standardisation, the weighted sum, the sigmoid and the ranking of
     contributions below are all live, and none of them is baked in. */
  function features(c) {
    const f = {};
    M.features.forEach((name, i) => { f[name] = c.f[i]; });
    return f;
  }

  // risk = sigmoid( intercept + sum( weight_i * standardised_feature_i ) )
  function predict(c) {
    const f = features(c);
    let z = M.intercept;
    const parts = [];

    M.features.forEach((name, i) => {
      const standardised = (f[name] - M.mean[i]) / M.scale[i];
      const contribution = M.coefficients[i] * standardised;
      z += contribution;
      parts.push({ name: M.readable_names[name] || name, value: contribution });
    });

    const probability = 1 / (1 + Math.exp(-z));
    parts.sort((a, b) => Math.abs(b.value) - Math.abs(a.value));
    return { probability, score: Math.round(probability * 100), parts };
  }

  CUSTOMERS.forEach((c) => {
    const p = predict(c);
    c.risk = p.probability;
    c.score = p.score;
    c.parts = p.parts;
    c.high = p.probability >= M.threshold;
  });
  CUSTOMERS.sort((a, b) => b.risk - a.risk);

  const HIGH = CUSTOMERS.filter((c) => c.high);
  const AT_RISK_REVENUE = HIGH.reduce((s, c) => s + c.spend, 0);

  /* ------------------------------------------------------------ animation */

  function countTo(el, target, opts) {
    const o = opts || {};
    const dur = o.duration || 1100;
    const t0 = performance.now();
    function frame(t) {
      const k = Math.min((t - t0) / dur, 1);
      const eased = 1 - Math.pow(1 - k, 3);
      const v = target * eased;
      el.textContent = (o.prefix || "") + fmt(v) + (o.suffix || "");
      if (k < 1) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }

  const observer = new IntersectionObserver((entries) => {
    entries.forEach((e) => {
      if (!e.isIntersecting) return;
      e.target.classList.add("in");
      $$("[data-count]", e.target).forEach((el) => {
        if (el.dataset.done) return;
        el.dataset.done = "1";
        countTo(el, parseFloat(el.dataset.count), {
          prefix: el.dataset.prefix || "", suffix: el.dataset.suffix || "",
        });
      });
      $$("[data-w]", e.target).forEach((el) => {
        setTimeout(() => { el.style.width = el.dataset.w; }, 60);
      });
      observer.unobserve(e.target);
    });
  }, { threshold: 0.2 });

  /* ----------------------------------------------------------------- hero */

  /* The hero background is the customer base: one dot per customer. Every few
     hundred milliseconds another one stops reloading and fades out. That is the
     problem the whole project exists to solve, so it is what we draw. */
  function heroField() {
    const canvas = $("#field");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
    let dots = [], w = 0, h = 0, quiet = 0, lastKill = 0;
    const counter = $("#quiet-count");
    const mouse = { x: 0, y: 0, tx: 0, ty: 0 };

    function layout() {
      const dpr = Math.min(devicePixelRatio || 1, 2);
      w = canvas.clientWidth; h = canvas.clientHeight;
      canvas.width = w * dpr; canvas.height = h * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      const gap = w < 700 ? 46 : 62;
      const cols = Math.ceil(w / gap) + 1;
      const rows = Math.ceil(h / gap) + 1;
      const ox = (w - (cols - 1) * gap) / 2;
      const oy = (h - (rows - 1) * gap) / 2;

      dots = [];
      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
          dots.push({
            x: ox + c * gap, y: oy + r * gap,
            phase: Math.random() * Math.PI * 2,
            depth: 0.35 + Math.random() * 0.65,
            state: 1,            // 1 = active, falling towards 0 once it goes quiet
            dying: false,
          });
        }
      }
      quiet = 0;
    }

    function frame(t) {
      ctx.clearRect(0, 0, w, h);

      // one more customer goes quiet every ~340ms, until a quarter of them have
      if (!reduced && t - lastKill > 340) {
        lastKill = t;
        const alive = dots.filter((d) => !d.dying);
        if (alive.length > dots.length * 0.74) {
          alive[Math.floor(Math.random() * alive.length)].dying = true;
          quiet++;
          if (counter) counter.textContent = quiet;
        }
      }

      mouse.x += (mouse.tx - mouse.x) * 0.06;
      mouse.y += (mouse.ty - mouse.y) * 0.06;

      dots.forEach((d) => {
        if (d.dying && d.state > 0) d.state = Math.max(d.state - 0.012, 0);

        const drift = reduced ? 0 : Math.sin(t / 1400 + d.phase) * 2.2;
        const px = d.x + mouse.x * d.depth * 14;
        const py = d.y + drift + mouse.y * d.depth * 14;

        // active dots breathe; quiet ones shrink to a cold speck
        const pulse = reduced ? 1 : 0.75 + Math.sin(t / 620 + d.phase) * 0.25;
        const r = (1.05 + 1.5 * d.state * pulse) * d.depth + 0.5;

        if (d.state > 0.04) {
          // still active — warm, and briefly brighter at the moment it starts to fade
          const flash = d.dying && d.state > 0.72 ? (d.state - 0.72) * 2.4 : 0;
          const a = 0.16 + 0.52 * d.state * d.depth + flash;
          ctx.fillStyle = "rgba(255, 90, 31, " + Math.min(a, 1).toFixed(3) + ")";
          ctx.beginPath();
          ctx.arc(px, py, Math.max(r, 0.4), 0, Math.PI * 2);
          ctx.fill();
        } else {
          // gone quiet — a cold hollow ring, clearly a different thing
          ctx.strokeStyle = "rgba(128, 140, 150, " + (0.30 * d.depth).toFixed(3) + ")";
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.arc(px, py, Math.max(r + 0.8, 1.2), 0, Math.PI * 2);
          ctx.stroke();
        }
      });

      requestAnimationFrame(frame);
    }

    layout();
    addEventListener("resize", layout);
    addEventListener("pointermove", (e) => {
      mouse.tx = (e.clientX / innerWidth - 0.5) * 2;
      mouse.ty = (e.clientY / innerHeight - 0.5) * 2;
    });
    requestAnimationFrame(frame);
  }

  // headline words rise and sharpen, one after another
  function revealHero() {
    $$("h1.hero-title i, .reveal").forEach((el) => {
      const d = parseInt(el.dataset.d || "0", 10);
      setTimeout(() => el.classList.add("in"), 140 + d * 72);
    });
  }

  function scrollChrome() {
    const bar = $("#progress");
    const nav = $(".nav");
    if (!bar && !nav) return;
    function onScroll() {
      const max = document.documentElement.scrollHeight - innerHeight;
      if (bar) bar.style.width = (max > 0 ? (scrollY / max) * 100 : 0) + "%";
      if (nav) nav.classList.toggle("stuck", scrollY > 12);
    }
    addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }

  /* ------------------------------------------------------------------ map */

  const byTown = {};
  CUSTOMERS.forEach((c) => {
    const t = (byTown[c.region] = byTown[c.region] || { total: 0, high: 0 });
    t.total++;
    if (c.high) t.high++;
  });

  // Nudge labels apart where towns sit close together on the map.
  const LABEL_DY = {
    Colombo: 0, Negombo: -16, Gampaha: 12, Galle: -18, Matara: 22,
    Kandy: 10, Kurunegala: -20, Anuradhapura: -18, Jaffna: 0,
    Batticaloa: 20, Trincomalee: 18, Ratnapura: 16,
  };

  // A couple of towns need their label on the other side to clear a neighbour.
  const LABEL_SIDE = { Batticaloa: "right" };

  function drawMap() {
    const svg = $("#map");
    svg.setAttribute("viewBox", "-90 -20 " + (MAP_W + 260) + " " + (MAP_H + 40));
    let html = '<path class="island" d="' + MAP_PATH + '"/>';

    Object.keys(TOWN_XY).forEach((town) => {
      const stats = byTown[town] || { total: 0, high: 0 };
      const [fx, fy] = TOWN_XY[town];
      const x = fx * MAP_W, y = fy * MAP_H;
      const r = 10 + stats.high * 4.5;
      const hot = stats.high >= 3;
      const right = LABEL_SIDE[town] ? LABEL_SIDE[town] === "right" : fx < 0.55;
      const dy = LABEL_DY[town] || 0;

      html +=
        '<g class="town" data-town="' + town + '">' +
        '<circle class="ripple" cx="' + x + '" cy="' + y + '" r="6"/>' +
        '<circle class="dot" cx="' + x + '" cy="' + y + '" r="' + r + '" ' +
        'fill="' + (hot ? "#FF5A1F" : stats.high ? "#B8441A" : "#3A424A") + '" ' +
        'opacity="' + (stats.high ? 1 : 0.65) + '"/>' +
        '<circle class="hit" cx="' + x + '" cy="' + y + '" r="26"/>' +
        '<text x="' + (right ? x + r + 14 : x - r - 14) + '" y="' + (y + 9 + dy) + '" ' +
        'text-anchor="' + (right ? "start" : "end") + '">' + town + " " + stats.high + "</text>" +
        "</g>";
    });

    svg.innerHTML = html;

    $$(".town", svg).forEach((g) => {
      g.addEventListener("click", () => {
        const town = g.dataset.town;
        const ripple = $(".ripple", g);
        ripple.classList.remove("go");
        void ripple.offsetWidth;
        ripple.classList.add("go");
        state.town = state.town === town ? null : town;
        $$(".town", svg).forEach((t) => t.classList.toggle("on", t.dataset.town === state.town));
        renderList();
      });
    });
  }

  /* ---------------------------------------------------------------- charts */

  function bars(el, rows, total) {
    el.innerHTML = rows.map((r) =>
      '<div class="bar-row">' +
        '<div class="bar-top"><span>' + r.label + "</span><span>" + r.n + "</span></div>" +
        '<div class="bar-track"><div class="bar-fill' + (r.soft ? " soft" : "") +
        '" data-w="' + Math.max((r.n / total) * 100, 2) + '%"></div></div>' +
      "</div>"
    ).join("");
    observer.observe(el);
  }

  /* ----------------------------------------------------------------- list */

  const state = { cause: null, town: null, selected: null, lang: null };

  function filtered() {
    return CUSTOMERS.filter((c) =>
      (!state.cause || c.cause === state.cause) &&
      (!state.town || c.region === state.town));
  }

  function renderList() {
    const list = $("#list");
    if (!list) return;
    const rows = filtered();
    const count = $("#list-count");
    if (count) count.textContent = rows.length + " customers";

    if (!rows.length) {
      list.innerHTML = '<div style="padding:34px;text-align:center;color:var(--faint)">Nobody matches that filter.</div>';
      return;
    }

    list.innerHTML = rows.map((c) =>
      '<div class="row' + (state.selected === c.id ? " on" : "") + '" data-id="' + c.id + '">' +
        '<div class="row-id mono">' + c.id + "</div>" +
        '<div class="row-cause">' + c.cause + "</div>" +
        '<div class="row-region">' + c.region + "</div>" +
        '<div class="row-spend mono">Rs. ' + fmt(c.spend) + "</div>" +
        '<div class="row-score mono" style="color:' + (c.high ? "var(--risk)" : "var(--muted)") + '">' +
          c.score + "</div>" +
      "</div>"
    ).join("");

    $$(".row", list).forEach((row) => {
      row.addEventListener("click", () => select(row.dataset.id));
    });
  }

  /* --------------------------------------------------------------- detail */

  function pct(before, now) {
    if (!before) return 0;
    return ((now - before) / before) * 100;
  }

  function select(id) {
    const c = CUSTOMERS.find((x) => x.id === id);
    if (!c) return;
    const cmpBtn = $("#compare");
    if (cmpBtn) cmpBtn.classList.remove("on");
    state.selected = id;
    state.lang = c.language;
    renderList();
    renderDetail(c);
    $("#detail").scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function renderDetail(c) {
    const gap = pct(c.gapBefore, c.gapNow);
    const data = pct(c.dataBefore, c.dataNow);
    const opens = pct(c.opensBefore, c.opensNow);
    const top = c.parts.slice(0, 6);
    const max = Math.max.apply(null, top.map((p) => Math.abs(p.value)));

    const el = $("#detail");
    if (!el) return;
    el.className = "detail";
    el.innerHTML =
      "<div>" +
        '<div style="display:flex;align-items:baseline;gap:12px;flex-wrap:wrap">' +
          '<h3 style="font-size:20px">' + c.id + "</h3>" +
          '<span style="color:var(--muted);font-size:13.5px">' + c.region + " · " + c.plan +
            " · " + c.language + " · " + c.months + " months with Hutch</span>" +
        "</div>" +

        '<div class="diag">' +
          '<div class="diag-l">Diagnosis</div>' +
          "<h4>" + c.cause + "</h4>" +
          "<p>" + c.action + "</p>" +
          (c.cellKind !== "healthy"
            ? "<p class='diag-note'>Tower " + c.cell + ": " + c.cellWhy + ".</p>" : "") +
        "</div>" +
        /* Flagged is not the same as contacted. A suppressed customer is shown
           here with the reason, never dropped silently — the failure we could
           not see was the one that survived longest. */
        (c.high && c.hold
          ? '<div class="diag held">' +
              '<div class="diag-l">Held back — not contacted</div>' +
              "<h4>" + c.hold + "</h4>" +
              "<p>A policy decision, not a model decision. Hutch can change this " +
              "rule without retraining anything.</p>" +
            "</div>"
          : "") +

        '<table class="facts"><thead><tr>' +
          "<th>Behaviour</th><th style='text-align:right'>Before</th>" +
          "<th style='text-align:right'>Now</th><th style='text-align:right'>Change</th>" +
        "</tr></thead><tbody>" +
          factRow("Days between reloads", c.gapBefore, c.gapNow, gap, true) +
          factRow("Data used (GB)", c.dataBefore, c.dataNow, data, false) +
          factRow("App opens", c.opensBefore, c.opensNow, opens, false) +
          "<tr><td>Their tower <span class='mono'>" + c.cell + "</span></td>" +
            "<td class='num'>its own normal</td><td class='num mono'>" +
            (c.cellDrop > 0.05 ? "+" + c.cellDrop.toFixed(1) + " pp drops" : "no change") +
            "</td><td class='delta " + (c.cellKind !== "healthy" ? "bad" : "") + "'>" +
            c.cellKind + "</td></tr>" +
          "<tr><td>Extra charges</td><td class='num'>—</td><td class='num mono'>Rs. " +
            fmt(c.overage) + "</td><td class='delta " + (c.overage ? "bad" : "") + "'>" +
            (c.overage ? "charged" : "none") + "</td></tr>" +
        "</tbody></table>" +

        '<div class="contribs">' +
          '<div class="panel-h" style="margin-bottom:12px">Why the model scored it this way</div>' +
          top.map((p) =>
            '<div class="contrib">' +
              '<div class="contrib-top"><b>' + p.name + "</b><span class='mono' style='color:var(--muted)'>" +
                (p.value > 0 ? "+" : "") + p.value.toFixed(2) + "</span></div>" +
              '<div class="contrib-track"><div class="axis"></div>' +
                '<div class="contrib-fill ' + (p.value > 0 ? "up" : "down") +
                '" data-w="' + (Math.abs(p.value) / max) * 50 + '%"></div>' +
              "</div>" +
            "</div>"
          ).join("") +
        "</div>" +
      "</div>" +

      "<div>" +
        '<div class="ring-card">' + ring(c) + "</div>" +
        '<div style="margin-top:18px">' +
          '<div class="sms-head">' +
            ["Sinhala", "Tamil", "English"].map((l) =>
              '<button class="lang' + (l === state.lang ? " on" : "") + '" data-lang="' + l + '">' +
              l + "</button>").join("") +
          "</div>" +
          '<div class="phone"><div class="bubble" id="bubble">' + c.messages[state.lang] + "</div></div>" +
          '<div class="sms-foot">' +
            '<button class="btn btn-primary" id="send">Send this offer</button>' +
            '<span class="sent" id="sent">&#10003; Sent · Rs. ' + fmt(c.spend) + " protected</span>" +
          "</div>" +
        "</div>" +
      "</div>";

    // animate the ring and the contribution bars
    requestAnimationFrame(() => {
      const val = $(".ring .val", el);
      const len = 2 * Math.PI * 62;
      val.style.strokeDashoffset = len * (1 - c.risk);
      $$("[data-w]", el).forEach((b) => { b.style.width = b.dataset.w; });
    });

    $$(".lang", el).forEach((b) => {
      b.addEventListener("click", () => {
        state.lang = b.dataset.lang;
        $$(".lang", el).forEach((x) => x.classList.toggle("on", x === b));
        const bubble = $("#bubble", el);
        bubble.classList.add("swap");
        setTimeout(() => {
          bubble.textContent = c.messages[state.lang];
          bubble.classList.remove("swap");
        }, 260);
      });
    });

    $("#send", el).addEventListener("click", (e) => {
      const btn = e.currentTarget;
      btn.textContent = "Sending…";
      btn.disabled = true;
      setTimeout(() => {
        btn.textContent = "Sent";
        $("#sent", el).classList.add("show");
      }, 850);
    });
  }

  function factRow(label, before, now, change, higherIsBad) {
    const bad = higherIsBad ? change > 12 : change < -12;
    const sign = change > 0 ? "+" : "";
    return "<tr><td>" + label + "</td>" +
      "<td class='num mono'>" + before.toFixed(1) + "</td>" +
      "<td class='num mono'>" + now.toFixed(1) + "</td>" +
      "<td class='delta " + (bad ? "bad" : "ok") + " mono'>" + sign + change.toFixed(0) + "%</td></tr>";
  }

  function ring(c) {
    const len = 2 * Math.PI * 62;
    return '<svg class="ring" viewBox="0 0 148 148">' +
      '<circle class="track" cx="74" cy="74" r="62"/>' +
      '<circle class="val" cx="74" cy="74" r="62" transform="rotate(-90 74 74)" ' +
        'stroke-dasharray="' + len + '" stroke-dashoffset="' + len + '"/>' +
      '<text class="ring-n" x="74" y="80" text-anchor="middle">' + c.score + "</text>" +
      '<text class="ring-sub" x="74" y="99" text-anchor="middle">RISK / 100</text>' +
      "</svg>" +
      '<div class="verdict ' + (c.high ? "high" : "low") + '">' +
        (c.high ? "Above alert line — act now" : "Below alert line — watch") + "</div>" +
      '<div style="font-size:12px;color:var(--faint);margin-top:6px">Alert line: ' +
        Math.round(M.threshold * 100) + " / 100</div>";
  }

  /* ------------------------------------------------------------ demo cases */

  /* Hunting for a bill-shock customer live in front of a panel wastes time and
     invites a fumble. These pick the clearest example of each reason up front,
     and "compare all four" puts every message on one screen at once. */

  const CAUSES = ["Network problem", "Bill shock", "Plan too big", "Losing interest"];

  function exemplar(cause) {
    const of = CUSTOMERS.filter((c) => c.cause === cause);
    if (!of.length) return null;
    // the highest-risk one, so the story is strongest
    return of[0];
  }

  function clearCaseButtons() {
    $$(".case").forEach((b) => b.classList.remove("on"));
  }

  function showCompare() {
    const el = $("#detail");
    if (!el) return;
    state.selected = null;
    renderList();
    clearCaseButtons();
    const cmpBtn = $("#compare");
    if (cmpBtn) cmpBtn.classList.add("on");

    const picks = CAUSES.map(exemplar).filter(Boolean);
    const lang = state.lang || "English";

    el.className = "compare-view";
    el.innerHTML =
      '<div class="compare-head">' +
        "<h3>Four customers, four reasons, four different messages</h3>" +
        '<div class="sms-head">' +
          ["Sinhala", "Tamil", "English"].map((l) =>
            '<button class="lang' + (l === lang ? " on" : "") + '" data-lang="' + l + '">' +
            l + "</button>").join("") +
        "</div>" +
      "</div>" +
      '<div class="compare-grid">' +
        picks.map((c, i) =>
          '<div class="cmp" style="animation-delay:' + (i * 80) + 'ms">' +
            '<div class="cmp-top">' +
              '<span class="cmp-cause">' + c.cause + "</span>" +
              '<span class="cmp-score mono">' + c.score + "</span>" +
            "</div>" +
            '<div class="cmp-meta">' + c.id + " · " + c.region + " · " + c.plan + "</div>" +
            '<div class="cmp-msg" data-id="' + c.id + '">' + c.messages[lang] + "</div>" +
            '<div class="cmp-fix">' + c.action + "</div>" +
          "</div>").join("") +
      "</div>";

    $$(".lang", el).forEach((b) => {
      b.addEventListener("click", () => {
        state.lang = b.dataset.lang;
        $$(".lang", el).forEach((x) => x.classList.toggle("on", x === b));
        // all four messages change language together
        $$(".cmp-msg", el).forEach((m) => {
          m.classList.add("swap");
          setTimeout(() => {
            const c = CUSTOMERS.find((x) => x.id === m.dataset.id);
            if (c) m.textContent = c.messages[state.lang];
            m.classList.remove("swap");
          }, 260);
        });
      });
    });
  }

  function wireCases() {
    $$(".case[data-case]").forEach((btn) => {
      const c = exemplar(btn.dataset.case);
      if (!c) { btn.disabled = true; btn.style.opacity = .4; return; }
      btn.addEventListener("click", () => {
        clearCaseButtons();
        btn.classList.add("on");
        const cmpBtn = $("#compare");
        if (cmpBtn) cmpBtn.classList.remove("on");
        select(c.id);
      });
    });
    const cmp = $("#compare");
    if (cmp) cmp.addEventListener("click", showCompare);
  }

  /* ---------------------------------------------------------- model panel */

  function renderModelPanel() {
    const el = $("#weights");
    if (!el) return;
    const pairs = M.features.map((f, i) => ({
      name: M.readable_names[f] || f, w: M.coefficients[i],
    })).sort((a, b) => b.w - a.w);
    const max = Math.max.apply(null, pairs.map((p) => Math.abs(p.w)));

    el.innerHTML = pairs.map((p) =>
      '<div class="weight-row">' +
        "<span style='color:var(--muted)'>" + p.name + "</span>" +
        '<div class="weight-track"><div class="axis"></div>' +
          '<div class="weight-fill ' + (p.w > 0 ? "up" : "down") +
          '" data-w="' + (Math.abs(p.w) / max) * 50 + '%"></div>' +
        "</div>" +
      "</div>"
    ).join("");
    observer.observe(el);
  }

  /* ----------------------------------------------------------------- boot */

  function boot() {
    // Each piece is isolated: if one fails (an old cached index.html, a missing
    // element), the rest of the console still renders instead of a blank page.
    const step = (name, fn) => {
      try { fn(); } catch (err) { console.error("StaySignal: " + name + " failed", err); }
    };

    step("hero", heroField);
    step("reveal", revealHero);
    step("chrome", scrollChrome);
    step("map", drawMap);

    step("kpis", () => {
      const set = (sel, v) => { const el = $(sel); if (el) el.dataset.count = v; };
      set("#kpi-high", HIGH.length);
      set("#kpi-rev", AT_RISK_REVENUE);
      set("#kpi-total", CUSTOMERS.length);
      set("#stat-high", HIGH.length);
      set("#stat-rev", AT_RISK_REVENUE);
    });

    step("charts", () => {
      const causes = {};
      CUSTOMERS.forEach((c) => { causes[c.cause] = (causes[c.cause] || 0) + 1; });
      const causeEl = $("#cause-bars");
      if (causeEl) {
        bars(causeEl, Object.keys(causes).map((k) => ({ label: k, n: causes[k] }))
          .sort((a, b) => b.n - a.n), CUSTOMERS.length);
      }
      const townEl = $("#town-bars");
      if (townEl) {
        bars(townEl,
          Object.keys(byTown).map((t) => ({ label: t, n: byTown[t].high, soft: byTown[t].high < 3 }))
            .sort((a, b) => b.n - a.n).slice(0, 6),
          Math.max.apply(null, Object.keys(byTown).map((t) => byTown[t].high)) || 1);
      }
    });

    step("filters", () => {
      $$(".chip[data-cause]").forEach((chip) => {
        chip.addEventListener("click", () => {
          const c = chip.dataset.cause;
          state.cause = c === "all" ? null : (state.cause === c ? null : c);
          $$(".chip[data-cause]").forEach((x) =>
            x.classList.toggle("on",
              (state.cause === null && x.dataset.cause === "all") || x.dataset.cause === state.cause));
          renderList();
        });
      });
    });

    step("list", renderList);
    step("demo cases", wireCases);
    step("weights", renderModelPanel);
    step("observe", () => { $$(".rv").forEach((el) => observer.observe(el)); });

    step("demo button", () => {
      const btn = $("#demo-btn");
      if (!btn) return;
      btn.addEventListener("click", () => {
        const target = $("#console");
        if (target) target.scrollIntoView({ behavior: "smooth" });
        setTimeout(() => { if (HIGH.length) select(HIGH[0].id); }, 700);
      });
    });

    step("model numbers", () => {
      const auc = $("#model-auc"), th = $("#model-thresh");
      if (auc) auc.textContent = M.test_roc_auc.toFixed(3);
      if (th) th.textContent = M.threshold.toFixed(2);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
