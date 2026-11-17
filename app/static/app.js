"use strict";

const $ = (id) => document.getElementById(id);
const els = {
  form: $("link-form"), url: $("folder-url"), listBtn: $("list-btn"), error: $("error"),
  filesSection: $("files-section"), tbody: document.querySelector("#files-table tbody"),
  selectAll: $("select-all"), count: $("selection-count"), runBtn: $("run-btn"),
  langs: $("languages"), empty: $("empty-msg"), controls: $("files-controls"),
  progress: $("progress"), bar: $("progress-bar"), barLabel: $("progress-label"),
  resultsSection: $("results-section"), results: $("results"), exportBtn: $("export-btn"),
};
const LANG_NAMES = { eng: "English", fra: "French", ara: "Arabic" };

let files = [];          // files listed from the folder
let folderUrl = "";      // URL the list was fetched with
let polling = null;
let busy = false;

function showError(message) {
  els.error.textContent = message;
  els.error.hidden = !message;
}

async function api(path, options) {
  let response;
  try {
    response = await fetch(path, options);
  } catch {
    throw new Error("Cannot reach the server. Is it running?");
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = Array.isArray(body.detail) ? "Invalid request." : body.detail;
    throw new Error(detail || `Request failed (${response.status}).`);
  }
  return body;
}

function formatSize(bytes) {
  if (bytes == null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function typeLabel(file) {
  if (file.kind === "pdf") return "PDF";
  return file.mime_type === "image/png" ? "PNG" : "JPG";
}

function selectedIds() {
  return [...els.tbody.querySelectorAll("input[type=checkbox]:checked")].map((c) => c.value);
}
function selectedLanguages() {
  const chosen = [...els.langs.querySelectorAll("input:checked")].map((c) => c.value);
  return chosen.length ? chosen : ["eng"];
}

function updateControls() {
  const boxes = [...els.tbody.querySelectorAll("input[type=checkbox]")];
  const n = boxes.filter((b) => b.checked).length;
  els.count.textContent = `${n} of ${boxes.length} selected`;
  els.selectAll.checked = boxes.length > 0 && n === boxes.length;
  els.selectAll.indeterminate = n > 0 && n < boxes.length;
  els.runBtn.disabled = busy || n === 0;
}

function setBusy(value) {
  busy = value;
  els.listBtn.disabled = value;
  els.selectAll.disabled = value;
  els.tbody.querySelectorAll("input").forEach((i) => (i.disabled = value));
  els.langs.querySelectorAll("input").forEach((i) => (i.disabled = value));
  updateControls();
}

function renderFiles() {
  els.tbody.replaceChildren();
  els.empty.hidden = files.length > 0;
  els.controls.hidden = files.length === 0;
  els.filesSection.hidden = false;
  for (const file of files) {
    const row = document.createElement("tr");
    row.dataset.id = file.id;

    const pick = document.createElement("td");
    const box = document.createElement("input");
    box.type = "checkbox";
    box.value = file.id;
    box.setAttribute("aria-label", `Select ${file.name}`);
    pick.append(box);

    const name = document.createElement("td");
    name.className = "name";
    name.textContent = file.name;

    const type = document.createElement("td");
    type.textContent = typeLabel(file);

    const size = document.createElement("td");
    size.className = "num-col";
    size.textContent = formatSize(file.size);

    const status = document.createElement("td");
    status.className = "status";

    row.append(pick, name, type, size, status);
    els.tbody.append(row);
  }
  updateControls();
}

function setStatus(fileId, status) {
  const cell = els.tbody.querySelector(`tr[data-id="${CSS.escape(fileId)}"] .status`);
  if (!cell) return;
  if (!status) { cell.replaceChildren(); return; }
  const badge = document.createElement("span");
  badge.className = `badge ${status}`;
  badge.textContent = status;
  cell.replaceChildren(badge);
}

function renderResults(job) {
  els.results.replaceChildren();
  for (const file of job.files) {
    if (file.status !== "done" && file.status !== "failed") continue;
    const details = document.createElement("details");
    details.open = job.files.length === 1;

    const summary = document.createElement("summary");
    const fname = document.createElement("span");
    fname.className = "fname";
    fname.textContent = file.name;
    const badge = document.createElement("span");
    badge.className = `badge ${file.status}`;
    badge.textContent = file.status === "done" ? file.method.replace("_", " ") : "failed";
    const meta = document.createElement("span");
    meta.className = "meta";
    const bits = [];
    if (file.pages) bits.push(`${file.pages} page${file.pages > 1 ? "s" : ""}`);
    if (file.duration_ms != null) bits.push(`${(file.duration_ms / 1000).toFixed(1)} s`);
    meta.textContent = bits.join(" · ");
    summary.append(fname, badge, meta);

    const body = document.createElement("div");
    body.className = "result-body";
    if (file.status === "failed") {
      const p = document.createElement("p");
      p.className = "err";
      p.textContent = file.error;
      body.append(p);
    } else {
      for (const warning of file.warnings) {
        const w = document.createElement("p");
        w.className = "warn";
        w.textContent = warning;
        body.append(w);
      }
      const actions = document.createElement("div");
      actions.className = "actions";
      const copy = document.createElement("button");
      copy.type = "button";
      copy.className = "secondary";
      copy.textContent = "Copy text";
      copy.addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText(file.text);
          copy.textContent = "Copied";
        } catch {
          copy.textContent = "Copy failed";
        }
        setTimeout(() => (copy.textContent = "Copy text"), 1500);
      });
      actions.append(copy);
      const pre = document.createElement("pre");
      pre.textContent = file.text || "(no text found)";
      body.append(actions, pre);
    }
    details.append(summary, body);
    els.results.append(details);
  }
  els.resultsSection.hidden = els.results.children.length === 0;
}

