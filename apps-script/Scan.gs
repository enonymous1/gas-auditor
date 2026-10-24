/**
 * Scan.gs -- the two server functions the browser drives.
 *
 * Why stateless chunks: a full scan is N projects x ~4 API calls and can
 * exceed Apps Script's 6-minute per-execution limit. So the server keeps
 * NO scan state at all:
 *
 *   1. startScan()      -> discovery only; returns the Drive metadata list.
 *   2. auditChunk(list) -> audits the slice the browser sends (CONFIG
 *      .CHUNK_SIZE projects), returns finished rows.
 *
 * The browser loops auditChunk() until the list is exhausted, holds all
 * rows, and renders/downloads them client-side. Closing the page ends
 * the scan -- acceptable for an on-demand tool, and it means this app
 * stores nothing about anyone, anywhere. (Persistence -- e.g. writing
 * results to the user's own Drive -- is a deliberate later addition,
 * and it would need an extra Drive scope in the manifest.)
 */

/**
 * Discovery, plus any caller-supplied seed IDs merged in by direct
 * files.get -- container-bound projects are invisible to Drive listing,
 * so the browser passes the IDs the user pasted (they persist in the
 * page's localStorage). Unfetchable seeds are skipped, never fatal.
 */
function startScan(seedIds) {
  var projects = driveListScriptFiles_();
  var seen = {};
  projects.forEach(function (f) { seen[f.id] = true; });
  (seedIds || []).forEach(function (id) {
    if (!id || seen[id]) return;
    var meta = driveGetFile_(id);
    if (meta) {
      meta._seeded = true;
      projects.push(meta);
      seen[id] = true;
    }
  });
  return {
    user: safeUserEmail_(),
    projects: projects
  };
}

/** Audit one browser-supplied slice of Drive files; returns audit rows. */
function auditChunk(driveFiles) {
  return (driveFiles || []).map(function (f) { return auditProject_(f); });
}

function safeUserEmail_() {
  try {
    return Session.getActiveUser().getEmail() || '';
  } catch (e) {
    return ''; // not available in every deployment context; purely cosmetic
  }
}
