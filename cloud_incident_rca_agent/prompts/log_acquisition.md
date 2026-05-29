# Log Acquisition

Prefer `cls-log-mcp` when service, time window, trace id, route, error code, or
specific keywords are known. Use Chrome MCP only to inspect read-only console
context such as CLS query pages, alarms, deployments, traces, or metrics.

Do not query logs without a bounded time window and at least one narrowing
condition.