function renderJob(job) {
  job.files.forEach((f) => setStatus(f.id, f.status));
  const finished = job.files.filter((f) => f.status === "done" || f.status === "failed").length;
  els.bar.max = job.files.length;
  els.bar.value = finished;
  const failed = job.files.filter((f) => f.status === "failed").length;
  els.barLabel.textContent =
    `${finished} / ${job.files.length} processed` + (failed ? `, ${failed} failed` : "");
  renderResults(job);
}

async function poll(jobId) {
  try {
    const job = await api(`/api/jobs/${jobId}`);
    renderJob(job);
    if (job.status === "completed") {
      els.exportBtn.href = `/api/jobs/${jobId}/export`;
      els.exportBtn.removeAttribute("aria-disabled");
      setBusy(false);
      return;
    }
    polling = setTimeout(() => poll(jobId), 800);
  } catch (err) {
    showError(err.message);
    setBusy(false);
  }
}

async function loadConfig() {
  try {
    const config = await api("/api/config");
    els.langs.querySelectorAll("label").forEach((l) => l.remove());
    const available = config.ocr_languages.length ? config.ocr_languages : ["eng"];
    available.forEach((code, i) => {
      const label = document.createElement("label");
      label.className = "check";
      const box = document.createElement("input");
      box.type = "checkbox";
      box.value = code;
      box.checked = i === 0;
      label.append(box, ` ${LANG_NAMES[code] || code}`);
      els.langs.append(label);
    });
  } catch (err) {
    showError(err.message);
  }
}

els.form.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearTimeout(polling);
  showError("");
  els.resultsSection.hidden = true;
  els.progress.hidden = true;
  els.listBtn.disabled = true;
  els.listBtn.textContent = "Loading…";
  try {
    folderUrl = els.url.value.trim();
    const data = await api("/api/folders/list", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: folderUrl }),
    });
    files = data.files;
    renderFiles();
  } catch (err) {
    els.filesSection.hidden = true;
    showError(err.message);
  } finally {
    els.listBtn.disabled = false;
    els.listBtn.textContent = "List files";
  }
});

els.selectAll.addEventListener("change", () => {
  els.tbody.querySelectorAll("input[type=checkbox]").forEach((b) => (b.checked = els.selectAll.checked));
  updateControls();
});
els.tbody.addEventListener("change", updateControls);

els.runBtn.addEventListener("click", async () => {
  showError("");
  setBusy(true);
  els.exportBtn.setAttribute("aria-disabled", "true");
  els.exportBtn.href = "#";
  els.results.replaceChildren();
  els.resultsSection.hidden = true;
  files.forEach((f) => setStatus(f.id, ""));
  const ids = selectedIds();
  ids.forEach((id) => setStatus(id, "pending"));
  els.bar.max = ids.length;
  els.bar.value = 0;
  els.barLabel.textContent = `0 / ${ids.length} processed`;
  els.progress.hidden = false;
  try {
    const { job_id } = await api("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: folderUrl, file_ids: ids, languages: selectedLanguages() }),
    });
    poll(job_id);
  } catch (err) {
    showError(err.message);
    setBusy(false);
  }
});

loadConfig();
