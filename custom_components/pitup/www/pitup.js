/* PitUp — Lovelace-картка `custom:pitup-card` та бічна панель `pitup-panel`.
   Читає атрибути сенсора sensor.pitup (масив vehicles) і малює інформер. */

function pitupColor(s) {
  return s === "overdue" ? "#e5484d" : s === "soon" ? "#f5a623" : "#2e9e5b";
}
function pitupDot(s) {
  return s === "overdue" ? "🔴" : s === "soon" ? "🟡" : "🟢";
}

function pitupRender(hass) {
  const s = hass && hass.states && hass.states["sensor.pitup"];
  if (!s) {
    return '<div style="padding:16px;color:#888">Сенсор <b>sensor.pitup</b> недоступний — перевір інтеграцію PitUp.</div>';
  }
  const vs = s.attributes.vehicles || [];
  if (!vs.length) {
    return '<div style="padding:16px;color:#888">Немає техніки або даних.</div>';
  }
  return vs
    .map(function (v) {
      const c = pitupColor(v.status);
      let next = "";
      if (v.next) {
        let body;
        if (v.next.status === "overdue") {
          body = "⚠️ прострочено" + (v.next.over_km ? " на " + v.next.over_km + " " + v.unit : "");
        } else {
          const p = [];
          if (v.next.due_km != null) p.push("через " + v.next.due_km + " " + v.unit);
          if (v.next.next_date) p.push("до " + v.next.next_date);
          body = p.join(" ");
        }
        next =
          '<div style="font-size:13px;color:var(--secondary-text-color,#555);margin-top:3px">Найближче: <b>' +
          (v.next.name || "") + "</b> — " + body + "</div>";
      }
      return (
        '<div style="border-left:4px solid ' + c +
        ';background:var(--ha-card-background,var(--card-background-color,#fff));border-radius:8px;padding:10px 14px;margin:8px 0;box-shadow:0 1px 2px rgba(0,0,0,.06)">' +
        '<div style="font-weight:600;font-size:15px">' + pitupDot(v.status) + " " + (v.title || "") + "</div>" +
        '<div style="font-size:13px;color:var(--secondary-text-color,#666);margin-top:2px">Пробіг: <b>' +
        (v.mileage != null ? v.mileage : "—") + " " + (v.unit || "") + "</b>" +
        (v.mileage_estimated ? " (≈)" : "") +
        (v.overdue ? ' · <span style="color:#e5484d">прострочено: ' + v.overdue + "</span>" : "") +
        (v.soon ? ' · <span style="color:#f5a623">скоро: ' + v.soon + "</span>" : "") +
        "</div>" + next + "</div>"
      );
    })
    .join("");
}

