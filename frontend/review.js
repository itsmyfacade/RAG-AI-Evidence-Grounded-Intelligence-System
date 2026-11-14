const reviewState = { packet: null, index: 0, decisions: {} };
const review$ = (id) => document.getElementById(id);

function reviewText(id, value) { review$(id).textContent = value || ""; }

function updateReviewProgress() {
  const cases = reviewState.packet?.cases || [];
  const reviewed = cases.filter((item) => {
    const decision = reviewState.decisions[item.case_id]?.decision;
    return decision && decision !== "pending";
  }).length;
  const pending = Math.max(0, cases.length - reviewed);
  const percent = cases.length ? Math.round((reviewed / cases.length) * 100) : 0;
  reviewText("review-total", cases.length);
  reviewText("reviewed-count", reviewed);
  reviewText("pending-count", pending);
  reviewText("review-progress-label", `${percent}%`);
  const bar = review$("review-progress-bar");
  if (bar) bar.style.width = `${percent}%`;
  const exportButton = review$("export-review");
  if (exportButton) {
    exportButton.disabled = cases.length === 0 || pending > 0;
    exportButton.textContent = pending === 0 && cases.length > 0 ? "Export review decisions" : "Export decisions (complete review first)";
  }
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

function saveDecision() {
  const item = reviewState.packet?.cases?.[reviewState.index]; if (!item) return;
  reviewState.decisions[item.case_id] = { decision: review$("decision").value, notes: review$("review-notes").value.trim(), reviewed_at: new Date().toISOString() };
  updateReviewProgress();
  const reviewed = reviewState.packet.cases.filter((entry) => reviewState.decisions[entry.case_id]?.decision && reviewState.decisions[entry.case_id].decision !== "pending").length;
  reviewText("review-status", `${reviewed} of ${reviewState.packet.cases.length} cases have a non-pending decision recorded locally.`);
}

function exportDecisions() {
  const packetCases = reviewState.packet?.cases || [];
  const complete = packetCases.length > 0 && packetCases.every((item) => {
    const decision = reviewState.decisions[item.case_id]?.decision;
    return decision && decision !== "pending";
  });
  const payload = {
    schema_version: "aegis-phase4-review-decisions-v1",
    source_packet: reviewState.packet?.dataset_version || "unknown",
    independent_human_reviewed: false,
    review_status: complete ? "reviewer_decisions_recorded" : "incomplete",
    decisions: reviewState.decisions,
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const link = document.createElement("a"); link.href = URL.createObjectURL(blob); link.download = "aegis-ground-truth-review-decisions.json"; link.click(); URL.revokeObjectURL(link.href);
}

review$("packet-file").addEventListener("change", async (event) => {
  const file = event.target.files?.[0]; if (!file) return;
  try {
    const packet = JSON.parse(await file.text());
    if (!Array.isArray(packet.cases) || !packet.cases.length) throw new Error("The packet contains no review cases.");
    reviewState.packet = packet; reviewState.index = 0; reviewState.decisions = {};
    review$("review-workspace").hidden = false; review$("review-empty-state").hidden = true; updateReviewProgress();
    reviewText("review-status", `${packet.cases.length} cases loaded. No decisions have been recorded.`); renderReviewCase();
  } catch (error) { reviewText("review-status", `Could not load packet: ${error.message}`); }
});
review$("previous-case").addEventListener("click", () => { if (reviewState.index > 0) { reviewState.index -= 1; renderReviewCase(); } });
review$("next-case").addEventListener("click", () => { if (reviewState.index < reviewState.packet.cases.length - 1) { reviewState.index += 1; renderReviewCase(); } });
review$("save-decision").addEventListener("click", saveDecision);
review$("export-review").addEventListener("click", exportDecisions);
