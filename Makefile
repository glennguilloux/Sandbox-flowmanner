# ============================================================
# Flowmanner — Makefile
# ============================================================
# Common development, testing, deployment, and utility targets.
#
# Usage:
#   make dev              # start full dev stack with hot reload
#   make test-backend     # run backend pytest
#   make deploy-frontend  # deploy frontend to VPS
#   make health           # check all services
# ============================================================

SHELL := /bin/bash
.DEFAULT_GOAL := help

# ---- Paths ----
PROJECT_ROOT := /opt/flowmanner
BACKEND_DIR  := $(PROJECT_ROOT)/backend
FRONTEND_DIR := /home/glenn/FlowmannerV2-frontend

# ---- Python ----
# Prefer the backend venv if it exists; fall back to bare python.
PYTHON := $(shell test -x $(BACKEND_DIR)/.venv/bin/python && echo $(BACKEND_DIR)/.venv/bin/python || echo python)
# Use python -m ruff when available, otherwise fall back to a ruff binary on PATH.
RUFF := $(shell $(PYTHON) -m ruff --version > /dev/null 2>&1 && echo "$(PYTHON) -m ruff" || (command -v ruff > /dev/null 2>&1 && echo ruff || echo echo 'ruff not found'))

# ---- Docker ----
COMPOSE_PROD := docker compose -f $(PROJECT_ROOT)/docker-compose.yml
COMPOSE_DEV  := docker compose -f $(PROJECT_ROOT)/docker-compose.yml -f $(PROJECT_ROOT)/docker-compose.dev.yml
BACKEND_IMAGE := workflows-backend:restored

# ---- VPS ----
VPS_HOST := 74.208.115.142
VPS_SSH  := ssh -i ~/.ssh/vps_flowmanner_new -o StrictHostKeyChecking=accept-new root@$(VPS_HOST)

