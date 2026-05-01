# 🐳 Docker Compose - Proxy MITM + Scraper WSJ

Configuration Docker Compose complète avec :
- **mitmproxy** - Proxy MITM avec interface web et scripts de modification
- **wsj-scraper** - Scraper WSJ configuré pour passer par le proxy

## 📦 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Docker Host                          │
│                                                             │
│  ┌──────────────────┐           ┌──────────────────┐      │
│  │   mitmproxy      │◄──────────│  wsj-scraper     │      │
│  │                  │   proxy    │                  │      │
│  │  - Intercept     │  :8080     │  - Playwright    │      │
│  │  - Modify        │            │  - Scrapling     │      │
│  │  - Log           │            │                  │      │
│  │                  │            │                  │      │
│  │  Web UI :8081    │            │                  │      │
│  └──────────────────┘            └──────────────────┘      │
│           │                                                 │
│           └─► Internet (WSJ, DataDome, etc.)              │
└─────────────────────────────────────────────────────────────┘
```

## 🚀 Démarrage rapide

### 1. Build des images

```bash
cd /Users/sylvainlegouellec/repos/palantir-trading-engine/scrapers

# Build le proxy
docker-compose build proxy

# Build le scraper
docker-compose build wsj-scraper
```

### 2. Lancer le proxy

```bash
# Lancer uniquement le proxy avec interface web
docker-compose up -d proxy

# Vérifier les logs
docker-compose logs -f proxy

# Attendre que le proxy soit prêt
# Vous devriez voir: "Web server listening at http://0.0.0.0:8081"
```

**Interface web** : Ouvrez http://localhost:8081

### 3. Lancer le scraper

```bash
# Lancer le scraper (une seule fois)
docker-compose run --rm wsj-scraper python wsj_scraper.py --limit 5 --verbose

# Ou lancer en mode daemon
docker-compose up -d wsj-scraper
docker-compose logs -f wsj-scraper
```

## 📊 Voir le traffic intercepté

### Option 1 : Interface Web (recommandé)

1. Ouvrir http://localhost:8081
2. Cliquer sur une requête pour voir :
   - Headers complets
   - Body déchiffré (JSON, etc.)
   - Response complète
   - Timing

### Option 2 : Logs du proxy

```bash
# Voir les logs en temps réel
docker-compose logs -f proxy

# Vous verrez les modifications appliquées :
# 🎯 DataDome Request #1
# 📦 Original Payload: {...}
# ✅ Modified Payload: {...}
```

## 🔧 Configuration

### Changer le script de modification

Éditez `docker-compose.yml` :

```yaml
services:
  proxy:
    # ...
    command: ["--listen-host", "0.0.0.0", "--listen-port", "8080", "--web-host", "0.0.0.0", "-s", "interactive_modifier.py"]
    #                                                                                              ^^^^^^^^^^^^^^^^^^^^^^^^
    #                                                                                              Changer ici
```

Scripts disponibles :
- `datadome_modifier.py` - Modifications configurables DataDome
- `datadome_logger.py` - Juste observer (pas de modification)
- `modify_requests.py` - Exemples généraux
- `interactive_modifier.py` - Auto + manuel dans l'interface web

Puis :
```bash
docker-compose restart proxy
```

### Modifier les paramètres du scraper

Éditez `docker-compose.yml` :

```yaml
services:
  wsj-scraper:
    environment:
      - BASE_URL=https://www.wsj.com/economy  # Changer l'URL
    command: python wsj_scraper.py --limit 10 --no-headless  # Changer les args
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
    },
}
```

Les changements sont **live** (pas besoin de rebuild) :
```bash
docker-compose restart proxy
```

## 📁 Structure des fichiers

```
scrapers/
├── docker-compose.yml           # Configuration principale
├── README_DOCKER.md            # Ce fichier
│
├── proxy/
│   ├── Dockerfile.mitmproxy    # Image du proxy
│   ├── datadome_modifier.py    # Scripts de modification
│   ├── datadome_logger.py
│   ├── modify_requests.py
│   └── interactive_modifier.py
│
├── wsj/
│   ├── Dockerfile              # Image du scraper
│   ├── requirements.txt
│   ├── wsj_scraper.py
│   └── install_ca_in_container.sh
│
└── data/                       # Articles extraits (volume)
    └── ...
