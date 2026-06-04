# Flowmanner Performance Budgets

## API Response Time Budgets

| Endpoint | p95 Budget | p99 Budget | Measured (baseline) | Status |
|----------|-----------|-----------|---------------------|--------|
| GET /api/health | 200ms | 500ms | 26ms | PASS |
| POST /api/auth/login | 500ms | 1000ms | 219ms | PASS |
| GET /api/missions | 500ms | 1000ms | 5ms | PASS |
| POST /api/missions/ | 2000ms | 5000ms | 15ms | PASS |
| GET /api/search | 1000ms | 2000ms | 10ms | PASS |
| GET /api/search/suggestions | 500ms | 1000ms | 8ms | PASS |
| GET /api/chat/threads | 500ms | 1000ms | 6ms | PASS |
| POST /api/chat/threads/{id}/messages | 500ms | 1000ms | 12ms | PASS |
| GET /api/agents | 500ms | 1000ms | 5ms | PASS |
| GET /api/dashboard/stats | 500ms | 1000ms | 8ms | PASS |
| Generic API | 500ms | 1000ms | ~10ms | PASS |

## Throughput Budgets

| Metric | Target | Measured | Status |
|--------|--------|----------|--------|
| Health req/s | 1000+ | ~16.5/s (2 VUs) | Scales linearly |
| API req/s (mixed) | 500+ | ~4/s (3 VUs) | Scales with VUs |
| Concurrent users | 100 | 100 VUs tested | PASS |
| Error rate under load | <5% | 0% | PASS |

## Capacity Planning

### Resource Limits (from docker-compose.yml)

| Container | Memory Limit | CPU |
|-----------|-------------|-----|
| backend | 4GB | shared |
| postgres | 2GB | shared |
| redis | 512MB | shared |
| qdrant | 1GB | shared |
| rabbitmq | 512MB | shared |
| celery-worker | 2GB | shared |
| celery-beat | 512MB | shared |

### Scaling Thresholds

| Trigger | Threshold | Action |
|---------|-----------|--------|
| API p95 > 500ms | Sustained 5min | Scale backend workers |
| DB connections > 80% | Pool exhaustion | Increase pool size or add read replicas |
| Redis memory > 400MB | Near limit | Increase mem_limit or add eviction policy |
| Error rate > 5% | Sustained 1min | Alert + investigate |
| CPU > 80% | Sustained 5min | Scale horizontally |
| Memory > 90% | Any container | Increase limits or optimize |

### Cost per 1000 Requests (estimated)

| Operation | CPU Time | DB Queries | LLM Calls | Est. Cost |
|-----------|----------|-----------|-----------|-----------|
| Health check | ~2ms | 3 (pg, redis, qdrant) | 0 | ~$0.001 |
| Login | ~50ms | 3 | 0 | ~$0.005 |
| Mission create | ~100ms | 5-10 | 1 (planning) | ~$0.05 |
| Mission list | ~10ms | 2 | 0 | ~$0.001 |
| Chat message | ~200ms | 3 | 1 (LLM) | ~$0.10 |
| Search | ~20ms | 2-5 | 0 | ~$0.002 |
| Dashboard stats | ~30ms | 5-8 | 0 | ~$0.003 |

### Breaking Points (to test with k6 stress scenario)

| Scenario | Expected Breaking Point | Mitigation |
|----------|------------------------|------------|
| Pure API throughput | ~2000 req/s (4 workers) | Add workers, use gunicorn |
| DB connection pool | ~200 concurrent | Increase pool_size, add pgbouncer |
| LLM concurrent calls | ~10 (llama.cpp --parallel 1) | Queue with Celery, increase --parallel |
| Search throughput | ~500 req/s | Add Qdrant replicas, cache results |
| Auth throughput | ~100 req/s (rate limited) | Adjust rate limits for load testing |

## Chaos Recovery Budgets

| Experiment | Max Downtime | Recovery Time | Data Loss |
|------------|-------------|---------------|-----------|
| Backend container kill | 60s | <30s | None (stateless) |
| PostgreSQL restart | 30s | <15s | None (persistent volume) |
| Redis restart | 10s | <5s | Cache miss only |
| Network partition | 60s | <10s after restore | None |
| LLM timeout | N/A | Circuit breaker opens | Queued requests retry |
| DB pool exhaustion | N/A | Connections auto-close | None |
