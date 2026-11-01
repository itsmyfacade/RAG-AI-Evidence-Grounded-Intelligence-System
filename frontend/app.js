const state = {
  samples: [],
  filtered: [],
  activeView: "investigate",
  selectedScenarioId: null,
  question: "",
  lifecycle: "idle",
  loading: false,
  activeRequestId: 0,
  report: null,
  trace: [],
  error: null,
  activeDetail: "evidence",
};

const $ = (id) => document.getElementById(id);

function setText(id, value) {
  const node = $(id);
  if (node) node.textContent = value ?? "";
}

function show(id, visible) {
  const node = $(id);
  if (node) node.hidden = !visible;
}

function sourceLabel(type) {
  const labels = { document: "Document", sql: "SQL record", log: "API log", deployment: "Deployment", configuration: "Configuration", ticket: "Support ticket", webhook: "Webhook" };
  return labels[type] || type || "Evidence";
}

function setLifecycle(next) {
  const lifecycle = ["idle", "ready", "running", "completed", "failed"].includes(next) ? next : "idle";
  state.lifecycle = lifecycle;
  const selected = state.samples.find((item) => item.scenario_id === state.selectedScenarioId);
  const labels = { idle: "Idle", ready: "Ready", running: "Running", completed: "Completed", failed: "Failed" };
  const details = {
    idle: "Select a symptom-oriented scenario to prepare an investigation.",
    ready: selected ? `Run ${selected.scenario_id} to produce an evidence-grounded operational assessment.` : "Select a scenario to prepare an investigation.",
    running: "The API request is active; the report will appear only after validation completes.",
    completed: "The bounded workflow completed. Review the assessment, then inspect its evidence or execution trace.",
    failed: "No validated report is available. Review the error state and retry when the service is ready.",
  };
  const indicator = $("execution-indicator");
  indicator.className = `execution-indicator is-${lifecycle}`;
  show("execution-indicator", ["running", "completed", "failed"].includes(lifecycle));
  setText("execution-label", labels[lifecycle]);
  setText("execution-detail", details[lifecycle]);
  show("execution-action", lifecycle === "completed");
  show("report", lifecycle === "completed");
  show("empty-state", lifecycle === "failed");
  setText("status", labels[lifecycle]);
  setText("workspace-status", labels[lifecycle]);
  setText("execution-view-label", labels[lifecycle]);
  setText("execution-view-detail", details[lifecycle]);
  setText("execution-view-status", labels[lifecycle]);
  const actionLabels = { idle: "Select a scenario", ready: "Ready to investigate", running: "Investigation running", completed: "Investigation completed", failed: "Investigation unavailable" };
  const actionMessages = { idle: "Select a scenario to begin.", ready: "Review the question, then run the bounded investigation.", running: "The request is active; results appear after validation.", completed: "Assessment available below. Inspect evidence or execution details as needed.", failed: "Retry when the service is ready." };
  setText("action-readiness", actionLabels[lifecycle]);
  setText("action-message", actionMessages[lifecycle]);
  const action = $("composer-action");
  if (action) action.className = `composer-action is-${lifecycle}`;
  const meta = $("execution-view-meta");
  if (meta) {
    meta.replaceChildren();
    if (state.report) {
      const provider = document.createElement("span");
      provider.textContent = `${state.report.provider || "Provider unavailable"} · ${state.report.retrieval_mode || "Retrieval unavailable"}`;
      const attempts = document.createElement("span");
      attempts.textContent = `Attempts: ${state.report.attempts ?? "—"}`;
      const citations = document.createElement("span");
      citations.textContent = `Evidence references: ${Array.isArray(state.report.evidence) ? state.report.evidence.length : "—"}`;
      meta.append(provider, attempts, citations);
    }
  }
  show("execution-view-empty", !state.report);
  show("execution-view-trace-panel", Boolean(state.report && state.trace.length));
  if (lifecycle === "running") $("run").setAttribute("aria-busy", "true");
  else $("run").removeAttribute("aria-busy");
}

function renderEmptyState() {
  const selected = state.samples.find((item) => item.scenario_id === state.selectedScenarioId);
  if (selected) {
    setText("empty-title", "Ready to investigate");
    setText("empty-description", `Run ${selected.scenario_id} to produce an evidence-grounded operational assessment. The report will separate observations, hypotheses, and supported conclusions.`);
    if (!state.loading && state.lifecycle !== "failed") setLifecycle("ready");
  } else {
    setText("empty-title", "Select a scenario to begin");
    setText("empty-description", "Choose an available symptom-oriented scenario, then review its question before starting the bounded investigation.");
    if (!state.loading && state.lifecycle !== "failed") setLifecycle("idle");
  }
}

