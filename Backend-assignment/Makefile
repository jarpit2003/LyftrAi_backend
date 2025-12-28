.PHONY: help install dev test lint format clean build run docker-build docker-run docker-stop docker-clean up down logs

# Default target
help:
	@echo "Available commands:"
	@echo "  install      Install dependencies"
	@echo "  dev          Run development server"
	@echo "  test         Run tests"
	@echo "  lint         Run linting"
	@echo "  format       Format code"
	@echo "  clean        Clean temporary files"
	@echo "  build        Build application"
	@echo "  run          Run production server"
	@echo "  docker-build Build Docker image"
	@echo "  docker-run   Run Docker container"
	@echo "  docker-stop  Stop Docker containers"
	@echo "  docker-clean Clean Docker resources"

# Installation
install:
	pip install -r requirements.txt
	pip install -r requirements-dev.txt

# Development
dev:
	python -m app.main

# Testing
test:
	pytest tests/ -v --cov=app --cov-report=html --cov-report=term-missing

test-fast:
	pytest tests/ -v -x

test-watch:
	ptw tests/ --runner "python -m pytest -v"

# Code quality
lint:
	flake8 app/ tests/
	mypy app/
	black --check app/ tests/
	isort --check-only app/ tests/

format:
	black app/ tests/
	isort app/ tests/

# Cleaning
clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf .coverage
	rm -rf htmlcov/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/

# Build and run
build:
	python -m build

run:
	python -m app.main

# Docker commands
docker-build:
	docker build -t webhook-message-service .

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f

docker-run:
	docker compose up -d --build

docker-dev:
	docker compose up -d --build

docker-stop:
	docker compose down

docker-clean:
	docker compose down -v
	docker system prune -f

# Database commands
db-init:
	python -c "from app.storage import StorageManager; import asyncio; asyncio.run(StorageManager().initialize())"

db-clean:
	rm -f ./data/*.db

# Logs
logs:
	docker compose logs -f

logs-dev:
	docker compose logs -f

# Health check
health:
	curl -f http://localhost:8000/health || echo "Service not healthy"

# Environment setup
env-dev:
	cp .env.example .env

env-prod:
	cp .env.example .env.production

# Dependencies
deps-update:
	pip-compile requirements.in
	pip-compile requirements-dev.in

deps-install:
	pip install -r requirements.txt
	pip install -r requirements-dev.txt

# Security
security:
	bandit -r app/
	safety check

# Performance
perf:
	pytest tests/ --benchmark-only

# Documentation
docs:
	mkdocs serve

docs-build:
	mkdocs build

# Release
release: clean test lint build
	@echo "Ready for release"

# All checks
check: lint test security
	@echo "All checks passed"
