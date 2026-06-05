import logging
import os
import random
import sys
from functools import wraps
from typing import Any

from flask import g, request

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from config.canary_config import (
        CANARY_ENABLED,
        CANARY_PERCENTAGE,
        CANARY_WORKFLOWS,
        COMPLEX_LEGACY_WORKFLOWS,
        MIGRATED_WORKFLOWS,
        N8N_MIGRATION_PERCENTAGE,
        ROLLBACK_TRIGGERS,
        USE_N8N_WORKFLOWS,
        get_routing_backend,
    )
except ImportError:
    logging.warning("Could not import canary_config, using defaults")
    CANARY_ENABLED = False
    CANARY_PERCENTAGE = 10
    CANARY_WORKFLOWS = []
    USE_N8N_WORKFLOWS = True
    N8N_MIGRATION_PERCENTAGE = 0
    MIGRATED_WORKFLOWS = []
    COMPLEX_LEGACY_WORKFLOWS = []

logger = logging.getLogger(__name__)

class CanaryMetrics:
    def __init__(self):
        self.requests_n8n = 0
        self.requests_governance = 0
        self.errors_n8n = 0
        self.errors_governance = 0
        self.latencies_n8n = []
        self.latencies_governance = []
    
    def record_request(self, backend: str, success: bool, latency_ms: float):
        if backend == 'n8n':
            self.requests_n8n += 1
            if not success:
                self.errors_n8n += 1
            self.latencies_n8n.append(latency_ms)
        elif backend == 'governance':
            self.requests_governance += 1
            if not success:
                self.errors_governance += 1
            self.latencies_governance.append(latency_ms)
    
    def get_error_rate(self, backend: str) -> float:
        if backend == 'n8n' and self.requests_n8n > 0:
            return (self.errors_n8n / self.requests_n8n) * 100
        elif backend == 'governance' and self.requests_governance > 0:
            return (self.errors_governance / self.requests_governance) * 100
        return 0.0
    
    def get_p99_latency(self, backend: str) -> float:
        latencies = self.latencies_n8n if backend == 'n8n' else self.latencies_governance
        if not latencies:
            return 0.0
        sorted_latencies = sorted(latencies)
        return sorted_latencies[int(len(sorted_latencies) * 0.99)]
    
    def get_stats(self) -> dict[str, Any]:
        return {
            'n8n': {
                'requests': self.requests_n8n,
                'errors': self.errors_n8n,
                'error_rate': self.get_error_rate('n8n'),
                'p99_latency_ms': self.get_p99_latency('n8n'),
                'avg_latency_ms': sum(self.latencies_n8n) / len(self.latencies_n8n) if self.latencies_n8n else 0
            },
            'governance': {
                'requests': self.requests_governance,
                'errors': self.errors_governance,
                'error_rate': self.get_error_rate('governance'),
                'p99_latency_ms': self.get_p99_latency('governance'),
                'avg_latency_ms': sum(self.latencies_governance) / len(self.latencies_governance) if self.latencies_governance else 0
            }
        }

canary_metrics = CanaryMetrics()

def should_route_to_governance(workflow_id: str | None = None) -> bool:
    if not USE_N8N_WORKFLOWS:
        return True
    
    if workflow_id and workflow_id in MIGRATED_WORKFLOWS:
        return True
    
    if workflow_id and workflow_id in COMPLEX_LEGACY_WORKFLOWS:
        return False
    
    if CANARY_ENABLED and workflow_id and workflow_id in CANARY_WORKFLOWS:
        return random.randint(1, 100) <= N8N_MIGRATION_PERCENTAGE
    
    return False

def get_routing_backend(workflow_id: str | None = None) -> str:
    if should_route_to_governance(workflow_id):
        return 'governance'
    return 'n8n'

def check_rollback_conditions() -> dict[str, Any]:
    governance_error_rate = canary_metrics.get_error_rate('governance')
    governance_p99 = canary_metrics.get_p99_latency('governance')
    
    rollback = False
    reasons = []
    
    if governance_error_rate > ROLLBACK_TRIGGERS.get('error_rate_threshold', 5.0):
        rollback = True
        reasons.append(f"Error rate {governance_error_rate:.1f}% exceeds threshold {ROLLBACK_TRIGGERS['error_rate_threshold']}%")
    
    if governance_p99 > ROLLBACK_TRIGGERS.get('latency_p99_threshold_ms', 3000):
        rollback = True
        reasons.append(f"P99 latency {governance_p99:.0f}ms exceeds threshold {ROLLBACK_TRIGGERS['latency_p99_threshold_ms']}ms")
    
    return {
        'should_rollback': rollback,
        'reasons': reasons,
        'metrics': {
            'error_rate': governance_error_rate,
            'p99_latency': governance_p99
        }
    }

def record_metric(backend: str, success: bool, latency_ms: float):
    canary_metrics.record_request(backend, success, latency_ms)
    
    if backend == 'governance':
        rollback_check = check_rollback_conditions()
        if rollback_check['should_rollback']:
            logger.warning(f"Canary rollback triggered: {rollback_check['reasons']}")

def route_to_governance_request():
    g.routing_backend = 'governance'
    return None

def route_to_n8n_request():
    g.routing_backend = 'n8n'
    return None

def canary_routing_middleware(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        workflow_id = request.view_args.get('workflow_id') or request.json.get('workflow_id') if request.is_json else None
        backend = get_routing_backend(workflow_id)
        
        g.routing_backend = backend
        g.workflow_id = workflow_id
        
        logger.debug(f"Canary routing: workflow_id={workflow_id}, backend={backend}")
        
        return f(*args, **kwargs)
    
    return decorated_function

def get_canary_stats() -> dict[str, Any]:
    return {
        'config': {
            'enabled': CANARY_ENABLED,
            'percentage': CANARY_PERCENTAGE,
            'workflows': CANARY_WORKFLOWS,
            'use_n8n': USE_N8N_WORKFLOWS,
            'migration_percentage': N8N_MIGRATION_PERCENTAGE
        },
        'metrics': canary_metrics.get_stats(),
        'rollback_check': check_rollback_conditions()
    }

def reset_canary_metrics():
    global canary_metrics
    canary_metrics = CanaryMetrics()
    logger.info("Canary metrics reset")

if __name__ == '__main__':
    print("Canary Router Middleware")
    print("=" * 50)
    print(f"Enabled: {CANARY_ENABLED}")
    print(f"Canary Percentage: {CANARY_PERCENTAGE}%")
    print(f"Canary Workflows: {CANARY_WORKFLOWS}")
    print(f"Use n8n: {USE_N8N_WORKFLOWS}")
    print(f"Migration Percentage: {N8N_MIGRATION_PERCENTAGE}%")
    print(f"Migrated Workflows: {MIGRATED_WORKFLOWS}")
    print("=" * 50)
    
    test_workflow = "test_wf"
    backend = get_routing_backend(test_workflow)
    print(f"\nTest routing for '{test_workflow}': {backend}")
