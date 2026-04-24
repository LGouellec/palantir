# Mode Kafka pour le scraper WSJ distribué

## Vue d'ensemble

Le mode Kafka remplace l'ancienne implémentation Redis pour la distribution des URLs entre les pods workers. 

### Architecture

```
┌─────────────────┐
│   Coordinator   │
│     Pod 0       │
└────────┬────────┘
         │
         │ Produit les URLs
         ▼
┌─────────────────────────┐
│  Kafka Topic: wsj-urls  │
│   (Multiple partitions) │
└────────┬────────────────┘
         │
         │ Consumer Group: wsj-scraper-workers
         │
    ┌────┴────┬─────────┬─────────┐
    ▼         ▼         ▼         ▼
┌────────┐┌────────┐┌────────┐┌────────┐
│Worker 1││Worker 2││Worker 3││Worker 4│
│ Pod 1  ││ Pod 2  ││ Pod 3  ││ Pod 4  │
└────────┘└────────┘└────────┘└────────┘
    │         │         │         │
    └─────────┴────┬────┴─────────┘
                   ▼
         ┌───────────────────┐
         │  Kafka Topic:     │
         │  wsj-articles     │
         └───────────────────┘
```

## Avantages par rapport à Redis

1. **Consumer Group Protocol**: Kafka gère automatiquement la distribution des partitions entre les workers
2. **Résilience**: Les messages ne sont pas perdus même si un worker crash
3. **Scalabilité**: Ajout/suppression de workers sans configuration manuelle
4. **Offset Management**: Kafka track automatiquement les messages consommés
5. **Architecture unifiée**: Tout passe par Kafka (URLs et articles)

## Configuration

### Variables d'environnement

```bash
# Configuration du pod
export POD_INDEX=0              # Index du pod (0 = coordinator, 1+ = workers)
export TOTAL_PODS=5             # Nombre total de pods

# Mode de distribution
export DISTRIBUTION=kafka       # Mode kafka

# Configuration Kafka pour la distribution des URLs
export KAFKA_URLS_TOPIC=wsj-urls                  # Topic pour les URLs
export KAFKA_URLS_GROUP=wsj-scraper-workers       # Consumer group

# Configuration Kafka pour les articles scrapés
export KAFKA_ENABLED=true
export KAFKA_TOPIC=wsj-articles
export KAFKA_BOOTSTRAP_SERVERS=localhost:9092
```

### Fichier de configuration Kafka

Créer `kafka_config.properties`:

```properties
# Kafka brokers
bootstrap.servers=localhost:9092

# Producer settings
acks=all
retries=3
max.in.flight.requests.per.connection=1
compression.type=snappy
linger.ms=10

# Security (si nécessaire)
# security.protocol=SASL_SSL
# sasl.mechanism=PLAIN
# sasl.username=...
# sasl.password=...
```

## Utilisation

### Coordinator (Pod 0)

Le coordinator découvre les URLs et les produit dans le topic Kafka:

```bash
POD_INDEX=0 TOTAL_PODS=5 python wsj_scraper_distributed.py \
  --mode kafka \
  --limit 1000 \
  --kafka-urls-topic wsj-urls \
  --kafka-urls-consumer-group wsj-scraper-workers \
  --kafka --kafka-topic wsj-articles
```

### Workers (Pods 1-4)

Les workers consomment les URLs depuis Kafka et scrappent les articles:

```bash
# Worker 1
POD_INDEX=1 TOTAL_PODS=5 python wsj_scraper_distributed.py \
  --mode kafka \
  --kafka-urls-topic wsj-urls \
  --kafka-urls-consumer-group wsj-scraper-workers \
  --kafka --kafka-topic wsj-articles \
  --delay 2.0

# Worker 2
POD_INDEX=2 TOTAL_PODS=5 python wsj_scraper_distributed.py \
  --mode kafka \
  --kafka-urls-topic wsj-urls \
  --kafka-urls-consumer-group wsj-scraper-workers \
  --kafka --kafka-topic wsj-articles \
  --delay 2.0

# ... etc pour les autres workers
```

## Déploiement Kubernetes

