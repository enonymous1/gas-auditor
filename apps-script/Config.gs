/**
 * Config.gs -- constants for the Apps Script-native GAS auditor.
 *
 * Architecture in one paragraph: this project is deployed as a web app
 * with "Execute as: User accessing", so every API call below runs with
 * the *viewer's* own OAuth token (ScriptApp.getOAuthToken()) and the
 * scopes declared in appsscript.json. There is no server-side credential
 * or result storage: the browser drives the scan in chunks
 * (see Scan.gs / JavaScript.html) and holds the results.
 */

var CONFIG = {
  DRIVE_API_BASE: 'https://www.googleapis.com/drive/v3',
  SCRIPT_API_BASE: 'https://script.googleapis.com/v1',
  SCRIPT_MIMETYPE: 'application/vnd.google-apps.script',

  // projects.getMetrics requires a granularity: 'DAILY' (~7 days) or 'WEEKLY'.
  METRICS_GRANULARITY: 'WEEKLY',

  // Recent processes sampled per project via processes:listScriptProcesses.
  PROCESS_LIMIT: 50,

  // Projects audited per google.script.run chunk call. Each project is
  // ~4 API calls; 8 projects keeps a chunk comfortably inside Apps
  // Script's 6-minute execution limit while still feeling responsive.
  CHUNK_SIZE: 8
};
