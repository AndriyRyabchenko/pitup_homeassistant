/* PitUp - Lovelace-картка `custom:pitup-card` та бічна панель `pitup-panel`.
   Читає атрибути сенсора sensor.pitup (масив vehicles) і малює інформер. */

// Усе з API (назви техніки й пунктів, вид поліса, дати, числа) - лише через pitupEsc:
// назви вводять і інші користувачі PitUp (спільна техніка, майстер), а HTML тут
// вставляється в сторінку HA з доступом до її сесії.
function pitupEsc(x) {
  return String(x == null ? "" : x).replace(/[&<>"']/g, function (c) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
  });
}

function pitupColor(s) {
  return s === "overdue" ? "#e5484d" : s === "soon" ? "#f5a623" : s === "ok" ? "#2e9e5b" : "#8a8a8a";
}

// Картки техніки - як у гаражі застосунку PitUp: до 3 - великі з фото, 4-6 - плитки у дві
// колонки, більше - компактний список (config.layout: auto | large | grid | compact).
const PITUP_STATUS = { overdue: "Прострочено", soon: "Скоро", ok: "У нормі", none: "Немає регламенту" };
const PITUP_ICON = {
  car: "mdi:car", moto: "mdi:motorbike", bike: "mdi:bicycle", scooter: "mdi:scooter",
  generator: "mdi:engine", boat: "mdi:sail-boat", tractor: "mdi:tractor", atv: "mdi:atv",
  garden: "mdi:saw-blade", filter: "mdi:water-outline",
};

const PITUP_CSS = `
  .pu-list{display:grid;gap:12px}
  .pu-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
  .pu-card{display:block;border:1px solid var(--divider-color,rgba(127,127,127,.25));border-radius:16px;overflow:hidden;
    background:var(--ha-card-background,var(--card-background-color,#fff));color:var(--primary-text-color)}
  .pu-photo{position:relative;background:var(--secondary-background-color,rgba(127,127,127,.12));display:flex;
    align-items:center;justify-content:center;color:var(--secondary-text-color);overflow:hidden}
  .pu-photo img{width:100%;height:100%;object-fit:cover;display:block}
  .pu-photo ha-icon{--mdc-icon-size:40px;opacity:.6}
  .pu-pill{position:absolute;top:8px;left:8px;display:inline-flex;align-items:center;gap:5px;font-size:12px;font-weight:500;
    padding:2px 8px;border-radius:999px;background:rgba(0,0,0,.55);color:#fff;backdrop-filter:blur(4px)}
  .pu-pill i,.pu-dot{width:7px;height:7px;border-radius:50%;display:inline-block;flex:none}
  .pu-body{padding:12px 14px}
  .pu-head{display:flex;align-items:baseline;justify-content:space-between;gap:8px}
  .pu-title{font-weight:600;font-size:17px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .pu-plate{font:500 12px ui-monospace,SFMono-Regular,Menlo,monospace;padding:1px 6px;border-radius:6px;
    border:1px solid var(--divider-color,rgba(127,127,127,.35));white-space:nowrap;color:var(--secondary-text-color)}
  .pu-mile{font-size:14px;color:var(--secondary-text-color);font-variant-numeric:tabular-nums;margin-top:2px}
  .pu-info{display:flex;align-items:baseline;gap:6px;font-size:13px;margin-top:6px;color:var(--primary-text-color);
    white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .pu-info span:last-child{overflow:hidden;text-overflow:ellipsis}
  .pu-tile .pu-body{padding:8px 10px}
  .pu-tile .pu-title{font-size:14px}
  .pu-tile .pu-mile{font-size:12px}
  .pu-rows{border:1px solid var(--divider-color,rgba(127,127,127,.25));border-radius:16px;overflow:hidden}
  .pu-row{display:flex;align-items:center;gap:12px;padding:8px 12px}
  .pu-row+.pu-row{border-top:1px solid var(--divider-color,rgba(127,127,127,.18))}
  .pu-thumb{width:56px;height:42px;border-radius:10px;flex:none}
  .pu-thumb ha-icon{--mdc-icon-size:22px}
  .pu-row .pu-title{font-size:14px}
  .pu-row .pu-mile{font-size:12px;margin:0}
  .pu-grow{flex:1;min-width:0}
  .pu-empty{padding:16px;color:var(--secondary-text-color)}
`;

