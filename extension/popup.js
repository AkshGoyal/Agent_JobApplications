"use strict";

const DEFAULT_BASE_URL = "http://localhost:8000";

const baseUrlInput = document.getElementById("base-url");
const captureBtn = document.getElementById("capture-btn");
const statusEl = document.getElementById("status");

function setStatus(text, cls) {
  statusEl.textContent = text || "";
  statusEl.className = cls || "";
}

chrome.storage.local.get(["baseUrl"], (stored) => {
  baseUrlInput.value = stored.baseUrl || DEFAULT_BASE_URL;
});

baseUrlInput.addEventListener("change", () => {
  chrome.storage.local.set({ baseUrl: baseUrlInput.value.trim() || DEFAULT_BASE_URL });
});

// Injected into the active tab by chrome.scripting.executeScript — runs only
// on the page the user is currently viewing, only when they click Capture.
// Selectors are a nicety for LinkedIn's current DOM; if the page has changed
// or this isn't a LinkedIn job page at all, we fall back to the full visible
// text and let the server-side LLM extraction (the same one manual paste
// uses) figure out the fields. Selectors are never treated as ground truth.
function extractVisibleJobText() {
  const trySelectors = (selectors) => {
    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el && el.innerText && el.innerText.trim()) return el.innerText.trim();
    }
    return null;
  };

  const title = trySelectors([
    "h1.job-details-jobs-unified-top-card__job-title",
    ".jobs-unified-top-card__job-title",
    "h1",
  ]);
  const company = trySelectors([
    ".job-details-jobs-unified-top-card__company-name",
    ".jobs-unified-top-card__company-name",
  ]);
  const description = trySelectors([
    "#job-details",
    ".jobs-description__content",
    ".jobs-box__html-content",
  ]);

  if (description) {
    const parts = [title, company, description].filter(Boolean);
    return parts.join("\n\n");
  }
  // Selectors missed (DOM changed, or not a LinkedIn job page) — send the
  // full visible text and let extraction do the work, same as pasting it
  // by hand would.
  return document.body.innerText;
}

captureBtn.addEventListener("click", async () => {
  captureBtn.disabled = true;
  setStatus("Reading the page…");
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !tab.id) throw new Error("no active tab");

    const [{ result: jdText }] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: extractVisibleJobText,
    });
    if (!jdText || !jdText.trim()) {
      throw new Error("couldn't read any text from this page");
    }

    const baseUrl = (baseUrlInput.value.trim() || DEFAULT_BASE_URL).replace(/\/+$/, "");
    setStatus("Sending to your local assistant…");
    const res = await fetch(`${baseUrl}/api/ingest/capture`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: tab.url, jd_text: jdText, rank: true }),
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.detail || res.statusText);

    if (body.duplicate) {
      setStatus(`Already captured as job ${body.job_id} — nothing added.`, "warn");
    } else if (body.warning) {
      setStatus(`Captured as job ${body.job_id}. ${body.warning}`, "warn");
    } else {
      const score = body.job && body.job.relevance_score;
      setStatus(
        `Captured as job ${body.job_id}` + (score != null ? ` — score ${score}.` : "."),
        "ok"
      );
    }
  } catch (err) {
    setStatus("Error: " + err.message, "err");
  } finally {
    captureBtn.disabled = false;
  }
});
