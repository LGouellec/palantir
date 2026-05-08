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

logs:
	docker-compose logs -f

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
