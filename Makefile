SHELL := /bin/bash

.DEFAULT_GOAL := help

# Override these when Docker is exposed through a non-default executable:
#   make DOCKER=/path/to/docker local-deploy
WINDOWS_DOCKER := /mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe
DEFAULT_DOCKER := $(shell if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then command -v docker; elif [ -x "$(WINDOWS_DOCKER)" ] && "$(WINDOWS_DOCKER)" compose version >/dev/null 2>&1; then printf '%s' "$(WINDOWS_DOCKER)"; else printf '%s' docker; fi)
DOCKER ?= $(DEFAULT_DOCKER)
COMPOSE ?= "$(DOCKER)" compose

LOCAL_URL ?= https://127.0.0.1:8443
LOCAL_HOSTNAME ?= investmentsassistant.home.arpa
LAN_CIDR ?= 192.168.1.0/24
LOCAL_CERT_DIR ?= config/nginx/certs
LOCAL_CERT ?= $(LOCAL_CERT_DIR)/selfsigned.crt
LOCAL_KEY ?= $(LOCAL_CERT_DIR)/selfsigned.key
LAN_ALLOW_FILE ?= config/nginx/lan-allow.conf
SERVICE ?= app

.PHONY: help install dev-install run dev lint format test clean \
        docker-build docker-up docker-down docker-logs docker-restart docker-ps \
        gen-certs \
        local-docker-check local-env-check local-model-check local-tls \
        local-lan-config \
        local-build local-up local-wait local-ready local-status local-logs \
        local-down local-restart local-deploy

help:
	@echo "Investment Assistant — Available Commands"
	@echo "=========================================="
	@echo ""
	@echo "  Development"
	@echo "  -----------"
	@echo "  make install          Install Python dependencies"
	@echo "  make dev-install      Install development dependencies"
	@echo "  make run              Run locally with Uvicorn"
	@echo "  make dev              Run with auto-reload"
	@echo "  make lint             Run Ruff and mypy"
	@echo "  make format           Format source with Ruff"
	@echo "  make test             Run the test suite"
	@echo "  make clean            Remove Python/test caches"
	@echo ""
	@echo "  Modular local deployment"
	@echo "  ------------------------"
	@echo "  make local-env-check  Validate .env, auth, and Compose"
	@echo "  make local-model-check Verify the configured host GGUF exists"
	@echo "  make local-tls        Create/repair the local TLS certificate"
	@echo "  make local-lan-config Generate the Nginx LAN allow-list"
	@echo "  make local-build      Build the app image"
	@echo "  make local-up         Start the Compose stack"
	@echo "  make local-wait       Wait for the app readiness probe"
	@echo "  make local-ready      Probe the HTTPS readiness endpoint"
	@echo "  make local-status     Show service status"
	@echo "  make local-logs       Follow logs (SERVICE=app|nginx|postgres)"
	@echo "  make local-restart    Restart the app container"
	@echo "  make local-down       Stop the local stack"
	@echo "  make local-deploy     Run all deployment stages in order"
	@echo ""
	@echo "  Compatibility aliases"
	@echo "  ---------------------"
	@echo "  make docker-build     Alias for local-build"
	@echo "  make docker-up        Alias for local-up"
	@echo "  make docker-down      Alias for local-down"
	@echo "  make docker-logs      Alias for local-logs"
	@echo "  make docker-restart   Alias for local-restart"
	@echo "  make docker-ps        Alias for local-status"
	@echo "  make gen-certs        Alias for local-tls"

# ── Python / development ──────────────────────────────────────────────────────

install:
	poetry install --only main

dev-install:
	poetry install

run:
	poetry run uvicorn src.app:app --host 0.0.0.0 --port 8000

dev:
	poetry run uvicorn src.app:app --host 0.0.0.0 --port 8000 --reload

lint:
	poetry run ruff check src/
	poetry run mypy --follow-imports=skip src/

format:
	poetry run ruff format src/

test:
	poetry run pytest

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete
	rm -rf .pytest_cache/ .mypy_cache/ .ruff_cache/

# ── Modular local deployment ──────────────────────────────────────────────────

