# Flowmanner Reusable Prompt Library

Goal-driven prompts for the Flowmanner swarm orchestration system.
Each template maps to `POST /api/swarm/execute` or protocol endpoints.

---

## 1. Feature Implementation

### Full-Stack Feature
```json
{
  "goal": "Implement [FEATURE_NAME] end-to-end:\n\nBackend:\n- [API endpoint description]\n- [Database model changes]\n- [Service layer logic]\n\nFrontend:\n- [UI component]\n- [API integration]\n- [State management]\n\nAcceptance:\n- All endpoints return correct responses\n- Frontend renders and handles errors\n- Unit tests pass\n- No TypeScript errors",
  "strategy": "parallel",
  "max_agents": 4
}
```

**Example:**
```json
{
  "goal": "Implement team invitation system end-to-end:\n\nBackend:\n- POST /api/teams/{id}/invite — create invitation with email, role\n- GET /api/invitations/{token} — validate invitation token\n- POST /api/invitations/{token}/accept — accept and add to team\n- Email notification via existing email service\n\nFrontend:\n- Invite modal with email input and role selector\n- Invitation acceptance page at /invite/{token}\n- Team member list showing pending invitations\n\nAcceptance:\n- Invitations expire after 7 days\n- Duplicate emails rejected with clear error\n- Role is assigned correctly on accept\n- All tests pass",
  "strategy": "parallel",
  "max_agents": 4
}
```

### API Endpoint Only
```json
{
  "goal": "Create REST API endpoint: [METHOD] [PATH]\n\nPurpose: [what it does]\nRequest body: [schema]\nResponse: [schema]\nAuth: [required/optional/public]\nValidation: [rules]\n\nAcceptance:\n- Returns correct status codes (200, 400, 401, 404, 409)\n- Input validation with clear error messages\n- OpenAPI schema updated\n- Unit tests covering happy path and edge cases",
  "strategy": "parallel",
  "max_agents": 2
}
```

### Frontend Component
```json
{
  "goal": "Build React component: [COMPONENT_NAME]\n\nLocation: src/components/[path]\nProps: [interface]\nBehavior: [description]\nStyling: glassmorphism (bg-white/40, border-white/40, rounded-2xl, backdrop-blur-sm)\n\nAcceptance:\n- Renders correctly in light theme\n- Handles loading, error, and empty states\n- Accessible (keyboard nav, ARIA labels)\n- No TypeScript errors\n- Responsive on mobile",
  "strategy": "parallel",
  "max_agents": 2
}
```

---

## 2. Code Review & Security

### Security Audit
```json
{
  "goal": "Security audit of [MODULE/ENDPOINT]:\n\nScope:\n- [files or endpoints to review]\n\nCheck for:\n- SQL injection (parameterized queries)\n- XSS (sanitized output)\n- CSRF protection\n- Authentication bypass\n- Authorization leaks (user A accessing user B data)\n- Rate limiting\n- Input validation gaps\n- Secret exposure in responses\n- Error message information leakage\n\nDeliverable:\n- List of findings with severity (critical/high/medium/low)\n- Specific file:line references\n- Recommended fixes with code snippets",
  "strategy": "sequential",
  "max_agents": 2
}
```

### Code Review with Fix
```json
{
  "goal": "Review and fix code in [FILES]:\n\nReview criteria:\n- Correctness: does it do what it claims?\n- Error handling: all failure paths covered?\n- Performance: N+1 queries, unnecessary allocations?\n- Style: follows project conventions?\n- Security: OWASP top 10?\n\nDeliverable:\n- Fixed code with inline comments explaining each change\n- List of issues found and resolved\n- Any remaining concerns for manual review",
  "strategy": "sequential",
  "max_agents": 2
}
```

### Dependency Audit
```json
{
  "goal": "Audit project dependencies for security and freshness:\n\nCheck:\n- Known CVEs in current dependencies\n- Outdated packages (>1 major version behind)\n- Unused dependencies\n- License conflicts\n- Transitive dependency risks\n\nDeliverable:\n- Table of findings: package, current version, latest, CVEs, action\n- Updated requirements.txt/pyproject.toml with safe versions\n- Any breaking changes noted",
  "strategy": "parallel",
  "max_agents": 2
}
```

---

## 3. Refactoring

