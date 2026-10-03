const form = document.querySelector("#intake-form");
const fileInput = document.querySelector("#receipt-file");
const submitButton = document.querySelector("#submit-button");
const result = document.querySelector("#result");
const extractForm = document.querySelector("#extract-form");
const evidenceInput = document.querySelector("#evidence-id");
const extractButton = document.querySelector("#extract-button");
const extractionResult = document.querySelector("#extraction-result");

fileInput.addEventListener("change", () => {
  clearResult(result);
});

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const selected = fileInput.files && fileInput.files[0];
  if (!selected) {
    showRejected(result, "Upload rejected", "Choose a receipt image before submitting.");
    return;
  }
  submitReceipt(selected);
});

extractForm.addEventListener("submit", (event) => {
  event.preventDefault();
  extractEvidence(evidenceInput.value);
});

async function submitReceipt(file) {
  submitButton.disabled = true;
  showPending(result, "Preserving receipt…");
  const body = new FormData();
  body.append("file", file, file.name);
  try {
    const response = await fetch("/api/receipts", { method: "POST", body });
    const payload = await readJson(response);
    if (response.ok && payload && payload.status === "accepted") {
      showAccepted(payload);
      return;
    }
    const reason = payload && payload.reason
      ? payload.reason
      : "The upload could not be processed.";
    showRejected(result, "Upload rejected", reason);
  } catch (_error) {
    showRejected(result, "Upload rejected", "The upload could not be processed.");
  } finally {
    submitButton.disabled = false;
  }
}

async function extractEvidence(evidenceId) {
  const id = String(evidenceId || "").trim();
  evidenceInput.value = id;
  if (!id) {
    showRejected(extractionResult, "Extraction failed", "Enter an evidence ID.");
    return;
  }
  extractButton.disabled = true;
  showPending(extractionResult, "Reading preserved receipt…");
  try {
    const response = await fetch(`/api/receipts/${encodeURIComponent(id)}/extraction`, {
      method: "POST",
    });
    const payload = await readJson(response);
    if (payload && payload.extraction_id) {
      showExtraction(payload);
      return;
    }
    const reason = payload && payload.reason
      ? payload.reason
      : "The receipt could not be read.";
    showRejected(extractionResult, "Extraction failed", reason);
  } catch (_error) {
    showRejected(extractionResult, "Extraction failed", "The receipt could not be read.");
  } finally {
    extractButton.disabled = false;
  }
}

async function readJson(response) {
  try {
    return await response.json();
  } catch (_error) {
    return null;
  }
}

function clearResult(container) {
  container.dataset.state = "";
  container.replaceChildren();
}

function showPending(container, message) {
  container.dataset.state = "pending";
  container.replaceChildren();
  const title = document.createElement("p");
  title.className = "result-title";
  title.textContent = message;
  container.appendChild(title);
}

function showRejected(container, titleText, reason) {
  container.dataset.state = "rejected";
  container.replaceChildren();
  const title = document.createElement("p");
  title.className = "result-title";
  title.textContent = titleText;
  const detail = document.createElement("p");
  detail.className = "result-detail";
  detail.textContent = reason;
  container.append(title, detail);
}

function showAccepted(payload) {
  result.dataset.state = "accepted";
  result.replaceChildren();
  const title = document.createElement("p");
  title.className = "result-title";
  title.textContent = "Upload accepted";
  const list = document.createElement("dl");
  addField(list, "Evidence ID", payload.evidence_id);
  addField(list, "Original filename", payload.original_filename);
  addField(list, "MIME type", payload.mime_type);
  addField(list, "File size", formatBytes(payload.byte_size));
  const extract = document.createElement("button");
  extract.type = "button";
  extract.textContent = "Extract this receipt";
  extract.addEventListener("click", () => {
    extractEvidence(payload.evidence_id);
  });
  result.append(title, list, extract);
}

function showExtraction(payload) {
  const status = payload.extraction_status;
  if (status === "failed") {
    showRejected(
      extractionResult,
      "Extraction failed",
      payload.failure_reason || "The receipt could not be read.",
    );
    return;
  }
  extractionResult.dataset.state = status === "extracted" ? "accepted" : "empty";
  extractionResult.replaceChildren();
  const title = document.createElement("p");
  title.className = "result-title";
  title.textContent = extractionTitle(status);
  const list = document.createElement("dl");
  addField(list, "Evidence ID", payload.evidence_id);
  addField(list, "Merchant candidate", payload.merchant_normalized_candidate);
  addField(list, "Merchant raw", payload.merchant_raw);
  addField(list, "Date candidate", payload.purchase_date_candidate);
  addField(list, "Time candidate", payload.purchase_time_candidate);
  addField(list, "Subtotal candidate", payload.subtotal_candidate);
  addField(list, "Tax candidate", payload.tax_candidate);
  addField(list, "Total candidate", payload.total_candidate);
  extractionResult.append(title, list);

  const lines = Array.isArray(payload.lines) ? payload.lines : [];
  if (lines.length) {
    const lineList = document.createElement("div");
    lineList.className = "line-list";
    lines.forEach((line) => {
      lineList.appendChild(renderLine(line));
    });
    extractionResult.appendChild(lineList);
  }

  if (payload.raw_text) {
    const rawHeading = document.createElement("h3");
    rawHeading.textContent = "Raw receipt text";
    const raw = document.createElement("p");
    raw.className = "raw-text";
    raw.textContent = payload.raw_text;
    extractionResult.append(rawHeading, raw);
  }
}

function extractionTitle(status) {
  if (status === "no_text") {
    return "No text detected";
  }
  if (status === "insufficient_data") {
    return "Not enough receipt text";
  }
  return "Extraction candidate";
}

function renderLine(line) {
  const card = document.createElement("article");
  card.className = "line-card";
  const heading = document.createElement("h3");
  heading.textContent = `Item ${line.line_order}`;
  const list = document.createElement("dl");
  addField(list, "Raw text", line.raw_text);
  addField(list, "Normalized candidate", line.normalized_name_candidate);
  addField(list, "Quantity candidate", line.quantity_candidate);
  addField(list, "Unit price candidate", line.unit_price_candidate);
  addField(list, "Line total candidate", line.line_total_candidate);
  card.append(heading, list);
  return card;
}

function addField(list, label, value) {
  const term = document.createElement("dt");
  term.textContent = label;
  const description = document.createElement("dd");
  description.textContent = value == null || value === "" ? "Unknown" : String(value);
  list.append(term, description);
}

function formatBytes(byteSize) {
  const size = Number(byteSize);
  if (!Number.isFinite(size)) {
    return "";
  }
  const exact = `${new Intl.NumberFormat("en-US").format(size)} bytes`;
  if (size < 1024) {
    return exact;
  }
  const megabytes = size / (1024 * 1024);
  if (megabytes >= 1) {
    return `${megabytes.toFixed(2)} MB (${exact})`;
  }
  return `${(size / 1024).toFixed(1)} KB (${exact})`;
}

window.submitReceipt = submitReceipt;
window.extractEvidence = extractEvidence;
