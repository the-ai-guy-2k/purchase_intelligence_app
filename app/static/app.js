const form = document.querySelector("#intake-form");
const fileInput = document.querySelector("#receipt-file");
const submitButton = document.querySelector("#submit-button");
const result = document.querySelector("#result");

fileInput.addEventListener("change", () => {
  clearResult();
});

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const selected = fileInput.files && fileInput.files[0];
  if (!selected) {
    showRejected("Choose a receipt image before submitting.");
    return;
  }
  submitReceipt(selected);
});

async function submitReceipt(file) {
  submitButton.disabled = true;
  showPending("Preserving receipt…");
  const body = new FormData();
  body.append("file", file, file.name);
  try {
    const response = await fetch("/api/receipts", { method: "POST", body });
    let payload = null;
    try {
      payload = await response.json();
    } catch (_error) {
      showRejected("The upload could not be processed.");
      return;
    }
    if (response.ok && payload && payload.status === "accepted") {
      showAccepted(payload);
      return;
    }
    const reason = payload && payload.reason
      ? payload.reason
      : "The upload could not be processed.";
    showRejected(reason);
  } catch (_error) {
    showRejected("The upload could not be processed.");
  } finally {
    submitButton.disabled = false;
  }
}

function clearResult() {
  result.dataset.state = "";
  result.replaceChildren();
}

function showPending(message) {
  result.dataset.state = "pending";
  result.replaceChildren();
  const title = document.createElement("p");
  title.className = "result-title";
  title.textContent = message;
  result.appendChild(title);
}

function showRejected(reason) {
  result.dataset.state = "rejected";
  result.replaceChildren();
  const title = document.createElement("p");
  title.className = "result-title";
  title.textContent = "Upload rejected";
  const detail = document.createElement("p");
  detail.className = "result-detail";
  detail.textContent = reason;
  result.append(title, detail);
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
  result.append(title, list);
}

function addField(list, label, value) {
  const term = document.createElement("dt");
  term.textContent = label;
  const description = document.createElement("dd");
  description.textContent = value == null ? "" : String(value);
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
