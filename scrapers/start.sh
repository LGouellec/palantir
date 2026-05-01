#!/bin/bash
# Script de démarrage rapide pour Docker Compose

set -e

echo "🚀 Démarrage du système Proxy + Scraper"
echo "========================================"
echo ""

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker n'est pas démarré"
    echo "   Démarrez Docker Desktop et réessayez"
    exit 1
fi

echo "✅ Docker est actif"
echo ""

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null; then
    echo "❌ docker-compose n'est pas installé"
    exit 1
fi

echo "✅ docker-compose disponible"
echo ""

# Build images if not exists
if [ "$1" == "--rebuild" ]; then
    echo "🔄 Rebuild complet (no cache)..."
    docker-compose build --no-cache
elif ! docker images | grep -q "scrapers.*proxy"; then
    echo "📦 Build des images Docker..."
    docker-compose build
else
    echo "✅ Images Docker déjà construites"
fi

echo ""

# Start proxy
echo "🔐 Démarrage du proxy MITM..."
docker-compose up -d proxy

# Wait for proxy to be ready
echo "⏳ Attente du démarrage du proxy..."
for i in {1..30}; do
    if curl -s http://localhost:8081 > /dev/null 2>&1; then
        echo "✅ Proxy démarré !"
        break
    fi
    sleep 1
    if [ $i -eq 30 ]; then
        echo "❌ Le proxy n'a pas démarré dans les temps"
        echo "   Vérifiez les logs: docker-compose logs proxy"
        exit 1
    fi
done

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  ✅ Système prêt !"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "📊 Interface web du proxy:"
echo "   http://localhost:8081"
echo ""
echo "🕷️  Pour lancer le scraper:"
echo "   docker-compose run --rm wsj-scraper python wsj_scraper.py --limit 5"
echo ""
echo "   Ou avec make:"
echo "   make scraper"
echo ""
echo "📋 Voir les logs:"
echo "   docker-compose logs -f proxy"
echo ""
echo "🛑 Arrêter:"
echo "   docker-compose down"
echo "   make down"
echo ""
echo "═══════════════════════════════════════════════════════════"
echo ""

# Optionally open web interface
if [ "$1" == "--open" ]; then
    echo "🌐 Ouverture de l'interface web..."
    sleep 2
    open http://localhost:8081 || xdg-open http://localhost:8081 || echo "Ouvrez http://localhost:8081 dans votre navigateur"
fi
