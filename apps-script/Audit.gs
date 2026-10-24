/**
 * Audit.gs -- per-project audit logic, ported from the Python package
 * (content.py / metrics.py / processes.py / audit.py). The summarise*
 * functions are pure (payload in, flat values out) and are unit-tested
 * in Node against the same fixtures as the Python tests
 * (tests-gas/test_audit.js). Row field names match the Python
 * AUDIT_FIELDS exactly, so this dashboard and the CSV/Polars pipeline
 * describe the same data.
 */

/* ---------------- manifest / content (cf. Python content.py) ---------------- */

/**
 * The manifest is the getContent file named 'appsscript' with type 'JSON';
 * its source is a JSON *string*. Advanced services live at
 * dependencies.enabledAdvancedServices (no top-level key).
 */
function parseManifest_(files) {
  var out = {
    oauth_scopes: [],
    advanced_services: [],
    manifest_time_zone: '',
    runtime_version: '',
    has_webapp: false,
    has_execution_api: false
  };
  var manifestFile = null;
  for (var i = 0; i < files.length; i++) {
    if (files[i].name === 'appsscript' && files[i].type === 'JSON') {
      manifestFile = files[i];
      break;
    }
  }
  if (!manifestFile || !manifestFile.source) return out;

  var manifest;
  try {
    manifest = JSON.parse(manifestFile.source);
  } catch (e) {
    return out; // invalid manifest JSON: audit the rest, scopes stay empty
  }

  out.oauth_scopes = manifest.oauthScopes || [];
  out.manifest_time_zone = manifest.timeZone || '';
  out.runtime_version = manifest.runtimeVersion || '';
  out.has_webapp = 'webapp' in manifest;
  out.has_execution_api = 'executionApi' in manifest;

  var deps = manifest.dependencies || {};
  (deps.enabledAdvancedServices || []).forEach(function (svc) {
    var label = svc.userSymbol || svc.serviceId || '?';
    out.advanced_services.push(
      label + ' (serviceId=' + (svc.serviceId || '?') + ', ' + (svc.version || '?') + ')'
    );
  });
  return out;
}

function summariseContent_(content) {
  var files = (content && content.files) || [];
  var counts = {};
  var functions = [];
  var totalChars = 0;

  files.forEach(function (f) {
    var t = f.type || 'UNKNOWN';
    counts[t] = (counts[t] || 0) + 1;
    totalChars += (f.source || '').length;
    var values = (f.functionSet && f.functionSet.values) || [];
    values.forEach(function (fn) { if (fn.name) functions.push(fn.name); });
  });

  var uniqueFunctions = Array.from(new Set(functions)).sort();
  var result = {
    file_count: files.length,
    file_counts_by_type: counts,
    server_js_count: counts.SERVER_JS || 0,
    html_count: counts.HTML || 0,
    json_count: counts.JSON || 0,
    function_count: uniqueFunctions.length,
    function_names: uniqueFunctions,
    total_source_chars: totalChars
  };
  var manifest = parseManifest_(files);
  Object.keys(manifest).forEach(function (k) { result[k] = manifest[k]; });
  result.oauth_scope_count = result.oauth_scopes.length;
  return result;
}

/* ---------------- metrics (cf. Python metrics.py) ---------------- */

/**
 * Payload: {activeUsers|totalExecutions|failedExecutions:
 *           [{startTime, endTime, value}]} with value a *string* int.
 * Executions are additive across intervals; active users are unique per
 * interval, so only the latest interval's value is reported.
 */
function summariseMetrics_(metrics) {
  function values(key) { return (metrics && metrics[key]) || []; }
  function asInt(entry) {
    var n = parseInt(entry && entry.value, 10);
    return isNaN(n) ? 0 : n;
  }
  var active = values('activeUsers').slice().sort(function (a, b) {
    return String(a.endTime || '') < String(b.endTime || '') ? -1 : 1;
  });
  return {
    active_users_latest: active.length ? asInt(active[active.length - 1]) : 0,
    total_executions: values('totalExecutions').reduce(function (s, e) { return s + asInt(e); }, 0),
    failed_executions: values('failedExecutions').reduce(function (s, e) { return s + asInt(e); }, 0)
  };
}

