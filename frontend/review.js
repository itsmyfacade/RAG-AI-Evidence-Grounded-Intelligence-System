const REVIEW_STORAGE_KEY = "aegis-review-state-v1";
const REVIEW_SCHEMA_VERSION = "aegis-phase4-review-decisions-v1";
const REVIEW_DECISIONS = new Set(["pending", "confirmed", "rejected", "ambiguous"]);
const reviewState = { packet: null, packetFingerprint: null, index: 0, decisions: {}, savedState: null, storageAvailable: true };
const review$ = (id) => document.getElementById(id);

function reviewText(id, value) { review$(id).textContent = value === null || value === undefined ? "" : String(value); }

function setStorageStatus(message, failure = false) {
  const target = review$("storage-status");
  if (!target) return;
  target.textContent = message;
  target.classList.toggle("is-warning", failure);
}

function readSavedState() {
  try {
    const raw = window.localStorage.getItem(REVIEW_STORAGE_KEY);
    if (!raw) return null;
    const saved = JSON.parse(raw);
    if (saved?.schema_version !== REVIEW_SCHEMA_VERSION || typeof saved.packet_fingerprint !== "string" || typeof saved.decisions !== "object") return null;
    setStorageStatus("Saved review state found. Load the matching packet to resume.");
    return saved;
  } catch (error) {
    reviewState.storageAvailable = false;
    setStorageStatus(`Browser storage is unavailable. Use exports as your backup. (${error.message})`, true);
    return null;
  }
}

function fallbackFingerprint(value) {
  let hash = 2166136261;
  for (const character of value) { hash ^= character.charCodeAt(0); hash = Math.imul(hash, 16777619); }
  return `fnv1a-${(hash >>> 0).toString(16).padStart(8, "0")}`;
}

async function fingerprintPacket(packet) {
  const source = JSON.stringify({ dataset_version: packet.dataset_version || "unknown", cases: packet.cases });
  if (window.crypto?.subtle && window.TextEncoder) {
    const digest = await window.crypto.subtle.digest("SHA-256", new TextEncoder().encode(source));
    return `sha256-${Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("")}`;
  }
  return fallbackFingerprint(source);
}

function sanitizeDecisions(decisions, cases) {
  const validIds = new Set(cases.map((item) => item.case_id));
  return Object.fromEntries(Object.entries(decisions || {}).filter(([caseId, value]) => validIds.has(caseId) && REVIEW_DECISIONS.has(value?.decision)).map(([caseId, value]) => [caseId, { decision: value.decision, notes: typeof value.notes === "string" ? value.notes : "", reviewed_at: typeof value.reviewed_at === "string" ? value.reviewed_at : new Date().toISOString() }]));
}

function persistDecisions() {
  if (!reviewState.packet || !reviewState.packetFingerprint) return true;
  const payload = { schema_version: REVIEW_SCHEMA_VERSION, packet_fingerprint: reviewState.packetFingerprint, source_packet: reviewState.packet.dataset_version || "unknown", saved_at: new Date().toISOString(), decisions: reviewState.decisions };
  try {
    window.localStorage.setItem(REVIEW_STORAGE_KEY, JSON.stringify(payload));
    reviewState.savedState = payload;
    reviewState.storageAvailable = true;
    setStorageStatus("Saved locally in this browser. Export remains the portable backup.");
    return true;
  } catch (error) {
    reviewState.storageAvailable = false;
    setStorageStatus(`Could not save locally. Export your decisions now. (${error.message})`, true);
    return false;
  }
}

function clearSavedDecisions() {
  try {
    window.localStorage.removeItem(REVIEW_STORAGE_KEY);
    reviewState.savedState = null;
    reviewState.storageAvailable = true;
    setStorageStatus("Saved decisions cleared from this browser.");
  } catch (error) {
    reviewState.storageAvailable = false;
    setStorageStatus(`Could not clear browser storage. (${error.message})`, true);
  }
}

