.DEFAULT_GOAL := help
PYTHON ?= .venv/bin/python
PIP ?= .venv/bin/pip

.PHONY: help setup install run bot api db-init migration migrate backup verificar test lint fmt typecheck check docker-up docker-down clean

help: ## Lista os alvos disponíveis
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

setup: ## Cria o venv e instala dependências de desenvolvimento
	python3 -m venv .venv
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"
	@test -f .env || cp .env.example .env
	@echo "Pronto. Edite o .env com os segredos (TD-001)."

install: ## Reinstala as dependências
	$(PIP) install -e ".[dev]"

run: ## Sobe bot + API conforme o .env
	$(PYTHON) -m oraculo

bot: ## Sobe apenas o bot Discord
	$(PYTHON) -m oraculo bot

api: ## Sobe apenas a API (health + webhooks)
	$(PYTHON) -m oraculo api

db-init: ## Cria o schema direto dos modelos (apenas desenvolvimento)
	$(PYTHON) -m oraculo db-init

migration: ## Gera migração Alembic: make migration m="descrição"
	.venv/bin/alembic revision --autogenerate -m "$(m)"

migrate: ## Aplica as migrações pendentes
	.venv/bin/alembic upgrade head

backup: ## Executa um backup imediato (RNF-005)
	$(PYTHON) -m oraculo backup

verificar: ## Valida a configuração para produção (RNF-003)
	$(PYTHON) -m oraculo verificar

test: ## Roda a suíte de testes
	$(PYTHON) -m pytest -q

lint: ## Verifica estilo e regras estáticas
	.venv/bin/ruff check src tests

fmt: ## Formata e corrige o que for automático
	.venv/bin/ruff check --fix src tests
	.venv/bin/ruff format src tests

typecheck: ## Checagem de tipos
	.venv/bin/mypy

check: lint test ## Lint + testes (usar antes de abrir PR)

docker-up: ## Sobe o ambiente completo (Postgres + Redis + app)
	docker compose up --build

docker-down: ## Derruba o ambiente e remove volumes órfãos
	docker compose down --remove-orphans

clean: ## Remove artefatos temporários
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache .mypy_cache