function invalidateReport() {
  state.report = null;
  state.trace = [];
  state.error = null;
  if (state.loading) return;
  setLifecycle(state.selectedScenarioId ? "ready" : "idle");
  renderEmptyState();
}

function renderFindings(findings) {
  const target = $("findings");
  target.replaceChildren();
  const items = Array.isArray(findings) ? findings : [];
  setText("finding-count", `${items.length} ${items.length === 1 ? "finding" : "findings"}`);
  if (!items.length) {
    const empty = document.createElement("p");
    empty.className = "empty-note";
    empty.textContent = "No structured findings were emitted.";
    target.appendChild(empty);
    return;
  }
  const labels = { observation: "Observed fact", hypothesis: "Plausible hypothesis", conclusion: "Supported conclusion" };
  for (const finding of items) {
    const card = document.createElement("article");
    card.className = `finding finding-${finding.status || "observation"}`;
    const top = document.createElement("div");
    top.className = "finding-topline";
    const kind = document.createElement("span");
    kind.className = "finding-kind";
    kind.textContent = labels[finding.status] || "Finding";
    const id = document.createElement("span");
    id.className = "mono-label";
    id.textContent = finding.finding_id || "—";
    top.append(kind, id);
    const statement = document.createElement("p");
    statement.className = "finding-statement";
    statement.textContent = finding.statement || "No statement provided.";
    const refs = document.createElement("div");
    refs.className = "finding-refs";
    refs.textContent = finding.evidence_refs?.length ? `Supported by ${finding.evidence_refs.join(" · ")}` : "No evidence references recorded";
    card.append(top, statement, refs);
    target.appendChild(card);
  }
}

function renderOperations(records) {
  const target = $("operations");
  target.replaceChildren();
  const items = Array.isArray(records) ? records : [];
  setText("evidence-count", `${items.length} records`);
  const groups = new Map();
  for (const record of items) {
    const key = record.source_type || "other";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(record);
  }
  if (!groups.size) {
    const empty = document.createElement("p");
    empty.className = "empty-note";
    empty.textContent = "No operational records were returned.";
    target.appendChild(empty);
    return;
  }
  for (const [type, group] of groups) {
    const item = document.createElement("div");
    item.className = "operation-card";
    const icon = document.createElement("span");
    icon.className = "operation-icon";
    icon.textContent = type === "webhook" ? "↔" : type === "deployment" ? "⇧" : type === "configuration" ? "⚙" : type === "log" ? "≋" : "▣";
    const copy = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = sourceLabel(type);
    const count = document.createElement("span");
    count.textContent = `${group.length} record${group.length === 1 ? "" : "s"}`;
    copy.append(title, count);
    item.append(icon, copy);
    target.appendChild(item);
  }
}

function renderUncertainty(report) {
  const target = $("uncertainty");
  target.replaceChildren();
  const items = [
    ...(report.evidence_gaps || []).map((text) => ({ label: "Evidence gap", text, tone: "gap" })),
    ...(report.contradictions || []).map((text) => ({ label: "Contradiction", text, tone: "conflict" })),
  ];
  if (!items.length) {
    const empty = document.createElement("p");
    empty.className = "empty-note";
    empty.textContent = "No additional evidence gaps or contradictions were reported.";
    target.appendChild(empty);
    return;
  }
  for (const entry of items) {
    const item = document.createElement("div");
    item.className = `uncertainty-item ${entry.tone}`;
    const label = document.createElement("span");
    label.textContent = entry.label;
    const text = document.createElement("p");
    text.textContent = entry.text;
    item.append(label, text);
    target.appendChild(item);
  }
}

function renderChecks(checks) {
  const target = $("checks");
  target.replaceChildren();
  const items = Array.isArray(checks) ? checks : [];
  if (!items.length) {
    const empty = document.createElement("p");
    empty.className = "empty-note";
    empty.textContent = "No additional checks were recommended.";
    target.appendChild(empty);
    return;
  }
  items.forEach((check, index) => {
    const item = document.createElement("div");
    item.className = "check-item";
    const number = document.createElement("span");
    number.textContent = String(index + 1).padStart(2, "0");
    const text = document.createElement("p");
    text.textContent = check;
    item.append(number, text);
    target.appendChild(item);
  });
}

