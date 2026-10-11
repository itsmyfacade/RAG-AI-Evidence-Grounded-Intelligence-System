const state = { samples: [], filtered: [] };

const $ = (id) => document.getElementById(id);

function setText(id, value) {
  $(id).textContent = value ?? "";
}

function renderList(id, values, formatter) {
  const target = $(id);
  target.replaceChildren();
  for (const value of values || []) {
    const item = document.createElement("li");
    item.textContent = formatter(value);
    target.appendChild(item);
  }
  if (!values || values.length === 0) {
    const item = document.createElement("li");
    item.textContent = "None reported.";
    target.appendChild(item);
  }
}

function renderEvidence(records) {
  const target = $("evidence");
  target.replaceChildren();
  for (const record of records || []) {
    const card = document.createElement("article");
    card.className = "evidence-card";
    const heading = document.createElement("strong");
    heading.textContent = `${record.evidence_id} · ${record.source_type}`;
    const source = document.createElement("span");
    source.textContent = `Source: ${record.source_id}`;
    const excerpt = document.createElement("p");
    excerpt.textContent = record.excerpt || JSON.stringify(record.value || {});
    card.append(heading, source, excerpt);
    target.appendChild(card);
  }
  if (!records || records.length === 0) {
    target.textContent = "No evidence records were emitted.";
  }
}

function renderTrace(trace) {
  const target = $("trace");
  target.replaceChildren();
  for (const entry of trace || []) {
    const row = document.createElement("li");
    row.textContent = `${entry.step}: ${entry.status} — ${entry.detail}`;
    target.appendChild(row);
  }
}

function populateSelect(samples) {
  const select = $("scenario");
  const selected = select.value;
  select.replaceChildren();
  for (const sample of samples) {
    const option = document.createElement("option");
    option.value = sample.scenario_id;
    option.textContent = `${sample.scenario_id} · ${sample.title}`;
    select.appendChild(option);
  }
  if (samples.some((sample) => sample.scenario_id === selected)) select.value = selected;
  updateQuestion();
}

function updateQuestion() {
  const sample = state.samples.find((item) => item.scenario_id === $("scenario").value);
  $("question").value = sample?.question || "";
}

function filterSamples() {
  const needle = $("filter").value.trim().toLowerCase();
  state.filtered = state.samples.filter((sample) =>
    [sample.scenario_id, sample.title, sample.domain, sample.evidence_profile]
      .join(" ").toLowerCase().includes(needle)
  );
  populateSelect(state.filtered);
  setText("sample-count", `${state.filtered.length} of ${state.samples.length} scenarios`);
}

async function loadSamples() {
  const response = await fetchWithTimeout("/samples", {}, 10000);
  const data = await readResponse(response);
  if (!response.ok) throw new Error(data.detail || "Sample scenarios are temporarily unavailable. Please retry.");
  state.samples = Array.isArray(data) ? data : [];
  state.filtered = state.samples;
  populateSelect(state.samples);
  setText("sample-count", `${state.samples.length} scenarios available`);
}

async function investigate() {
  const button = $("run");
  button.disabled = true;
  setText("status", "Running…");
  try {
    const response = await fetchWithTimeout("/investigate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scenario_id: $("scenario").value, question: $("question").value }),
    }, 45000);
    const data = await readResponse(response);
    if (!response.ok) throw new Error(data.detail || "Investigation failed. Check the request and service readiness.");
    const report = data.report;
    setText("status", report.status);
    setText("status-badge", report.status);
    setText("provider", `${report.provider} · ${data.mode || "local"}`);
    setText("summary", report.summary);
    renderList("findings", report.findings, (item) => `${item.finding_id}: ${item.statement}`);
    renderList("hypotheses", report.hypotheses, (item) => item);
    renderList("checks", report.recommended_checks, (item) => item);
    renderList("contradictions", report.contradictions, (item) => item);
    renderList("gaps", report.evidence_gaps, (item) => item);
    renderEvidence(report.evidence);
    renderTrace(report.agent_trace);
  } catch (error) {
    setText("status", "error");
    setText("summary", friendlyError(error));
  } finally {
    button.disabled = false;
  }
}

async function fetchWithTimeout(url, options, timeoutMs) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

async function readResponse(response) {
  const text = await response.text();
  if (!text.trim()) return {};
  try {
    return JSON.parse(text);
  } catch {
    throw new Error(`The service returned an incomplete response (HTTP ${response.status}). Please retry.`);
  }
}

function friendlyError(error) {
  if (error.name === "AbortError") return "The investigation timed out. The demo may be restarting; please retry.";
  if (error instanceof TypeError) return "The demo service could not be reached. Please retry in a moment.";
  return error.message || "The investigation could not be completed. Please retry.";
}

$("filter").addEventListener("input", filterSamples);
$("scenario").addEventListener("change", updateQuestion);
$("run").addEventListener("click", investigate);
loadSamples().catch((error) => {
  setText("status", "error");
  setText("summary", friendlyError(error));
});
