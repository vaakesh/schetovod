DEV := docker compose -f compose.yml -f compose.dev.yml
PROD := docker compose -f compose.yml -f compose.prod.yml

.PHONY: up down user prod-deploy prod-status prod-logs prod-stop prod-user

up:
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