function renderEvidence(records) {
  const target = $("evidence");
  target.replaceChildren();
  const items = Array.isArray(records) ? records : [];
  if (!items.length) {
    const empty = document.createElement("p");
    empty.className = "empty-note";
    empty.textContent = "No evidence records were emitted.";
    target.appendChild(empty);
    return;
  }
  const groups = new Map();
  for (const record of items) {
    const type = record.source_type || "other";
    if (!groups.has(type)) groups.set(type, []);
    groups.get(type).push(record);
  }
  for (const [type, group] of groups) {
    const section = document.createElement("details");
    section.className = "evidence-group";
    const heading = document.createElement("summary");
    heading.className = "evidence-group-heading";
    const title = document.createElement("h4");
    title.textContent = sourceLabel(type);
    const count = document.createElement("span");
    count.textContent = `${group.length} record${group.length === 1 ? "" : "s"}`;
    heading.append(title, count);
    const list = document.createElement("div");
    list.className = "evidence-group-items";
    for (const record of group) {
      const card = document.createElement("details");
      card.className = "evidence-card";
      const summary = document.createElement("summary");
      const id = document.createElement("span");
      id.className = "evidence-id";
      id.textContent = record.evidence_id || "Unknown evidence";
      const typeLabel = document.createElement("span");
      typeLabel.className = "evidence-type";
      typeLabel.textContent = sourceLabel(record.source_type);
      const source = document.createElement("span");
      source.className = "evidence-source";
      source.textContent = record.source_id ? `Source ${record.source_id}` : "Source unavailable";
      summary.append(id, typeLabel, source);
      const excerpt = document.createElement("p");
      excerpt.className = "evidence-excerpt";
      excerpt.textContent = record.excerpt || "No excerpt provided.";
      card.append(summary, excerpt);
      list.appendChild(card);
    }
    section.append(heading, list);
    target.appendChild(section);
  }
}

function renderTrace(trace, attempts) {
  const items = Array.isArray(trace) ? trace : [];
  const stageLabels = {
    supervisor: "Supervisor",
    document_research: "Document research",
    operations_analysis: "Operations analysis",
    investigation_synthesis: "Investigation synthesis",
    evidence_verification: "Evidence verification",
  };
  state.trace = items;
  for (const target of [$("trace"), $("execution-view-trace")].filter(Boolean)) {
    target.replaceChildren();
    if (!items.length) {
      const empty = document.createElement("li");
      empty.className = "empty-note";
      empty.textContent = "No execution trace was returned.";
      target.appendChild(empty);
      continue;
    }
    for (const entry of items) {
      const row = document.createElement("li");
      row.className = `trace-item trace-${entry.status || "completed"}`;
      const marker = document.createElement("span");
      marker.className = "trace-marker";
      marker.setAttribute("aria-hidden", "true");
      const copy = document.createElement("div");
      const topline = document.createElement("div");
      topline.className = "trace-topline";
      const title = document.createElement("strong");
      title.textContent = stageLabels[entry.step] || entry.step || "Workflow stage";
      const status = document.createElement("span");
      status.className = "trace-status";
      status.textContent = entry.status || "Returned";
      const detail = document.createElement("p");
      detail.textContent = entry.detail || entry.status || "Completed";
      topline.append(title, status);
      copy.append(topline, detail);
      row.append(marker, copy);
      target.appendChild(row);
    }
    if (attempts > 1) {
      const note = document.createElement("li");
      note.className = "trace-retry";
      note.textContent = `${attempts} bounded workflow attempts recorded.`;
      target.appendChild(note);
    }
  }
}

function setDetail(name) {
  state.activeDetail = name;
  document.querySelectorAll(".detail-tab").forEach((tab) => {
    const active = tab.dataset.detail === name;
    tab.classList.toggle("is-active", active);
    tab.setAttribute("aria-selected", String(active));
  });
  document.querySelectorAll(".detail-panel").forEach((panel) => {
    panel.hidden = panel.id !== `detail-${name}`;
    panel.classList.toggle("is-active", panel.id === `detail-${name}`);
  });
}

