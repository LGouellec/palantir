# Makefile for YFinance Analytics Engine Docker operations

# Variables
IMAGE_NAME := yfinance-analytics-engine
VERSION := latest
CONTAINER_NAME := yfinance-scraper

# Targets
.PHONY: help build run stop logs shell clean test push pull up down

help: ## Show this help message
	@echo "YFinance Analytics Engine - Docker Commands"
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-15s %s\n", $$1, $$2}'

build: ## Build Docker image
	@echo "Building Docker image..."
	docker build -t $(IMAGE_NAME):$(VERSION) .
	@echo "✅ Image built: $(IMAGE_NAME):$(VERSION)"

run: ## Run container (detached)
	@echo "Starting container..."
	docker run -d \
		--name $(CONTAINER_NAME) \
		-v nasdaq-cache:/app/.nasdaq_cache \
		-v $(PWD)/top_250_stocks.txt:/app/top_250_stocks.txt:ro \
		$(IMAGE_NAME):$(VERSION)
	@echo "✅ Container started: $(CONTAINER_NAME)"

run-interactive: ## Run container (interactive)
	@echo "Starting container in interactive mode..."
	docker run -it \
		--name $(CONTAINER_NAME) \
		-v nasdaq-cache:/app/.nasdaq_cache \
		-v $(PWD)/top_250_stocks.txt:/app/top_250_stocks.txt:ro \
		$(IMAGE_NAME):$(VERSION) \
		/bin/bash

stop: ## Stop running container
	@echo "Stopping container..."
	docker stop $(CONTAINER_NAME) || true
	@echo "✅ Container stopped"

rm: stop ## Remove container
	@echo "Removing container..."
	docker rm $(CONTAINER_NAME) || true
	@echo "✅ Container removed"

logs: ## Show container logs
	docker logs -f $(CONTAINER_NAME)

logs-tail: ## Show last 100 lines of logs
	docker logs --tail 100 $(CONTAINER_NAME)

shell: ## Open shell in running container
	docker exec -it $(CONTAINER_NAME) /bin/bash

stats: ## Show container resource usage
	docker stats $(CONTAINER_NAME)

inspect: ## Inspect container
	docker inspect $(CONTAINER_NAME)

restart: ## Restart container
	@echo "Restarting container..."
	docker restart $(CONTAINER_NAME)
	@echo "✅ Container restarted"

clean: rm ## Remove container and image
	@echo "Removing image..."
	docker rmi $(IMAGE_NAME):$(VERSION) || true
	@echo "✅ Image removed"

clean-all: ## Remove everything (containers, images, volumes)
	@echo "Removing all containers, images, and volumes..."
	docker stop $(CONTAINER_NAME) || true
	docker rm $(CONTAINER_NAME) || true
	docker rmi $(IMAGE_NAME):$(VERSION) || true
	docker volume rm nasdaq-cache || true
	@echo "✅ Everything removed"

# Docker Compose targets
up: ## Start with docker-compose
	@echo "Starting services with docker-compose..."
	docker-compose up -d
	@echo "✅ Services started"

up-kafka: ## Start with Kafka (docker-compose.with-kafka.yml)
	@echo "Starting services with Kafka..."
	docker-compose -f docker-compose.with-kafka.yml up -d
	@echo "✅ Services started (with Kafka)"
	@echo "Kafka UI: http://localhost:8080"

down: ## Stop docker-compose services
	@echo "Stopping services..."
	docker-compose down
	@echo "✅ Services stopped"

down-kafka: ## Stop Kafka services
	@echo "Stopping Kafka services..."
	docker-compose -f docker-compose.with-kafka.yml down
	@echo "✅ Kafka services stopped"

down-volumes: ## Stop services and remove volumes
	@echo "Stopping services and removing volumes..."
	docker-compose down -v
	@echo "✅ Services and volumes removed"

ps: ## Show running containers
	docker-compose ps

# Testing targets
test: ## Run tests in container
	@echo "Running tests..."
	docker run --rm $(IMAGE_NAME):$(VERSION) python test_refactoring.py
	@echo "✅ Tests completed"

test-batch: ## Run batch monitoring tests
	@echo "Running batch monitoring tests..."
	docker run --rm $(IMAGE_NAME):$(VERSION) python test_batch_monitoring.py
	@echo "✅ Batch tests completed"

# Development targets
dev-build: ## Build image for development (with tests)
	@echo "Building development image..."
	docker build --target builder -t $(IMAGE_NAME):dev .
	@echo "✅ Dev image built"

dev-shell: ## Open shell in dev container
	docker run -it --rm \
		-v $(PWD):/app \
		$(IMAGE_NAME):dev \
		/bin/bash

# Registry targets
tag: ## Tag image for registry
	@read -p "Enter registry URL (e.g., ghcr.io/username): " REGISTRY; \
	docker tag $(IMAGE_NAME):$(VERSION) $$REGISTRY/$(IMAGE_NAME):$(VERSION)
	@echo "✅ Image tagged for registry"

push: ## Push image to registry
	@read -p "Enter registry URL (e.g., ghcr.io/username): " REGISTRY; \
	docker push $$REGISTRY/$(IMAGE_NAME):$(VERSION)
	@echo "✅ Image pushed to registry"

pull: ## Pull image from registry
	@read -p "Enter registry URL (e.g., ghcr.io/username): " REGISTRY; \
	docker pull $$REGISTRY/$(IMAGE_NAME):$(VERSION)
	@echo "✅ Image pulled from registry"

# Utility targets
prune: ## Prune unused Docker resources
	@echo "Pruning unused Docker resources..."
	docker system prune -f
	@echo "✅ Pruned"

prune-all: ## Prune all unused Docker resources (including volumes)
	@echo "Pruning all unused Docker resources..."
	docker system prune -af --volumes
	@echo "✅ All pruned"

health: ## Check container health
	@docker inspect $(CONTAINER_NAME) | grep -A 10 '"Health"' || echo "No health check configured"

version: ## Show image version and size
	@docker images $(IMAGE_NAME):$(VERSION) --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"

# Quick commands
rebuild: clean build ## Clean and rebuild image

rerun: rm run ## Remove and restart container

# Default target
.DEFAULT_GOAL := help
