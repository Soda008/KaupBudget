/* KaupBudget front end - plain JS, talks to the /api server. */
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const money = (n) => (n == null || isNaN(n) ? "—" : Number(n).toLocaleString(undefined, { style: "currency", currency: "USD" }));
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const monthLabel = (m) => { const [y, mo] = m.split("-").map(Number); return new Date(y, mo - 1, 1).toLocaleString(undefined, { month: "short", year: "2-digit" }); };
const thisMonth = () => new Date().toISOString().slice(0, 7);

async function api(path, opts = {}) {
  const init = { ...opts };
  if (init.body && !(init.body instanceof FormData)) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(init.body);
  }
  const res = await fetch(path, init);
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail || msg; } catch (_) { /* not JSON */ }
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return res.json();
}

function toast(msg, isError = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast" + (isError ? " error" : "");
  t.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => (t.hidden = true), isError ? 6000 : 2500);
}

/* ---------- Categories & colors ----------
   Each category keeps the same color everywhere: palette slot by its position
   (by id). Past 8 categories, extras share a neutral "more" color. */
let CATS = [];
const cssVar = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
function catColor(id) {
  if (id == null) return cssVar("--s-none");
  const i = CATS.findIndex((c) => c.id === id);
  return i >= 0 && i < 8 ? cssVar(`--s${i + 1}`) : cssVar("--s-more");
}
async function loadCategories() {
  CATS = await api("/api/categories");
  const active = CATS.filter((c) => !c.archived);
  const opts = (blank) => `<option value="">${blank}</option>` + active.map((c) => `<option value="${c.id}">${esc(c.name)}</option>`).join("");
  $("#f-category").innerHTML = `<option value="">All</option><option value="none">Uncategorized</option>` + active.map((c) => `<option value="${c.id}">${esc(c.name)}</option>`).join("");
  $("#rv-category").innerHTML = opts("— pick a category —");
  $("#td-category").innerHTML = opts("— none —");
  $("#r-category").innerHTML = active.map((c) => `<option value="${c.id}">${esc(c.name)}</option>`).join("") + `<option value="none">Uncategorized</option>`;
}
function catLabel(tx) {
  if (!tx.category) return `<span class="cat unconfirmed"><span class="dot" style="background:${catColor(null)}"></span>Uncategorized</span>`;
  const cls = tx.category_confirmed ? "cat" : "cat unconfirmed";
  const title = tx.category_confirmed ? "" : ' title="Suggested - open to confirm"';
  return `<span class="${cls}"${title}><span class="dot" style="background:${catColor(tx.category_id)}"></span>${esc(tx.category)}${tx.category_confirmed ? "" : "?"}</span>`;
}

/* Suggestion chips: top 3, most likely first. Clicking one sets the select. */
function renderChips(box, select, suggestions) {
  box.innerHTML = suggestions.map((s, i) =>
    `<button type="button" class="chip" data-id="${s.id}" title="${esc(s.reason || "")}">
       <span class="dot" style="background:${catColor(s.id)}"></span>${esc(s.name)}
       <small>${["1st", "2nd", "3rd"][i] || ""}</small></button>`).join("");
  const sync = () => $$(".chip", box).forEach((c) => c.classList.toggle("selected", c.dataset.id === select.value));
  $$(".chip", box).forEach((c) => c.addEventListener("click", () => { select.value = c.dataset.id; sync(); }));
  select.onchange = sync;
  sync();
}

