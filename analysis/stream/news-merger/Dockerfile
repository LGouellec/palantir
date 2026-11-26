# syntax=docker/dockerfile:1
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /src
COPY pom.xml ./
RUN --mount=type=cache,target=/root/.m2 mvn -B -q dependency:go-offline
COPY src ./src
# Tests run in CI before the image build; skip them here to keep multi-arch builds fast.
RUN --mount=type=cache,target=/root/.m2 mvn -B -q package -DskipTests

FROM eclipse-temurin:21-jre AS runtime
ARG BUILD_DATE
ARG VERSION
ARG REVISION
LABEL org.opencontainers.image.title="news-merger" \
      org.opencontainers.image.description="Kafka Streams app merging scraper news topics into financial-news" \
      org.opencontainers.image.source="https://github.com/LGouellec/palantir-trading-engine" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${REVISION}"
WORKDIR /app
COPY --from=build /src/target/news-merger.jar ./news-merger.jar
RUN useradd --system --uid 10001 news-merger
USER 10001
ENV JAVA_OPTS="-XX:MaxRAMPercentage=75"
ENTRYPOINT ["sh", "-c", "exec java $JAVA_OPTS -jar /app/news-merger.jar"]