function pitupRenderPanel(hass) {
  const s = hass && hass.states && hass.states["sensor.pitup"];
  if (!s) {
    return '<div style="padding:16px;color:#888">Сенсор <b>sensor.pitup</b> недоступний — перевір інтеграцію PitUp.</div>';
  }
  const vs = s.attributes.vehicles || [];
  const t = s.attributes.totals || {};
  if (!vs.length) {
    return '<div style="padding:16px;color:#888">Немає техніки або даних.</div>';
  }
  const parts = [];
  if (t.overdue) parts.push('<span style="color:#e5484d">🔴 ' + t.overdue + " протерміновано</span>");
  if (t.soon) parts.push('<span style="color:#f5a623">🟡 ' + t.soon + " скоро</span>");
  const psum = (t.policy_overdue || 0) + (t.policy_soon || 0);
  if (psum) parts.push('<span style="color:#f5a623">🛡️ ' + psum + " страховок</span>");
  let sum = parts.length
    ? '<div style="margin:0 0 12px;font-size:14px">' + parts.join(" &nbsp;·&nbsp; ") + "</div>"
    : '<div style="margin:0 0 12px;color:#2e9e5b">✅ Усе гаразд</div>';

  const cards = vs.map(function (v) {
    const c = pitupColor(v.status);
    let h = '<div style="border-left:5px solid ' + c +
      ';background:var(--ha-card-background,var(--card-background-color,#fff));border-radius:12px;padding:14px 16px;margin:12px 0;box-shadow:0 1px 3px rgba(0,0,0,.08)">';
    h += '<div style="display:flex;justify-content:space-between;align-items:baseline;gap:8px">' +
      '<div style="font-weight:700;font-size:17px">' + pitupDot(v.status) + " " + (v.title || "") + "</div>" +
      '<div style="font-size:14px;color:var(--secondary-text-color,#888);white-space:nowrap">' +
      (v.mileage != null ? v.mileage : "—") + " " + (v.unit || "") + (v.mileage_estimated ? " ≈" : "") + "</div></div>";
    if (v.overdue || v.soon) {
      h += '<div style="margin-top:6px;font-size:13px">';
      if (v.overdue) h += '<span style="color:#e5484d">🔴 ' + v.overdue + " протерміновано</span> ";
      if (v.soon) h += '<span style="color:#f5a623">🟡 ' + v.soon + " скоро</span>";
      h += "</div>";
    } else if ((v.items || []).length) {
      h += '<div style="margin-top:6px;font-size:13px;color:#2e9e5b">✅ регламент у нормі</div>';
    }
    const warn = (v.items || []).filter(function (i) { return i.status !== "ok"; });
    if (warn.length) {
      h += '<div style="margin-top:8px;display:grid;gap:4px">';
      warn.slice(0, 8).forEach(function (i) {
        const ic = pitupColor(i.status);
        const d = i.status === "overdue"
          ? "прострочено" + (i.over_km ? " на " + i.over_km + " " + v.unit : "")
          : "через " + (i.due_km != null ? i.due_km + " " + v.unit : "") + (i.next_date ? " · " + i.next_date : "");
        h += '<div style="font-size:13px;display:flex;gap:6px"><span style="color:' + ic +
          '">●</span><span><b>' + i.name + "</b> — " + d + "</span></div>";
      });
      h += "</div>";
    }
    const pols = (v.policies || []).filter(function (p) { return p.status === "overdue" || p.status === "soon"; });
    if (pols.length) {
      h += '<div style="margin-top:8px;padding-top:8px;border-top:1px solid var(--divider-color,#eee)">';
      pols.forEach(function (p) {
        const pc = p.status === "overdue" ? "#e5484d" : "#f5a623";
        h += '<div style="font-size:13px;color:' + pc + '">🛡️ ' + p.kind + " — " +
          (p.status === "overdue" ? "прострочено" : "спливає через " + p.days_left + " дн") +
          (p.end_date ? " (до " + p.end_date + ")" : "") + "</div>";
      });
      h += "</div>";
    }
    return h + "</div>";
  }).join("");

  return sum + cards;
}

class PitUpCard extends HTMLElement {
  setConfig(config) {
    this._config = config;
  }
  set hass(hass) {
    if (!this._card) {
      this._card = document.createElement("ha-card");
      this._card.header = (this._config && this._config.title) || "PitUp — техніка";
      this._body = document.createElement("div");
      this._body.style.padding = "4px 12px 12px";
      this._card.appendChild(this._body);
      this.appendChild(this._card);
    }
    this._body.innerHTML = pitupRender(hass);
  }
  getCardSize() {
    return 3;
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
      this._root.style.cssText = "padding:16px;max-width:860px;margin:0 auto";
      const h = document.createElement("h1");
      h.textContent = "PitUp — техніка";
      h.style.cssText = "font-size:20px;font-weight:700;color:#ff5722;margin:8px 0 8px";
      this._body = document.createElement("div");
      this._root.appendChild(h);
      this._root.appendChild(this._body);
      this.appendChild(this._root);
    }
    this._body.innerHTML = pitupRenderPanel(this._hass);
  }
}
if (!customElements.get("pitup-panel")) customElements.define("pitup-panel", PitUpPanel);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "pitup-card",
  name: "PitUp",
  description: "Стан техніки з PitUp (скоро / протерміновано, найближче ТО).",
});