/* ---------- Tabs ---------- */
function show(view) {
  $$(".tab").forEach((t) => t.classList.toggle("active", t.dataset.view === view));
  $$(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${view}`));
  if (view === "purchases") loadPurchases();
  if (view === "reports") loadReports();
  if (view === "settings") loadSettings();
}
$$(".tab").forEach((t) => t.addEventListener("click", () => show(t.dataset.view)));

/* ---------- Purchases ---------- */
async function loadPurchases() {
  const p = new URLSearchParams();
  if ($("#f-month").value) p.set("month", $("#f-month").value);
  if ($("#f-category").value) p.set("category_id", $("#f-category").value);
  if ($("#f-search").value.trim()) p.set("q", $("#f-search").value.trim());
  if ($("#f-missing").checked) p.set("missing_receipt", "true");
  const rows = await api(`/api/transactions?${p}`);
  $("#tx-table tbody").innerHTML = rows.map((t) => `
    <tr class="click" data-id="${t.id}">
      <td>${esc(t.date)}</td>
      <td>${esc(t.vendor)}</td>
      <td>${catLabel(t)}</td>
      <td class="num">${money(t.amount)}</td>
      <td>${t.receipt_id ? '<span class="badge yes">✓ Receipt</span>' : '<span class="badge">None</span>'}</td>
    </tr>`).join("");
  $$("#tx-table tbody tr").forEach((tr) => tr.addEventListener("click", () => openTx(+tr.dataset.id)));
  $("#tx-empty").hidden = rows.length > 0;
  const total = rows.reduce((s, r) => s + r.amount, 0);
  const missing = rows.filter((r) => !r.receipt_id).length;
  $("#purchase-summary").textContent = rows.length ? `${rows.length} purchases · ${money(total)} · ${missing} without a receipt` : "";
}
["#f-month", "#f-category", "#f-missing"].forEach((s) => $(s).addEventListener("change", loadPurchases));
let searchTimer;
$("#f-search").addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(loadPurchases, 250); });

/* Purchase detail dialog */
let currentTx = null;
async function openTx(id) {
  const tx = await api(`/api/transactions/${id}`);
  currentTx = tx;
  $("#td-title").textContent = tx.vendor;
  const f = $("#td-form");
  f.vendor.value = tx.vendor; f.date.value = tx.date; f.amount.value = tx.amount;
  f.notes.value = tx.notes || "";
  f.category_id.value = tx.category_id ?? "";
  renderChips($("#td-suggest"), f.category_id, tx.suggestions);
  $("#td-bank").textContent = tx.bank_vendor
    ? `Bank shows: ${tx.bank_vendor} · ${money(tx.bank_amount)} · ${tx.bank_date}` : "";
  const box = $("#td-receipt");
  if (tx.receipt) {
    box.innerHTML = `<img src="/api/receipts/${tx.receipt.id}/image" alt="Receipt for ${esc(tx.vendor)}">`;
  } else {
    box.innerHTML = `<div class="none"><span>No receipt for this purchase.</span>
      <label class="filebtn">Upload receipt…<input type="file" id="td-upload" accept=".pdf,.jpg,.jpeg,.png,.webp" hidden></label></div>`;
    $("#td-upload").addEventListener("change", (e) => {
      const file = e.target.files[0];
      if (!file) return;
      $("#tx-dialog").close();
      show("add");
      uploadReceipt(file, tx.id);
    });
  }
  $("#tx-dialog").showModal();
}
$("#td-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  try {
    await api(`/api/transactions/${currentTx.id}`, { method: "PATCH", body: {
      vendor: f.vendor.value, date: f.date.value, amount: f.amount.value,
      notes: f.notes.value, category_id: f.category_id.value || null } });
    $("#tx-dialog").close();
    toast("Saved");
    loadPurchases();
  } catch (err) { toast(err.message, true); }
});
$("#td-delete").addEventListener("click", async () => {
  if (!confirm("Delete this purchase and its receipt?")) return;
  await api(`/api/transactions/${currentTx.id}`, { method: "DELETE" });
  $("#tx-dialog").close();
  toast("Deleted");
  loadPurchases();
});
$("#btn-add-manual").addEventListener("click", async () => {
  const vendor = prompt("Vendor?");
  if (!vendor) return;
  const amount = prompt("Amount?");
  if (amount == null) return;
  try {
    const tx = await api("/api/transactions", { method: "POST", body: { vendor, amount, date: new Date().toISOString().slice(0, 10) } });
    await loadPurchases();
    openTx(tx.id);
  } catch (err) { toast(err.message, true); }
});

/* ---------- Add receipt ---------- */
let review = null; // { receipt, suggestions, matches, txHint }
const drop = $("#drop");
["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", (e) => { const f = e.dataTransfer.files[0]; if (f) uploadReceipt(f); });
$("#file-input").addEventListener("change", (e) => { const f = e.target.files[0]; if (f) uploadReceipt(f); e.target.value = ""; });

async function uploadReceipt(file, txHint = null) {
  $("#review").hidden = true;
  $("#drop").hidden = true;
  $("#reading").hidden = false;
  const fd = new FormData();
  fd.append("file", file);
  try {
    const data = await api(`/api/receipts/upload${txHint ? `?transaction_id=${txHint}` : ""}`, { method: "POST", body: fd });
    showReview({ ...data, txHint });
  } catch (err) {
    toast(err.message, true);
    $("#drop").hidden = false;
  } finally {
    $("#reading").hidden = true;
  }
}

function showReview(data) {
  review = data;
  const r = data.receipt;
  const f = $("#rv-form");
  $("#rv-img").src = `/api/receipts/${r.id}/image?t=${Date.now()}`;
  for (const k of ["vendor", "date", "subtotal", "tax", "tip", "total"]) f[k].value = r[k] ?? "";
  $("#rv-error").hidden = !r.extract_error;
  $("#rv-error").textContent = r.extract_error ? `Couldn't read it automatically: ${r.extract_error} Fill in the fields below.` : "";
  $("#rv-reader").textContent = r.extractor && r.extractor !== "manual" ? `Read by: ${r.extractor}` : "";
  f.category_id.value = data.suggestions[0] ? data.suggestions[0].id : "";
  renderChips($("#rv-suggest"), f.category_id, data.suggestions);
  renderMatches(data.matches, data.txHint);
  $("#rv-items").innerHTML = r.items.map((it) => `<tr><td>${esc(it.description)}</td><td class="num">${money(it.price)}</td></tr>`).join("");
  $("#rv-item-count").textContent = r.items.length;
  $("#review").hidden = false;
}

function renderMatches(matches, txHint) {
  const box = $("#rv-matches");
  const pre = txHint || (matches[0] && matches[0].score >= 0.7 ? matches[0].id : "");
  box.innerHTML = matches.map((m) => `
    <label class="match"><input type="radio" name="transaction_id" value="${m.id}" ${String(m.id) === String(pre) ? "checked" : ""}>
      ${esc(m.date)} · ${esc(m.vendor)} · ${money(m.amount)}
      <span class="score">${m.id === txHint ? "chosen" : Math.round(m.score * 100) + "% match"}</span></label>`).join("") +
    `<label class="match"><input type="radio" name="transaction_id" value="" ${pre ? "" : "checked"}>
      No bank charge yet (create a new purchase)</label>`;
}

/* Re-check suggestions and matches when vendor/date/total change */
let refreshTimer;
["vendor", "date", "total", "tip"].forEach((k) => $("#rv-form")[k].addEventListener("change", () => {
  clearTimeout(refreshTimer);
  refreshTimer = setTimeout(async () => {
    if (!review) return;
    const f = $("#rv-form");
    const p = new URLSearchParams({ vendor: f.vendor.value });
    if (f.date.value) p.set("date", f.date.value);
    if (f.total.value) p.set("total", f.total.value);
    if (f.tip.value) p.set("tip", f.tip.value);
    if (review.txHint) p.set("transaction_id", review.txHint);
    const d = await api(`/api/receipts/${review.receipt.id}/review?${p}`);
    renderChips($("#rv-suggest"), f.category_id, d.suggestions);
    renderMatches(d.matches, review.txHint);
  }, 200);
}));

$("#rv-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  const body = Object.fromEntries(["vendor", "date", "subtotal", "tax", "tip", "total"].map((k) => [k, f[k].value]));
  body.category_id = f.category_id.value || null;
  body.transaction_id = (f.querySelector('input[name="transaction_id"]:checked') || {}).value || null;
  try {
    await api(`/api/receipts/${review.receipt.id}/save`, { method: "POST", body });
    toast("Receipt saved");
    resetAdd();
  } catch (err) { toast(err.message, true); }
});
$("#rv-discard").addEventListener("click", async () => {
  if (!review || !confirm("Discard this receipt?")) return;
  await api(`/api/receipts/${review.receipt.id}`, { method: "DELETE" });
  resetAdd();
});
$("#rv-reread").addEventListener("click", async () => {
  if (!review) return;
  $("#reading").hidden = false;
  try {
    const d = await api(`/api/receipts/${review.receipt.id}/reread${review.txHint ? `?transaction_id=${review.txHint}` : ""}`, { method: "POST" });
    showReview({ ...d, txHint: review.txHint });
  } catch (err) { toast(err.message, true); }
  finally { $("#reading").hidden = true; }
});
function resetAdd() {
  review = null;
  $("#review").hidden = true;
  $("#drop").hidden = false;
}