### Module Extraction
```json
{
  "goal": "Extract [FUNCTIONALITY] from [SOURCE_FILE] into a standalone module:\n\nCurrent state:\n- [describe what exists]\n- [why it needs extraction]\n\nTarget:\n- New module: [path]\n- Public API: [functions/classes to expose]\n- Keep backward compatibility via re-exports\n\nAcceptance:\n- All existing imports still work\n- No behavioral changes\n- Tests updated and passing\n- File size under 400 lines",
  "strategy": "sequential",
  "max_agents": 3
}
```

### Database Migration
```json
{
  "goal": "Migrate [TABLE/MODEL] from [OLD_SCHEMA] to [NEW_SCHEMA]:\n\nChanges:\n- [column renames/adds/removes]\n- [type changes]\n- [index changes]\n\nConstraints:\n- Zero downtime (add columns nullable, backfill, then set NOT NULL)\n- Preserve existing data\n- Rollback plan\n\nDeliverable:\n- Alembic migration file\n- Backfill script if needed\n- Updated SQLAlchemy models\n- Updated Pydantic schemas\n- Tests for migration up/down",
  "strategy": "sequential",
  "max_agents": 3
}
```

### API Version Migration
```json
{
  "goal": "Migrate [ENDPOINT] from v1 to v2 response format:\n\nv1 format: {data}\nv2 format: {data, meta, error}\n\nScope:\n- [list of endpoints to migrate]\n- Update all frontend callers\n- Maintain backward compatibility for 30 days\n\nAcceptance:\n- All endpoints return v2 envelope\n- Frontend handles both formats during transition\n- Deprecation headers added to v1 responses",
  "strategy": "parallel",
  "max_agents": 3
}
```

---

## 4. Testing

### Test Suite Creation
```json
{
  "goal": "Create comprehensive test suite for [MODULE]:\n\nModule: [path]\nPublic API: [functions/endpoints to test]\n\nTest types needed:\n- Unit tests for each public function\n- Integration tests for API endpoints\n- Edge cases: empty input, null, boundary values\n- Error cases: invalid input, missing data, permissions\n\nCoverage target: 80%+\n\nDeliverable:\n- Test file at tests/test_[module].py\n- All tests passing\n- Coverage report showing 80%+",
  "strategy": "parallel",
  "max_agents": 2
}
```

### E2E Test Suite
```json
{
  "goal": "Create Playwright E2E tests for [USER_FLOW]:\n\nFlow:\n1. [step 1]\n2. [step 2]\n3. [step 3]\n\nTest scenarios:\n- Happy path: complete flow succeeds\n- Validation: invalid input shows errors\n- Auth: unauthenticated redirect\n- Error: API failure shows retry option\n\nDeliverable:\n- Playwright spec file\n- All tests passing in headless mode\n- Screenshots on failure",
  "strategy": "sequential",
  "max_agents": 2
}
```

### Load Test
```json
{
  "goal": "Create k6 load test for [ENDPOINT]:\n\nEndpoint: [METHOD] [PATH]\nExpected load: [requests/second]\nDuration: [time]\n\nScenarios:\n- Ramp up: 0 → 100 users over 2 minutes\n- Sustained: 100 users for 5 minutes\n- Spike: 0 → 500 users instantly\n\nMetrics to capture:\n- p50, p95, p99 latency\n- Error rate\n- Throughput\n\nDeliverable:\n- k6 script at scripts/load-tests/[name].js\n- Performance budget assertions\n- CI integration config",
  "strategy": "sequential",
  "max_agents": 2
}
```

---

## 5. Documentation

### API Documentation
```json
{
  "goal": "Write API documentation for [ENDPOINTS]:\n\nEndpoints:\n- [METHOD] [PATH] — [description]\n- [METHOD] [PATH] — [description]\n\nFor each endpoint document:\n- Purpose and use case\n- Request parameters and body schema\n- Response schema with examples\n- Error codes and meanings\n- Authentication requirements\n- Rate limits\n\nFormat: Markdown with code examples in curl and Python",
  "strategy": "parallel",
  "max_agents": 2
}
```

### Architecture Decision Record
```json
{
  "goal": "Write ADR for [DECISION]:\n\nContext: [why this decision is needed]\nOptions considered:\n1. [Option A] — [pros/cons]\n2. [Option B] — [pros/cons]\n3. [Option C] — [pros/cons]\n\nFormat:\n- Title: ADR-[NUMBER]: [Decision Title]\n- Status: proposed/accepted/deprecated\n- Context: problem statement\n- Decision: what we chose and why\n- Consequences: positive and negative\n- Alternatives considered: why rejected",
  "strategy": "debate",
  "max_agents": 3
}
```