function updateReviewProgress() {
  const cases = reviewState.packet?.cases || [];
  const reviewed = cases.filter((item) => reviewState.decisions[item.case_id]?.decision && reviewState.decisions[item.case_id].decision !== "pending").length;
  const pending = Math.max(0, cases.length - reviewed);
  const ambiguous = cases.filter((item) => reviewState.decisions[item.case_id]?.decision === "ambiguous").length;
  const percent = cases.length ? Math.round((reviewed / cases.length) * 100) : 0;
  reviewText("review-total", cases.length);
  reviewText("reviewed-count", reviewed);
  reviewText("pending-count", pending);
  reviewText("ambiguous-count", ambiguous);
  reviewText("review-progress-label", `${percent}%`);
  const bar = review$("review-progress-bar");
  if (bar) bar.style.width = `${percent}%`;
  const exportButton = review$("export-review");
  if (exportButton) exportButton.disabled = cases.length === 0;
}

function renderReviewCase() {
  const cases = reviewState.packet?.cases || [];
  const item = cases[reviewState.index];
  if (!item) return;
  reviewText("case-position", `Case ${reviewState.index + 1} of ${cases.length}`);
  reviewText("case-id", item.case_id);
  reviewText("case-label", `${item.category} · ${item.split} · ${item.answerability}`);
  reviewText("case-title", `${item.difficulty} investigation`);
  reviewText("case-question", item.question);
  reviewText("review-rationale", item.review_rationale);
  const renderRecords = (id, records, empty) => {
    const target = review$(id);
    target.replaceChildren();
    if (!records?.length) { const note = document.createElement("p"); note.className = "empty-note"; note.textContent = empty; target.append(note); return; }
    for (const record of records) {
      const article = document.createElement("article"); article.className = "review-evidence";
      const heading = document.createElement("strong"); heading.textContent = `${record.document_id} · ${record.title || "Source"}`;
      const excerpt = document.createElement("p"); excerpt.textContent = record.excerpt || "No excerpt supplied.";
      article.append(heading, excerpt); target.append(article);
    }
  };
  renderRecords("expected-evidence", item.expected_evidence, "No expected evidence. Review whether abstention is justified.");
  renderRecords("distractors", item.potential_distractors, "No distractors listed.");
  const decision = reviewState.decisions[item.case_id] || { decision: "pending", notes: "" };
  review$("decision").value = decision.decision;
  review$("review-notes").value = decision.notes;
  review$("previous-case").disabled = reviewState.index === 0;
  review$("next-case").disabled = reviewState.index === cases.length - 1;
}

function persistCurrentDraft(showStatus = false) {
  const item = reviewState.packet?.cases?.[reviewState.index];
  if (!item) return;
  reviewState.decisions[item.case_id] = { decision: review$("decision").value, notes: review$("review-notes").value.trim(), reviewed_at: new Date().toISOString() };
  updateReviewProgress();
  const saved = persistDecisions();
  if (showStatus) reviewText("review-status", saved ? "Decision saved locally." : "Decision is only in memory. Export it before leaving.");
}

function saveDecision() { persistCurrentDraft(true); }

function resetReview() {
  if (!reviewState.packet) return;
  if (!window.confirm("Clear all saved decisions for this review packet? This cannot be undone unless you have an export.")) return;
  reviewState.decisions = {};
  clearSavedDecisions();
  updateReviewProgress();
  renderReviewCase();
  reviewText("review-status", "All decisions were reset. No cases are marked complete.");
}

