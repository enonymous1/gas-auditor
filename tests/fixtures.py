"""Fixture payloads in the exact shapes the real Google APIs return,
plus fake Drive/Script services built on them. Shared by all test modules.
"""

from __future__ import annotations

CONTENT = {
    "scriptId": "ABC",
    "files": [
        {"name": "Code", "type": "SERVER_JS",
         "source": "function a(){} function b(){}",
         "functionSet": {"values": [{"name": "a"}, {"name": "b"}]}},
        {"name": "page", "type": "HTML", "source": "<html></html>"},
        {"name": "appsscript", "type": "JSON",
         "source": (
             '{"timeZone":"America/New_York","runtimeVersion":"V8",'
             ' "oauthScopes":["https://www.googleapis.com/auth/spreadsheets.readonly"],'
             ' "webapp":{"access":"MYSELF"},'
             ' "dependencies":{"enabledAdvancedServices":'
             '   [{"userSymbol":"Drive","serviceId":"drive","version":"v2"}]}}'
         )},
    ],
}

METRICS = {
    "activeUsers": [
        {"endTime": "2026-10-12", "value": "3"},
        {"endTime": "2026-10-19", "value": "5"},
    ],
    "totalExecutions": [{"value": "10"}, {"value": "7"}],
    "failedExecutions": [{"value": "2"}, {"value": "1"}],
}

PROCESSES = [
    {"processType": "TIME_DRIVEN", "processStatus": "COMPLETED",
     "startTime": "2026-10-19T01:00:00Z", "functionName": "tick"},
    {"processType": "WEBAPP", "processStatus": "FAILED",
     "startTime": "2026-10-20T01:00:00Z", "functionName": "doGet"},
    {"processType": "TIME_DRIVEN", "processStatus": "TIMED_OUT",
     "startTime": "2026-10-18T01:00:00Z", "functionName": "tick"},
]

DRIVE_FILE = {
    "id": "ABC", "name": "DriveName",
    "modifiedTime": "2026-10-01T00:00:00Z",
    "createdTime": "2024-01-01T00:00:00Z",
    "webViewLink": "https://example.invalid/abc",
    "owners": [{"emailAddress": "me@example.com"}],
}


class _Req:
    def __init__(self, value):
        self._value = value

    def execute(self):
        return self._value


class FakeScript:
    """Mimics the google-api-python-client resource chain used by the package."""

    def projects(self):
        return self

    def processes(self):
        return self

    # projects.*
    def get(self, scriptId):
        return _Req({
            "scriptId": scriptId, "title": "T", "parentId": "PARENT1",
            "createTime": "2024-01-01T00:00:00Z",
            "updateTime": "2026-01-01T00:00:00Z",
            "creator": {"emailAddress": "me@example.com"},
            "lastModifyUser": {"emailAddress": "me@example.com"},
        })

    def getContent(self, scriptId):
        return _Req(CONTENT)

    def getMetrics(self, scriptId, metricsGranularity):
        assert metricsGranularity in ("DAILY", "WEEKLY")
        return _Req({
            "totalExecutions": [{"value": "4"}],
            "failedExecutions": [{"value": "1"}],
            "activeUsers": [{"endTime": "2026-10-19", "value": "2"}],
        })

    # processes.*
    def listScriptProcesses(self, scriptId, pageSize, pageToken=None, **kwargs):
        return _Req({"processes": [
            {"processType": "TRIGGER", "processStatus": "COMPLETED",
             "startTime": "2026-10-20T00:00:00Z", "functionName": "onEdit"},
        ]})
