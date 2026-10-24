/**
 * Api.gs -- thin UrlFetch wrappers over the Drive API v3 and the
 * Apps Script API v1, authenticated with the *accessing user's* token.
 *
 * Every function returns parsed JSON and throws an Error carrying the
 * HTTP status on failure; Audit.gs catches per stage so one bad project
 * never aborts the scan (same contract as the Python version).
 */

function apiGet_(url) {
  // Retry 429/5xx with exponential backoff: the Apps Script API enforces
  // per-minute per-user quotas and a scan bursts calls (the Python
  // version's first live run lost 4 stages to 429s without this).
  var maxRetries = 4;
  for (var attempt = 0; ; attempt++) {
    var resp = UrlFetchApp.fetch(url, {
      method: 'get',
      headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() },
      muteHttpExceptions: true
    });
    var code = resp.getResponseCode();
    var text = resp.getContentText();
    if (code >= 200 && code < 300) {
      return text ? JSON.parse(text) : {};
    }
    var retryable = code === 429 || (code >= 500 && code < 600);
    if (!retryable || attempt >= maxRetries) {
      throw new Error('HttpError ' + code + ': ' + text.slice(0, 300));
    }
    var delayMs = Math.min(2000 * Math.pow(2, attempt), 30000);
    if (typeof Utilities !== 'undefined') Utilities.sleep(delayMs);
  }
}

function encodeParams_(params) {
  return Object.keys(params)
    .map(function (k) { return encodeURIComponent(k) + '=' + encodeURIComponent(params[k]); })
    .join('&');
}

/** Page Drive files.list for every Apps Script project (trashed excluded). */
function driveListScriptFiles_() {
  var q = "mimeType = '" + CONFIG.SCRIPT_MIMETYPE + "' and trashed = false";
  var fields = 'nextPageToken,files(id,name,mimeType,createdTime,modifiedTime,' +
    'webViewLink,parents,owners(emailAddress),lastModifyingUser(emailAddress))';
  var files = [];
  var pageToken = null;
  do {
    var params = {
      q: q, fields: fields, pageSize: 1000, orderBy: 'modifiedTime desc'
    };
    if (pageToken) params.pageToken = pageToken;
    var resp = apiGet_(CONFIG.DRIVE_API_BASE + '/files?' + encodeParams_(params));
    files = files.concat(resp.files || []);
    pageToken = resp.nextPageToken || null;
  } while (pageToken);
  return files;
}

/**
 * files.get for ONE file ID. This is the only way to reach container-
 * bound scripts: Google hides them from Drive listing ("bound scripts do
 * not appear in Google Drive"), but a known scriptId fetches fine.
 * Returns null when the file can't be fetched.
 */
function driveGetFile_(fileId) {
  var fields = 'id,name,mimeType,createdTime,modifiedTime,description,' +
    'webViewLink,parents,owners(emailAddress),lastModifyingUser(emailAddress)';
  try {
    return apiGet_(CONFIG.DRIVE_API_BASE + '/files/' +
      encodeURIComponent(fileId) + '?fields=' + encodeURIComponent(fields));
  } catch (e) {
    return null;
  }
}

/** projects.get -- title, parentId (bound container), creator, timestamps. */
function scriptGetProject_(scriptId) {
  return apiGet_(CONFIG.SCRIPT_API_BASE + '/projects/' + encodeURIComponent(scriptId));
}

/** projects.getContent -- files[] with name/type/source/functionSet. */
function scriptGetContent_(scriptId) {
  return apiGet_(
    CONFIG.SCRIPT_API_BASE + '/projects/' + encodeURIComponent(scriptId) + '/content'
  );
}

/** projects.getMetrics -- metricsGranularity is REQUIRED by the API. */
function scriptGetMetrics_(scriptId) {
  var params = { metricsGranularity: CONFIG.METRICS_GRANULARITY };
  return apiGet_(
    CONFIG.SCRIPT_API_BASE + '/projects/' + encodeURIComponent(scriptId) +
    '/metrics?' + encodeParams_(params)
  );
}

/**
 * processes:listScriptProcesses -- recent executions for one project.
 * NOTE: ':' in the URL path is literal (gRPC transcoding), do not encode it.
 * Returned Process objects use processType / processStatus keys.
 */
function scriptListProcesses_(scriptId, limit) {
  var params = { scriptId: scriptId, pageSize: limit || CONFIG.PROCESS_LIMIT };
  var resp = apiGet_(
    CONFIG.SCRIPT_API_BASE + '/processes:listScriptProcesses?' + encodeParams_(params)
  );
  return resp.processes || [];
}