function pitupNum(x) {
  if (x == null || x === "") return "-";
  const n = Number(x);
  if (!isFinite(n)) return pitupEsc(x);
  return n.toLocaleString("uk-UA", { maximumFractionDigits: 2 }).replace(/\u00a0/g, " ");
}
function pitupDate(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || "");
  return m ? m[3] + "." + m[2] + "." + m[1] : pitupEsc(iso);
}
function pitupMileage(v) {
  return pitupNum(v.mileage) + " " + pitupEsc(v.unit) + (v.mileage_estimated ? " ≈" : "");
}
// Фото (обкладинка) чи значок типу техніки; height - висота блоку (великі картки, плитки).
function pitupPhoto(v, cls, height) {
  const url = String(v.cover_url || "");
  const img = /^https:\/\//.test(url)
    ? '<img src="' + pitupEsc(url) + '" alt="" loading="lazy" referrerpolicy="no-referrer">'
    : '<ha-icon icon="' + (PITUP_ICON[v.kind] || "mdi:wrench") + '"></ha-icon>';
  return '<div class="pu-photo ' + cls + '"' + (height ? ' style="height:' + height + 'px"' : "") + ">" + img;
}
// Налаштування картки (config, візуальний редактор): усе необовʼязкове, за замовчуванням - як у застосунку.
function pitupOpts(config) {
  const c = config || {};
  return {
    layout: c.layout || "auto",            // auto | large | grid | compact
    info: c.info || "auto",                // auto | insurance | service | none - рядок під пробігом
    sort: c.sort || "default",             // default | attention | title
    onlyAttention: c.only_attention === true,
    photo: c.show_photo !== false,
    plate: c.show_plate !== false,
    status: c.show_status !== false,
    vehicles: Array.isArray(c.vehicles) ? c.vehicles.map(Number) : [],
  };
}

