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
// Рядок під пробігом: для авто й мото - страховка (як у застосунку), іншій техніці - найближче ТО.
function pitupInfo(v) {
  if (v.insurable) {
    const m = v.mtpl;
    let text, st;
    if (!m) { text = "Немає чинного полісу ОСЦПВ"; st = "overdue"; }
    else if (m.days_left != null && m.days_left < 0) { text = "ОСЦПВ закінчився " + pitupDate(m.end_date); st = "overdue"; }
    else { text = "ОСЦПВ до " + pitupDate(m.end_date) + (m.days_left != null ? " · ще " + pitupEsc(m.days_left) + " дн." : ""); st = m.status || "ok"; }
    return '<div class="pu-info"><span class="pu-dot" style="background:' + pitupColor(st) + '"></span><span>' + text + "</span></div>";
  }
  const n = v.next;
  if (!n) return "";
  let d;
  if (n.status === "overdue") d = "прострочено" + (n.over_km ? " на " + pitupNum(n.over_km) + " " + pitupEsc(v.unit) : "");
  else if (n.due_km != null) d = "через " + pitupNum(n.due_km) + " " + pitupEsc(v.unit);
  else d = n.next_date ? "до " + pitupDate(n.next_date) : "";
  return '<div class="pu-info"><span class="pu-dot" style="background:' + pitupColor(n.status) + '"></span><span>' +
    pitupEsc(n.name) + (d ? ", " + d : "") + "</span></div>";
}
function pitupPill(v) {
  return '<span class="pu-pill"><i style="background:' + pitupColor(v.status) + '"></i>' +
    (PITUP_STATUS[v.status] || "") + "</span>";
}
function pitupLarge(v) {
  return '<div class="pu-card">' + pitupPhoto(v, "", 200) +
    pitupPill(v) + "</div>" +
    '<div class="pu-body"><div class="pu-head"><div class="pu-title">' + pitupEsc(v.title) + "</div>" +
    (v.plate ? '<span class="pu-plate">' + pitupEsc(v.plate) + "</span>" : "") + "</div>" +
    '<div class="pu-mile">' + pitupMileage(v) + "</div>" + pitupInfo(v) + "</div></div>";
}
function pitupTile(v) {
  return '<div class="pu-card pu-tile">' + pitupPhoto(v, "", 110) +
    "</div>" + '<div class="pu-body"><div class="pu-head"><div class="pu-title">' + pitupEsc(v.title) + "</div>" +
    '<span class="pu-dot" style="background:' + pitupColor(v.status) + '"></span></div>' +
    '<div class="pu-mile">' + pitupMileage(v) + "</div></div></div>";
}
function pitupRow(v) {
  return '<div class="pu-row">' + pitupPhoto(v, "pu-thumb") + "</div>" +
    '<div class="pu-grow"><div class="pu-title">' + pitupEsc(v.title) + "</div>" +
    '<div class="pu-mile">' + pitupMileage(v) + "</div></div>" +
    '<span class="pu-dot" style="background:' + pitupColor(v.status) + '"></span></div>';
}

function pitupRender(hass, config) {
  const s = hass && hass.states && hass.states["sensor.pitup"];
  if (!s) {
    return '<div class="pu-empty">Сенсор <b>sensor.pitup</b> недоступний - перевір інтеграцію PitUp.</div>';
  }
  let vs = s.attributes.vehicles || [];
  const ids = config && Array.isArray(config.vehicles) ? config.vehicles.map(Number) : null;
  if (ids && ids.length) vs = vs.filter(function (v) { return ids.indexOf(Number(v.id)) >= 0; });
  if (!vs.length) {
    return '<div class="pu-empty">Немає техніки або даних.</div>';
  }
  let layout = (config && config.layout) || "auto";
  if (layout === "auto") layout = vs.length <= 3 ? "large" : vs.length <= 6 ? "grid" : "compact";
  if (layout === "large") return '<div class="pu-list">' + vs.map(pitupLarge).join("") + "</div>";
  if (layout === "grid") return '<div class="pu-grid">' + vs.map(pitupTile).join("") + "</div>";
  return '<div class="pu-rows">' + vs.map(pitupRow).join("") + "</div>";
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
  setConfig(config) {
    this._config = config || {};
    this._drawn = false;  // змінили налаштування (layout, vehicles) - перемалювати
  }
  set hass(hass) {
    if (!this._card) {
      this._card = document.createElement("ha-card");
      this._card.header = (this._config && this._config.title) || "PitUp - техніка";
      const style = document.createElement("style");
      style.textContent = PITUP_CSS;
      this._body = document.createElement("div");
      this._body.style.padding = "4px 12px 12px";
      this._card.appendChild(style);
      this._card.appendChild(this._body);
      this.appendChild(this._card);
    }
    // hass приходить при зміні будь-якої сутності HA - малюємо лише коли змінився sensor.pitup.
    const st = hass && hass.states && hass.states["sensor.pitup"];
    if (this._drawn && st === this._state) return;
    this._drawn = true;
    this._state = st;
    this._body.innerHTML = pitupRender(hass, this._config);
  }
  getCardSize() {
    return 6;
  }
}
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

window.customCards = window.customCards || [];
window.customCards.push({
  type: "pitup-card",
  name: "PitUp",
  description: "Техніка з PitUp як у застосунку: фото, стан, номер, пробіг, страховка чи найближче ТО.",
});
