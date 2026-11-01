DEV := docker compose -f compose.yml -f compose.dev.yml
PROD := docker compose -f compose.yml -f compose.prod.yml
# telemetry is on in dev only when the local server-observability is running
OBS_COLLECTOR := docker ps -q --filter network=observability --filter label=com.docker.compose.service=otel-collector --filter status=running

.PHONY: up down user prod-deploy prod-status prod-logs prod-stop prod-user

up: export OTEL_SDK_DISABLED = $(if $(shell $(OBS_COLLECTOR)),false,true)
up: export DEPLOYMENT_ENVIRONMENT = development
up:
	docker network inspect observability >/dev/null 2>&1 || docker network create observability
	$(DEV) up --build -d

down:
	$(DEV) down

# make user login=ivan, asks for the password
user:
	$(DEV) exec app python -m auth.create_user --login "$(login)"

prod-deploy:
	bash scripts/deploy-prod.sh

prod-status:
	$(PROD) ps

prod-logs:
	$(PROD) logs --tail 100 -f

prod-stop:
	$(PROD) stop

prod-user:
	$(PROD) exec app python -m auth.create_user --login "$(login)"
