# Job Search Assistant — Capture (Chrome extension)

One-click "manual paste, but a button": while you're looking at a job
posting, click the extension icon and it sends the visible page text to
your local Job Search Assistant, which runs the exact same LLM extraction
and ingest pipeline as `ingest paste` / the web UI's paste form.

**Non-goals, by construction, not just policy:**
- No `host_permissions` in the manifest — the extension only gets read
  access to the page you're viewing, and only *after* you click the icon
  (`activeTab`). It cannot run on a schedule or in the background.
- No login, no navigation, no reading any tab other than the one you're on.
- No fetch of the job's URL — the URL is sent as a label only (same as
  every other ingestion path in this app), never fetched by the extension
  or the server.
- Selectors are a nicety, not the source of truth: if LinkedIn's DOM
  doesn't match the selectors in `popup.js`, the extension falls back to
  the full visible page text and lets the server's LLM extraction (the
  same one used for manual paste) parse it.

## Install (load unpacked)

1. Start the local app: `python -m web.app` (from the repo root) —
   see the main `CLAUDE.md` for the exact command and port.
2. In Chrome, go to `chrome://extensions`, enable **Developer mode** (top
   right), click **Load unpacked**, and select this `extension/` folder.
3. Pin the extension (puzzle-piece icon in the toolbar → pin).
4. Click the extension icon once — the popup's "Job Search Assistant URL"
   field defaults to `http://localhost:8000`. Change it if your app runs
   elsewhere (e.g. a Codespaces forwarded URL) — it's saved automatically.

## Manual test checklist

- [ ] Open a real LinkedIn job posting, click the extension, click
      **Capture this job** → popup shows `Captured as job <id> — score N.`
      and the job appears in the web UI / `list` CLI output.
- [ ] Click **Capture this job** again on the *same* posting → popup shows
      `Already captured as job <id> — nothing added.` (duplicate detection).
- [ ] Open a non-LinkedIn page (e.g. any article) and capture it → the
      fallback (full page text) is sent; extraction may produce odd
      fields, which is expected — it went through the same pipeline as a
      bad manual paste would.
- [ ] With the local app **not** running, capture a job → popup shows a
      clear `Error: ...` message, and nothing is left half-created.
- [ ] Confirm in the web UI / `show <job_id>` that the job's source shows
      it came from the extension, distinct from a manual paste.
- [ ] Close the browser entirely for a while — confirm nothing fires on
      its own (no background captures happen without clicking the icon).
