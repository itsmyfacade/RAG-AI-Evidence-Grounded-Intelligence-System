from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_frontend_exposes_the_investigation_console_structure() -> None:
    markup = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    for required_id in ("filter", "sample-count", "scenario", "question", "question-note", "run", "action-readiness", "action-message", "readiness", "empty-state", "empty-title", "empty-description", "execution-indicator", "execution-label", "execution-detail", "execution-action", "report", "findings", "operations", "uncertainty", "trace", "evidence", "view-investigate", "view-scenarios", "view-execution", "view-validation", "benchmark-provenance", "benchmark-scope", "benchmark-interpretation", "benchmark-abstention", "benchmark-overview", "benchmark-comparison", "benchmark-categories", "catalog-filter", "scenario-catalog", "execution-view-trace", "workspace-subtitle"):
        assert f'id="{required_id}"' in markup
    for required_class in ("app-frame", "nav-rail", "command-area", "analysis-layout", "operational-panel", "decision-panel", "detail-region"):
        assert required_class in markup
    assert 'class="wordmark"' in markup
    assert '<svg class="brand-mark"' not in markup
    assert "mark-shield" not in markup
    assert "Investigation in progress" not in markup
    assert "Workflow timeline" in markup
    assert markup.count('class="workspace-view"') + markup.count('class="workspace-view ') == 4
    assert 'data-nav="investigate"' in markup
    assert 'data-nav="scenarios"' in markup
    assert 'data-nav="execution"' in markup
    assert 'id="status-badge"' in markup


def test_frontend_layout_is_fluid_and_question_field_is_readable() -> None:
    styles = (ROOT / "frontend" / "styles.css").read_text(encoding="utf-8")
    assert "max-width: 1500px" not in styles
    assert "grid-template-columns: 82px minmax(0, 1fr)" in styles
    assert ".analysis-layout" in styles
    assert ".nav-rail" in styles
    assert "width: 100%" in styles
    assert "textarea { min-height: 120px" in styles
    assert "overflow-y: auto" in styles
    assert "prefers-reduced-motion" in styles
    assert ".execution-indicator" in styles
    assert ".wordmark-main" in styles
    assert ".loading-state" not in styles
    assert "writing-mode" not in styles
    assert ".nav-rail-label" in styles
    assert ".wordmark-rule { width: 1px" in styles
    assert ".workspace-view[hidden]" in styles
    assert ".scenario-catalog" in styles
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in styles
    assert ".composer-action" in styles
    assert ".action-readiness" in styles
    assert "border: 0" in styles
    assert ".action-readiness p { margin: 0" in styles
    assert "max-width: 38ch" not in styles
    assert "[hidden] { display: none !important; }" in styles
    assert "@media (max-width: 900px)" in styles
    assert ".evidence-group" in styles
    assert ".evidence-group-heading" in styles
    assert ".evidence-group > summary" in styles
    assert ".analysis-layout { align-items: start; }" in styles


def test_frontend_rendering_contract_handles_real_api_states() -> None:
    script = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    for token in ("loadReadiness", "renderReport", "renderFindings", "renderEvidence", "renderTrace", "renderScenarioCatalog", "selectScenario", "setLifecycle", "AbortController", "readResponse", "friendlyError", "navigate", "setDetail", "invalidateReport", "workspace-subtitle", "stageLabels", "trace-topline"):
        assert token in script
    assert "renderEmptyState" in script
    assert "Ready to investigate" in script
    assert "report.provider" in script
    assert "report.retrieval_mode" in script
    assert "report.evidence" in script
    assert "report.evidence_gaps" in script
    for lifecycle in ("idle", "ready", "running", "completed", "failed"):
        assert f'"{lifecycle}"' in script
    assert "scenarioId" in script
    assert "activeView" in script
    assert "activeRequestId" in script
    assert "workspace-view" in script
    assert "state.report = null" in script
    assert "renderTrace(report.agent_trace || data.agent_trace" in script
    assert "scrollIntoView" not in script
    assert "setLifecycle(\"completed\")" in script
    assert "action-readiness" in script
    assert "evidence-group" in script
    assert 'document.createElement("details")' in script
    assert "No additional evidence gaps or contradictions were reported." in script
    assert 'show("empty-state", lifecycle === "failed")' in script
    assert 'show("execution-indicator", ["running", "completed", "failed"].includes(lifecycle))' in script


def test_frontend_navigation_preserves_root_and_render_mounts() -> None:
    index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    review = (ROOT / "frontend" / "review.html").read_text(encoding="utf-8")
    assert 'href="./"' in index
    assert review.count('href="./"') == 2
    assert 'href="/demo/"' not in index
    assert 'href="/demo/"' not in review


def test_model_output_review_is_separate_and_blinded() -> None:
    markup = (ROOT / "frontend" / "model-review.html").read_text(encoding="utf-8")
    script = (ROOT / "frontend" / "model-review.js").read_text(encoding="utf-8")
    assert 'src="model-review.js"' in markup
    assert 'src="fingerprint.js"' in markup
    assert "aegis-phase3-fingerprint-v3" in script
    for required_id in ("model-packet-file", "model-decisions-file", "model-review-workspace", "model-answer", "model-evidence", "model-overall-decision", "model-review-notes", "model-export-review"):
        assert f'id="{required_id}"' in markup
    assert "aegis-phase3-model-output-review-packet-v1" in script
    assert "aegis-model-output-review-state-v1" in script
    assert "blinded_initial_judgment" in script
    assert "localStorage" in script
    assert "expected_evidence" not in markup
    assert "expected_citation_ids" not in markup