### Runbook
```json
{
  "goal": "Write operational runbook for [SERVICE/FEATURE]:\n\nCover:\n- What it does and why it matters\n- Architecture diagram (ASCII)\n- Common failure modes and symptoms\n- Step-by-step diagnosis procedures\n- Fix procedures with exact commands\n- Escalation contacts and thresholds\n- Monitoring dashboards and alerts\n\nFormat: Markdown with command blocks, decision trees, and severity levels",
  "strategy": "sequential",
  "max_agents": 2
}
```

---

## 6. Debugging

### Bug Investigation
```json
{
  "goal": "Investigate and fix bug: [DESCRIPTION]\n\nSymptoms:\n- [what users see]\n- [error messages]\n- [when it happens]\n\nKnown clues:\n- [logs]\n- [reproduction steps]\n- [affected users/endpoints]\n\nDeliverable:\n- Root cause analysis with evidence\n- Fix with explanation\n- Test that reproduces the bug\n- Prevention: what check would have caught this",
  "strategy": "sequential",
  "max_agents": 3
}
```

### Performance Investigation
```json
{
  "goal": "Investigate slow [ENDPOINT/QUERY/PROCESS]:\n\nCurrent performance:\n- [latency]\n- [expected latency]\n\nScope:\n- [code path to investigate]\n\nCheck:\n- Database query plans (EXPLAIN ANALYZE)\n- N+1 queries\n- Missing indexes\n- Unnecessary data fetching\n- Algorithm complexity\n- External API latency\n\nDeliverable:\n- Profiling results with flame graph or query plan\n- Bottleneck identification with evidence\n- Fix with before/after benchmarks\n- Monitoring alert for regression",
  "strategy": "sequential",
  "max_agents": 3
}
```

### Flaky Test Investigation
```json
{
  "goal": "Fix flaky test: [TEST_NAME]\n\nSymptoms:\n- Passes locally, fails in CI (or vice versa)\n- Failure rate: [X%]\n- Error message: [message]\n\nInvestigate:\n- Race conditions (async timing)\n- Test isolation (shared state)\n- External dependency mocking\n- Date/time sensitivity\n- Order-dependent failures\n\nDeliverable:\n- Root cause identified\n- Fix that makes test deterministic\n- Run 100 times to verify stability",
  "strategy": "sequential",
  "max_agents": 2
}
```

---

## 7. Architecture Decisions

### Technology Evaluation
```json
{
  "goal": "Evaluate [TECH_A] vs [TECH_B] for [USE_CASE]:\n\nCriteria:\n- Performance: latency, throughput, resource usage\n- Developer experience: learning curve, debugging, ecosystem\n- Operational: deployment, monitoring, scaling\n- Cost: licensing, infrastructure, maintenance\n- Risk: maturity, community, lock-in\n\nDeliverable:\n- Comparison table with scores (1-5) per criterion\n- Recommendation with reasoning\n- Migration path from current state\n- Proof-of-concept code for recommended option",
  "strategy": "debate",
  "max_agents": 3
}
```

### System Design
```json
{
  "goal": "Design [SYSTEM/FEATURE] architecture:\n\nRequirements:\n- [functional requirements]\n- [non-functional: scale, latency, availability]\n- [constraints: existing stack, team size, timeline]\n\nDeliverable:\n- Component diagram (ASCII)\n- Data model with relationships\n- API contracts between components\n- Failure modes and recovery\n- Scaling strategy\n- Monitoring and alerting plan\n- Implementation phases (MVP → v1 → v2)",
  "strategy": "debate",
  "max_agents": 4
}
```

---

## 8. Performance Optimization

### Database Optimization
```json
{
  "goal": "Optimize database performance for [TABLE/QUERY]:\n\nCurrent state:\n- [query or operation]\n- [current latency]\n- [target latency]\n\nInvestigate:\n- Missing indexes (check pg_stat_user_tables)\n- Query plan (EXPLAIN ANALYZE)\n- Table bloat and vacuum status\n- Connection pool utilization\n- Query caching opportunities\n\nDeliverable:\n- Index recommendations with CREATE INDEX statements\n- Query rewrites if applicable\n- Before/after EXPLAIN ANALYZE comparison\n- Monitoring queries for ongoing health",
  "strategy": "sequential",
  "max_agents": 2
}
```

