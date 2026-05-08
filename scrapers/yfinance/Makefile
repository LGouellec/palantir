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
		-v $(PWD)/top_stocks.txt:/app/top_stocks.txt:ro \
		$(IMAGE_NAME):$(VERSION)
	@echo "✅ Container started: $(CONTAINER_NAME)"

run-interactive: ## Run container (interactive)
	@echo "Starting container in interactive mode..."
	docker run -it \
		--name $(CONTAINER_NAME) \
		-v nasdaq-cache:/app/.nasdaq_cache \
		-v $(PWD)/top_stocks.txt:/app/top_stocks.txt:ro \
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

shell: ## Open shell in running container
	docker exec -it $(CONTAINER_NAME) /bin/bash

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