/* ---------- Reports ---------- */
let monthlyChart, categoryChart;
function chartDefaults() {
  Chart.defaults.font.family = 'system-ui, -apple-system, "Segoe UI", sans-serif';
  Chart.defaults.color = cssVar("--muted");
  Chart.defaults.borderColor = cssVar("--grid");
}

async function loadReports() {
  chartDefaults();
  const months = $("#r-months").value;
  const data = await api(`/api/reports/monthly?months=${months}`);
  const labels = data.months.map(monthLabel);

  // Categories past the 8 palette slots fold into "More" (never invent new hues).
  const series = [];
  const more = { name: "More", totals: data.months.map(() => 0), color: cssVar("--s-more") };
  for (const c of data.categories) {
    const i = CATS.findIndex((x) => x.id === c.id);
    if (c.id == null) series.push({ ...c, color: catColor(null) });
    else if (i < 8) series.push({ ...c, color: catColor(c.id) });
    else c.totals.forEach((v, j) => (more.totals[j] += v));
  }
  if (more.totals.some(Boolean)) series.push(more);

  monthlyChart?.destroy();
  monthlyChart = new Chart($("#chart-monthly"), {
    type: "bar",
    data: {
      labels,
      datasets: series.map((s) => ({
        label: s.name, data: s.totals, backgroundColor: s.color,
        borderColor: cssVar("--surface"), borderWidth: { top: 2 }, borderSkipped: "bottom",
        borderRadius: 4, maxBarThickness: 40,
      })),
    },
    options: {
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      scales: {
        x: { stacked: true, grid: { display: false } },
        y: { stacked: true, ticks: { callback: (v) => money(v) } },
      },
      plugins: {
        legend: { position: "bottom", labels: { boxWidth: 12, boxHeight: 12, color: cssVar("--ink-2") } },
        tooltip: {
          filter: (item) => item.raw > 0,
          callbacks: {
            label: (c) => ` ${c.dataset.label}: ${money(c.raw)}`,
            footer: (items) => `Total: ${money(items.reduce((s, i) => s + i.raw, 0))}`,
          },
        },
      },
    },
  });

  // Table view of the same numbers
  const head = `<thead><tr><th>Category</th>${labels.map((l) => `<th class="num">${l}</th>`).join("")}<th class="num">Total</th></tr></thead>`;
  const body = data.categories.map((c) => `<tr><td><span class="cat"><span class="dot" style="background:${catColor(c.id)}"></span>${esc(c.name)}</span></td>
    ${c.totals.map((v) => `<td class="num">${v ? money(v) : "—"}</td>`).join("")}
    <td class="num">${money(c.totals.reduce((a, b) => a + b, 0))}</td></tr>`).join("");
  const foot = `<tr class="total"><td>Total</td>${data.month_totals.map((v) => `<td class="num">${money(v)}</td>`).join("")}
    <td class="num">${money(data.month_totals.reduce((a, b) => a + b, 0))}</td></tr>`;
  $("#monthly-table").innerHTML = data.categories.length ? head + `<tbody>${body}${foot}</tbody>` : `<tbody><tr><td class="empty">No spending in this range yet.</td></tr></tbody>`;

  loadCategoryReview();
}

