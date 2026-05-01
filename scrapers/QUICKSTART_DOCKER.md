# 🚀 Quick Start - Docker Compose

Lancer le proxy MITM et le scraper WSJ avec Docker en 3 commandes.

## ⚡ Installation ultra-rapide

```bash
cd /Users/sylvainlegouellec/repos/palantir-trading-engine/scrapers

# 1. Build les images (première fois uniquement)
make build

# 2. Démarrer le proxy avec interface web
make proxy

# 3. Lancer le scraper
make scraper
```

**C'est tout !** 🎉

Ouvrez http://localhost:8081 pour voir le traffic intercepté en temps réel.

## 📊 Interface Web

L'interface web mitmproxy vous montre :
- ✅ Toutes les requêtes HTTPS déchiffrées
- ✅ Headers complets
- ✅ Body des requêtes (JSON déchiffré)
- ✅ Body des réponses
- ✅ Timing de chaque requête
- ✅ Possibilité de modifier et rejouer

**URL** : http://localhost:8081

## 🎯 Commandes principales

```bash
# Démarrage
make proxy          # Démarrer le proxy
make scraper        # Lancer le scraper (une fois)
make up             # Tout démarrer

# Monitoring
make logs           # Voir tous les logs
make logs-proxy     # Logs du proxy uniquement
make web            # Ouvrir l'interface web

# Arrêt
make down           # Arrêter tout
make clean          # Tout nettoyer
```

## 🔧 Configuration

### Changer le script de modification

Éditez `docker-compose.yml` :

```yaml
services:
  proxy:
    command: ["--listen-host", "0.0.0.0", "--listen-port", "8080", 
              "--web-host", "0.0.0.0", "-s", "interactive_modifier.py"]
              #                                 ^^^^^^^^^^^^^^^^^^^^^^
              #                                 Changer ici
```

Scripts disponibles :
- `datadome_modifier.py` - Modifications DataDome configurables
- `datadome_logger.py` - Juste observer
- `interactive_modifier.py` - Auto + manuel
- `modify_requests.py` - Exemples généraux

Puis :
```bash
make restart-proxy
```

### Modifier les transformations DataDome

Éditez `proxy/datadome_modifier.py` :

```python
MODIFICATIONS = {
    "add_fields": {
        "custom_field": "my_value",
    },
    "replace_values": {
        "fingerprint": "CUSTOM_FINGERPRINT",
        "sessionId": "NEW_SESSION_123",
    },
}
```

Redémarrez le proxy :
```bash
make restart-proxy
```

Les modifications sont appliquées immédiatement !

### Changer les paramètres du scraper

Éditez `docker-compose.yml` :

```yaml
services:
  wsj-scraper:
    environment:
      - BASE_URL=https://www.wsj.com/economy  # URL de départ
    command: python wsj_scraper.py --limit 10 --no-headless
```

Ou lancez directement avec des args custom :
```bash
docker-compose run --rm wsj-scraper python wsj_scraper.py \
  --limit 20 \
  --base-url https://www.wsj.com/world \
  --verbose
```

## 📁 Où sont les données ?

### Articles scrapés

```bash
# Dans le répertoire data/
ls -la data/

# Ou dans le container
docker-compose run --rm wsj-scraper ls -la /app/articles
```

### Traffic intercepté

Sauvegarder depuis l'interface web :
1. Ouvrir http://localhost:8081
2. File → Save
3. Choisir le format (.mitm ou .har)

## 🐛 Troubleshooting

### Le scraper ne peut pas se connecter au proxy

```bash
# Vérifier que le proxy est démarré
make ps

# Vérifier les logs
make logs-proxy

# Tester la connexion
make test
```

### L'interface web n'est pas accessible

```bash
# Vérifier que le proxy est démarré
docker-compose ps

# Redémarrer le proxy
make restart-proxy

# Vérifier les logs
make logs-proxy
```

### Les modifications ne sont pas appliquées

```bash
# Redémarrer le proxy (charge les nouveaux scripts)
make restart-proxy

# Vérifier les logs pour les erreurs Python
make logs-proxy | grep -i error
```

## 🎓 Workflows

### Workflow 1 : Development (live reload)

```bash
# 1. Démarrer le proxy
make dev

# 2. Éditer proxy/datadome_modifier.py
vim proxy/datadome_modifier.py

# 3. Redémarrer le proxy (charge les modifs)
make restart-proxy

# 4. Tester
make scraper

# 5. Voir le résultat dans http://localhost:8081
```

### Workflow 2 : Quick test

```bash
# Tout en une commande
make quickstart
# Puis
make scraper
```

### Workflow 3 : Debug

```bash
# 1. Démarrer le proxy
make proxy

# 2. Ouvrir un shell dans le scraper
make shell

# 3. Dans le shell du container :
python wsj_scraper.py --limit 1 --verbose --no-headless

# 4. Voir le traffic dans http://localhost:8081
```

### Workflow 4 : Production

```bash
# Démarrer en mode daemon
make up

# Voir les logs
make logs

# Arrêter
make down
```

## 📊 Exemples concrets

### Exemple 1 : Logger toutes les requêtes DataDome

```bash
# 1. Éditer docker-compose.yml
# Changer command pour utiliser datadome_logger.py

# 2. Démarrer
make restart-proxy

# 3. Lancer le scraper
make scraper

# 4. Voir les logs
make logs-proxy
```

Vous verrez :
```
🎯 REQUEST #1
Method: POST
URL: https://api-js.datadome.co/validate
Headers: {...}
Body: {...}

📨 RESPONSE
Status: 200
Body: {...}
```

### Exemple 2 : Modifier le fingerprint DataDome

```bash
# 1. Éditer proxy/datadome_modifier.py
MODIFICATIONS = {
    "replace_values": {
        "fingerprint": "CUSTOM_FINGERPRINT_12345",
    },
}

# 2. Redémarrer le proxy
make restart-proxy

# 3. Lancer le scraper
make scraper

# 4. Dans les logs du proxy, vous verrez :
# 🔄 Replaced: fingerprint
#    Old: abc...xyz
#    New: CUSTOM_FINGERPRINT_12345
```

### Exemple 3 : Bloquer Google Analytics

```bash
# 1. Éditer proxy/modify_requests.py
blocked_domains = ["google-analytics.com", "googletagmanager.com"]

# 2. Utiliser ce script dans docker-compose.yml
command: [..., "-s", "modify_requests.py"]

# 3. Redémarrer
make restart-proxy

# Les requêtes vers ces domaines seront bloquées !
```

## 🎉 Résumé ultra-court

```bash
make build      # Une seule fois
make proxy      # Démarrer le proxy
make scraper    # Lancer le scraper
```

Ouvrez http://localhost:8081 → Vous voyez tout le traffic HTTPS déchiffré ! 🚀

## 📚 Documentation

- **README_DOCKER.md** - Documentation complète
- **MODIFY_REQUESTS.md** - Guide de modification des requêtes
- **mitmproxy_setup.md** - Documentation mitmproxy

## ⚡ Aide

```bash
make help   # Liste toutes les commandes disponibles
```