function renderReport(data) {
  const report = data.report || {};
  state.report = report;
  state.error = null;
  setText("assessment-title", report.status === "completed" ? "Evidence-backed assessment" : "Investigation requires review");
  setText("summary", report.summary || data.answer || "No summary was returned.");
  setText("investigation-context", `${$("scenario").value || "Investigation"} · ${report.question || data.question || ""}`);
  setText("status-badge", report.status || data.status || "unknown");
  setText("investigation-id", report.investigation_id || data.investigation_id || "");
  setText("provider", report.provider || data.mode || "unknown");
  setText("retrieval", report.retrieval_mode || "unknown");
  setText("model", report.model || "deterministic local");
  setText("attempts", report.attempts ?? "—");
  setLifecycle("completed");
  renderFindings(report.findings);
  renderOperations(report.evidence);
  renderChecks(report.recommended_checks);
  renderUncertainty(report);
  renderEvidence(report.evidence);
  renderTrace(report.agent_trace || data.agent_trace, report.attempts);
  setLifecycle("completed");
  setDetail(state.activeDetail);
}

function populateSelect(samples) {
  const select = $("scenario");
  const selected = state.selectedScenarioId || select.value;
  select.replaceChildren();
  for (const sample of samples) {
    const option = document.createElement("option");
    option.value = sample.scenario_id;
    option.textContent = `${sample.scenario_id} · ${sample.title}`;
    select.appendChild(option);
  }
  if (samples.some((sample) => sample.scenario_id === selected)) select.value = selected;
  else if (samples[0]) select.value = samples[0].scenario_id;
  state.selectedScenarioId = select.value || null;
  updateQuestion();
  renderEmptyState();
}

function updateQuestion() {
  const sample = state.samples.find((item) => item.scenario_id === state.selectedScenarioId);
  state.question = sample?.question || state.question || "";
  $("question").value = state.question;
}

function renderScenarioCatalog(samples) {
  const target = $("scenario-catalog");
  if (!target) return;
  target.replaceChildren();
  setText("catalog-count", `${samples.length} of ${state.samples.length} scenarios`);
  if (!samples.length) {
    const empty = document.createElement("p");
    empty.className = "view-empty-copy";
    empty.textContent = "No scenarios match the current search.";
    target.appendChild(empty);
    return;
  }
  for (const sample of samples) {
    const card = document.createElement("article");
    card.className = `scenario-card${sample.scenario_id === state.selectedScenarioId ? " is-selected" : ""}`;
    const meta = document.createElement("div");
    meta.className = "scenario-card-meta";
    const id = document.createElement("span");
    id.textContent = sample.scenario_id;
    const domain = document.createElement("span");
    domain.textContent = sample.domain || "Synthetic operations";
    meta.append(id, domain);
    const title = document.createElement("h3");
    title.textContent = sample.title || "Untitled scenario";
    const question = document.createElement("p");
    question.textContent = sample.question || "No scenario question supplied.";
    const action = document.createElement("button");
    action.className = "quiet-action";
    action.type = "button";
    action.dataset.scenario = sample.scenario_id;
    action.textContent = sample.scenario_id === state.selectedScenarioId ? "Investigate selected →" : "Investigate →";
    card.append(meta, title, question, action);
    target.appendChild(card);
  }
}

function filterSamples() {
  const needle = $("filter").value.trim().toLowerCase();
  state.filtered = state.samples.filter((sample) => [sample.scenario_id, sample.title, sample.domain].join(" ").toLowerCase().includes(needle));
  populateSelect(state.filtered);
  setText("sample-count", `${state.filtered.length} of ${state.samples.length} scenarios`);
  renderScenarioCatalog(state.filtered);
}

function navigate(name) {
  if (!["investigate", "scenarios", "execution"].includes(name)) return;
  state.activeView = name;
  document.querySelectorAll(".nav-item").forEach((item) => {
    const active = item.dataset.nav === name;
    item.classList.toggle("is-active", active);
    if (active) item.setAttribute("aria-current", "page");
    else item.removeAttribute("aria-current");
  });
  document.querySelectorAll(".workspace-view").forEach((view) => {
    const active = view.dataset.view === name;
    view.hidden = !active;
    view.classList.toggle("is-active", active);
  });
  const titles = { investigate: "Incident investigation", scenarios: "Scenario explorer", execution: "Execution" };
  const subtitles = {
    investigate: "Correlate technical documentation with operational records to establish what the available evidence supports.",
    scenarios: "Review synthetic incident contexts and open one for evidence-grounded investigation.",
    execution: "Inspect the returned bounded workflow trace and evidence-validation metadata for this session.",
  };
  setText("workspace-title", titles[name]);
  setText("workspace-subtitle", subtitles[name]);
  const target = name === "scenarios" ? $("catalog-filter") : name === "execution" ? $("execution-title") : $("composer-title");
  if (target) target.focus({ preventScroll: true });
  if (name === "scenarios") renderScenarioCatalog(state.filtered);
  if (name === "execution") setLifecycle(state.lifecycle);
}

