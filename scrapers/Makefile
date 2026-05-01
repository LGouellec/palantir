.PHONY: help build up down logs proxy scraper clean rebuild test

help:
	@echo "🐳 Docker Compose - Proxy MITM + WSJ Scraper"
	@echo "=============================================="
	@echo ""
	@echo "Setup:"
	@echo "  make build       - Build toutes les images Docker"
	@echo "  make rebuild     - Rebuild depuis zéro (no cache)"
	@echo ""
	@echo "Start/Stop:"
	@echo "  make up          - Démarrer tous les services"
	@echo "  make down        - Arrêter tous les services"
	@echo "  make proxy       - Démarrer uniquement le proxy"
	@echo ""
	@echo "Monitoring:"
	@echo "  make logs        - Voir les logs de tous les services"
	@echo "  make logs-proxy  - Voir les logs du proxy uniquement"
	@echo "  make web         - Ouvrir l'interface web du proxy"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean       - Supprimer containers et volumes"
	@echo "  make clean-all   - Supprimer tout (images incluses)"
	@echo ""
	@echo "Testing:"
	@echo "  make test        - Test de connexion au proxy"
	@echo "  make shell       - Shell dans le container scraper"
	@echo ""

build:
	@echo "📦 Building Docker images..."
	docker-compose build

rebuild:
	@echo "🔄 Rebuilding from scratch (no cache)..."
	docker-compose build --no-cache

up:
	@echo "🚀 Starting all services..."
	docker-compose up -d
	@echo "✅ Services started"
	@echo "📊 Proxy web interface: http://localhost:8081"

down:
	@echo "🛑 Stopping all services..."
	docker-compose down -v
	@echo "✅ Services stopped"

proxy:
	@echo "🔐 Starting proxy..."
	docker-compose up -d proxy
	@sleep 3
	@echo "✅ Proxy started"
	@echo "📊 Web interface: http://localhost:8081"
	@echo "📡 Proxy: http://localhost:8080"

logs:
	docker-compose logs -f

logs-proxy:
	docker-compose logs -f proxy

logs-scraper:
	docker-compose logs -f wsj-scraper

web:
	@echo "🌐 Opening proxy web interface..."
	@open http://localhost:8081 || xdg-open http://localhost:8081 || echo "Open http://localhost:8081 in your browser"

ps:
	docker-compose ps

clean:
	@echo "🧹 Cleaning up containers and volumes..."
	docker-compose down -v
	@echo "✅ Cleaned"

clean-all:
	@echo "🧹 Removing everything (containers, volumes, images)..."
	docker-compose down -v --rmi all
	@echo "✅ Everything removed"

test:
	@echo "🧪 Testing proxy connection..."
	@docker-compose run --rm wsj-scraper curl -v http://proxy:8080 || echo "❌ Proxy not reachable"
	@echo ""
	@echo "🧪 Testing web interface..."
	@curl -s http://localhost:8081 > /dev/null && echo "✅ Web interface OK" || echo "❌ Web interface not accessible"

shell:
	@echo "💻 Opening shell in scraper container..."
	docker-compose run --rm wsj-scraper bash

shell-proxy:
	@echo "💻 Opening shell in proxy container..."
	docker-compose exec proxy sh

# Quick start workflow
quickstart: build proxy
	@echo ""
	@echo "✅ Quick start complete!"
	@echo ""
	@echo "Next steps:"
	@echo "  1. Open http://localhost:8081 to see the proxy web interface"
	@echo "  2. Run: make scraper"
	@echo "  3. Watch the traffic in the web interface!"
	@echo ""

# Development workflow
dev: proxy
	@echo ""
	@echo "🔥 Development mode"
	@echo ""
	@echo "Proxy is running with live reload"
	@echo "Edit proxy/*.py and restart with: make restart-proxy"
	@echo ""
	@echo "To run scraper: make scraper"
	@echo ""

restart-proxy:
	@echo "🔄 Restarting proxy..."
	docker-compose restart proxy
	@echo "✅ Proxy restarted (new scripts loaded)"

# Production mode
prod:
	@echo "🚀 Starting in production mode..."
	docker-compose -f docker-compose.yml up -d
	@echo "✅ Production services started"
