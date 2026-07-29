"""Custom Prometheus metrics for the things the PRD's Monitoring section
calls out that generic HTTP instrumentation can't see: agent latency, token
usage, and errors per agent (as opposed to per-route)."""

from prometheus_client import Counter, Histogram

agent_calls_total = Counter("ai_agent_calls_total", "Agent invocations", ["agent", "action"])
agent_duration_ms = Histogram(
    "ai_agent_duration_ms",
    "Agent call duration in milliseconds",
    ["agent"],
    buckets=(10, 50, 100, 250, 500, 1000, 2500, 5000, 10000, 30000),
)
agent_tokens_total = Counter("ai_agent_tokens_total", "Tokens consumed", ["agent"])
agent_errors_total = Counter("ai_agent_errors_total", "Agent call errors", ["agent", "action"])


def record_agent_call(agent: str, action: str, duration_ms: int, tokens: int, error: bool) -> None:
    agent_calls_total.labels(agent=agent, action=action).inc()
    agent_duration_ms.labels(agent=agent).observe(duration_ms)
    if tokens:
        agent_tokens_total.labels(agent=agent).inc(tokens)
    if error:
        agent_errors_total.labels(agent=agent, action=action).inc()