async function loadCategoryReview() {
  const cid = $("#r-category").value;
  if (!cid) return;
  const months = $("#r-months").value;
  const d = await api(`/api/reports/category/${cid}?months=${months}`);
  const color = cid === "none" ? catColor(null) : catColor(+cid);
  const vs = d.vs_average_pct;
  $("#review-tiles").innerHTML = `
    <div class="tile"><div class="label">This month</div><div class="value">${money(d.current)}</div>
      <div class="sub">${vs == null ? "No average yet" : `${vs > 0 ? "▲" : vs < 0 ? "▼" : "■"} ${Math.abs(vs)}% vs average`}</div></div>
    <div class="tile"><div class="label">Monthly average</div><div class="value">${money(d.average)}</div><div class="sub">finished months with spending</div></div>
    <div class="tile"><div class="label">Total, ${d.months.length} months</div><div class="value">${money(d.range_total)}</div><div class="sub">${d.counts.reduce((a, b) => a + b, 0)} purchases</div></div>
    <div class="tile"><div class="label">Missing receipts</div><div class="value">${d.missing_receipts}</div><div class="sub">in this range</div></div>`;

  categoryChart?.destroy();
  categoryChart = new Chart($("#chart-category"), {
    type: "bar",
    data: {
      labels: d.months.map(monthLabel),
      datasets: [
        { type: "bar", label: d.name, data: d.totals, backgroundColor: color, borderRadius: 4, borderSkipped: "bottom", maxBarThickness: 36 },
        { type: "line", label: "Average", data: d.months.map(() => d.average), borderColor: cssVar("--ink-2"),
          borderWidth: 2, borderDash: [5, 4], pointRadius: 0, pointHoverRadius: 0 },
      ],
    },
    options: {
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      scales: { x: { grid: { display: false } }, y: { beginAtZero: true, ticks: { callback: (v) => money(v) } } },
      plugins: {
        legend: { position: "bottom", labels: { boxWidth: 12, boxHeight: 12, color: cssVar("--ink-2") } },
        tooltip: { callbacks: { label: (c) => ` ${c.dataset.label}: ${money(c.raw)}` } },
      },
    },
  });

  $("#vendor-table").innerHTML = d.top_vendors.length
    ? `<thead><tr><th>Vendor</th><th class="num">Purchases</th><th class="num">Spent</th></tr></thead><tbody>` +
      d.top_vendors.map((v) => `<tr><td>${esc(v.vendor)}</td><td class="num">${v.n}</td><td class="num">${money(v.total)}</td></tr>`).join("") + "</tbody>"
    : `<tbody><tr><td class="empty">No purchases in this category yet.</td></tr></tbody>`;
}
$("#r-months").addEventListener("change", loadReports);
$("#r-category").addEventListener("change", loadCategoryReview);