### Frontend Performance
```json
{
  "goal": "Optimize frontend performance for [PAGE/COMPONENT]:\n\nCurrent metrics:\n- [LCP, FCP, CLS if known]\n- [bundle size if known]\n\nInvestigate:\n- Bundle size analysis (next build --analyze)\n- Unnecessary re-renders (React DevTools)\n- Image optimization (next/image usage)\n- Code splitting opportunities\n- API call optimization (deduplication, caching)\n- Suspense boundary placement\n\nDeliverable:\n- Specific optimizations with code changes\n- Before/after bundle size\n- Before/after Core Web Vitals\n- Lighthouse score improvement",
  "strategy": "parallel",
  "max_agents": 3
}
```

---

## 9. DevOps & Infrastructure

### Deployment Pipeline
```json
{
  "goal": "Create/improve CI/CD pipeline for [SERVICE]:\n\nCurrent state:\n- [manual steps]\n- [pain points]\n\nPipeline stages:\n1. Lint + type check\n2. Unit tests\n3. Build Docker image\n4. Integration tests\n5. Deploy to staging\n6. Smoke tests\n7. Deploy to production\n\nDeliverable:\n- GitHub Actions workflow file\n- Docker optimization (multi-stage, layer caching)\n- Rollback procedure\n- Status badges",
  "strategy": "sequential",
  "max_agents": 3
}
```

### Monitoring Setup
```json
{
  "goal": "Set up monitoring and alerting for [SERVICE/FEATURE]:\n\nMetrics to track:\n- [business metrics]\n- [technical metrics]\n- [error metrics]\n\nAlerts:\n- [threshold-based alerts]\n- [anomaly detection]\n\nDeliverable:\n- Prometheus metrics definitions\n- Grafana dashboard JSON\n- Alert rules with thresholds\n- Runbook links for each alert\n- On-call escalation config",
  "strategy": "parallel",
  "max_agents": 2
}
```

---

## 10. Evaluation & Quality

### Golden Dataset Expansion
```json
{
  "goal": "Expand evaluation golden dataset for [CATEGORY]:\n\nCurrent: [N] test cases\nTarget: [M] test cases\n\nNew cases should cover:\n- [gap 1: edge cases not tested]\n- [gap 2: new feature areas]\n- [gap 3: regression scenarios]\n\nFor each test case:\n- input_prompt: realistic user request\n- expected_behavior: what good output looks like\n- task_type: [category]\n- difficulty: easy/medium/hard\n- tags: relevant keywords\n\nDeliverable:\n- New test cases via POST /api/evaluation/datasets/{id}/test-cases/bulk\n- Coverage analysis: what scenarios are now covered\n- Run evaluation to establish baseline scores",
  "strategy": "parallel",
  "max_agents": 2
}
```

### Model Comparison Benchmark
```json
{
  "goal": "Benchmark [MODEL_A] vs [MODEL_B] on [DATASET]:\n\nDataset: [name or ID]\nModels: [model_a, model_b]\n\nCompare on:\n- Aggregate score\n- Per-category scores (code, rag, agent, creative)\n- Latency per request\n- Cost per evaluation run\n- Failure rate\n\nDeliverable:\n- POST /api/evaluation/benchmarks results\n- Winner recommendation with confidence\n- Category-specific recommendations\n- Cost-performance trade-off analysis",
  "strategy": "parallel",
  "max_agents": 2
}
```

---

## Quick Reference: Strategy Selection

| Use Case | Strategy | Why |
|----------|----------|-----|
| Feature implementation | `parallel` | Frontend + backend work simultaneously |
| Security audit | `sequential` | Findings inform deeper investigation |
| Architecture decision | `debate` | Agents argue positions, judge decides |
| Bug fix | `sequential` | Must understand before fixing |
| Documentation | `parallel` | Independent doc sections |
| Refactoring | `sequential` | Dependencies between changes |
| Testing | `parallel` | Test types are independent |
| Performance | `sequential` | Must measure before optimizing |

## Quick Reference: Agent Matching

| Task Type | Best Agent | Confidence |
|-----------|-----------|------------|
| code_generation | Coder | 0.90 |
| code_review | Reviewer | 0.80 |
| documentation | Writer | 0.80 |
| research | Researcher | 0.85 |
| data_analysis | Analyst | 0.75 |
| deployment | DevOps | 0.75 |
| system_design | Architect | 0.85 |
| debugging | Coder | 0.90 |
| security_audit | Reviewer | 0.80 |
| performance | Coder + Analyst | 0.85 |