local-docker-check:
	@command -v "$(DOCKER)" >/dev/null 2>&1 || { \
		echo "ERROR: Docker executable not found: $(DOCKER)" >&2; exit 1; \
	}
	@$(COMPOSE) version >/dev/null 2>&1 || { \
		echo "ERROR: Docker Compose is not available through $(DOCKER)." >&2; exit 1; \
	}
	@"$(DOCKER)" info >/dev/null 2>&1 || { \
		echo "ERROR: Docker daemon is unavailable. Start Docker Desktop or the Docker service, then retry." >&2; exit 1; \
	}
	@echo "Docker ready: $(DOCKER)"

local-env-check: local-docker-check
	@set -euo pipefail; \
	test -f .env || { echo "ERROR: .env not found. Run: cp .env.example .env" >&2; exit 1; }; \
	read_env() { \
		value="$$(grep -E "^$${1}=" .env | tail -n1 | cut -d= -f2- || true)"; \
		value="$$(printf '%s' "$$value" | sed 's/[[:space:]]*#.*$$//' | sed 's/^[[:space:]]*//;s/[[:space:]]*$$//')"; \
		case "$$value" in \
			\'*) value="$${value#\'}"; value="$${value%\'}" ;; \
			\"*) value="$${value#\"}"; value="$${value%\"}" ;; \
		esac; \
		printf '%s' "$$value"; \
	}; \
	for key in POSTGRES_PASSWORD AUTH_PASSWORD_HASH AUTH_SESSION_SECRET BROKER_CREDENTIALS_KEY; do \
		value="$$(read_env "$$key")"; \
		[ -n "$$value" ] || { echo "ERROR: $$key is required in .env" >&2; exit 1; }; \
		case "$$value" in change_me*) echo "ERROR: $$key still has the example value" >&2; exit 1 ;; esac; \
	done; \
	auth_hash="$$(read_env AUTH_PASSWORD_HASH)"; \
	printf '%s' "$$auth_hash" | grep -qF 'scrypt$$v1$$' || { echo "ERROR: AUTH_PASSWORD_HASH must be generated by scripts/create_auth_hash.py" >&2; exit 1; }; \
	[ "$$(read_env AUTH_REQUIRE_LOGIN)" = true ] || { echo "ERROR: AUTH_REQUIRE_LOGIN must be true" >&2; exit 1; }; \
	[ "$$(read_env ENVIRONMENT)" != development ] || { echo "ERROR: ENVIRONMENT=development is not allowed for local deployment" >&2; exit 1; }; \
	broker_key="$$(read_env BROKER_CREDENTIALS_KEY)"; \
	printf '%s' "$$broker_key" | grep -Eq '^[A-Za-z0-9_-]{43}=$$' || { echo "ERROR: BROKER_CREDENTIALS_KEY is not a valid Fernet key" >&2; exit 1; }; \
	compose_environment="$$($(COMPOSE) config --environment)"; \
	compose_auth_hash="$$(printf '%s\n' "$$compose_environment" | awk -F= '$$1 == "AUTH_PASSWORD_HASH" { sub(/^[^=]*=/, ""); print; exit }')"; \
	[ "$$compose_auth_hash" = "$$auth_hash" ] || { echo "ERROR: Compose altered AUTH_PASSWORD_HASH; preserve its single quotes" >&2; exit 1; }; \
	echo "Environment and Compose configuration valid."

local-model-check:
	@set -euo pipefail; \
	test -f .env || { echo "ERROR: .env not found. Run: cp .env.example .env" >&2; exit 1; }; \
	model_path="$$(grep -E '^LLM_MODEL_PATH=' .env | tail -n1 | cut -d= -f2- | sed 's/^[[:space:]]*//;s/[[:space:]]*$$//')"; \
	case "$$model_path" in /app/models/*) ;; *) echo "ERROR: LLM_MODEL_PATH must start with /app/models/" >&2; exit 1 ;; esac; \
	host_model="models/$${model_path#/app/models/}"; \
	test -f "$$host_model" || { echo "ERROR: model file not found: $$host_model" >&2; exit 1; }; \
	echo "Model available: $$host_model"

local-lan-config:
	@set -euo pipefail; \
	python3 -c 'import ipaddress, sys; ipaddress.ip_network(sys.argv[1], strict=False)' "$(LAN_CIDR)"; \
	mkdir -p "$(dir $(LAN_ALLOW_FILE))"; \
	{ \
		echo "# Generated by make local-lan-config; do not edit by hand."; \
		echo "allow 127.0.0.1;"; \
		echo "allow 172.16.0.0/12;"; \
		echo "allow $(LAN_CIDR);"; \
		echo "deny all;"; \
	} > "$(LAN_ALLOW_FILE)"; \
	echo "Nginx LAN allow-list generated for $(LAN_CIDR)."

local-tls:
	@set -euo pipefail; \
	mkdir -p "$(LOCAL_CERT_DIR)"; \
	certificate_text="$$(openssl x509 -in "$(LOCAL_CERT)" -noout -text 2>/dev/null || true)"; \
	if ! printf '%s' "$$certificate_text" | grep -Fq 'DNS:localhost' \
		|| ! printf '%s' "$$certificate_text" | grep -Fq 'DNS:$(LOCAL_HOSTNAME)' \
		|| ! printf '%s' "$$certificate_text" | grep -q 'IP Address:127.0.0.1' \
		|| ! printf '%s' "$$certificate_text" | grep -q 'CA:TRUE'; then \
		echo "Generating local self-signed TLS certificate..."; \
		openssl req -x509 -nodes -days 3650 -newkey rsa:4096 \
			-keyout "$(LOCAL_KEY)" -out "$(LOCAL_CERT)" \
			-subj "/C=PT/ST=Local/L=Local/O=InvestmentAssistant/CN=$(LOCAL_HOSTNAME)" \
			-addext "basicConstraints=critical,CA:TRUE,pathlen:0" \
			-addext "keyUsage=critical,keyCertSign,cRLSign,digitalSignature,keyEncipherment" \
			-addext "extendedKeyUsage=serverAuth" \
			-addext "subjectAltName=DNS:localhost,DNS:$(LOCAL_HOSTNAME),IP:127.0.0.1"; \
		chmod 600 "$(LOCAL_KEY)"; \
	else \
		echo "Local TLS certificate already valid: $(LOCAL_CERT)"; \
	fi

local-build: local-env-check local-model-check local-lan-config local-tls
	$(COMPOSE) build app

local-up: local-docker-check local-lan-config
	$(COMPOSE) up -d
	@echo "Services started; UI: $(LOCAL_URL)"

local-wait: local-docker-check
	@set -euo pipefail; \
	healthy=0; \
	for attempt in $$(seq 1 60); do \
		if $(COMPOSE) exec -T app python -c \
			"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/ready', timeout=3)" \
			>/dev/null 2>&1; then \
			healthy=1; break; \
		fi; \
		sleep 2; \
	done; \
	$(COMPOSE) ps; \
	if [ "$$healthy" -ne 1 ]; then \
		$(COMPOSE) logs --tail=80 app; \
		echo "ERROR: app did not become ready" >&2; exit 1; \
	fi; \
	echo "App readiness probe passed."

local-ready: local-docker-check
	@curl --fail --silent --show-error --cacert "$(LOCAL_CERT)" "$(LOCAL_URL)/api/ready"
	@echo

local-status: local-docker-check
	$(COMPOSE) ps

local-logs: local-docker-check
	$(COMPOSE) logs -f $(SERVICE)

local-down: local-docker-check
	$(COMPOSE) down

local-restart: local-docker-check
	$(COMPOSE) restart app

# This is intentionally a sequence of independent targets rather than one
# opaque shell script. Each stage can be rerun while diagnosing a deployment.
local-deploy:
	@$(MAKE) --no-print-directory local-build
	@$(MAKE) --no-print-directory local-up
	@$(MAKE) --no-print-directory local-wait
	@$(MAKE) --no-print-directory local-ready
	@$(MAKE) --no-print-directory local-status
	@echo "Deployment complete: $(LOCAL_URL)"

# ── Compatibility aliases ─────────────────────────────────────────────────────

docker-build: local-build
docker-up: local-up
docker-down: local-down
docker-logs: local-logs
docker-restart: local-restart
docker-ps: local-status
gen-certs: local-tls
