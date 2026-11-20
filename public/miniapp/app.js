/* Ранок — Telegram Mini App (демо OK GER)
 * Каталог, кастомізація напоїв, кошик, оформлення замовлення.
 * У Telegram використовує нативні MainButton / BackButton / HapticFeedback / CloudStorage,
 * у звичайному браузері — власні кнопки, щоб демо можна було відкрити й із сайту.
 */
(() => {
  "use strict";

  const tg = window.Telegram && window.Telegram.WebApp;
  const inTG = !!(tg && tg.initData);
  const can = (v) => inTG && typeof tg.isVersionAtLeast === "function" && tg.isVersionAtLeast(v);
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const state = {
    menu: null,
    cart: [], // {key, id, opts, qty}
    screen: "home",
    sheet: null, // {product, opts, qty}
    pickup: "asap",
    pay: "card",
    stamps: 0,
    sending: false,
  };

  /* ================= THEME ================= */
  function applyTheme() {
    const dark = inTG
      ? tg.colorScheme !== "light"
      : !(window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches);
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    const bg = dark ? "#020617" : "#f4f6fb";
    if (can("6.1")) {
      try { tg.setHeaderColor(bg); tg.setBackgroundColor(bg); } catch (e) { /* noop */ }
    }
    if (can("7.10")) {
      try { tg.setBottomBarColor(bg); } catch (e) { /* noop */ }
    }
  }

  /* ================= TELEGRAM HELPERS ================= */
  let mainHandler = null;
  function setMain(text, handler) {
    if (inTG) {
      const mb = tg.MainButton;
      if (mainHandler) mb.offClick(mainHandler);
      mainHandler = handler;
      mb.setParams({ text, color: "#2563eb", text_color: "#ffffff", is_active: true, is_visible: true });
      mb.onClick(mainHandler);
    } else {
      $("fallbackBar").hidden = false;
      const b = $("fallbackBtn");
      b.textContent = text;
      b.disabled = false;
      b.onclick = handler;
    }
  }
  function hideMain() {
    if (inTG) {
      if (mainHandler) tg.MainButton.offClick(mainHandler);
      mainHandler = null;
      tg.MainButton.hide();
    } else {
      $("fallbackBar").hidden = true;
    }
  }
  function mainBusy(on) {
    if (inTG) {
      on ? tg.MainButton.showProgress(false) : tg.MainButton.hideProgress();
    } else {
      $("fallbackBtn").disabled = on;
    }
  }

  let backHandler = null;
  function setBack(handler) {
    if (!can("6.1")) return;
    if (backHandler) tg.BackButton.offClick(backHandler);
    backHandler = handler;
    if (handler) {
      tg.BackButton.onClick(handler);
      tg.BackButton.show();
    } else {
      tg.BackButton.hide();
    }
  }

  function haptic(kind) {
    if (!inTG || !tg.HapticFeedback || !can("6.1")) return;
    try {
      if (kind === "select") tg.HapticFeedback.selectionChanged();
      else if (kind === "success" || kind === "error" || kind === "warning") tg.HapticFeedback.notificationOccurred(kind);
      else tg.HapticFeedback.impactOccurred(kind || "light");
    } catch (e) { /* noop */ }
  }

  function closingGuard() {
    if (!can("6.2")) return;
    state.cart.length ? tg.enableClosingConfirmation() : tg.disableClosingConfirmation();
  }

  const store = {
    get(key) {
      return new Promise((resolve) => {
        if (can("6.9") && tg.CloudStorage) {
          tg.CloudStorage.getItem(key, (err, val) => resolve(err ? null : val));
        } else {
          try { resolve(localStorage.getItem("ranok_" + key)); } catch (e) { resolve(null); }
        }
      });
    },
    set(key, val) {
      if (can("6.9") && tg.CloudStorage) {
        tg.CloudStorage.setItem(key, String(val), () => {});
      } else {
        try { localStorage.setItem("ranok_" + key, String(val)); } catch (e) { /* noop */ }
      }
    },
  };

  let toastTimer = null;
  function toast(text) {
    const t = $("toast");
    t.textContent = text;
    t.classList.add("is-show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.remove("is-show"), 1800);
  }

  function confirmBox(text) {
    return new Promise((resolve) => {
      if (can("6.2")) tg.showConfirm(text, (ok) => resolve(!!ok));
      else resolve(window.confirm(text));
    });
  }
  function alertBox(text) {
    if (can("6.2")) tg.showAlert(text);
    else window.alert(text);
  }

  /* ================= ILLUSTRATIONS ================= */
  const BG = {
    espresso: "bg-coffee", cup: "bg-coffee", cappuccino: "bg-coffee", latte: "bg-latte",
    croissant: "bg-pastry", bun: "bg-pastry", pie: "bg-cherry",
    syrnyky: "bg-cream", toast: "bg-break", granola: "bg-cream",
    honeycake: "bg-cream", napoleon: "bg-cream", cheesecake: "bg-berry",
  };
  const ART = {
    cappuccino:
      '<ellipse cx="50" cy="54" rx="42" ry="38" fill="#efe5d8"/><rect x="74" y="46" width="16" height="11" rx="5.5" fill="#fff"/>' +
      '<circle cx="50" cy="52" r="29" fill="#fff"/><circle cx="50" cy="52" r="24" fill="#8a5a3c"/>' +
      '<path d="M50 65c-9-6-14-11-14-17a7 7 0 0 1 14-2 7 7 0 0 1 14 2c0 6-5 11-14 17z" fill="#f3e3cf"/>',
    cup:
      '<ellipse cx="50" cy="54" rx="42" ry="38" fill="#efe5d8"/><rect x="74" y="46" width="16" height="11" rx="5.5" fill="#fff"/>' +
      '<circle cx="50" cy="52" r="29" fill="#fff"/><circle cx="50" cy="52" r="24" fill="#3a2418"/>' +
      '<circle cx="50" cy="52" r="20" fill="none" stroke="#7a4a2c" stroke-width="3" opacity=".7"/><circle cx="44" cy="46" r="4" fill="#fff" opacity=".18"/>',
    espresso:
      '<ellipse cx="50" cy="80" rx="36" ry="8" fill="#efe5d8"/>' +
      '<path d="M67 46h5a8 8 0 0 1 0 16h-6" fill="none" stroke="#fff" stroke-width="5"/>' +
      '<path d="M28 40h40v14a20 20 0 0 1-20 20 20 20 0 0 1-20-20z" fill="#fff"/>' +
      '<ellipse cx="48" cy="40" rx="20" ry="5" fill="#5b3a24"/><ellipse cx="48" cy="40" rx="13" ry="3" fill="#c58a55"/>' +
      '<path d="M40 30c0-6 6-6 6-12M52 30c0-6 6-6 6-12" fill="none" stroke="#fff" stroke-opacity=".55" stroke-width="3" stroke-linecap="round"/>',
    latte:
      '<rect x="56" y="4" width="5" height="34" rx="2.5" fill="#60a5fa" transform="rotate(12 58 21)"/>' +
      '<path d="M37 58h26l-1.6 24a5 5 0 0 1-5 4.6H43.6a5 5 0 0 1-5-4.6z" fill="#f3e7d7"/>' +
      '<path d="M36 41h28l-1 17H37z" fill="#a8744f"/><path d="M35 24h30l-1 17H36z" fill="#fbf6ef"/>' +
      '<path d="M34 20h32l-4 63a6 6 0 0 1-6 5H44a6 6 0 0 1-6-5z" fill="none" stroke="#fff" stroke-opacity=".7" stroke-width="2.5"/>',
    croissant:
      '<path d="M12 64c6-24 25-36 38-36s32 12 38 36c-6 7-15 5-19-2-5 8-13 11-19 11s-14-3-19-11c-4 7-13 9-19 2z" fill="#e89a3c"/>' +
      '<path d="M33 40c4 8 6 18 6 29M50 30v41M67 40c-4 8-6 18-6 29" stroke="#b8681e" stroke-width="3.2" fill="none" stroke-linecap="round"/>' +
      '<path d="M23 54c6-13 16-21 27-22" stroke="#fbd38d" stroke-width="4" fill="none" stroke-linecap="round" opacity=".85"/>',
    bun:
      '<ellipse cx="50" cy="80" rx="38" ry="7" fill="#000" opacity=".12"/><circle cx="50" cy="50" r="34" fill="#d98a3d"/>' +
      '<path d="M46 50a4 4 0 1 1 8 0 10 10 0 1 1-18 0 16 16 0 1 1 30 0 22 22 0 1 1-42 0" fill="none" stroke="#9a5420" stroke-width="4" stroke-linecap="round"/>' +
      '<path d="M24 38c10 6 18-6 28 0s18 6 24 0" stroke="#fff7ea" stroke-width="4.5" fill="none" stroke-linecap="round"/>',
    pie:
      '<ellipse cx="50" cy="60" rx="38" ry="22" fill="#d38b3c"/><ellipse cx="50" cy="55" rx="34" ry="17" fill="#f0b765"/>' +
      '<path d="M36 50l6 6M48 48l6 6M60 50l6 6" stroke="#c27a2c" stroke-width="3" stroke-linecap="round"/>' +
      '<path d="M70 24c2-6 6-9 10-10M81 28c0-6 0-10-1-14" stroke="#4d7c0f" stroke-width="2.2" fill="none" stroke-linecap="round"/>' +
      '<circle cx="69" cy="30" r="7" fill="#be123c"/><circle cx="81" cy="33" r="6" fill="#e11d48"/>',
    syrnyky:
      '<ellipse cx="50" cy="64" rx="44" ry="22" fill="#fff"/>' +
      '<ellipse cx="34" cy="63" rx="16" ry="8" fill="#c47a2a"/><ellipse cx="34" cy="60" rx="16" ry="8" fill="#f2b45c"/>' +
      '<ellipse cx="66" cy="63" rx="16" ry="8" fill="#c47a2a"/><ellipse cx="66" cy="60" rx="16" ry="8" fill="#f2b45c"/>' +
      '<ellipse cx="50" cy="52" rx="16" ry="8" fill="#c47a2a"/><ellipse cx="50" cy="49" rx="16" ry="8" fill="#f5be6a"/>' +
      '<path d="M43 46c0-7 14-7 14 0 0 4-14 4-14 0z" fill="#fffaf0"/><circle cx="72" cy="52" r="4" fill="#be123c"/><circle cx="27" cy="54" r="3" fill="#be123c"/>',
    toast:
      '<path d="M22 32c0-12 56-12 56 0 0 6-4 8-4 12v32a5 5 0 0 1-5 5H31a5 5 0 0 1-5-5V44c0-4-4-6-4-12z" fill="#b8763d"/>' +
      '<path d="M28 34c0-8 44-8 44 0 0 5-3 7-3 10v29a3 3 0 0 1-3 3H34a3 3 0 0 1-3-3V44c0-3-3-5-3-10z" fill="#f1c98c"/>' +
      '<ellipse cx="42" cy="52" rx="10" ry="15" fill="#65a30d" transform="rotate(-20 42 52)"/><ellipse cx="42" cy="52" rx="7" ry="11" fill="#bef264" transform="rotate(-20 42 52)"/>' +
      '<circle cx="60" cy="60" r="12" fill="#fff"/><circle cx="60" cy="60" r="5.5" fill="#f59e0b"/>' +
      '<circle cx="54" cy="40" r="2.5" fill="#16a34a"/><circle cx="64" cy="44" r="2" fill="#16a34a"/>',
    granola:
      '<ellipse cx="50" cy="80" rx="34" ry="6" fill="#000" opacity=".12"/><path d="M16 48h68a34 34 0 0 1-68 0z" fill="#fff"/>' +
      '<ellipse cx="50" cy="48" rx="34" ry="9" fill="#fef3c7"/>' +
      '<circle cx="36" cy="46" r="4" fill="#b45309"/><circle cx="46" cy="44" r="3.5" fill="#d97706"/><circle cx="58" cy="47" r="4" fill="#b45309"/>' +
      '<circle cx="66" cy="44" r="3.5" fill="#1d4ed8"/><circle cx="52" cy="49" r="3" fill="#be123c"/><circle cx="42" cy="50" r="3" fill="#1d4ed8"/>',
    honeycake:
      '<ellipse cx="50" cy="80" rx="40" ry="7" fill="#fff"/><rect x="22" y="34" width="56" height="42" rx="4" fill="#f6e3c0"/>' +
      '<rect x="22" y="41" width="56" height="5" fill="#c47a2a"/><rect x="22" y="53" width="56" height="5" fill="#c47a2a"/><rect x="22" y="65" width="56" height="5" fill="#c47a2a"/>' +
      '<rect x="20" y="28" width="60" height="9" rx="4.5" fill="#d99a52"/><circle cx="34" cy="31" r="1.6" fill="#f6e3c0"/><circle cx="52" cy="33" r="1.6" fill="#f6e3c0"/><circle cx="68" cy="31" r="1.6" fill="#f6e3c0"/>',
    napoleon:
      '<ellipse cx="50" cy="80" rx="40" ry="7" fill="#fff"/><rect x="22" y="34" width="56" height="42" rx="3" fill="#fff3dc"/>' +
      '<rect x="22" y="40" width="56" height="4" fill="#e2b170"/><rect x="22" y="50" width="56" height="4" fill="#e2b170"/><rect x="22" y="60" width="56" height="4" fill="#e2b170"/><rect x="22" y="70" width="56" height="4" fill="#e2b170"/>' +
      '<rect x="20" y="28" width="60" height="8" rx="3" fill="#fbe9c9"/><circle cx="30" cy="31" r="1.4" fill="#fff"/><circle cx="44" cy="33" r="1.4" fill="#fff"/><circle cx="58" cy="31" r="1.4" fill="#fff"/><circle cx="72" cy="33" r="1.4" fill="#fff"/>',
    cheesecake:
      '<ellipse cx="50" cy="80" rx="40" ry="7" fill="#fff"/>' +
      '<path d="M20 42c0-8 60-8 60 0v28c0 7-60 7-60 0z" fill="#fde7b0"/>' +
      '<path d="M20 42v28c0 7 60 7 60 0V42" fill="none" stroke="#8a4b1f" stroke-width="3" opacity=".55"/>' +
      '<ellipse cx="50" cy="42" rx="30" ry="7" fill="#5b3418"/><ellipse cx="44" cy="41" rx="10" ry="2.5" fill="#7c4a26"/>',
  };
  function art(name) {
    return '<svg viewBox="0 0 100 100" aria-hidden="true">' + (ART[name] || ART.cup) + "</svg>";
  }

  /* ================= PRICING ================= */
  const product = (id) => state.menu.products.find((p) => p.id === id);
  const groupOpt = (g, id) => state.menu.groups[g].options.find((o) => o.id === id);

  function unitPrice(p, opts) {
    let sum = p.price;
    p.groups.forEach((g) => {
      const o = groupOpt(g, opts[g]);
      if (o) sum += o.d;
    });
    return sum;
  }
  const lineTotal = (l) => unitPrice(product(l.id), l.opts) * l.qty;
  const cartCount = () => state.cart.reduce((s, l) => s + l.qty, 0);
  const cartTotal = () => state.cart.reduce((s, l) => s + lineTotal(l), 0);
  const qtyOf = (id) => state.cart.filter((l) => l.id === id).reduce((s, l) => s + l.qty, 0);

  const HIDDEN_OPTS = ["none", "no", "cow", "single"];
  function optsLabel(p, opts) {
    return p.groups
      .map((g) => {
        const o = groupOpt(g, opts[g]);
        if (!o || HIDDEN_OPTS.includes(o.id)) return null;
        return g === "size" ? o.label.split(" ·")[0] : o.label.toLowerCase();
      })
      .filter(Boolean)
      .join(", ");
  }
  function defaultOpts(p) {
    const opts = {};
    p.groups.forEach((g) => {
      const list = state.menu.groups[g].options;
      opts[g] = g === "size" && list.some((o) => o.id === "m") ? "m" : list[0].id;
    });
    return opts;
  }

  /* ================= HOME ================= */
  function renderHero() {
    const s = state.menu.store;
    $("storeName").textContent = s.name;
    $("storeTagline").textContent = s.tagline;
    $("storeAddress").textContent = s.address;
    $("storePrep").textContent = s.prep;

    const h = new Date().getHours();
    const hello = h < 12 ? "Доброго ранку" : h < 18 ? "Доброго дня" : "Доброго вечора";
    const user = inTG && tg.initDataUnsafe && tg.initDataUnsafe.user;
    $("greeting").textContent = user && user.first_name ? `${hello}, ${user.first_name}!` : `${hello}!`;

    const now = new Date();
    const mins = now.getHours() * 60 + now.getMinutes();
    const open = mins >= 7 * 60 + 30 && mins < 20 * 60;
    $("openLabel").textContent = open ? "Відкрито до 20:00" : "Передзамовлення";
    $("openStatus").classList.toggle("is-closed", !open);
  }

  function renderStamps() {
    const n = state.stamps;
    const wrap = $("stamps");
    let html = "";
    for (let i = 0; i < 7; i++) {
      const on = i < n;
      const gift = i === 6;
      html += `<span class="stamp${on ? " is-on" : ""}${gift && !on ? " is-gift" : ""}">` +
        (gift
          ? '<svg viewBox="0 0 24 24" width="14" height="14"><path d="M4 11h16v9H4zM3 7h18v4H3zM12 7v13M12 7c-2-4-6-4-6-1s6 1 6 1zm0 0c2-4 6-4 6-1s-6 1-6 1z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>'
          : on
          ? '<svg viewBox="0 0 24 24" width="14" height="14"><path d="M5 9h11v4a5 5 0 0 1-5 5h-1a5 5 0 0 1-5-5zM16 10h2a2 2 0 0 1 0 4h-2" fill="none" stroke="currentColor" stroke-width="2.2"/></svg>'
          : "") +
        "</span>";
    }
    wrap.innerHTML = html;
    $("stampCount").textContent = n;
    const left = 7 - n;
    $("loyaltyText").textContent =
      n >= 7 ? "Наступна кава — безкоштовно! Скажіть баристі" :
      left === 1 ? "Ще 1 кава — і наступна в подарунок" :
      `Ще ${left} ${left <= 4 ? "кави" : "кав"} — і наступна в подарунок`;
  }

  function renderTabs() {
    $("tabs").innerHTML = state.menu.categories
      .map((c, i) => `<button type="button" class="tab${i === 0 ? " is-active" : ""}" data-cat="${c.id}">${esc(c.label)}</button>`)
      .join("");
    $("tabs").querySelectorAll(".tab").forEach((b) =>
      b.addEventListener("click", () => {
        haptic("select");
        const target = $("cat-" + b.dataset.cat);
        if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
      })
    );
  }

  function setActiveTab(cat) {
    $("tabs").querySelectorAll(".tab").forEach((b) => {
      const on = b.dataset.cat === cat;
      b.classList.toggle("is-active", on);
      if (on) b.scrollIntoView({ inline: "center", block: "nearest", behavior: "smooth" });
    });
  }

  function renderCatalog() {
    const m = state.menu;
    $("catalog").innerHTML = m.categories
      .map((c) => {
        const items = m.products.filter((p) => p.cat === c.id);
        return (
          `<h2 class="cat-title" id="cat-${c.id}" data-cat="${c.id}">${esc(c.label)}</h2><div class="grid">` +
          items
            .map((p) => {
              const q = qtyOf(p.id);
              const tag = p.tag ? `<span class="card__tag${p.tag === "Новинка" ? " is-new" : ""}">${esc(p.tag)}</span>` : "";
              const from = p.groups.length ? "<small>від </small>" : "";
              return (
                `<button type="button" class="card" data-id="${p.id}" aria-label="${esc(p.name)}, ${p.price} zł">` +
                `<div class="card__art ${BG[p.art] || "bg-coffee"}">${art(p.art)}</div>${tag}` +
                (q ? `<span class="card__badge">${q}</span>` : "") +
                `<div class="card__body"><span class="card__name">${esc(p.name)}</span>` +
                `<div class="card__foot"><span class="card__price">${from}${p.price} zł</span><span class="card__add" aria-hidden="true">+</span></div></div>` +
                `</button>`
              );
            })
            .join("") +
          "</div>"
        );
      })
      .join("");

    $("catalog").querySelectorAll(".card").forEach((el) =>
      el.addEventListener("click", () => openSheet(product(el.dataset.id)))
    );
    observeSections();
  }

  let observer = null;
  function observeSections() {
    if (!("IntersectionObserver" in window)) return;
    if (observer) observer.disconnect();
    observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => { if (e.isIntersecting) setActiveTab(e.target.dataset.cat); });
      },
      { rootMargin: "-80px 0px -70% 0px" }
    );
    document.querySelectorAll(".cat-title").forEach((h) => observer.observe(h));
  }

  function homeMain() {
    if (state.screen !== "home" || state.sheet) return;
    if (cartCount()) setMain(`Кошик · ${cartCount()} шт. · ${cartTotal()} zł`, openCart);
    else hideMain();
  }

  /* ================= PRODUCT SHEET ================= */
  function openSheet(p) {
    haptic("light");
    state.sheet = { product: p, opts: defaultOpts(p), qty: 1 };
    $("sheetArt").className = "sheet__art " + (BG[p.art] || "bg-coffee");
    $("sheetArt").innerHTML = art(p.art);
    $("sheetTitle").textContent = p.name;
    $("sheetDesc").textContent = p.desc;
    renderSheetGroups();
    $("sheetBackdrop").hidden = false;
    $("sheet").hidden = false;
    $("sheet").scrollTop = 0;
    setBack(closeSheet);
    sheetMain();
  }

  function renderSheetGroups() {
    const { product: p, opts } = state.sheet;
    $("sheetGroups").innerHTML = p.groups
      .map((g) => {
        const grp = state.menu.groups[g];
        return (
          `<div class="block"><div class="block__label">${esc(grp.label)}</div><div class="chips">` +
          grp.options
            .map((o) => `<button type="button" class="chip${opts[g] === o.id ? " is-active" : ""}" data-g="${g}" data-o="${o.id}">${esc(o.label)}${o.d ? `<small>+${o.d} zł</small>` : ""}</button>`)
            .join("") +
          "</div></div>"
        );
      })
      .join("");
    $("sheetGroups").querySelectorAll(".chip").forEach((c) =>
      c.addEventListener("click", () => {
        haptic("select");
        state.sheet.opts[c.dataset.g] = c.dataset.o;
        renderSheetGroups();
        sheetMain();
      })
    );
    $("qtyVal").textContent = state.sheet.qty;
  }

  function sheetMain() {
    const s = state.sheet;
    const total = unitPrice(s.product, s.opts) * s.qty;
    setMain(`Додати в кошик · ${total} zł`, addFromSheet);
  }

  function closeSheet() {
    state.sheet = null;
    $("sheet").hidden = true;
    $("sheetBackdrop").hidden = true;
    setBack(null);
    homeMain();
  }

  function addFromSheet() {
    const s = state.sheet;
    if (!s) return;
    const key = s.product.id + "|" + JSON.stringify(s.opts);
    const ex = state.cart.find((l) => l.key === key);
    if (ex) ex.qty = Math.min(20, ex.qty + s.qty);
    else state.cart.push({ key, id: s.product.id, opts: { ...s.opts }, qty: s.qty });
    haptic("success");
    toast(`Додано: ${s.product.name}`);
    closingGuard();
    closeSheet();
    renderCatalog();
    homeMain();
  }

  /* ================= CART ================= */
  function show(screen) {
    state.screen = screen;
    ["home", "cart", "done"].forEach((s) => $("screen-" + s).classList.toggle("is-active", s === screen));
    window.scrollTo({ top: 0 });
  }

  function openCart() {
    haptic("light");
    show("cart");
    setBack(goHome);
    renderCart();
  }

  function goHome() {
    show("home");
    setBack(null);
    renderCatalog();
    homeMain();
  }

  function chipRow(el, list, current, onPick) {
    el.innerHTML = list
      .map((o) => `<button type="button" class="chip${o.id === current ? " is-active" : ""}" data-id="${o.id}">${esc(o.label)}</button>`)
      .join("");
    el.querySelectorAll(".chip").forEach((c) =>
      c.addEventListener("click", () => { haptic("select"); onPick(c.dataset.id); })
    );
  }

  function renderCart() {
    const list = $("cartList");
    if (!state.cart.length) {
      list.innerHTML = '<div class="empty"><b>Кошик порожній</b>Додайте щось смачне з меню</div>';
    } else {
      list.innerHTML = state.cart
        .map((l, i) => {
          const p = product(l.id);
          const o = optsLabel(p, l.opts);
          return (
            `<div class="line"><div class="line__art ${BG[p.art] || "bg-coffee"}">${art(p.art)}</div>` +
            `<div class="line__info"><div class="line__name">${esc(p.name)}</div>` +
            (o ? `<div class="line__opts">${esc(o)}</div>` : "") +
            `<div class="line__price">${lineTotal(l)} zł</div></div>` +
            `<div class="stepper"><button type="button" data-i="${i}" data-d="-1" aria-label="Менше">−</button><span>${l.qty}</span>` +
            `<button type="button" data-i="${i}" data-d="1" aria-label="Більше">+</button></div></div>`
          );
        })
        .join("");
      list.querySelectorAll(".stepper button").forEach((b) =>
        b.addEventListener("click", () => {
          const l = state.cart[+b.dataset.i];
          l.qty += +b.dataset.d;
          if (l.qty <= 0) state.cart.splice(+b.dataset.i, 1);
          if (l.qty > 20) l.qty = 20;
          haptic("light");
          closingGuard();
          renderCart();
        })
      );
    }

    chipRow($("pickupChips"), state.menu.pickup, state.pickup, (id) => { state.pickup = id; renderCart(); });
    chipRow($("payChips"), state.menu.pay, state.pay, (id) => { state.pay = id; renderCart(); });

    $("sumItems").textContent = `${cartCount()} шт.`;
    $("sumTotal").textContent = `${cartTotal()} zł`;

    if (state.cart.length) setMain(`Оформити замовлення · ${cartTotal()} zł`, submitOrder);
    else hideMain();
  }

  /* ================= ORDER ================= */
  async function submitOrder() {
    if (state.sending || !state.cart.length) return;
    state.sending = true;
    mainBusy(true);

    const payload = {
      initData: inTG ? tg.initData : "",
      items: state.cart.map((l) => ({ id: l.id, qty: l.qty, opts: l.opts })),
      pickup: state.pickup,
      pay: state.pay,
      comment: $("comment").value.trim().slice(0, 200),
    };

    let order = null;
    try {
      if (inTG) {
        const res = await fetch("/api/miniapp/order", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok || !data.ok) throw new Error(data.error || "HTTP " + res.status);
        order = data.order;
      } else {
        await new Promise((r) => setTimeout(r, 700));
        order = { num: "R-" + (100 + Math.floor(Math.random() * 900)), total: cartTotal(), preview: true };
      }
    } catch (e) {
      state.sending = false;
      mainBusy(false);
      haptic("error");
      alertBox("Не вдалося надіслати замовлення. Перевірте з'єднання і спробуйте ще раз.");
      return;
    }

    const coffees = state.cart.reduce((s, l) => s + (product(l.id).coffee ? l.qty : 0), 0);
    const summary = {
      count: cartCount(),
      total: order.total,
      pickup: state.menu.pickup.find((o) => o.id === state.pickup).label,
      pay: state.menu.pay.find((o) => o.id === state.pay).label,
    };
    state.stamps = state.stamps >= 7 ? Math.min(7, coffees) : Math.min(7, state.stamps + coffees);
    store.set("stamps", state.stamps);
    renderStamps();

    state.cart = [];
    $("comment").value = "";
    state.sending = false;
    mainBusy(false);
    closingGuard();
    haptic("success");
    showDone(order, summary);
  }

  let readyTimer = null;
  function showDone(order, s) {
    show("done");
    setBack(null);
    $("orderNum").textContent = order.num;
    $("doneText").textContent = order.preview
      ? "Це попередній перегляд у браузері. Відкрийте застосунок у Telegram — і підтвердження прийде прямо в чат."
      : "Покажіть номер на касі. Ми напишемо в чат, щойно все буде готово.";
    $("tAccepted").textContent = new Date().toLocaleTimeString("uk-UA", { hour: "2-digit", minute: "2-digit" });
    const items = $("timeline").querySelectorAll("li");
    items[1].className = "is-active";
    items[2].className = "";
    $("tReady").textContent = "≈ 7–10 хв";
    $("doneSummary").innerHTML =
      `<div class="row"><span>Позицій</span><b>${s.count} шт.</b></div>` +
      `<div class="row"><span>Забрати</span><b>${esc(s.pickup)}</b></div>` +
      `<div class="row"><span>Оплата</span><b>${esc(s.pay)}</b></div>` +
      `<div class="row"><span>Разом</span><b>${s.total} zł</b></div>`;

    clearTimeout(readyTimer);
    readyTimer = setTimeout(() => {
      items[1].className = "is-done";
      items[2].className = "is-done";
      $("tReady").textContent = "заберіть на касі";
      haptic("success");
    }, order.preview ? 6000 : 60000);

    setMain("Повернутися в меню", goHome);
  }

  /* ================= INIT ================= */
  function bindStatic() {
    $("sheetClose").addEventListener("click", closeSheet);
    $("sheetBackdrop").addEventListener("click", closeSheet);
    $("qtyMinus").addEventListener("click", () => {
      if (state.sheet.qty > 1) { state.sheet.qty--; haptic("light"); renderSheetGroups(); sheetMain(); }
    });
    $("qtyPlus").addEventListener("click", () => {
      if (state.sheet.qty < 20) { state.sheet.qty++; haptic("light"); renderSheetGroups(); sheetMain(); }
    });
    $("cartBack").addEventListener("click", goHome);
    $("clearCart").addEventListener("click", async () => {
      if (!state.cart.length) return;
      if (await confirmBox("Очистити кошик?")) {
        state.cart = [];
        closingGuard();
        haptic("warning");
        renderCart();
      }
    });
  }

  async function init() {
    if (inTG) {
      document.documentElement.classList.add("tg");
      tg.ready();
      tg.expand();
      if (can("7.7")) { try { tg.disableVerticalSwipes(); } catch (e) { /* noop */ } }
      tg.onEvent("themeChanged", applyTheme);
    }
    applyTheme();
    bindStatic();

    try {
      const res = await fetch("menu.json?v=1");
      state.menu = await res.json();
    } catch (e) {
      $("catalog").innerHTML = '<div class="empty"><b>Не вдалося завантажити меню</b>Перевірте інтернет і відкрийте ще раз</div>';
      return;
    }

    const saved = parseInt(await store.get("stamps"), 10);
    state.stamps = Number.isFinite(saved) ? Math.max(0, Math.min(7, saved)) : 0;

    renderHero();
    renderStamps();
    renderTabs();
    renderCatalog();
    homeMain();
  }

  init();
})();
