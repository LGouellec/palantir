# Build context is the `scrapers/` directory (see docker-compose.yml), so all
# COPY paths are prefixed with `twitter/`, matching the other scrapers.

FROM node:20-slim AS build
WORKDIR /app
COPY twitter/package.json ./
RUN npm install
COPY twitter/tsconfig.json ./
COPY twitter/src ./src
RUN npm run build

FROM node:20-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production

# Production deps only
COPY twitter/package.json ./
RUN npm install --omit=dev && npm cache clean --force

# Compiled output
COPY --from=build /app/dist ./dist

# Entrypoint
COPY twitter/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Persisted state
RUN mkdir -p /app/history /app/output

# Defaults (override via docker-compose / -e)
ENV SEARCH_MODE=Latest \
    MAX_TWEETS=50 \
    DELAY_MS=1500 \
    CONTINUOUS=false \
    CONTINUOUS_INTERVAL=300 \
    KAFKA_ENABLED=false \
    KAFKA_TOPIC=twitter-tweets \
    HISTORY_FILE=/app/history/scraped_history.json \
    HISTORY_TTL_DAYS=30 \
    TZ=UTC

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