# ---- Colors ----
GREEN  := \033[0;32m
YELLOW := \033[0;33m
RED    := \033[0;31m
RESET  := \033[0m

# ============================================================
# Development
# ============================================================

# ── Homelab dev (original, depends on production compose) ──

.PHONY: dev
dev: ## [HOMELAB] Start full dev environment with hot reload (requires production compose)
	@echo -e "$(GREEN)Starting dev environment...$(RESET)"
	$(COMPOSE_DEV) up -d
	@echo -e "$(GREEN)Backend: http://localhost:8000/docs$(RESET)"
	@echo -e "$(GREEN)Jaeger:  http://localhost:16686$(RESET)"

.PHONY: dev-backend
dev-backend: ## [HOMELAB] Start only backend in dev mode (dependencies must be running)
	@echo -e "$(GREEN)Starting backend in dev mode...$(RESET)"
	$(COMPOSE_DEV) up -d --no-deps backend
	@echo -e "$(GREEN)Backend: http://localhost:8000/docs$(RESET)"

.PHONY: dev-frontend
dev-frontend: ## Start frontend dev server
	@echo -e "$(GREEN)Starting frontend dev server...$(RESET)"
	cd $(FRONTEND_DIR) && npm run dev

.PHONY: dev-stop
dev-stop: ## [HOMELAB] Stop homelab dev environment
	$(COMPOSE_DEV) down

.PHONY: dev-logs
dev-logs: ## [HOMELAB] Tail homelab dev environment logs
	$(COMPOSE_DEV) logs -f

# ── Standalone dev (self-contained, works on any machine) ──

COMPOSE_STANDALONE := docker compose -f $(PROJECT_ROOT)/dev/docker-compose.dev.yml --env-file $(PROJECT_ROOT)/dev/.env.dev

.PHONY: dev-up
dev-up: ## Start self-contained dev environment (works on any machine with Docker)
	@echo -e "$(GREEN)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(RESET)"
	@echo -e "$(GREEN)  Flowmanner — Standalone Dev Environment$(RESET)"
	@echo -e "$(GREEN)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(RESET)"
	@echo ""
	@echo -e "$(YELLOW)Building dev image (first run may take a few minutes)...$(RESET)"
	$(COMPOSE_STANDALONE) build dev-backend
	@echo ""
	@echo -e "$(GREEN)Starting services...$(RESET)"
	$(COMPOSE_STANDALONE) up -d
	@echo ""
	@echo -e "$(GREEN)Waiting for backend to be healthy (first boot may take 60-90s)...$(RESET)"
	@for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do \
		if curl -sf http://localhost:8000/health > /dev/null 2>&1; then \
			echo -e "$(GREEN)✅ Backend is ready!$(RESET)"; \
			break; \
		fi; \
		sleep 3; \
		echo -n "."; \
	done
	@echo ""
	@echo -e "$(GREEN)==========================================$(RESET)"
	@echo -e "$(GREEN)  Flowmanner Dev is running!$(RESET)"
	@echo -e "$(GREEN)  API docs:  http://localhost:8000/docs$(RESET)"
	@echo -e "$(GREEN)  Health:    http://localhost:8000/health$(RESET)"
	@echo -e "$(GREEN)  RabbitMQ:  http://localhost:15672 (guest/dev_rabbitmq)$(RESET)"
	@echo -e "$(GREEN)==========================================$(RESET)"

.PHONY: dev-down
dev-down: ## Stop self-contained dev environment
	@echo -e "$(YELLOW)Stopping standalone dev environment...$(RESET)"
	$(COMPOSE_STANDALONE) down
	@echo -e "$(GREEN)Dev environment stopped.$(RESET)"

.PHONY: dev-reset
dev-reset: ## Stop self-contained dev environment AND delete all data volumes
	@echo -e "$(RED)WARNING: This will delete all dev data!$(RESET)"
	@read -p "Are you sure? [y/N] " yn; \
	case $$yn in \
		[Yy]* ) $(COMPOSE_STANDALONE) down -v; echo -e "$(GREEN)Dev environment reset.$(RESET)" ;;\
		* ) echo "Cancelled." ;;\
	esac

.PHONY: dev-logs-standalone
dev-logs-standalone: ## Tail standalone dev environment logs
	$(COMPOSE_STANDALONE) logs -f

.PHONY: dev-build
dev-build: ## Build the standalone dev backend image
	@echo -e "$(GREEN)Building dev backend image...$(RESET)"
	$(COMPOSE_STANDALONE) build dev-backend
	@echo -e "$(GREEN)Dev image built.$(RESET)"

# ============================================================
# Testing
# ============================================================

.PHONY: test
test: test-backend test-frontend ## Run all tests (backend + frontend)

.PHONY: guard-llm-success
guard-llm-success: ## CI guard: fail if any route_request result is read without a success check
	@echo -e "$(GREEN)Running LLM failure-propagation guard...$(RESET)"
	cd $(BACKEND_DIR) && $(PYTHON) scripts/guard_llm_success.py app

.PHONY: test-backend
test-backend: ## Run backend pytest
	@echo -e "$(GREEN)Running backend tests...$(RESET)"
	cd $(BACKEND_DIR) && $(PYTHON) -m pytest tests/ -v --tb=short

.PHONY: test-frontend
test-frontend: ## Run frontend vitest
	@echo -e "$(GREEN)Running frontend tests...$(RESET)"
	cd $(FRONTEND_DIR) && npx vitest run

.PHONY: test-e2e
test-e2e: ## Run Playwright e2e tests
	@echo -e "$(GREEN)Running e2e tests...$(RESET)"
	cd $(FRONTEND_DIR) && npx playwright test

.PHONY: test-backend-cov
test-backend-cov: ## Run backend tests with coverage
	@echo -e "$(GREEN)Running backend tests with coverage...$(RESET)"
	cd $(BACKEND_DIR) && $(PYTHON) -m pytest tests/ -v --tb=short --cov=app --cov-report=term-missing

.PHONY: reproduce
reproduce: ## Reproduce a failed CI run by RUN_ID
	@echo "RUN_ID=$(RUN_ID)"
	@echo "Planned artifact location: .github/actions/reproducer-artifacts/$(RUN_ID)"
	@echo "Reproducer artifacts not yet available. Planned: fetch artifact for RUN_ID=$(RUN_ID), restore env, re-run failed tests."

# ============================================================
# Deployment
# ============================================================

.PHONY: deploy
deploy: deploy-backend deploy-frontend ## Deploy all (backend + frontend)

.PHONY: deploy-backend
deploy-backend: ## Build and deploy backend (via deploy-backend.sh with precheck)
	bash $(PROJECT_ROOT)/deploy-backend.sh

.PHONY: deploy-frontend
deploy-frontend: ## Deploy frontend to VPS
	@echo -e "$(GREEN)Deploying frontend to VPS...$(RESET)"
	bash $(PROJECT_ROOT)/deploy-frontend.sh

.PHONY: deploy-all
deploy-all: ## Run deploy-all.sh script
	bash $(PROJECT_ROOT)/deploy-all.sh

# ============================================================
# Database
# ============================================================

.PHONY: db-migrate
db-migrate: ## Create a new Alembic migration (usage: make db-migrate MSG="description")
	@echo -e "$(GREEN)Creating migration: $(MSG)$(RESET)"
	docker compose exec backend alembic revision --autogenerate -m "$(MSG)"

.PHONY: db-upgrade
db-upgrade: ## Upgrade database to latest migration
	@echo -e "$(GREEN)Running alembic upgrade head...$(RESET)"
	docker compose exec backend alembic upgrade head

.PHONY: db-downgrade
db-downgrade: ## Downgrade one migration
	docker compose exec backend alembic downgrade -1

.PHONY: db-current
db-current: ## Show current migration version
	docker compose exec backend alembic current

.PHONY: db-history
db-history: ## Show migration history
	docker compose exec backend alembic history

.PHONY: db-backup
db-backup: ## Backup PostgreSQL database
	@echo -e "$(GREEN)Backing up PostgreSQL...$(RESET)"
	@mkdir -p $(PROJECT_ROOT)/backups
	docker exec workflow-postgres pg_dump -U flowmanner flowmanner | gzip > $(PROJECT_ROOT)/backups/flowmanner_$$(date +%Y%m%d_%H%M%S).sql.gz
	@echo -e "$(GREEN)Backup saved to $(PROJECT_ROOT)/backups/$(RESET)"

.PHONY: validate-migration
validate-migration: ## Pre-deploy migration validation gate: snapshot diff + offline SQL render
	@echo -e "$(GREEN)Running migration validation gate...$(RESET)"
	bash $(PROJECT_ROOT)/scripts/validate-migration.sh

.PHONY: snapshot-refresh
snapshot-refresh: ## Refresh backend/scripts/model_snapshot.json from the running backend container
	@echo -e "$(GREEN)Refreshing model metadata snapshot...$(RESET)"
	$(COMPOSE_PROD) exec -T backend python /app/scripts/snapshot_model_metadata.py > $(PROJECT_ROOT)/backend/scripts/model_snapshot.json
	@echo -e "$(GREEN)Snapshot refreshed: $(PROJECT_ROOT)/backend/scripts/model_snapshot.json$(RESET)"

.PHONY: db-seed-demo
db-seed-demo: ## Seed demo data (requires ENABLE_DEMO_MODE=true in .env)
	@echo -e "$(GREEN)Seeding demo data...$(RESET)"
	docker compose exec backend python scripts/seed_demo_data.py

# ============================================================
# Docker
# ============================================================

.PHONY: build
build: build-backend ## Build all images

.PHONY: build-backend
build-backend: ## Build backend Docker image
	@echo -e "$(GREEN)Building backend image: $(BACKEND_IMAGE)$(RESET)"
	docker build -t $(BACKEND_IMAGE) $(BACKEND_DIR)

.PHONY: build-backend-dev
build-backend-dev: ## Build backend dev image
	@echo -e "$(GREEN)Building backend dev image...$(RESET)"
	docker build -t workflows-backend:dev -f $(BACKEND_DIR)/Dockerfile.dev $(BACKEND_DIR)

.PHONY: ps
ps: ## Show container status
	@echo -e "$(GREEN)Homelab containers:$(RESET)"
	docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
	@echo ""
	@echo -e "$(GREEN)VPS containers:$(RESET)"
	$(VPS_SSH) "cd /opt/flowmanner && docker compose ps" 2>/dev/null || echo -e "$(YELLOW)Could not reach VPS$(RESET)"

.PHONY: logs
logs: ## Tail all container logs
	docker compose logs -f

.PHONY: logs-backend
logs-backend: ## Tail backend logs
	docker logs backend --tail 100 -f

.PHONY: logs-frontend
logs-frontend: ## Tail frontend logs (VPS)
	$(VPS_SSH) "docker logs flowmanner-frontend --tail 100" 2>/dev/null || echo -e "$(YELLOW)Could not reach VPS$(RESET)"

.PHONY: restart
restart: ## Restart all containers
	cd $(PROJECT_ROOT) && docker compose restart

.PHONY: restart-backend
restart-backend: ## Restart backend container
	cd $(PROJECT_ROOT) && docker compose restart backend

# ============================================================
# Utilities
# ============================================================

.PHONY: clean
clean: ## Remove build artifacts and caches
	@echo -e "$(YELLOW)Cleaning build artifacts...$(RESET)"
	find $(BACKEND_DIR) -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find $(BACKEND_DIR) -name '*.pyc' -delete 2>/dev/null || true
	rm -rf $(FRONTEND_DIR)/.next 2>/dev/null || true
	rm -rf $(FRONTEND_DIR)/node_modules/.cache 2>/dev/null || true
	@echo -e "$(GREEN)Clean complete.$(RESET)"

.PHONY: lint
lint: ## Run linters
	@echo -e "$(GREEN)Running backend linter...$(RESET)"
	cd $(BACKEND_DIR) && $(RUFF) check app/ --select E,F,W --ignore E501
	@echo -e "$(GREEN)Running frontend linter...$(RESET)"
	cd $(FRONTEND_DIR) && npx next lint 2>/dev/null || true

.PHONY: format
format: ## Run formatters
	@echo -e "$(GREEN)Formatting backend code...$(RESET)"
	cd $(BACKEND_DIR) && $(RUFF) format app/
	@echo -e "$(GREEN)Formatting frontend code...$(RESET)"
	cd $(FRONTEND_DIR) && npx prettier --write "src/**/*.{ts,tsx}" 2>/dev/null || true

.PHONY: health
health: ## Health check all services
	@echo -e "$(GREEN)=== Backend Health ===$(RESET)"
	@curl -sf http://127.0.0.1:8000/health 2>/dev/null && echo "" || echo -e "$(RED)Backend unreachable$(RESET)"
	@echo -e "$(GREEN)=== PostgreSQL ===$(RESET)"
	@docker exec workflow-postgres pg_isready -U flowmanner 2>/dev/null || echo -e "$(RED)PostgreSQL unreachable$(RESET)"
	@echo -e "$(GREEN)=== Redis ===$(RESET)"
	@docker exec workflow-redis redis-cli -a oFvdKE3HRxsm5CscZpifmwImDidNUmX5 ping 2>/dev/null || echo -e "$(RED)Redis unreachable$(RESET)"
	@echo -e "$(GREEN)=== Qdrant ===$(RESET)"
	@curl -sf http://127.0.0.1:6333/healthz 2>/dev/null && echo "" || echo -e "$(RED)Qdrant unreachable$(RESET)"
	@echo -e "$(GREEN)=== llama.cpp ===$(RESET)"
	@curl -sf http://localhost:11434/health 2>/dev/null && echo "" || echo -e "$(YELLOW)llama.cpp unreachable (may not be running)$(RESET)"
	@echo -e "$(GREEN)=== VPS Reachability ===$(RESET)"
	@$(VPS_SSH) "curl -sf http://10.99.0.3:8000/health > /dev/null && echo 'VPS can reach backend' || echo 'VPS cannot reach backend'" 2>/dev/null || echo -e "$(YELLOW)Could not reach VPS$(RESET)"

.PHONY: db-shell
db-shell: ## Open psql shell
	docker exec -it workflow-postgres psql -U flowmanner -d flowmanner

.PHONY: redis-shell
redis-shell: ## Open redis-cli shell
	docker exec -it workflow-redis redis-cli -a oFvdKE3HRxsm5CscZpifmwImDidNUmX5

.PHONY: backend-shell
backend-shell: ## Open bash shell in backend container
	docker exec -it backend bash

# ============================================================
# SDK Generation
# ============================================================

.PHONY: generate-sdk
generate-sdk: generate-ts-sdk generate-python-sdk ## Regenerate both TypeScript and Python SDKs

.PHONY: generate-ts-sdk
generate-ts-sdk: ## Regenerate TypeScript SDK from live OpenAPI spec
	@echo -e "$(GREEN)Generating TypeScript SDK...$(RESET)"
	bash $(PROJECT_ROOT)/scripts/generate-ts-sdk.sh

.PHONY: generate-python-sdk
generate-python-sdk: ## Regenerate Python SDK from live OpenAPI spec
	@echo -e "$(GREEN)Generating Python SDK...$(RESET)"
	bash $(PROJECT_ROOT)/scripts/generate-python-sdk.sh

.PHONY: check-sdk
check-sdk: ## CI hook — regenerate SDKs and fail if they differ from committed
	@echo -e "$(GREEN)Checking SDK is in sync with OpenAPI spec...$(RESET)"
	@# Regenerate
	@$(MAKE) generate-sdk --no-print-directory
	@# Check for differences in Python SDK (tracked in this repo)
	@if ! git diff --quiet -- sdk-python/ 2>/dev/null; then \
		echo -e "$(RED)❌ Python SDK is out of sync with OpenAPI spec!$(RESET)"; \
		echo -e "$(YELLOW)Run 'make generate-sdk' and commit the changes.$(RESET)"; \
		git diff --stat -- sdk-python/ 2>/dev/null; \
		exit 1; \
	else \
		echo -e "$(GREEN)✅ Python SDK is up to date.$(RESET)"; \
	fi
	@# Check TypeScript SDK (lives in frontend repo)
	@if [ -d "$(FRONTEND_DIR)/src/lib/sdk" ]; then \
		echo -e "$(YELLOW)⚠️  TypeScript SDK check skipped (frontend is in separate repo).$(RESET)"; \
		echo -e "$(YELLOW)   Run 'make generate-ts-sdk' and commit in frontend repo manually.$(RESET)"; \
	fi


# ============================================================
# Load Testing (k6)
# ============================================================

.PHONY: load-test load-test-mission load-test-chat load-test-dashboard

load-test: load-test-mission load-test-chat load-test-dashboard ## Run all k6 load tests

load-test-mission: ## k6: mission create + fetch + list (5 VUs, 2m)
	@echo "$(CYAN)Running mission load test...$(NC)"
	@BASE_URL=http://localhost:8000 k6 run tests/load/mission-create.js

load-test-chat: ## k6: chat thread + message (3 VUs, 1.5m)
	@echo "$(CYAN)Running chat load test...$(NC)"
	@BASE_URL=http://localhost:8000 k6 run tests/load/chat-message.js

load-test-dashboard: ## k6: dashboard API parallel load (10 VUs, 3m)
	@echo "$(CYAN)Running dashboard load test...$(NC)"
	@BASE_URL=http://localhost:8000 k6 run tests/load/dashboard-load.js
# ============================================================
# Help
# ============================================================

.PHONY: help
help: ## Show this help message
	@echo ""
	@echo "Flowmanner Development Commands"
	@echo "==============================="
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(RESET) %s\n", $$1, $$2}'
	@echo ""