/* ---------- Settings ---------- */
let SETTINGS = null;
async function loadSettings() {
  SETTINGS = await api("/api/settings");
  $("#providers").innerHTML = SETTINGS.providers.map((p) => {
    const on = p.id === SETTINGS.provider;
    const model = SETTINGS[`${p.id}_model`] || "";
    let fields = "";
    if (p.id !== "manual") fields += `<label>Model <input data-k="${p.id}_model" value="${esc(model)}" placeholder="${esc(p.default_model)}"></label>`;
    if (p.key_setting) fields += `<label>API key ${p.has_key ? "(saved)" : ""}
        <input data-k="${p.key_setting}" type="password" placeholder="${p.has_key ? "•••••• leave blank to keep" : "paste key"}"></label>`;
    if (p.id === "ollama") fields += `<label>Ollama address <input data-k="ollama_url" value="${esc(SETTINGS.ollama_url || "")}" placeholder="http://localhost:11434"></label>`;
    return `<div class="provider ${on ? "on" : ""}">
      <label class="provider-head"><input type="radio" name="provider" value="${p.id}" ${on ? "checked" : ""}> ${esc(p.label)}</label>
      <p class="note">${esc(p.note)}</p>
      ${fields ? `<div class="provider-body">${fields}</div>` : ""}</div>`;
  }).join("");
  $$('#providers input[name="provider"]').forEach((r) => r.addEventListener("change", () =>
    $$("#providers .provider").forEach((d) => d.classList.toggle("on", d.contains(r) && r.checked))));
  $("#about").textContent = `Version ${SETTINGS.version}. Data is stored in ${SETTINGS.data_dir}.` +
    (SETTINGS.password_on ? " Password protection is on." : "");
  renderCategoryList();
}
$("#btn-save-settings").addEventListener("click", async () => {
  const body = { provider: ($('#providers input[name="provider"]:checked') || {}).value };
  $$("#providers [data-k]").forEach((i) => (body[i.dataset.k] = i.value));
  try {
    await api("/api/settings", { method: "PUT", body });
    toast("Reader settings saved");
    loadSettings();
  } catch (err) { toast(err.message, true); }
});

function renderCategoryList() {
  $("#cat-list").innerHTML = CATS.map((c) => `
    <li class="${c.archived ? "archived" : ""}" data-id="${c.id}">
      <span class="dot" style="background:${catColor(c.id)}"></span>
      <input value="${esc(c.name)}">
      <button class="ghost" data-act="${c.archived ? "restore" : "archive"}">${c.archived ? "Restore" : "Hide"}</button>
    </li>`).join("");
  $$("#cat-list li").forEach((li) => {
    const id = +li.dataset.id;
    $("input", li).addEventListener("change", async (e) => {
      try { await api(`/api/categories/${id}`, { method: "PATCH", body: { name: e.target.value } }); await loadCategories(); toast("Renamed"); }
      catch (err) { toast(err.message, true); }
    });
    $("button", li).addEventListener("click", async (e) => {
      await api(`/api/categories/${id}`, { method: "PATCH", body: { archived: e.target.dataset.act === "archive" } });
      await loadCategories();
      renderCategoryList();
    });
  });
}
$("#cat-add").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api("/api/categories", { method: "POST", body: { name: e.target.elements["name"].value } });
    e.target.reset();
    await loadCategories();
    renderCategoryList();
  } catch (err) { toast(err.message, true); }
});
$("#csv-input").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append("file", file);
  try {
    const r = await api("/api/import/csv", { method: "POST", body: fd });
    $("#csv-result").textContent = `Imported ${r.imported} charges${r.skipped ? `, skipped ${r.skipped} already imported` : ""}.`;
  } catch (err) { toast(err.message, true); }
  e.target.value = "";
});

/* ---------- Start ---------- */
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
  if ($("#view-reports").classList.contains("active")) loadReports();
});
(async () => {
  $("#f-month").value = thisMonth();
  await loadCategories();
  const start = location.hash.slice(1);
  show(["purchases", "add", "reports", "settings"].includes(start) ? start : "purchases");
})();