async function loadReadiness() {
  try {
    const response = await fetchWithTimeout("/ready", {}, 8000);
    const data = await readResponse(response);
    const ready = response.ok && data.ready !== false;
    setText("readiness", ready ? "Service ready" : "Service degraded");
    $("readiness").classList.toggle("is-ready", ready);
    $("readiness").classList.toggle("is-degraded", !ready);
  } catch {
    setText("readiness", "Readiness unavailable");
    $("readiness").classList.add("is-degraded");
  }
}

async function loadSamples() {
  const response = await fetchWithTimeout("/samples", {}, 10000);
  const data = await readResponse(response);
  if (!response.ok) throw new Error(data.detail || "Sample scenarios are temporarily unavailable. Please retry.");
  state.samples = Array.isArray(data) ? data : [];
  state.filtered = state.samples;
  populateSelect(state.samples);
  setText("sample-count", `${state.samples.length} scenarios available`);
  renderScenarioCatalog(state.filtered);
  renderEmptyState();
}

async function investigate() {
  const button = $("run");
  if (state.loading || !$("scenario").value) return;
  const scenarioId = $("scenario").value;
  const requestId = ++state.activeRequestId;
  state.loading = true;
  state.report = null;
  state.trace = [];
  state.error = null;
  button.disabled = true;
  setLifecycle("running");
  try {
    const response = await fetchWithTimeout("/investigate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ scenario_id: scenarioId, question: $("question").value }) }, 45000);
    const data = await readResponse(response);
    if (!response.ok) throw new Error(data.detail || "Investigation failed. Check service readiness and retry.");
    if (requestId !== state.activeRequestId || $("scenario").value !== scenarioId) {
      setLifecycle($("scenario").value ? "ready" : "idle");
      return;
    }
    renderReport(data);
  } catch (error) {
    if (requestId !== state.activeRequestId) return;
    state.error = error.message;
    state.report = null;
    setLifecycle("failed");
    setText("empty-title", friendlyError(error));
    setText("empty-description", "No report was displayed. The service returned no validated result; retry when it is ready.");
  } finally {
    state.loading = false;
    button.disabled = false;
  }
}

function selectScenario(scenarioId) {
  if (!state.samples.some((sample) => sample.scenario_id === scenarioId)) return;
  state.selectedScenarioId = scenarioId;
  $("scenario").value = scenarioId;
  updateQuestion();
  invalidateReport();
  renderScenarioCatalog(state.filtered);
}

function filterCatalog() {
  const needle = $("catalog-filter").value.trim().toLowerCase();
  state.filtered = state.samples.filter((sample) => [sample.scenario_id, sample.title, sample.domain, sample.question].join(" ").toLowerCase().includes(needle));
  renderScenarioCatalog(state.filtered);
}

async function fetchWithTimeout(url, options, timeoutMs) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try { return await fetch(url, { ...options, signal: controller.signal }); } finally { clearTimeout(timer); }
}

async function readResponse(response) {
  const text = await response.text();
  if (!text.trim()) return {};
  try { return JSON.parse(text); } catch { throw new Error(`The service returned an incomplete response (HTTP ${response.status}). Please retry.`); }
}

function friendlyError(error) {
  if (error.name === "AbortError") return "The investigation timed out. The demo may be restarting; please retry.";
  if (error instanceof TypeError) return "The demo service could not be reached. Please retry in a moment.";
  return error.message || "The investigation could not be completed. Please retry.";
}

$("filter").addEventListener("input", filterSamples);
$("catalog-filter").addEventListener("input", filterCatalog);
$("scenario").addEventListener("change", () => { selectScenario($("scenario").value); });
$("run").addEventListener("click", investigate);
document.querySelectorAll("[data-nav]").forEach((button) => button.addEventListener("click", () => navigate(button.dataset.nav)));
$("scenario-catalog").addEventListener("click", (event) => {
  const button = event.target.closest("[data-scenario]");
  if (!button) return;
  selectScenario(button.dataset.scenario);
  navigate("investigate");
});
document.querySelectorAll("[data-detail]").forEach((button) => button.addEventListener("click", () => setDetail(button.dataset.detail)));
loadReadiness();
loadSamples().catch((error) => {
  setLifecycle("failed");
  setText("sample-count", "Scenarios unavailable");
  setText("empty-title", friendlyError(error));
  setText("empty-description", "The service did not return a scenario list. Check readiness and retry.");
});