function pitupInsurance(v) {
  const m = v.mtpl;
  let text, st;
  if (!m) { text = "Немає чинного полісу ОСЦПВ"; st = "overdue"; }
  else if (m.days_left != null && m.days_left < 0) { text = "ОСЦПВ закінчився " + pitupDate(m.end_date); st = "overdue"; }
  else { text = "ОСЦПВ до " + pitupDate(m.end_date) + (m.days_left != null ? " · ще " + pitupEsc(m.days_left) + " дн." : ""); st = m.status || "ok"; }
  return '<div class="pu-info"><span class="pu-dot" style="background:' + pitupColor(st) + '"></span><span>' + text + "</span></div>";
}
function pitupService(v) {
  const n = v.next;
  if (!n) return "";
  let d;
  if (n.status === "overdue") d = "прострочено" + (n.over_km ? " на " + pitupNum(n.over_km) + " " + pitupEsc(v.unit) : "");
  else if (n.due_km != null) d = "через " + pitupNum(n.due_km) + " " + pitupEsc(v.unit);
  else d = n.next_date ? "до " + pitupDate(n.next_date) : "";
  return '<div class="pu-info"><span class="pu-dot" style="background:' + pitupColor(n.status) + '"></span><span>' +
    pitupEsc(n.name) + (d ? ", " + d : "") + "</span></div>";
}
// Рядок під пробігом: auto - для авто й мото страховка (як у застосунку), іншій техніці - найближче ТО.
function pitupInfo(v, o) {
  if (o.info === "none") return "";
  if (o.info === "service") return pitupService(v);
  if (o.info === "insurance") return v.insurable ? pitupInsurance(v) : "";
  return v.insurable ? pitupInsurance(v) : pitupService(v);
}
function pitupPill(v) {
  return '<span class="pu-pill"><i style="background:' + pitupColor(v.status) + '"></i>' +
    (PITUP_STATUS[v.status] || "") + "</span>";
}
function pitupDotStatus(v, o) {
  return o.status ? '<span class="pu-dot" style="background:' + pitupColor(v.status) + '"></span>' : "";
}
function pitupLarge(v, o) {
  const photo = o.photo ? pitupPhoto(v, "", 200) + (o.status ? pitupPill(v) : "") + "</div>" : "";
  return '<div class="pu-card">' + photo +
    '<div class="pu-body"><div class="pu-head"><div class="pu-title">' + pitupEsc(v.title) + "</div>" +
    (o.plate && v.plate ? '<span class="pu-plate">' + pitupEsc(v.plate) + "</span>" : (!o.photo ? pitupDotStatus(v, o) : "")) +
    "</div>" + '<div class="pu-mile">' + pitupMileage(v) + "</div>" + pitupInfo(v, o) + "</div></div>";
}
function pitupTile(v, o) {
  return '<div class="pu-card pu-tile">' + (o.photo ? pitupPhoto(v, "", 110) + "</div>" : "") +
    '<div class="pu-body"><div class="pu-head"><div class="pu-title">' + pitupEsc(v.title) + "</div>" +
    pitupDotStatus(v, o) + "</div>" + '<div class="pu-mile">' + pitupMileage(v) + "</div></div></div>";
}
function pitupRow(v, o) {
  return '<div class="pu-row">' + (o.photo ? pitupPhoto(v, "pu-thumb") + "</div>" : "") +
    '<div class="pu-grow"><div class="pu-title">' + pitupEsc(v.title) + "</div>" +
    '<div class="pu-mile">' + pitupMileage(v) + "</div></div>" + pitupDotStatus(v, o) + "</div>";
}

// Потребує уваги: регламент чи поліс «скоро / прострочено» (як «Потребує уваги» в застосунку).
function pitupRank(v) {
  const p = v.policy && v.policy.status;
  if (v.status === "overdue" || p === "overdue") return 0;
  if (v.status === "soon" || p === "soon") return 1;
  return 2;
}

function pitupRender(hass, config) {
  const s = hass && hass.states && hass.states["sensor.pitup"];
  if (!s) {
    return '<div class="pu-empty">Сенсор <b>sensor.pitup</b> недоступний - перевір інтеграцію PitUp.</div>';
  }
  const o = pitupOpts(config);
  let vs = (s.attributes.vehicles || []).slice();
  if (o.vehicles.length) vs = vs.filter(function (v) { return o.vehicles.indexOf(Number(v.id)) >= 0; });
  if (o.onlyAttention) vs = vs.filter(function (v) { return pitupRank(v) < 2; });
  if (o.sort === "attention") vs.sort(function (a, b) { return pitupRank(a) - pitupRank(b); });
  if (o.sort === "title") vs.sort(function (a, b) { return String(a.title).localeCompare(String(b.title), "uk"); });
  if (!vs.length) {
    return '<div class="pu-empty">' + (o.onlyAttention ? "Усе гаразд - нічого не потребує уваги." : "Немає техніки або даних.") + "</div>";
  }
  let layout = o.layout;
  if (layout === "auto") layout = vs.length <= 3 ? "large" : vs.length <= 6 ? "grid" : "compact";
  const draw = function (fn) { return vs.map(function (v) { return fn(v, o); }).join(""); };
  if (layout === "large") return '<div class="pu-list">' + draw(pitupLarge) + "</div>";
  if (layout === "grid") return '<div class="pu-grid">' + draw(pitupTile) + "</div>";
  return '<div class="pu-rows">' + draw(pitupRow) + "</div>";
}

