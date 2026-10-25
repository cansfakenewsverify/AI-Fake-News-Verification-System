// Injected into every document before it loads (Page.addScriptToEvaluateOnNewDocument).
//
// Three jobs, all purely visual or protective — the page's own data, text and DOM content are
// never rewritten:
//   1. a visible mouse cursor + click ripple, so the viewer can follow what is being operated
//   2. opaque mask blocks over http(s) URLs that are not from a known fact-check domain
//      (scam links must never be readable in the film)
//   3. outbound navigation is blocked and the href recorded instead — no sign-ins, and the
//      "分享到 Threads" button is shown without ever opening Threads
(() => {
  if (window.__cap) return;

  const ALLOW_HOSTS = [
    "fakenewsverify.vercel.app",
    "fakenewsverify-api.onrender.com",
    "mygopen.com",
    "tfc-taiwan.org.tw",
    "cofacts.tw",
    "cofacts.g0v.tw",
  ];
  const OWN_HOST = "fakenewsverify.vercel.app";
  const URL_RE = /https?:\/\/[^\s　-〿＀-￯"'<>）)】\]]+/g;

  // The cursor starts inside the viewport on purpose: it carries the compositor heartbeat, and an
  // element parked outside the visible area gets its animation skipped, which stops the recording.
  const state = { x: 24, y: 24, blocked: [], ready: false };

  /* ---------------------------------------------------------------- style */
  const style = document.createElement("style");
  style.textContent = `
    #__cap_layer{position:fixed;inset:0;pointer-events:none;z-index:2147483600}
    #__cap_masks{position:absolute;top:0;left:0;width:0;height:0;pointer-events:none;z-index:2147483500}
    .__cap_mask{position:absolute;border-radius:4px;background:#c9c9d0;box-shadow:inset 0 0 0 1px rgba(0,0,0,.08)}
    /* The sub-pixel animation is a metronome, not decoration: Chrome's screencast only emits a
       frame when the compositor produces one, so a page sitting still stops the recording dead.
       0.02px is far below one device pixel — it changes no rendered pixel, it just keeps the
       compositor ticking so held shots are recorded as held shots. */
    #__cap_cur{position:absolute;width:26px;height:26px;margin:-2px 0 0 -2px;transform-origin:2px 2px;
      filter:drop-shadow(0 2px 4px rgba(0,0,0,.45));transition:none;
      animation:__cap_beat .5s linear infinite alternate}
    @keyframes __cap_beat{from{transform:translate3d(0,0,0)}to{transform:translate3d(.02px,0,0)}}
    .__cap_rip{position:absolute;width:16px;height:16px;margin:-8px 0 0 -8px;border-radius:50%;
      border:2px solid rgba(17,17,17,.75);animation:__cap_rip .55s ease-out forwards}
    @keyframes __cap_rip{from{transform:scale(.4);opacity:.95}to{transform:scale(3.4);opacity:0}}
  `;

  const layer = document.createElement("div");
  layer.id = "__cap_layer";
  const cur = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  cur.id = "__cap_cur";
  cur.setAttribute("viewBox", "0 0 26 26");
  cur.innerHTML = '<path d="M3 2 L3 20.5 L8.1 15.9 L11.2 22.6 L14.6 21 L11.5 14.4 L18.4 14.1 Z"'
    + ' fill="#111111" stroke="#ffffff" stroke-width="1.6" stroke-linejoin="round"/>';
  const masks = document.createElement("div");
  masks.id = "__cap_masks";

  function mount() {
    if (!document.body) return false;
    if (!style.isConnected) document.head.appendChild(style);
    if (!layer.isConnected) { layer.appendChild(cur); document.body.appendChild(layer); }
    if (!masks.isConnected) document.body.appendChild(masks);
    place();
    return true;
  }
  const place = () => { cur.style.left = state.x + "px"; cur.style.top = state.y + "px"; };

  /* ----------------------------------------------------------- url masking */
  function hostAllowed(u) {
    try { return ALLOW_HOSTS.includes(new URL(u).hostname.replace(/^www\./, "")); } catch { return false; }
  }

  function remask() {
    if (!mount()) return 0;
    masks.textContent = "";
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        if (!node.nodeValue || !/https?:\/\//.test(node.nodeValue)) return NodeFilter.FILTER_REJECT;
        const p = node.parentElement;
        if (!p || p.closest("#__cap_layer,#__cap_masks,script,style,noscript")) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      },
    });
    let n = 0, node;
    while ((node = walker.nextNode())) {
      const text = node.nodeValue;
      URL_RE.lastIndex = 0;
      let m;
      while ((m = URL_RE.exec(text))) {
        if (hostAllowed(m[0])) continue;
        const range = document.createRange();
        range.setStart(node, m.index);
        range.setEnd(node, m.index + m[0].length);
        for (const r of range.getClientRects()) {
          if (r.width < 2 || r.height < 2) continue;
          const d = document.createElement("div");
          d.className = "__cap_mask";
          d.style.left = (r.left + window.scrollX - 1) + "px";
          d.style.top = (r.top + window.scrollY - 1) + "px";
          d.style.width = (r.width + 2) + "px";
          d.style.height = (r.height + 2) + "px";
          masks.appendChild(d);
          n++;
        }
      }
    }
    return n;
  }

  /* --------------------------------------------------- outbound protection */
  function blockOutbound(e) {
    const a = e.target && e.target.closest ? e.target.closest("a[href]") : null;
    if (!a) return;
    let host;
    try { host = new URL(a.href, location.href).hostname; } catch { return; }
    if (host === OWN_HOST || host === location.hostname) return;
    e.preventDefault();
    state.blocked.push({ href: a.href, text: (a.textContent || "").trim().slice(0, 80), at: Date.now() });
  }
  // Bubble phase, and no stopPropagation: the app's own handler must still run, so the button
  // really does change to 「已開啟 Threads」 and really does compose the intent URL on camera.
  // Only the navigation itself is cancelled.
  document.addEventListener("click", blockOutbound, false);
  const realOpen = window.open;
  window.open = function (url, ...rest) {
    let host = "";
    try { host = new URL(url, location.href).hostname; } catch { /* ignore */ }
    if (host && host !== OWN_HOST && host !== location.hostname) {
      state.blocked.push({ href: String(url), text: "window.open", at: Date.now() });
      return null;
    }
    return realOpen.call(window, url, ...rest);
  };

  /* ----------------------------------------------------- target resolution */
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return false;
    const s = getComputedStyle(el);
    return s.visibility !== "hidden" && s.display !== "none" && Number(s.opacity) > 0.05;
  };

  function find(spec) {
    const q = typeof spec === "string" ? { text: spec } : spec || {};
    const scope = q.sel ? [...document.querySelectorAll(q.sel)] : null;
    if (q.placeholder) {
      const hit = [...document.querySelectorAll("input,textarea")]
        .filter((el) => (el.placeholder || "").includes(q.placeholder) && visible(el));
      return hit[q.nth ?? 0] || null;
    }
    if (!q.text) {
      const list = (scope || []).filter(visible);
      return list[q.nth ?? 0] || null;
    }
    const pool = scope || [...document.querySelectorAll("button,a,[role=tab],[role=button],label,input,summary,h1,h2,h3,p,span,li,div")];
    const exact = [];
    const partial = [];
    for (const el of pool) {
      if (!visible(el)) continue;
      const txt = (el.innerText || el.textContent || "").replace(/\s+/g, " ").trim();
      if (!txt) continue;
      if (txt === q.text) exact.push(el);
      // Generous slack: a UI string is often a short phrase inside a longer sentence
      // ("這不是有效的網址" inside "…，請以 http:// 或 https:// 開頭。"). The deepest-match ranking
      // below is what keeps this from selecting a whole section.
      else if (txt.includes(q.text) && txt.length <= q.text.length + (q.slack ?? 80)) partial.push(el);
    }
    const deepest = (list) => list.filter((el) => !list.some((o) => o !== el && el.contains(o)));
    const ranked = [...deepest(exact), ...deepest(partial)];
    return ranked[q.nth ?? 0] || null;
  }

  /* -------------------------------------------------------------- page API */
  window.__cap = {
    find,
    blocked: () => state.blocked,
    cursor: () => ({ x: state.x, y: state.y }),
    remask,
    box(spec) {
      const el = find(spec);
      if (!el) return null;
      const r = el.getBoundingClientRect();
      if (r.bottom < 0 || r.top > innerHeight) el.scrollIntoView({ block: "center", behavior: "instant" });
      const b = el.getBoundingClientRect();
      return { cx: b.left + b.width / 2, cy: b.top + b.height / 2, w: b.width, h: b.height, top: b.top + scrollY };
    },
    topOf(spec, offset) {
      const el = find(spec);
      if (!el) return null;
      return Math.max(0, el.getBoundingClientRect().top + window.scrollY - (offset ?? 120));
    },
    text(spec) {
      const el = find(spec);
      return el ? (el.innerText || el.textContent || "").replace(/\s+/g, " ").trim() : null;
    },
    setValue(spec, value) {
      const el = find(spec);
      if (!el) return false;
      el.focus();
      const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto, "value").set.call(el, value);
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
      setTimeout(remask, 60);
      return true;
    },
    /** Phone takes show a touch device, so the arrow is hidden — but it must keep animating
     *  (it is the heartbeat), so it is made almost transparent rather than removed. */
    setCursorVisible(on) {
      mount();
      cur.style.opacity = on ? "1" : "0.01";
    },
    ripple(x, y) {
      mount();
      const d = document.createElement("div");
      d.className = "__cap_rip";
      d.style.left = x + "px";
      d.style.top = y + "px";
      layer.appendChild(d);
      setTimeout(() => d.remove(), 700);
    },
    scrollTo(to, ms) {
      const from = window.scrollY;
      const t0 = performance.now();
      return new Promise((done) => {
        const tick = (now) => {
          const k = Math.min(1, (now - t0) / ms);
          const e = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
          window.scrollTo(0, from + (to - from) * e);
          if (k < 1) requestAnimationFrame(tick); else done(true);
        };
        requestAnimationFrame(tick);
      });
    },
  };

  /* -------------------------------------------------------------- plumbing */
  document.addEventListener("mousemove", (e) => { state.x = e.clientX; state.y = e.clientY; place(); }, true);
  const mo = new MutationObserver(() => {
    clearTimeout(state.timer);
    state.timer = setTimeout(remask, 120);
  });
  const start = () => {
    if (!mount()) return setTimeout(start, 50);
    mo.observe(document.body, { childList: true, subtree: true, characterData: true });
    remask();
    setInterval(remask, 1200);
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
