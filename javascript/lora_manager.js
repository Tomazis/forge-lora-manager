(function () {
  const EXT_TXT = "lora-manager-picker";
  const EXT_IMG = "lora-manager-picker-img2img";
  const WEIGHT_MIN = -4;
  const WEIGHT_MAX = 4;
  const LS = {
    favorites: "lm-favorites",
    presets: "lm-presets",
    lastFolder: "lm-last-folder",
    searchAll: "lm-scope-all",
    view: "lm-view",
  };

  const State = { items: [], loaded: false };
  window._lmState = State;
  window._lmGetSelected = window._lmGetSelected || {};

  const app = () => (typeof gradioApp === "function" ? gradioApp() : document);
  const qs = (sel, root) => (root || app()).querySelector(sel);
  const qsa = (sel, root) => (root || app()).querySelectorAll(sel);
  const clamp = (x, a, b) => Math.min(b, Math.max(a, x));

  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([key, value]) => {
      if (key === "class") node.className = value;
      else if (key === "dataset") Object.entries(value).forEach(([dk, dv]) => { node.dataset[dk] = dv; });
      else if (value != null) node.setAttribute(key, value);
    });
    children.forEach((child) => {
      if (child != null) node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
    });
    return node;
  }

  function dbg(...args) {
    try { console.log("[lora-manager]", ...args); } catch (_) { /* ignore */ }
  }

  async function fetchJSON(url, opts) {
    try {
      const res = await fetch(url, Object.assign({ cache: "no-store" }, opts || {}));
      dbg("fetch", url, res.status);
      if (!res.ok) throw new Error(String(res.status));
      const data = await res.json();
      dbg("fetch json", url, data && data.ok, data && data.error, data && (data.items && data.items.length));
      return data;
    } catch (err) {
      dbg("fetch fail", url, String(err && err.message || err));
      return {};
    }
  }

  function readLS(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (_) {
      return fallback;
    }
  }

  async function loadLibrary() {
    const data = await fetchJSON("/lora-manager/list");
    State.items = Array.isArray(data.items) ? data.items : [];
    State.loaded = true;
    return State.items;
  }

  function foldersFrom(items) {
    const map = {};
    items.forEach((item) => {
      const folder = item.folder || "";
      (map[folder] || (map[folder] = [])).push(item);
    });
    return map;
  }

  function favList() {
    return readLS(LS.favorites, []);
  }

  function isFavorite(item) {
    const favs = favList();
    return favs.includes(item.key) || favs.includes(`${item.folder}::${item.name}`) || !!item.favorite;
  }

  function toggleFavorite(item) {
    const favs = favList();
    const idx = favs.indexOf(item.key);
    if (idx >= 0) favs.splice(idx, 1);
    else favs.unshift(item.key);
    localStorage.setItem(LS.favorites, JSON.stringify(favs));
    return idx < 0;
  }

  function activationWords(text) {
    return String(text || "")
      .split(",")
      .map((part) => part.trim())
      .filter(Boolean);
  }

  function loraTokenName(item) {
    const raw = (item && (item.filename || item.name)) || "";
    return String(raw).replace(/\.[^.\\/]+$/, "") || (item && item.name) || "";
  }

  function loraInsertText(item, weight, activation) {
    const words = activationWords(activation);
    const tag = `<lora:${loraTokenName(item)}:${Number(weight || 1).toFixed(2)}>`;
    return (words.length ? words.join(", ") + ", " : "") + tag;
  }

  function setSafeHtml(node, html) {
    node.innerHTML = html || "";
    node.querySelectorAll("script,iframe,object,embed").forEach((n) => n.remove());
    node.querySelectorAll("*").forEach((n) => {
      Array.from(n.attributes).forEach((attr) => {
        if (/^on/i.test(attr.name)) n.removeAttribute(attr.name);
        if (attr.name === "href" && /^\s*javascript:/i.test(attr.value)) n.removeAttribute("href");
      });
    });
  }

  function closeOverlay() {
    document.getElementById("lm-overlay")?.remove();
  }

  function closePickerMenus() {
    document.querySelectorAll(".lm-menu").forEach((node) => node.remove());
    document.querySelectorAll(".lora-manager-picker.is-open").forEach((node) => node.classList.remove("is-open"));
  }

  function openOverlay(inner) {
    closePickerMenus();
    closeOverlay();
    const overlay = el("div", { id: "lm-overlay", class: "lm-overlay" });
    const panel = el("div", { class: "lm-overlay-panel" });
    const close = el("button", { class: "lm-overlay-close", type: "button", title: "Close" }, "×");
    close.addEventListener("click", closeOverlay);
    overlay.addEventListener("mousedown", (event) => event.stopPropagation());
    overlay.addEventListener("click", (event) => {
      if (event.target === overlay) closeOverlay();
    });
    panel.append(close, inner);
    overlay.append(panel);
    document.body.append(overlay);
    return overlay;
  }

  function metaValue(meta, keys) {
    if (!meta) return "";
    for (const key of keys) {
      if (meta[key] != null && meta[key] !== "") return meta[key];
    }
    return "";
  }

  function openExampleModal(example, onSetPreview) {
    const wrap = el("div", { class: "lm-example-view" });
    wrap.append(el("img", { src: example.url, alt: example.file || "example" }));
    const info = el("div", { class: "lm-example-meta" });
    const meta = example.meta || {};
    const rows = [
      ["Prompt", metaValue(meta, ["prompt"])],
      ["Negative", metaValue(meta, ["negativePrompt", "negative"])],
      ["Seed", metaValue(meta, ["seed"])],
      ["Steps", metaValue(meta, ["steps"])],
      ["CFG", metaValue(meta, ["cfgScale", "cfg"])],
      ["Sampler", metaValue(meta, ["sampler", "samplerName"])],
      ["Size", meta.Size || (meta.width && meta.height ? `${meta.width}×${meta.height}` : "")],
      ["Model", metaValue(meta, ["Model", "model"])],
    ];
    rows.forEach(([label, value]) => {
      if (value === "" || value == null) return;
      const row = el("div", { class: "lm-meta-row" });
      row.append(el("strong", {}, label));
      row.append(el("pre", {}, String(value)));
      info.append(row);
    });
    wrap.append(info);
    if (onSetPreview) {
      const setBtn = el("button", { class: "lm-btn", type: "button" }, "Set as preview");
      setBtn.addEventListener("click", () => onSetPreview(example));
      wrap.append(setBtn);
    }
    openOverlay(wrap);
  }

  function renderTriggers(wrap, text) {
    wrap.innerHTML = "";
    activationWords(text).forEach((word) => {
      const btn = el("button", { class: "lm-trig", type: "button", title: "Copy" }, word);
      btn.addEventListener("click", () => navigator.clipboard?.writeText(word));
      wrap.append(btn);
    });
  }

  function noFocusScroll(node) {
    node.addEventListener("mousedown", (event) => event.preventDefault());
  }

  function previewUrl(key) {
    return `/lora-manager/preview?key=${encodeURIComponent(key)}`;
  }

  const lazyObservers = new Map();
  function lazyObserverFor(root) {
    const key = root || "viewport";
    let obs = lazyObservers.get(key);
    if (obs) return obs;
    obs = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        const node = entry.target;
        if (node.dataset.src) {
          node.src = node.dataset.src;
          delete node.dataset.src;
        }
        obs.unobserve(node);
      });
    }, { root: root || null, rootMargin: "80px", threshold: 0.01 });
    lazyObservers.set(key, obs);
    return obs;
  }

  function lazyPreview(item, root) {
    const img = el("img", { alt: item.name || "", loading: "lazy", decoding: "async" });
    img.dataset.src = previewUrl(item.key);
    img.width = 286;
    img.height = 384;
    if (!("IntersectionObserver" in window)) {
      img.src = img.dataset.src;
      return img;
    }
    const obs = lazyObserverFor(root);
    img.addEventListener("error", () => {
      obs.unobserve(img);
      img.remove();
    });
    requestAnimationFrame(() => {
      if (img.isConnected) obs.observe(img);
    });
    return img;
  }

  function triggerMap(item, previous) {
    const map = {};
    (item.triggers || []).forEach((word) => {
      map[word] = previous && previous[word] === false ? false : true;
    });
    return map;
  }

  function enabledTriggers(obj) {
    if (obj.trig) return Object.keys(obj.trig).filter((word) => obj.trig[word]);
    const item = State.items.find((row) => row.key === obj.key || row.name === obj.name);
    return item?.triggers || [];
  }

  async function fillLoraCard(host, item, options) {
    const opts = options || {};
    const draft = {
      triggers: (item.triggers || []).join(", "),
      weight: Number(item.preferred_weight) || 1,
    };
    dbg("card", item.key, { sha256: item.sha256, model_id: item.model_id, version_id: item.version_id, preview: item.preview });
    const examples = opts.examples || (await fetchJSON(`/lora-manager/examples?key=${encodeURIComponent(item.key)}`));
    dbg("examples", item.key, examples);
    host.innerHTML = "";

    const starred = isFavorite(item);
    const star = el("button", {
      class: "lm-star" + (starred ? " is-on" : ""),
      type: "button",
      title: starred ? "Unfavorite" : "Favorite",
    }, starred ? "★" : "☆");
    star.addEventListener("click", () => {
      toggleFavorite(item);
      fillLoraCard(host, item, Object.assign({}, opts, { examples }));
      if (opts.onFavorite) opts.onFavorite();
    });
    const copyAll = el("button", { class: "lm-copy-all", type: "button", title: "Copy triggers and <lora:filename>" }, "Copy");
    copyAll.addEventListener("click", () => {
      navigator.clipboard?.writeText(loraInsertText(item, draft.weight, draft.triggers));
    });
    const media = el("div", { class: "lm-card-media" });
    if (item.preview) {
      media.append(el("img", {
        class: "lm-card-preview",
        src: previewUrl(item.key),
        alt: item.name,
        loading: "eager",
        decoding: "async",
      }));
    }
    media.append(star, copyAll);
    const title = el("h3", {}, item.name);
    const filename = el("div", { class: "lm-muted lm-filename", title: item.filename || item.name }, item.filename || item.name);
    const folder = el("div", { class: "lm-muted" }, item.folder || "(root)");
    const base = el("div", { class: "lm-muted" }, item.base_model || "base model unknown");
    const linkHref = civitaiUrl(item);
    const link = el("a", { class: "lm-civitai", href: linkHref, target: "_blank", rel: "noopener" }, "Open on civitai.red");

    const trigWrap = el("div", { class: "lm-triggers" });
    const triggerInput = el("textarea", { class: "lm-input", rows: "3" });
    triggerInput.value = draft.triggers;
    renderTriggers(trigWrap, draft.triggers);
    triggerInput.addEventListener("input", () => {
      draft.triggers = triggerInput.value;
      renderTriggers(trigWrap, draft.triggers);
    });

    const weight = el("input", { class: "lm-input", type: "number", step: "0.05", value: String(draft.weight) });
    weight.addEventListener("input", () => {
      draft.weight = Number(weight.value || 1) || 1;
    });
    const notes = el("textarea", { class: "lm-input", rows: "3" });
    notes.value = item.notes || "";
    const descView = el("div", { class: "lm-desc" });
    setSafeHtml(descView, item.description || "");
    const descEdit = el("textarea", { class: "lm-input", rows: "5" });
    descEdit.value = item.description || "";
    descEdit.style.display = "none";
    const descToggle = el("button", { class: "lm-btn", type: "button" }, "Edit HTML");
    descToggle.addEventListener("click", () => {
      const editing = descEdit.style.display !== "none";
      descEdit.style.display = editing ? "none" : "";
      descView.style.display = editing ? "" : "none";
      descToggle.textContent = editing ? "Edit HTML" : "Preview";
      if (editing) setSafeHtml(descView, descEdit.value);
    });

    const exWrap = el("div", { class: "lm-examples" });
    const exItems = examples.items || [];
    if (!exItems.length) dbg("examples empty", item.key, { ok: examples.ok, error: examples.error, sha256: examples.sha256 });
    const openEx = (ex) => {
      openExampleModal(ex, async (picked) => {
        await fetchJSON("/lora-manager/set-preview", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ key: item.key, index: picked.index }),
        });
        closeOverlay();
        await loadLibrary();
        const fresh = State.items.find((row) => row.key === item.key);
        if (fresh && opts.onReload) opts.onReload(fresh);
        else if (fresh) fillLoraCard(host, fresh, opts);
      });
    };
    if (exItems.length) {
      let exIndex = 0;
      const renderCarousel = () => {
        exWrap.innerHTML = "";
        const cur = exItems[exIndex];
        const stage = el("div", { class: "lm-carousel-stage" });
        const prev = el("button", { class: "lm-carousel-nav", type: "button", title: "Previous" }, "‹");
        const next = el("button", { class: "lm-carousel-nav", type: "button", title: "Next" }, "›");
        const slide = el("button", { class: "lm-carousel-slide", type: "button", title: "Open example" });
        slide.append(el("img", { src: cur.url, alt: "", loading: "lazy", decoding: "async" }));
        slide.addEventListener("click", () => openEx(cur));
        prev.disabled = exItems.length < 2;
        next.disabled = exItems.length < 2;
        prev.addEventListener("click", (event) => {
          event.stopPropagation();
          exIndex = (exIndex - 1 + exItems.length) % exItems.length;
          renderCarousel();
        });
        next.addEventListener("click", (event) => {
          event.stopPropagation();
          exIndex = (exIndex + 1) % exItems.length;
          renderCarousel();
        });
        stage.append(prev, slide, next);
        exWrap.append(stage, el("div", { class: "lm-carousel-count" }, `${exIndex + 1} / ${exItems.length}`));
      };
      renderCarousel();
    }

    const status = el("div", { class: "lm-status" });
    const save = el("button", { class: "lm-btn", type: "button" }, "Save metadata");
    save.addEventListener("click", async () => {
      const res = await fetchJSON("/lora-manager/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          key: item.key,
          triggers: triggerInput.value,
          preferred_weight: Number(weight.value || 0),
          notes: notes.value,
          description: descEdit.value,
        }),
      });
      status.textContent = res.ok ? "Saved both sidecars." : (res.error || "Save failed");
      await loadLibrary();
    });
    const sync = el("button", { class: "lm-btn", type: "button" }, "Sync");
    sync.addEventListener("click", async () => {
      status.textContent = "Syncing…";
      const res = await fetchJSON("/lora-manager/sync", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key: item.key }),
      });
      status.textContent = res.ok
        ? `Synced. Examples: ${res.examples || 0}`
        : `${res.error || res.status || "Sync failed"}${res.examples ? ` · examples ${res.examples}` : ""}`;
      await loadLibrary();
      const fresh = State.items.find((row) => row.key === item.key);
      if (fresh && opts.onReload) opts.onReload(fresh);
      else if (fresh) fillLoraCard(host, fresh, opts);
    });
    const copy = el("button", { class: "lm-btn", type: "button" }, "Copy");
    copy.addEventListener("click", () => {
      navigator.clipboard?.writeText(loraInsertText(item, draft.weight, draft.triggers));
    });
    const actions = el("div", { class: "lm-card-actions" }, save, sync, copy);

    host.append(media, title, filename, folder, base);
    if (link) host.append(link);
    host.append(el("label", { class: "lm-label" }, "Activation text"));
    host.append(trigWrap, triggerInput);
    host.append(el("label", { class: "lm-label" }, "Preferred weight"), weight);
    host.append(el("label", { class: "lm-label" }, "Notes"), notes);
    host.append(el("label", { class: "lm-label" }, "Description"), descToggle, descView, descEdit);
    host.append(el("h4", {}, "Examples"), exWrap, actions, status);
  }

  async function openItemModal(item) {
    const body = el("div", { class: "lm-card lm-card-modal" });
    const opts = {};
    opts.onReload = (fresh) => fillLoraCard(body, fresh, opts);
    openOverlay(body);
    await fillLoraCard(body, item, opts);
  }

  function openManager(key) {
    window._lmOpenKey = key;
    const nav = qsa("#tabs > .tab-nav button, #tabs .tab-nav button, .tab-nav button");
    const btn = qs("#tab_lora_manager, button#lora_manager")
      || Array.from(nav).find((node) => /lora\s*manager/i.test((node.textContent || "").trim()));
    if (btn) btn.click();
    window.dispatchEvent(new CustomEvent("lora-manager-open", { detail: { key } }));
  }

  function createUI(rootId) {
    const wrapper = el("div", { id: rootId, class: "lora-manager-picker" });
    const wrap = el("div", { class: "lm-picker-wrap" });
    const box = el("div", { class: "lm-picker-box", tabindex: "0" });
    const placeholder = el("span", { class: "lm-picker-placeholder" }, "Select LoRA");
    const openHit = el("button", { class: "lm-picker-hit", type: "button", title: "Select LoRA" }, "▾");
    box.append(placeholder);
    wrap.append(box, openHit);
    wrapper.append(el("div", { class: "lm-picker-label" }, "LoRA Manager"), wrap);

    const selected = new Map();
    let menu = null;
    let lastFolder = localStorage.getItem(LS.lastFolder) || "";
    let presets = readLS(LS.presets, {});
    let view = localStorage.getItem(LS.view) || "list";

    function selectedList() {
      return Array.from(selected.entries())
        .filter(([, obj]) => obj && obj.on)
        .map(([key, obj]) => ({
          key,
          name: obj.name,
          filename: obj.filename,
          weight: clamp(typeof obj.w === "number" ? obj.w : 1, WEIGHT_MIN, WEIGHT_MAX),
          triggers: enabledTriggers(obj),
        }));
    }

    function bindWeight(weight, obj) {
      let startX = 0;
      let startW = obj.w;
      weight.addEventListener("mousedown", (event) => {
        event.preventDefault();
        event.stopPropagation();
        startX = event.clientX;
        startW = obj.w;
        const move = (ev) => {
          obj.w = clamp(startW + (ev.clientX - startX) / 80, WEIGHT_MIN, WEIGHT_MAX);
          weight.textContent = obj.w.toFixed(2);
        };
        const up = () => {
          document.removeEventListener("mousemove", move);
          document.removeEventListener("mouseup", up);
        };
        document.addEventListener("mousemove", move);
        document.addEventListener("mouseup", up);
      });
    }

    function buildChip(key, obj) {
      const chip = el("span", { class: "lm-chip" + (obj.on ? "" : " off") + (obj.open ? " is-open" : "") });
      const name = el("button", {
        class: "lm-chip-name",
        type: "button",
        title: obj.open ? "Hide triggers" : "Show triggers",
      }, (obj.open ? "▾ " : "▸ ") + obj.name);
      name.addEventListener("click", (event) => {
        event.stopPropagation();
        obj.open = !obj.open;
        renderBox();
      });
      const weight = el("span", { class: "lm-w", title: "Drag to change weight" }, obj.w.toFixed(2));
      bindWeight(weight, obj);
      const close = el("button", { class: "lm-x", type: "button" }, "×");
      close.addEventListener("click", (event) => {
        event.stopPropagation();
        selected.delete(key);
        renderBox();
      });
      chip.append(name, weight, close);
      if (obj.open) {
        const trigs = el("span", { class: "lm-chip-trigs" });
        Object.keys(obj.trig || {}).forEach((word) => {
          const on = obj.trig[word] !== false;
          const btn = el("button", { class: "lm-trig" + (on ? "" : " off"), type: "button", title: on ? "Disable trigger" : "Enable trigger" }, word);
          btn.addEventListener("click", (event) => {
            event.stopPropagation();
            obj.trig[word] = !on;
            renderBox();
          });
          trigs.append(btn);
        });
        if (trigs.childNodes.length) chip.append(trigs);
      }
      return chip;
    }

    function renderBox() {
      Array.from(box.querySelectorAll(".lm-chip")).forEach((node) => node.remove());
      if (!selected.size) {
        placeholder.style.display = "";
        return;
      }
      placeholder.style.display = "none";
      selected.forEach((obj, key) => box.append(buildChip(key, obj)));
    }

    function openPresets() {
      if (!menu) return;
      const existing = menu.querySelector(".lm-preset-menu");
      if (existing) {
        existing.remove();
        return;
      }
      const menuEl = el("div", { class: "lm-preset-menu" });
      const nameInput = el("input", { class: "lm-input lm-search", placeholder: "Preset name" });
      const saveBtn = el("button", { class: "lm-btn", type: "button" }, "Save current");
      saveBtn.addEventListener("click", () => {
        const name = (nameInput.value || "").trim();
        if (!name) return;
        presets[name] = selectedList();
        localStorage.setItem(LS.presets, JSON.stringify(presets));
        menuEl.remove();
      });
      menuEl.append(el("div", { class: "hdr" }, nameInput, saveBtn));
      Object.keys(presets).sort().forEach((name) => {
        const row = el("div", { class: "row" });
        const load = el("button", { class: "lm-btn", type: "button" }, name);
        load.addEventListener("click", () => {
          selected.clear();
          (presets[name] || []).forEach((item) => {
            const row = State.items.find((lora) => lora.key === item.key || lora.name === item.name) || { name: item.name, triggers: item.triggers };
            const trig = triggerMap(row, null);
            if (Array.isArray(item.triggers)) {
              Object.keys(trig).forEach((word) => { trig[word] = item.triggers.includes(word); });
            }
            selected.set(item.key || item.name, { name: item.name, w: item.weight, on: true, trig, open: false });
          });
          renderBox();
          menuEl.remove();
        });
        const del = el("button", { class: "lm-btn", type: "button" }, "✕");
        del.addEventListener("click", () => {
          delete presets[name];
          localStorage.setItem(LS.presets, JSON.stringify(presets));
          menuEl.remove();
          openPresets();
        });
        row.append(load, del);
        menuEl.append(row);
      });
      menu.append(menuEl);
    }

    function closeMenu() {
      wrapper.classList.remove("is-open");
      if (!menu) return;
      menu.remove();
      menu = null;
    }

    function positionMenu() {
      if (!menu) return;
      menu.style.position = "absolute";
      menu.style.left = "0";
      menu.style.right = "0";
      menu.style.top = "calc(100% + 6px)";
      menu.style.bottom = "auto";
      menu.style.width = "auto";
      menu.style.height = "min(520px, 70vh)";
      menu.style.maxHeight = "70vh";
    }

    async function openMenu() {
      if (menu) {
        closeMenu();
        return;
      }
      if (!State.loaded) await loadLibrary();
      const folders = foldersFrom(State.items);
      menu = el("div", { class: "lm-menu" });
      const left = el("div", { class: "lm-left" });
      const right = el("div", { class: "lm-right" });
      const top = el("div", { class: "lm-top" });
      const search = el("input", { class: "lm-input lm-search", placeholder: "Search" });
      const all = el("label", { class: "lm-all" }, el("input", { type: "checkbox" }), " All folders");
      all.querySelector("input").checked = localStorage.getItem(LS.searchAll) === "1";
      const refresh = el("button", { class: "lm-refresh", type: "button" }, "↻");
      const listBtn = el("button", { class: "lm-btn lm-btn-list" + (view === "list" ? " is-active" : ""), type: "button" }, "List");
      const gridBtn = el("button", { class: "lm-btn lm-btn-grid" + (view === "grid" ? " is-active" : ""), type: "button" }, "Grid");
      const presetsBtn = el("button", { class: "lm-btn", type: "button" }, "Presets");
      presetsBtn.addEventListener("click", (event) => {
        event.stopPropagation();
        openPresets();
      });
      top.append(search, all, refresh, listBtn, gridBtn, presetsBtn);
      const list = el("div", { class: "lm-list" });
      const grid = el("div", { class: "lm-grid" });
      right.append(top, list, grid);
      menu.append(left, right);
      menu.addEventListener("mousedown", (event) => event.stopPropagation());
      wrap.append(menu);
      wrapper.classList.add("is-open");
      positionMenu();

      let current = lastFolder;
      const folderNames = ["★ Favorites", ...Object.keys(folders).sort((a, b) => a.localeCompare(b))];
      if (!folderNames.includes(current)) current = folderNames[1] || folderNames[0];

      function renderFolders() {
        left.innerHTML = "";
        folderNames.forEach((name) => {
          const row = el("button", { class: "lm-folder" + (name === current ? " active" : ""), type: "button" }, name || "(root)");
          noFocusScroll(row);
          row.addEventListener("click", () => {
            current = name;
            if (name !== "★ Favorites") {
              lastFolder = name;
              localStorage.setItem(LS.lastFolder, lastFolder);
            }
            renderFolders();
            renderItems();
          });
          left.append(row);
        });
      }

      function visibleItems() {
        const query = (search.value || "").trim().toLowerCase();
        const searchAll = all.querySelector("input").checked;
        let pool;
        if (current === "★ Favorites") {
          pool = State.items.filter((item) => isFavorite(item));
        } else if (searchAll && query) {
          pool = State.items;
        } else {
          pool = folders[current] || [];
        }
        if (!query) return pool;
        return pool.filter((item) => {
          const hay = [item.name, item.folder, ...(item.triggers || []), item.base_model].join(" ").toLowerCase();
          return hay.includes(query);
        });
      }

      function pick(item) {
        const weight = Number(item.preferred_weight) || 1;
        selected.forEach((obj) => { obj.open = false; });
        if (!selected.has(item.key)) {
          selected.set(item.key, {
            name: loraTokenName(item),
            filename: item.filename,
            w: clamp(weight, WEIGHT_MIN, WEIGHT_MAX),
            on: true,
            trig: triggerMap(item, null),
            open: true,
          });
        } else {
          selected.get(item.key).open = true;
        }
        renderBox();
      }

      function makeStar(item) {
        const starred = isFavorite(item);
        const star = el("span", { class: "star" + (starred ? " is-on" : "") }, starred ? "★" : "☆");
        star.addEventListener("click", (event) => {
          event.stopPropagation();
          toggleFavorite(item);
          renderItems();
        });
        return star;
      }

      function renderItems() {
        const items = visibleItems();
        const listTop = list.scrollTop;
        const gridTop = grid.scrollTop;
        list.innerHTML = "";
        grid.innerHTML = "";
        list.style.display = view === "list" ? "" : "none";
        grid.style.display = view === "grid" ? "" : "none";
        items.forEach((item) => {
          const row = el("button", { class: "lm-item", type: "button", title: (item.triggers || []).join(", ") }, el("span", {}, item.name), makeStar(item));
          noFocusScroll(row);
          row.addEventListener("click", () => pick(item));
          row.addEventListener("contextmenu", (event) => {
            event.preventDefault();
            openItemModal(item);
          });
          list.append(row);

          const tile = el("button", { class: "lm-tile", type: "button", title: item.name });
          if (item.preview) tile.append(lazyPreview(item, grid));
          tile.append(el("span", {}, item.name), makeStar(item));
          noFocusScroll(tile);
          tile.addEventListener("click", () => pick(item));
          tile.addEventListener("contextmenu", (event) => {
            event.preventDefault();
            openItemModal(item);
          });
          grid.append(tile);
        });
        list.scrollTop = listTop;
        grid.scrollTop = gridTop;
      }

      listBtn.addEventListener("click", () => {
        view = "list";
        localStorage.setItem(LS.view, view);
        listBtn.classList.add("is-active");
        gridBtn.classList.remove("is-active");
        renderItems();
      });
      gridBtn.addEventListener("click", () => {
        view = "grid";
        localStorage.setItem(LS.view, view);
        gridBtn.classList.add("is-active");
        listBtn.classList.remove("is-active");
        renderItems();
      });
      search.addEventListener("input", renderItems);
      all.querySelector("input").addEventListener("change", (event) => {
        localStorage.setItem(LS.searchAll, event.target.checked ? "1" : "0");
        renderItems();
      });
      refresh.addEventListener("click", async () => {
        refresh.disabled = true;
        await loadLibrary();
        refresh.disabled = false;
        renderFolders();
        renderItems();
      });
      renderFolders();
      renderItems();
      search.focus({ preventScroll: true });
      const onDoc = (event) => {
        if (event.target.closest("#lm-overlay") || event.target.closest(".lm-menu") || wrapper.contains(event.target)) return;
        closeMenu();
        document.removeEventListener("mousedown", onDoc);
      };
      setTimeout(() => document.addEventListener("mousedown", onDoc), 0);
    }

    openHit.addEventListener("click", (event) => {
      event.stopPropagation();
      openMenu();
    });
    box.addEventListener("mousedown", (event) => {
      event.stopPropagation();
      if (event.target === box || event.target.classList.contains("lm-picker-placeholder")) openMenu();
    });
    renderBox();
    return { wrapper, getSelected: selectedList };
  }

  function place(wrapper, tab) {
    const negRow = qs(`#${tab}_neg_prompt_row`);
    if (negRow) {
      negRow.insertAdjacentElement("afterend", wrapper);
      return;
    }
    const container = qs(`#${tab}_prompt_container`);
    if (container) container.appendChild(wrapper);
  }

  function buildAugmentedPrompt(original, selected) {
    let result = original || "";
    const triggers = [];
    selected.forEach((sel) => {
      const words = Array.isArray(sel.triggers) ? sel.triggers : (State.items.find((row) => row.name === sel.name)?.triggers || []);
      words.forEach((word) => {
        if (word && !triggers.includes(word)) triggers.push(word);
      });
    });
    const low = result.toLowerCase();
    const missing = triggers.filter((word) => word && !low.includes(word.toLowerCase()));
    if (missing.length) {
      const sep = result.trim() ? (result.trim().endsWith(",") ? " " : ", ") : "";
      result = result + sep + missing.join(", ");
    }
    selected.forEach((sel) => {
      const token = `<lora:${loraTokenName(sel)}:${sel.weight.toFixed(2)}>`;
      if (!result.includes(token)) result = (result.trim() + " " + token).trim();
    });
    return result;
  }

  function temporarilyAugment(tab) {
    const selected = (window._lmGetSelected[tab] || (() => []))();
    if (!selected.length) return;
    const fields = [`#${tab}_prompt textarea`];
    if (tab === "txt2img") fields.push("#txt2img_hr_prompt textarea");
    const textareas = fields.map((sel) => qs(sel)).filter(Boolean);
    const changed = [];
    textareas.forEach((ta) => {
      const original = ta.value || "";
      const next = buildAugmentedPrompt(original, selected);
      if (next === original) return;
      ta.value = next;
      ta.dispatchEvent(new Event("input", { bubbles: true }));
      changed.push({ ta, original });
    });
    setTimeout(() => {
      changed.forEach(({ ta, original }) => {
        ta.value = original;
        ta.dispatchEvent(new Event("input", { bubbles: true }));
      });
    }, 400);
  }

  function installHooks() {
    qsa("#txt2img_generate, #img2img_generate").forEach((btn) => {
      if (btn.dataset._lmHooked) return;
      btn.dataset._lmHooked = "1";
      btn.addEventListener("click", () => {
        temporarilyAugment(btn.id.startsWith("img2img") ? "img2img" : "txt2img");
      }, true);
    });
    if (window._lmHiresHooked) return;
    window._lmHiresHooked = true;
    document.addEventListener("click", (event) => {
      const btn = event.target && event.target.closest && event.target.closest("button, [role='button']");
      if (!btn || btn.id === "txt2img_generate" || btn.id === "img2img_generate") return;
      const text = [btn.id, btn.title, btn.textContent, btn.className].join(" ").toLowerCase();
      if (/(hires|hi-res|upscale)/.test(text)) temporarilyAugment("txt2img");
    }, true);
  }

  function civitaiUrl(item) {
    if (item && item.civitai_url) return item.civitai_url;
    const host = "https://civitai.red";
    if (!item) return host;
    const modelId = item.model_id || item.modelId;
    const versionId = item.version_id || item.versionId;
    if (!modelId) return host;
    let url = `${host}/models/${modelId}`;
    if (versionId) url += `?modelVersionId=${versionId}`;
    return url;
  }

  function mountLibraryTab() {
    const root = document.getElementById("lora-manager-tab-root");
    if (!root) return;
    if (root.dataset.ready && root.querySelector(".lm-lib")) return;
    root.dataset.ready = "1";
    root.innerHTML = "";
    const toolbar = el("div", { class: "lm-lib-toolbar" });
    const search = el("input", { class: "lm-input lm-search", placeholder: "Filter name, trigger, tag, base model" });
    const baseFilter = el("select", { class: "lm-input" });
    const metaFilter = el("select", { class: "lm-input" });
    const favOnly = el("label", {}, el("input", { type: "checkbox" }), " Favorites");
    ["all metadata", "missing metadata", "has metadata"].forEach((label, i) => {
      metaFilter.append(el("option", { value: String(i) }, label));
    });
    const syncMissing = el("button", { class: "lm-btn", type: "button" }, "Sync missing");
    const syncAll = el("button", { class: "lm-btn", type: "button" }, "Refresh all");
    const progress = el("span", {});
    toolbar.append(search, baseFilter, metaFilter, favOnly, syncMissing, syncAll, progress);

    const layout = el("div", { class: "lm-lib" });
    const foldersCol = el("div", { class: "lm-lib-folders" });
    const grid = el("div", { class: "lm-lib-grid" });
    const card = el("div", { class: "lm-card" }, el("p", {}, "Select a LoRA"));
    layout.append(foldersCol, grid, card);
    root.append(toolbar, layout);

    let currentFolder = "";
    let currentKey = window._lmOpenKey || "";

    function filtered() {
      const q = (search.value || "").toLowerCase();
      const metaMode = metaFilter.value;
      return State.items.filter((item) => {
        if (currentFolder && item.folder !== currentFolder) return false;
        if (baseFilter.value && (item.base_model || "") !== baseFilter.value) return false;
        if (favOnly.querySelector("input").checked && !isFavorite(item)) return false;
        const hasMeta = item.has_forge_json || item.has_comfy_metadata;
        if (metaMode === "1" && hasMeta) return false;
        if (metaMode === "2" && !hasMeta) return false;
        if (!q) return true;
        const hay = [item.name, item.folder, item.base_model, ...(item.triggers || []), ...(item.tags || [])].join(" ").toLowerCase();
        return hay.includes(q);
      });
    }

    function renderFolders() {
      const names = [...new Set(State.items.map((item) => item.folder || ""))].sort();
      foldersCol.innerHTML = "";
      const allBtn = el("button", { class: "lm-folder" + (currentFolder === "" ? " active" : ""), type: "button" }, "All folders");
      noFocusScroll(allBtn);
      allBtn.addEventListener("click", () => { currentFolder = ""; render(); });
      foldersCol.append(allBtn);
      names.forEach((name) => {
        const btn = el("button", { class: "lm-folder" + (currentFolder === name ? " active" : ""), type: "button" }, name || "(root)");
        noFocusScroll(btn);
        btn.addEventListener("click", () => { currentFolder = name; render(); });
        foldersCol.append(btn);
      });
      const bases = [...new Set(State.items.map((item) => item.base_model).filter(Boolean))].sort();
      const prevBase = baseFilter.value;
      baseFilter.innerHTML = "";
      baseFilter.append(el("option", { value: "" }, "All base models"));
      bases.forEach((name) => baseFilter.append(el("option", { value: name }, name)));
      baseFilter.value = bases.includes(prevBase) ? prevBase : "";
    }

    async function showCard(item) {
      currentKey = item.key;
      await fillLoraCard(card, item, {
        onFavorite: () => {
          if (favOnly.querySelector("input").checked) renderGrid();
        },
        onReload: (fresh) => showCard(fresh),
      });
    }

    function renderGrid() {
      const top = grid.scrollTop;
      const prevObs = lazyObservers.get(grid);
      if (prevObs) {
        prevObs.disconnect();
        lazyObservers.delete(grid);
      }
      grid.innerHTML = "";
      filtered().forEach((item) => {
        const tile = el("button", { class: "lm-lib-tile", type: "button" });
        if (isFavorite(item)) tile.classList.add("is-fav");
        if (item.preview) tile.append(lazyPreview(item, grid));
        tile.append(el("span", {}, item.name));
        if (!item.has_forge_json && !item.has_comfy_metadata) tile.append(el("small", {}, "no metadata"));
        noFocusScroll(tile);
        tile.addEventListener("click", () => showCard(item));
        grid.append(tile);
      });
      grid.scrollTop = top;
    }

    function render() {
      renderFolders();
      renderGrid();
      if (currentKey) {
        const item = State.items.find((row) => row.key === currentKey);
        if (item) showCard(item);
      }
    }

    async function runJob(missingOnly) {
      const started = await fetchJSON(`/lora-manager/sync-all?missing_only=${missingOnly ? "true" : "false"}`, { method: "POST" });
      if (!started.job) {
        progress.textContent = started.error || "Could not start sync";
        return;
      }
      const poll = async () => {
        const job = await fetchJSON(`/lora-manager/sync-progress?job=${started.job}`);
        progress.textContent = `${job.done || 0}/${job.total || 0}  ok ${job.ok || 0}  fail ${job.failed || 0}`;
        if (job.running) setTimeout(poll, 800);
        else {
          await loadLibrary();
          render();
        }
      };
      poll();
    }

    search.addEventListener("input", renderGrid);
    metaFilter.addEventListener("change", renderGrid);
    baseFilter.addEventListener("change", renderGrid);
    favOnly.querySelector("input").addEventListener("change", renderGrid);
    syncMissing.addEventListener("click", () => runJob(true));
    syncAll.addEventListener("click", () => runJob(false));
    window.addEventListener("lora-manager-open", (event) => {
      currentKey = event.detail?.key || currentKey;
      const item = State.items.find((row) => row.key === currentKey);
      if (item) showCard(item);
    });
    render();
  }

  async function mount() {
    if (!qs("#txt2img_prompt_container") && !qs("#img2img_prompt_container") && !document.getElementById("lora-manager-tab-root")) {
      setTimeout(mount, 250);
      return;
    }
    if (!State.loaded) await loadLibrary();
    if (qs("#txt2img_prompt_container") && !document.getElementById(EXT_TXT)) {
      const ui = createUI(EXT_TXT);
      place(ui.wrapper, "txt2img");
      window._lmGetSelected.txt2img = ui.getSelected;
    }
    if (qs("#img2img_prompt_container") && !document.getElementById(EXT_IMG)) {
      const ui = createUI(EXT_IMG);
      place(ui.wrapper, "img2img");
      window._lmGetSelected.img2img = ui.getSelected;
    }
    mountLibraryTab();
    installHooks();
  }

  if (typeof onUiLoaded === "function") onUiLoaded(mount);
  else if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => setTimeout(mount, 50));
  else setTimeout(mount, 50);
  if (typeof onUiUpdate === "function") onUiUpdate(() => { mount(); });
})();
