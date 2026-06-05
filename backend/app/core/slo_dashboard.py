"""SLO Dashboard Configuration (H1.5).

Exports Langfuse-compatible dashboard definitions for SLO monitoring.
These can be imported into Langfuse's dashboard feature or used as
reference for Grafana dashboards backed by Prometheus metrics.

The dashboard config is JSON-serializable and mirrors the 4 SLOs
defined in app.core.slo.
"""

SLO_DASHBOARD_CONFIG = {
    "version": 1,
    "name": "Flowmanner SLO Dashboard (H1.5)",
    "description": "Real-time SLO compliance monitoring for Flowmanner production services.",
    "panels": [
        {
            "title": "Mission Success Rate SLO",
            "description": "Target: > 95% mission execution success rate.",
            "metrics": [
                {
                    "name": "flowmanner_slo_compliance_ratio",
                    "filter": 'slo_name="mission_success_rate"',
                    "aggregation": "last",
                    "display": "gauge",
                    "thresholds": [
                        {"value": 0.95, "color": "green", "label": "OK (>= 95%)"},
                        {"value": 0.85, "color": "yellow", "label": "Warning (85-95%)"},
                        {"value": 0.0, "color": "red", "label": "Critical (< 85%)"},
                    ],
                },
                {
                    "name": "flowmanner_slo_burn_rate",
                    "filter": 'slo_name="mission_success_rate"',
                    "aggregation": "last",
                    "display": "gauge",
                    "thresholds": [
                        {"value": 1.0, "color": "green", "label": "On track"},
                        {"value": 5.0, "color": "yellow", "label": "Elevated burn"},
                        {"value": 10.0, "color": "red", "label": "Critical burn"},
                    ],
                },
                {
                    "name": "flowmanner_slo_error_budget_remaining",
                    "filter": 'slo_name="mission_success_rate"',
                    "aggregation": "last",
                    "display": "gauge",
                    "thresholds": [
                        {"value": 0.5, "color": "green", "label": "> 50% budget"},
                        {"value": 0.1, "color": "yellow", "label": "10-50% budget"},
                        {"value": 0.0, "color": "red", "label": "< 10% budget"},
                    ],
                },
            ],
        },
        {
            "title": "SSE Token Latency SLO",
            "description": "Target: p99 SSE token delivery latency < 300ms.",
            "metrics": [
                {
                    "name": "flowmanner_slo_compliance_ratio",
                    "filter": 'slo_name="sse_token_latency_p99"',
                    "aggregation": "last",
                    "display": "gauge",
                    "thresholds": [
                        {"value": 0.999, "color": "green", "label": "OK"},
                        {"value": 0.99, "color": "yellow", "label": "Warning"},
                        {"value": 0.0, "color": "red", "label": "Critical"},
                    ],
                },
                {
                    "name": "flowmanner_sse_token_latency_seconds",
                    "aggregation": "last",
                    "display": "value",
                    "unit": "seconds",
                    "thresholds": [
                        {"value": 300, "color": "green", "label": "< 0.3s"},
                        {"value": 500, "color": "yellow", "label": "0.3-0.5s"},
                        {"value": 10000, "color": "red", "label": "> 0.5s"},
                    ],
                },
            ],
        },
        {
            "title": "Model Fallback Success SLO",
            "description": "Target: > 99% model fallback success rate.",
            "metrics": [
                {
                    "name": "flowmanner_slo_compliance_ratio",
                    "filter": 'slo_name="model_fallback_success"',
                    "aggregation": "last",
                    "display": "gauge",
                    "thresholds": [
                        {"value": 0.99, "color": "green", "label": "OK (>= 99%)"},
                        {"value": 0.95, "color": "yellow", "label": "Warning (95-99%)"},
                        {"value": 0.0, "color": "red", "label": "Critical (< 95%)"},
                    ],
                },
                {
                    "name": "flowmanner_slo_burn_rate",
                    "filter": 'slo_name="model_fallback_success"',
                    "aggregation": "last",
                    "display": "gauge",
                },
                {
                    "name": "flowmanner_slo_error_budget_remaining",
                    "filter": 'slo_name="model_fallback_success"',
                    "aggregation": "last",
                    "display": "gauge",
                },
            ],
        },
        {
            "title": "Deploy Success Rate SLO",
            "description": "Target: > 99% deployment success rate.",
            "metrics": [
                {
                    "name": "flowmanner_slo_compliance_ratio",
                    "filter": 'slo_name="deploy_success_rate"',
                    "aggregation": "last",
                    "display": "gauge",
                    "thresholds": [
                        {"value": 0.99, "color": "green", "label": "OK (>= 99%)"},
                        {"value": 0.95, "color": "yellow", "label": "Warning (95-99%)"},
                        {"value": 0.0, "color": "red", "label": "Critical (< 95%)"},
                    ],
                },
                {
                    "name": "flowmanner_slo_burn_rate",
                    "filter": 'slo_name="deploy_success_rate"',
                    "aggregation": "last",
                    "display": "gauge",
                },
                {
                    "name": "flowmanner_slo_error_budget_remaining",
                    "filter": 'slo_name="deploy_success_rate"',
                    "aggregation": "last",
                    "display": "gauge",
                },
            ],
        },
        {
            "title": "LLM Request Performance",
            "description": "LLM API request latency and success by provider.",
            "metrics": [
                {
                    "name": "flowmanner_llm_requests_total",
                    "aggregation": "rate",
                    "display": "timeseries",
                    "group_by": ["provider", "status"],
                },
                {
                    "name": "flowmanner_llm_request_duration_seconds",
                    "aggregation": "p99",
                    "display": "timeseries",
                    "group_by": ["provider"],
                },
                {
                    "name": "flowmanner_llm_tokens_total",
                    "aggregation": "rate",
                    "display": "timeseries",
                    "group_by": ["provider", "type"],
                },
            ],
        },
        {
            "title": "Mission Execution Overview",
            "description": "Mission execution volume, success rate, and duration.",
            "metrics": [
                {
                    "name": "flowmanner_missions_total",
                    "aggregation": "rate",
                    "display": "timeseries",
                    "group_by": ["status"],
                },
                {
                    "name": "flowmanner_mission_duration_seconds",
                    "aggregation": "p99",
                    "display": "timeseries",
                },
                {
                    "name": "flowmanner_mission_tokens",
                    "aggregation": "avg",
                    "display": "timeseries",
                },
            ],
        },
    ],
    "refresh_interval_seconds": 30,
    "tags": ["slo", "production", "h1.5"],
}


def get_slo_dashboard_config() -> dict:
    """Return the SLO dashboard configuration for Langfuse/Grafana import."""
    return SLO_DASHBOARD_CONFIG


def get_slo_dashboard_json() -> str:
    """Return the SLO dashboard configuration as a JSON string."""
    import json
    return json.dumps(SLO_DASHBOARD_CONFIG, indent=2)