function exportDecisions() {
  const packetCases = reviewState.packet?.cases || [];
  if (!packetCases.length) return;
  const complete = packetCases.every((item) => reviewState.decisions[item.case_id]?.decision && reviewState.decisions[item.case_id].decision !== "pending");
  const payload = { schema_version: REVIEW_SCHEMA_VERSION, packet_fingerprint: reviewState.packetFingerprint, source_packet: reviewState.packet.dataset_version || "unknown", independent_human_reviewed: false, review_status: complete ? "reviewer_decisions_recorded" : "incomplete", exported_at: new Date().toISOString(), decisions: reviewState.decisions };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const link = document.createElement("a"); link.href = URL.createObjectURL(blob); link.download = "aegis-ground-truth-review-decisions.json"; link.click(); URL.revokeObjectURL(link.href);
  reviewText("review-status", complete ? "Complete decision export created." : "Partial decision export created.");
}

async function importPacket(file) {
  const packet = JSON.parse(await file.text());
  if (!Array.isArray(packet.cases) || !packet.cases.length) throw new Error("The packet contains no review cases.");
  const fingerprint = await fingerprintPacket(packet);
  const hasCurrentDecisions = Object.keys(reviewState.decisions).length > 0;
  if (hasCurrentDecisions && !window.confirm("Replace the current review packet and decisions? Export your work first if needed.")) return;
  reviewState.packet = packet;
  reviewState.packetFingerprint = fingerprint;
  reviewState.index = 0;
  const saved = reviewState.savedState || readSavedState();
  if (saved?.packet_fingerprint === fingerprint) {
    reviewState.decisions = sanitizeDecisions(saved.decisions, packet.cases);
    setStorageStatus("Matching saved decisions restored from this browser.");
    reviewText("review-status", `${Object.keys(reviewState.decisions).length} saved decisions restored.`);
  } else {
    reviewState.decisions = {};
    if (saved?.decisions && Object.keys(saved.decisions).length) setStorageStatus("Saved decisions belong to a different packet and were not applied.", true);
    reviewText("review-status", `${packet.cases.length} cases loaded. No decisions were applied.`);
  }
  review$("review-workspace").hidden = false;
  review$("review-empty-state").hidden = true;
  updateReviewProgress();
  renderReviewCase();
}

async function importDecisions(file) {
  if (!reviewState.packet) throw new Error("Load the matching review packet before importing decisions.");
  const payload = JSON.parse(await file.text());
  if (payload.schema_version !== REVIEW_SCHEMA_VERSION || typeof payload.packet_fingerprint !== "string") throw new Error("This decision file is missing a compatible packet fingerprint.");
  if (payload.packet_fingerprint !== reviewState.packetFingerprint) throw new Error("This decision file belongs to a different review packet and was not applied.");
  if (Object.keys(reviewState.decisions).length && !window.confirm("Replace the current decisions with this exported file?")) return;
  reviewState.decisions = sanitizeDecisions(payload.decisions, reviewState.packet.cases);
  persistDecisions();
  updateReviewProgress();
  renderReviewCase();
  reviewText("review-status", `${Object.keys(reviewState.decisions).length} exported decisions imported and saved locally.`);
}

reviewState.savedState = readSavedState();
review$("packet-file").addEventListener("change", async (event) => {
  const file = event.target.files?.[0]; if (!file) return;
  try { await importPacket(file); } catch (error) { reviewText("review-status", `Could not load packet: ${error.message}`); }
});
review$("decisions-file").addEventListener("change", async (event) => {
  const file = event.target.files?.[0]; if (!file) return;
  try { await importDecisions(file); } catch (error) { reviewText("review-status", `Could not import decisions: ${error.message}`); }
});
review$("previous-case").addEventListener("click", () => { if (reviewState.index > 0) { reviewState.index -= 1; renderReviewCase(); } });
review$("next-case").addEventListener("click", () => { if (reviewState.index < reviewState.packet.cases.length - 1) { reviewState.index += 1; renderReviewCase(); } });
review$("save-decision").addEventListener("click", saveDecision);
review$("decision").addEventListener("change", () => persistCurrentDraft(false));
review$("review-notes").addEventListener("input", () => persistCurrentDraft(false));
review$("reset-review").addEventListener("click", resetReview);
review$("export-review").addEventListener("click", exportDecisions);