### ConfigMap pour la configuration Kafka

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: kafka-config
data:
  kafka_config.properties: |
    bootstrap.servers=kafka-service:9092
    acks=all
    retries=3
    compression.type=snappy
```

### Deployment pour le Coordinator

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: wsj-scraper-coordinator
spec:
  replicas: 1
  selector:
    matchLabels:
      app: wsj-scraper
      role: coordinator
  template:
    metadata:
      labels:
        app: wsj-scraper
        role: coordinator
    spec:
      containers:
      - name: scraper
        image: wsj-scraper:latest
        env:
        - name: POD_INDEX
          value: "0"
        - name: TOTAL_PODS
          value: "5"
        - name: DISTRIBUTION
          value: "kafka"
        - name: KAFKA_ENABLED
          value: "true"
        - name: KAFKA_BOOTSTRAP_SERVERS
          value: "kafka-service:9092"
        - name: KAFKA_TOPIC
          value: "wsj-articles"
        - name: KAFKA_URLS_TOPIC
          value: "wsj-urls"
        - name: KAFKA_URLS_GROUP
          value: "wsj-scraper-workers"
        volumeMounts:
        - name: kafka-config
          mountPath: /app/kafka_config.properties
          subPath: kafka_config.properties
      volumes:
      - name: kafka-config
        configMap:
          name: kafka-config
```

### StatefulSet pour les Workers

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: wsj-scraper-workers
spec:
  serviceName: wsj-scraper-workers
  replicas: 4
  selector:
    matchLabels:
      app: wsj-scraper
      role: worker
  template:
    metadata:
      labels:
        app: wsj-scraper
        role: worker
    spec:
      containers:
      - name: scraper
        image: wsj-scraper:latest
        env:
        - name: POD_INDEX
          valueFrom:
            fieldRef:
              fieldPath: metadata.labels['apps.kubernetes.io/pod-index']
        - name: TOTAL_PODS
          value: "5"
        - name: DISTRIBUTION
          value: "kafka"
        - name: KAFKA_ENABLED
          value: "true"
        - name: KAFKA_BOOTSTRAP_SERVERS
          value: "kafka-service:9092"
        - name: KAFKA_TOPIC
          value: "wsj-articles"
        - name: KAFKA_URLS_TOPIC
          value: "wsj-urls"
        - name: KAFKA_URLS_GROUP
          value: "wsj-scraper-workers"
        volumeMounts:
        - name: kafka-config
          mountPath: /app/kafka_config.properties
          subPath: kafka_config.properties
      volumes:
      - name: kafka-config
        configMap:
          name: kafka-config
```

## Monitoring

### Vérifier les messages dans le topic

```bash
# Voir les URLs dans le topic
kafka-console-consumer --bootstrap-server localhost:9092 \
  --topic wsj-urls \
  --from-beginning

# Voir les articles scrapés
kafka-console-consumer --bootstrap-server localhost:9092 \
  --topic wsj-articles \
  --from-beginning
```

### Vérifier les consumer groups

```bash
# Liste des consumer groups
kafka-consumer-groups --bootstrap-server localhost:9092 --list

# Détails du consumer group
kafka-consumer-groups --bootstrap-server localhost:9092 \
  --group wsj-scraper-workers \
  --describe
```

## Scalabilité

Pour ajouter plus de workers:

```bash
# Scaler le StatefulSet
kubectl scale statefulset wsj-scraper-workers --replicas=8
```

Kafka redistribuera automatiquement les partitions entre les nouveaux workers.

## Dépannage

### Les workers ne reçoivent pas de messages

1. Vérifier que le topic existe:
   ```bash
   kafka-topics --bootstrap-server localhost:9092 --list
   ```

2. Vérifier les offsets du consumer group:
   ```bash
   kafka-consumer-groups --bootstrap-server localhost:9092 \
     --group wsj-scraper-workers --describe
   ```

3. Reset les offsets si nécessaire:
   ```bash
   kafka-consumer-groups --bootstrap-server localhost:9092 \
     --group wsj-scraper-workers \
     --topic wsj-urls \
     --reset-offsets --to-earliest --execute
   ```

### Le coordinator ne produit pas de messages

1. Vérifier les logs du coordinator
2. Vérifier la connectivité Kafka
3. Vérifier les permissions de production sur le topic
