/**
 * Node tests for the Apps Script (.gs) implementation.
 *
 * Loads Config.gs + Api.gs + Audit.gs into a vm context with stubbed
 * Apps Script globals (UrlFetchApp, ScriptApp), then checks the parsers
 * and the full auditProject_ flow against the SAME fixture payloads as
 * the Python tests (tests/fixtures.py) -- the two implementations must
 * agree on the same API shapes.
 *
 * Run:  node tests-gas/test_audit.js
 */
'use strict';

const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const GAS_DIR = path.join(__dirname, '..', 'apps-script');

/* ---------------- fixtures (mirror tests/fixtures.py) ---------------- */

const CONTENT = {
  scriptId: 'ABC',
  files: [
    { name: 'Code', type: 'SERVER_JS', source: 'function a(){} function b(){}',
      functionSet: { values: [{ name: 'a' }, { name: 'b' }] } },
    { name: 'page', type: 'HTML', source: '<html></html>' },
    { name: 'appsscript', type: 'JSON',
      source: '{"timeZone":"America/New_York","runtimeVersion":"V8",' +
        ' "oauthScopes":["https://www.googleapis.com/auth/spreadsheets.readonly"],' +
        ' "webapp":{"access":"MYSELF"},' +
        ' "dependencies":{"enabledAdvancedServices":' +
        '   [{"userSymbol":"Drive","serviceId":"drive","version":"v2"}]}}' },
  ],
};

const METRICS = {
  activeUsers: [{ endTime: '2026-10-12', value: '3' }, { endTime: '2026-10-19', value: '5' }],
  totalExecutions: [{ value: '10' }, { value: '7' }],
  failedExecutions: [{ value: '2' }, { value: '1' }],
};

const PROCESSES = [
  { processType: 'TIME_DRIVEN', processStatus: 'COMPLETED', startTime: '2026-10-19T01:00:00Z', functionName: 'tick' },
  { processType: 'WEBAPP', processStatus: 'FAILED', startTime: '2026-10-20T01:00:00Z', functionName: 'doGet' },
  { processType: 'TIME_DRIVEN', processStatus: 'TIMED_OUT', startTime: '2026-10-18T01:00:00Z', functionName: 'tick' },
];

/* ---------------- stubbed Apps Script runtime ---------------- */

function jsonResponse(obj, code = 200) {
  return {
    getResponseCode: () => code,
    getContentText: () => JSON.stringify(obj),
  };
}

const sandbox = {
  console,
  ScriptApp: { getOAuthToken: () => 'fake-token' },
  UrlFetchApp: {
    fetch(url) {
      if (url.includes('/content')) return jsonResponse(CONTENT);
      if (url.includes('/metrics')) {
        assert.ok(url.includes('metricsGranularity=WEEKLY'), 'granularity param: ' + url);
        return jsonResponse({
          totalExecutions: [{ value: '4' }],
          failedExecutions: [{ value: '1' }],
          activeUsers: [{ endTime: '2026-10-19', value: '2' }],
        });
      }
      if (url.includes('listScriptProcesses')) {
        return jsonResponse({ processes: [
          { processType: 'TRIGGER', processStatus: 'COMPLETED',
            startTime: '2026-10-20T00:00:00Z', functionName: 'onEdit' },
        ] });
      }
      if (url.includes('/projects/')) {
        return jsonResponse({
          scriptId: 'ABC', title: 'T', parentId: 'PARENT1',
          createTime: '2024-01-01T00:00:00Z', updateTime: '2026-01-01T00:00:00Z',
          creator: { emailAddress: 'me@example.com' },
          lastModifyUser: { emailAddress: 'me@example.com' },
        });
      }
      throw new Error('unstubbed URL: ' + url);
    },
  },
};
vm.createContext(sandbox);
for (const f of ['Config.gs', 'Api.gs', 'Audit.gs']) {
  vm.runInContext(fs.readFileSync(path.join(GAS_DIR, f), 'utf8'), sandbox, { filename: f });
}

/* Cross-realm comparison: objects created inside the vm context have a
   different Object prototype, so deepStrictEqual rejects them even when
   structurally identical. Compare canonical JSON instead. */
function canonical(v) {
  if (Array.isArray(v)) return v.map(canonical);
  if (v && typeof v === 'object') {
    const out = {};
    for (const k of Object.keys(v).sort()) out[k] = canonical(v[k]);
    return out;
  }
  return v;
}
function assertJsonEqual(actual, expected, msg) {
  assert.strictEqual(JSON.stringify(canonical(actual)), JSON.stringify(canonical(expected)), msg);
}

const { summariseContent_, summariseMetrics_, summariseProcesses_, auditProject_, parseManifest_ } = sandbox;

/* ---------------- pure parser tests ---------------- */

const s = summariseContent_(CONTENT);
assert.strictEqual(s.file_count, 3);
assert.strictEqual(s.server_js_count, 1);
assert.strictEqual(s.html_count, 1);
assert.strictEqual(s.json_count, 1);
assertJsonEqual(s.file_counts_by_type, { SERVER_JS: 1, HTML: 1, JSON: 1 });
assertJsonEqual(s.function_names, ['a', 'b']);
assert.strictEqual(s.function_count, 2);
assert.strictEqual(s.oauth_scope_count, 1);
assert.strictEqual(s.has_webapp, true);
assert.strictEqual(s.has_execution_api, false);
assertJsonEqual(s.advanced_services, ['Drive (serviceId=drive, v2)']);
assert.strictEqual(s.manifest_time_zone, 'America/New_York');
assert.strictEqual(s.runtime_version, 'V8');

const badManifest = parseManifest_([{ name: 'appsscript', type: 'JSON', source: '{not json' }]);
assertJsonEqual(badManifest.oauth_scopes, []);

assertJsonEqual(summariseMetrics_(METRICS),
  { active_users_latest: 5, total_executions: 17, failed_executions: 3 });
assertJsonEqual(summariseMetrics_({}),
  { active_users_latest: 0, total_executions: 0, failed_executions: 0 });

const p = summariseProcesses_(PROCESSES);
assert.strictEqual(p.recent_process_count, 3);
assert.strictEqual(p.failed_process_count, 2);
assertJsonEqual(p.process_types, { TIME_DRIVEN: 2, WEBAPP: 1 });
assert.strictEqual(p.last_execution_function, 'doGet');
assert.strictEqual(p.last_execution_status, 'FAILED');

/* ---------------- full audit flow (stubbed HTTP) ---------------- */

const row = auditProject_({
  id: 'ABC', name: 'DriveName',
  modifiedTime: '2026-10-01T00:00:00Z', createdTime: '2024-01-01T00:00:00Z',
  webViewLink: 'https://example.invalid/abc',
  owners: [{ emailAddress: 'me@example.com' }],
});
assert.strictEqual(row.project_name, 'T');
assert.strictEqual(row.parent_id, 'PARENT1');
assert.strictEqual(row.file_count, 3);
assert.strictEqual(row.total_executions, 4);
assert.strictEqual(row.failed_executions, 1);
assert.strictEqual(row.active_users_latest, 2);
assert.strictEqual(row.last_execution_function, 'onEdit');
for (const col of ['project_error', 'content_error', 'metrics_error', 'processes_error']) {
  assert.strictEqual(row[col], '', col + ' should be empty, got: ' + row[col]);
}
// Row shape must match the Python AUDIT_FIELDS count (41).
assert.strictEqual(Object.keys(row).length, 41,
  'row keys: ' + Object.keys(row).join(','));

console.log('tests-gas: ALL PASS');
