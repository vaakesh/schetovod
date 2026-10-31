.PHONY: up cloudbeaver down

up:
	docker compose up --build -d app frontend postgres redis worker scheduler

cloudbeaver:
	docker compose --profile tools up -d cloudbeaver

down:
	docker compose --profile tools down