/* ---------------- processes (cf. Python processes.py) ---------------- */

/** Process keys are processType / processStatus / startTime / functionName. */
function summariseProcesses_(processes) {
  var types = {};
  var statuses = {};
  var last = null;
  (processes || []).forEach(function (p) {
    var t = p.processType || 'UNKNOWN';
    var s = p.processStatus || 'UNKNOWN';
    types[t] = (types[t] || 0) + 1;
    statuses[s] = (statuses[s] || 0) + 1;
    if (!last || String(p.startTime || '') > String(last.startTime || '')) last = p;
  });
  return {
    recent_process_count: (processes || []).length,
    process_types: types,
    process_statuses: statuses,
    failed_process_count: (statuses.FAILED || 0) + (statuses.TIMED_OUT || 0),
    last_execution_time: last ? (last.startTime || '') : '',
    last_execution_type: last ? (last.processType || '') : '',
    last_execution_status: last ? (last.processStatus || '') : '',
    last_execution_function: last ? (last.functionName || '') : ''
  };
}

/* ---------------- orchestration (cf. Python audit.py) ---------------- */

function blankRow_() {
  return {
    project_name: '', script_id: '', drive_modified_time: '', drive_created_time: '',
    web_view_link: '', parent_id: '', creator_email: '', last_modify_user_email: '',
    project_create_time: '', project_update_time: '',
    file_count: 0, file_counts_by_type: {}, server_js_count: 0, html_count: 0,
    json_count: 0, function_count: 0, function_names: [], total_source_chars: 0,
    oauth_scopes: [], oauth_scope_count: 0, advanced_services: [],
    manifest_time_zone: '', runtime_version: '', has_webapp: false,
    has_execution_api: false,
    metrics_granularity: CONFIG.METRICS_GRANULARITY,
    active_users_latest: 0, total_executions: 0, failed_executions: 0,
    recent_process_count: 0, process_types: {}, process_statuses: {},
    failed_process_count: 0, last_execution_time: '', last_execution_type: '',
    last_execution_status: '', last_execution_function: '',
    project_error: '', content_error: '', metrics_error: '', processes_error: ''
  };
}

function merge_(row, values) {
  Object.keys(values).forEach(function (k) { row[k] = values[k]; });
  return row;
}

/**
 * Audit one Drive file. Each API stage is isolated: a failure lands in
 * that stage's *_error field and the rest of the row still fills in.
 */
function auditProject_(driveFile) {
  var row = blankRow_();
  var scriptId = driveFile.id;
  var owners = driveFile.owners || [{}];
  merge_(row, {
    project_name: driveFile.name || '',
    script_id: scriptId,
    drive_modified_time: driveFile.modifiedTime || '',
    drive_created_time: driveFile.createdTime || '',
    web_view_link: driveFile.webViewLink || '',
    creator_email: (owners[0] && owners[0].emailAddress) || '',
    last_modify_user_email: (driveFile.lastModifyingUser || {}).emailAddress || ''
  });

  try {
    var meta = scriptGetProject_(scriptId);
    row.parent_id = meta.parentId || '';
    row.project_create_time = meta.createTime || '';
    row.project_update_time = meta.updateTime || '';
    if (meta.creator && meta.creator.emailAddress) row.creator_email = meta.creator.emailAddress;
    if (meta.lastModifyUser && meta.lastModifyUser.emailAddress) {
      row.last_modify_user_email = meta.lastModifyUser.emailAddress;
    }
    if (meta.title) row.project_name = meta.title;
  } catch (e) { row.project_error = String(e && e.message || e); }

  try {
    merge_(row, summariseContent_(scriptGetContent_(scriptId)));
  } catch (e) { row.content_error = String(e && e.message || e); }

  try {
    merge_(row, summariseMetrics_(scriptGetMetrics_(scriptId)));
  } catch (e) { row.metrics_error = String(e && e.message || e); }

  try {
    merge_(row, summariseProcesses_(scriptListProcesses_(scriptId, CONFIG.PROCESS_LIMIT)));
  } catch (e) { row.processes_error = String(e && e.message || e); }

  return row;
}