// Бічна панель: підсумок і ті самі картки, що на дашборді (розмір - за кількістю техніки).
function pitupRenderPanel(hass) {
  const s = hass && hass.states && hass.states["sensor.pitup"];
  const t = (s && s.attributes.totals) || {};
  const parts = [];
  if (t.overdue) parts.push('<span style="color:#e5484d">' + pitupEsc(t.overdue) + " прострочено</span>");
  if (t.soon) parts.push('<span style="color:#f5a623">' + pitupEsc(t.soon) + " скоро</span>");
  const psum = (t.policy_overdue || 0) + (t.policy_soon || 0);
  if (psum) parts.push('<span style="color:#f5a623">' + psum + " страховок потребують уваги</span>");
  const sum = !s ? "" : parts.length
    ? '<div style="margin:0 0 12px;font-size:14px">' + parts.join(" &nbsp;·&nbsp; ") + "</div>"
    : '<div style="margin:0 0 12px;color:#2e9e5b">Усе гаразд</div>';
  return sum + pitupRender(hass, {});
}

class PitUpCard extends HTMLElement {
  static getConfigElement() {
    return document.createElement("pitup-card-editor");
  }
  static getStubConfig() {
    return {};
  }
  setConfig(config) {
    this._config = config || {};
    this._drawn = false;  // змінили налаштування - перемалювати одразу (редактор показує прев'ю)
    if (this._hass) this._draw();
  }
  set hass(hass) {
    this._hass = hass;
    this._draw();
  }
  _draw() {
    if (!this._card) {
      this._card = document.createElement("ha-card");
      const style = document.createElement("style");
      style.textContent = PITUP_CSS;
      this._body = document.createElement("div");
      this._body.style.padding = "4px 12px 12px";
      this._card.appendChild(style);
      this._card.appendChild(this._body);
      this.appendChild(this._card);
    }
    const title = this._config && this._config.title;
    // Порожній заголовок у налаштуваннях - без заголовка; не задано - «PitUp - техніка».
    this._card.header = title === "" ? undefined : (title || "PitUp - техніка");
    this._body.style.paddingTop = this._card.header ? "4px" : "12px";
    // hass приходить при зміні будь-якої сутності HA - малюємо лише коли змінився sensor.pitup.
    const st = this._hass && this._hass.states && this._hass.states["sensor.pitup"];
    if (this._drawn && st === this._state) return;
    this._drawn = true;
    this._state = st;
    this._body.innerHTML = pitupRender(this._hass, this._config);
  }
  getCardSize() {
    return 6;
  }
}

// Візуальний редактор картки (ha-form): техніка, розмір, сортування, що показувати.
const PITUP_LABELS = {
  title: "Заголовок (порожньо - без заголовка)",
  vehicles: "Техніка (нічого не обрано - уся)",
  layout: "Розмір карток",
  sort: "Порядок",
  info: "Рядок під пробігом",
  only_attention: "Лише техніка, що потребує уваги",
  show_photo: "Фото",
  show_plate: "Номер",
  show_status: "Стан",
};
const PITUP_DEFAULTS = {
  layout: "auto", sort: "default", info: "auto", only_attention: false,
  show_photo: true, show_plate: true, show_status: true,
};

class PitUpCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = Object.assign({}, config);
    this._render();
  }
  set hass(hass) {
    this._hass = hass;
    this._render();
  }
  _schema() {
    const st = this._hass && this._hass.states["sensor.pitup"];
    const vs = (st && st.attributes.vehicles) || [];
    const opts = function (pairs) {
      return pairs.map(function (p) { return { value: p[0], label: p[1] }; });
    };
    return [
      { name: "title", selector: { text: {} } },
      { name: "vehicles", selector: { select: { multiple: true, mode: "list", options: vs.map(function (v) {
        return { value: String(v.id), label: v.title + (v.plate ? " · " + v.plate : "") };
      }) } } },
      { name: "layout", selector: { select: { mode: "dropdown", options: opts([
        ["auto", "Авто - за кількістю техніки"], ["large", "Великі з фото"], ["grid", "Плитки у дві колонки"], ["compact", "Компактний список"],
      ]) } } },
      { name: "sort", selector: { select: { mode: "dropdown", options: opts([
        ["default", "Як у PitUp"], ["attention", "Спершу та, що потребує уваги"], ["title", "За назвою"],
      ]) } } },
      { name: "info", selector: { select: { mode: "dropdown", options: opts([
        ["auto", "Авто - страховка для авто й мото, ТО для решти"], ["insurance", "Страховка (ОСЦПВ)"],
        ["service", "Найближче ТО"], ["none", "Нічого"],
      ]) } } },
      { name: "only_attention", selector: { boolean: {} } },
      { type: "grid", name: "", schema: [
        { name: "show_photo", selector: { boolean: {} } },
        { name: "show_plate", selector: { boolean: {} } },
        { name: "show_status", selector: { boolean: {} } },
      ] },
    ];
  }
  _render() {
    if (!this._hass || !this._config) return;
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.computeLabel = function (s) { return PITUP_LABELS[s.name] || s.name; };
      this._form.addEventListener("value-changed", (ev) => this._changed(ev.detail.value));
      this.appendChild(this._form);
    }
    const data = Object.assign({}, PITUP_DEFAULTS, this._config);
    data.vehicles = (this._config.vehicles || []).map(String);
    this._form.hass = this._hass;
    this._form.data = data;
    this._form.schema = this._schema();
  }
  _changed(value) {
    // У YAML - лише те, що відрізняється від типового (картка лишається короткою).
    const config = { type: this._config.type || "custom:pitup-card" };
    Object.keys(value).forEach(function (k) {
      if (k === "type") return;
      if (k === "vehicles") {
        if (value.vehicles && value.vehicles.length) config.vehicles = value.vehicles.map(Number);
      } else if (k === "title") {
        if (value.title !== undefined) config.title = value.title;
      } else if (value[k] !== PITUP_DEFAULTS[k]) {
        config[k] = value[k];
      }
    });
    this._config = config;
    this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: config }, bubbles: true, composed: true }));
  }
}
if (!customElements.get("pitup-card-editor")) customElements.define("pitup-card-editor", PitUpCardEditor);
if (!customElements.get("pitup-card")) customElements.define("pitup-card", PitUpCard);

class PitUpPanel extends HTMLElement {
  set hass(hass) {
    this._hass = hass;
    this._render();
  }
  set narrow(v) {}
  set route(v) {}
  set panel(v) {}
  _render() {
    if (!this._root) {
      this._root = document.createElement("div");
      this._root.style.cssText = "padding:16px;max-width:640px;margin:0 auto";
      const h = document.createElement("h1");
      h.textContent = "PitUp - техніка";
      h.style.cssText = "font-size:20px;font-weight:700;color:#ff5722;margin:8px 0 8px";
      const style = document.createElement("style");
      style.textContent = PITUP_CSS;
      this._body = document.createElement("div");
      this._root.appendChild(style);
      this._root.appendChild(h);
      this._root.appendChild(this._body);
      this.appendChild(this._root);
    }
    const st = this._hass && this._hass.states && this._hass.states["sensor.pitup"];
    if (this._drawn && st === this._state) return;
    this._drawn = true;
    this._state = st;
    this._body.innerHTML = pitupRenderPanel(this._hass);
  }
}
if (!customElements.get("pitup-panel")) customElements.define("pitup-panel", PitUpPanel);

// Скрипт може завантажитись двічі (стара версія у відкритій вкладці + нова після оновлення,
// ресурс Lovelace і extra_js_url) - у списку «Додати картку» PitUp має бути один.
window.customCards = window.customCards || [];
if (!window.customCards.some(function (c) { return c.type === "pitup-card"; })) window.customCards.push({
  type: "pitup-card",
  name: "PitUp",
  description: "Техніка з PitUp як у застосунку: фото, стан, номер, пробіг, страховка чи найближче ТО.",
});
