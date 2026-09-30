.PHONY: up cloudbeaver down

up:
	docker compose up --build -d app frontend postgres

cloudbeaver:
	docker compose --profile tools up -d cloudbeaver

down:
	docker compose --profile tools down
