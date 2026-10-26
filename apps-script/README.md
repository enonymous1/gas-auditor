# GAS Auditor — Apps Script-native dashboard (prototype 0.1)

The same audit as the Python package, implemented *as* a Google Apps Script
project and deployed as a web app. It runs **as the person viewing it**
("Execute as: User accessing"), so:

- No credentials to store, ever — Google issues each viewer's own token
  for the scopes in `appsscript.json`; the app never sees a refresh token.
- No data stored anywhere — the scan is stateless and client-driven
  (below); results live in the browser tab and can be downloaded as CSV.
- Scope today: **you**. Demo inside your Workspace org later by changing
  the deployment access. Public/"anyone" distribution is a later bridge
  (OAuth verification for these scopes) and is deliberately not crossed here.

## Files

| File | Role |
|---|---|
| `appsscript.json` | Manifest: the 4 read-only audit scopes + `script.external_request` (required for `UrlFetchApp` calls — see "Missing scope" note below), webapp `USER_ACCESSING` / `MYSELF` |
| `Config.gs` | API base URLs, metrics granularity, chunk size |
| `Api.gs` | UrlFetch wrappers: Drive v3 discovery, Script API v1 get/getContent/getMetrics/listScriptProcesses |
| `Audit.gs` | Parsers + per-project audit (ported from the Python modules; row fields identical to Python `AUDIT_FIELDS`) |
| `Scan.gs` | Server endpoints the page drives: `startScan()` (discovery), `auditChunk(slice)` |
| `WebApp.gs` | `doGet()` + template `include()` helper |
| `Index.html` | Page structure |
| `Stylesheet.html` | CSS include |
| `JavaScript.html` | Chunk loop, progressive table render, client-side CSV generation/download |

## How the scan works (and why)

A full scan is N projects × ~4 API calls and can exceed Apps Script's
6-minute per-execution limit, so no single server call does the whole scan:

1. Browser calls `startScan()` → server returns the Drive metadata list.
2. Browser calls `auditChunk()` with 8 projects at a time, appending rows
   and re-rendering after each chunk, until the list is exhausted.
3. **Download CSV** builds the file in the browser (same 41 columns, same
   order as the Python export) — no server storage involved.

Quotas to know: 6 min per execution; UrlFetch ~20,000 calls/day (consumer)
or ~100,000/day (Workspace). One chunk is ~32 calls and a few seconds.

## Container-bound projects (seed IDs)

Same platform rule as the Python version: bound scripts (created from
inside a Sheet/Doc/Slides/Form) are invisible to Drive listing, so this
dashboard can't discover them either. The page has a *Container-bound
projects* panel: paste script IDs (one per line, from each project's
editor URL) and they're merged into every scan by direct fetch. The list
persists in your browser's localStorage only — the app stays stateless
server-side. After a scan, **Download script IDs (.txt)** produces an
editable file of every known project ID in the same format the Python
CLI accepts (`--script-ids-file`), and vice versa.

## Missing scope: `script.external_request` (read this if Scan fails)

If Scan fails with *"Specified permissions are not sufficient to call
UrlFetchApp.fetch. Required permissions:
https://www.googleapis.com/auth/script.external_request"*, the manifest
is missing that scope. It happens because pinning `oauthScopes` in
`appsscript.json` turns off Apps Script's automatic scope detection, and
every Drive/Script API call in this app goes through `UrlFetchApp.fetch`
(`Api.gs`), which requires `script.external_request` in addition to the
data scopes. The fix is the scope's presence in the manifest (it is there
in this repo) plus a redeploy — a `push` alone does not change what the
deployed version serves — followed by re-authorization on first open
(if no prompt appears, revoke the app at
myaccount.google.com/permissions and reopen it). The Python tool is
unaffected: it calls the same APIs directly with OAuth tokens, not via
`UrlFetchApp`.

## Deploy (manual, ~5 minutes)

1. Go to https://script.google.com → **New project**.
2. For each `.gs` file here: create a script file with the same name in the
   editor (rename `Code.gs`, then ＋ → Script / HTML) and paste the contents.
   Create the three `.html` files as HTML files with the same names.
   (Or use clasp: `clasp create --type webapp --title "GAS Auditor"`, put
   these files in the project folder as `.js`/`.html`, `clasp push`.)
3. **Project Settings** → check **Show "appsscript.json" manifest file in
   editor**, then replace the editor's `appsscript.json` with this one.
4. **Deploy → New deployment → Web app**:
   - Execute as: **User accessing the web app**
   - Who has access: **Only myself**
5. Open the web app URL. First visit asks you to authorize the scopes —
   the 4 read-only data scopes plus `script.external_request` (the
   permission for `UrlFetchApp` to call Google's APIs; it grants no data
   access by itself) — because the project runs on Apps Script's default
   Cloud project,
   you may see an "unverified app" notice for your own project; that's the
   personal-use path (Advanced → proceed). It is *not* the public-launch
   verification, which only enters the picture at "anyone" access.

Iterating later: **Deploy → Manage deployments → edit → New version** —
the URL stays the same.

## Later bridges (deliberately not crossed yet)

- **Demo to your Workspace org:** change deployment access to your domain.
  For a warning-free experience, associate the script with a *standard*
  Google Cloud project whose OAuth consent screen is **Internal** — then
  no verification and no 7-day token expiry for org users.
- **Public / "anyone":** external consent screen + OAuth verification for
  the audit scopes (privacy policy, homepage, possibly a security
  assessment for Drive-class scopes). That's the Firebase discussion from
  the main README, revisited — at that point compare honestly against the
  Cloud Run design; Apps Script stops being the cheap option there.
- **Persistence** (saved scan history, scheduled rescans, a Sheet export):
  each needs an added scope (Drive/Sheets) and a storage decision. The
  natural home is the *user's own* Drive, so the app still holds nothing.

## Tests

The `.gs` logic is tested in Node against the same fixture payloads as the
Python suite (stubbed `UrlFetchApp`/`ScriptApp`):

```bash
node tests-gas/test_audit.js   # from the gas-auditor project root
```
