.PHONY: up cloudbeaver down user prod-deploy prod-status prod-logs prod-stop prod-user

up:
	docker compose up --build -d app frontend caddy postgres redis worker scheduler

cloudbeaver:
	docker compose --profile tools up -d cloudbeaver

down:
	docker compose --profile tools down

# make user login=ivan, asks for the password
user:
	docker compose exec app python -m auth.create_user --login "$(login)"

prod-deploy:
	bash scripts/deploy-prod.sh

prod-status:
	docker compose -f docker-compose-prod.yml ps

prod-logs:
	docker compose -f docker-compose-prod.yml logs --tail 100 -f

prod-stop:
	docker compose -f docker-compose-prod.yml stop

prod-user:
	docker compose -f docker-compose-prod.yml exec app python -m auth.create_user --login "$(login)"