```

## 🔐 Certificats SSL

### Option 1 : Ignorer les erreurs SSL (par défaut)

```yaml
environment:
  - NODE_TLS_REJECT_UNAUTHORIZED=0
```

**Avantages** : Fonctionne immédiatement
**Inconvénients** : Moins sécurisé

### Option 2 : Installer le certificat CA (recommandé pour production)

1. **Générer le CA** (au premier lancement du proxy) :
```bash
docker-compose up -d proxy
sleep 5  # Attendre la génération du CA
```

2. **Installer dans le scraper** :
```bash
# Exec dans le container scraper
docker-compose run --rm wsj-scraper /usr/local/bin/install_ca_in_container.sh
```

3. **Retirer la variable** `NODE_TLS_REJECT_UNAUTHORIZED=0` du docker-compose.yml

## 🎯 Commandes utiles

### Proxy

```bash
# Démarrer
docker-compose up -d proxy

# Logs en temps réel
docker-compose logs -f proxy

# Redémarrer (après changement de script)
docker-compose restart proxy

# Arrêter
docker-compose stop proxy
```

### Scraper

```bash
# Run une seule fois
docker-compose run --rm wsj-scraper python wsj_scraper.py --limit 5

# Run avec args custom
docker-compose run --rm wsj-scraper python wsj_scraper.py \
  --limit 10 \
  --base-url https://www.wsj.com/economy \
  --verbose

# Exec dans le container (debugging)
docker-compose run --rm wsj-scraper bash
```

### Tout ensemble

```bash
# Démarrer tout
docker-compose up -d

# Logs de tout
docker-compose logs -f

# Arrêter tout
docker-compose down

# Tout supprimer (images, volumes, etc.)
docker-compose down -v --rmi all
```

## 📊 Exporter le traffic

### Depuis l'interface web

1. Ouvrir http://localhost:8081
2. File → Save
3. Sauvegarder en `.mitm` ou `.har`

### Depuis le container

```bash
# Sauvegarder le traffic dans un fichier
docker-compose run --rm proxy mitmdump \
  --listen-port 8080 \
  -w /root/.mitmproxy/traffic.mitm \
  -s datadome_modifier.py

# Copier depuis le container
docker cp mitmproxy:/root/.mitmproxy/traffic.mitm ./traffic.mitm

# Rejouer plus tard
docker-compose run --rm proxy mitmproxy -r /root/.mitmproxy/traffic.mitm
```

## 🐛 Troubleshooting

### Le scraper ne peut pas se connecter au proxy

```bash
# Vérifier que le proxy est bien démarré
docker-compose ps

# Vérifier les logs du proxy
docker-compose logs proxy

# Vérifier la connectivité réseau
docker-compose run --rm wsj-scraper curl -v http://proxy:8080
```

### Erreur SSL: CERTIFICATE_UNKNOWN

→ Le certificat CA n'est pas installé. Utilisez `NODE_TLS_REJECT_UNAUTHORIZED=0` ou installez le CA.

### L'interface web n'est pas accessible

```bash
# Vérifier que le port 8081 est bien exposé
docker-compose ps

# Vérifier les logs
docker-compose logs proxy | grep "Web server"

# Tester depuis le host
curl http://localhost:8081
```

### Les modifications ne sont pas appliquées

```bash
# Vérifier que le bon script est chargé
docker-compose exec proxy ps aux | grep mitmweb

# Redémarrer le proxy
docker-compose restart proxy

# Vérifier les logs pour les erreurs Python
docker-compose logs proxy | grep -i error
```

## 📈 Production

Pour la production, créez un `docker-compose.prod.yml` :

```yaml
version: '3.8'

services:
  proxy:
    restart: always
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

  wsj-scraper:
    restart: on-failure
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G
```

Puis :
```bash
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

## 🎉 Résumé

```bash
# 1. Build
docker-compose build

# 2. Démarrer le proxy
docker-compose up -d proxy

# 3. Ouvrir l'interface web
open http://localhost:8081

# 4. Lancer le scraper
docker-compose run --rm wsj-scraper python wsj_scraper.py --limit 5

# 5. Voir le traffic modifié dans l'interface web !
```

**Tout le traffic HTTPS est déchiffré et modifiable en temps réel !** 🚀
