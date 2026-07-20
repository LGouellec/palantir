# syntax=docker/dockerfile:1
FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src
COPY proxy.csproj ./
RUN dotnet restore proxy.csproj
COPY . ./
RUN dotnet publish proxy.csproj -c Release -o /app --no-restore /p:UseAppHost=false

FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS runtime
ARG BUILD_DATE
ARG VERSION
ARG REVISION
LABEL org.opencontainers.image.title="flink-proxy" \
      org.opencontainers.image.description="REST external table proxy for Flink KEY_SEARCH_AGG over CosmosDB" \
      org.opencontainers.image.source="https://github.com/LGouellec/palantir-trading-engine" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${REVISION}"
WORKDIR /app
COPY --from=build /app ./
EXPOSE 8080
ENV ASPNETCORE_URLS=http://+:8080
# Run as the non-root user shipped in the aspnet image.
USER $APP_UID
ENTRYPOINT ["dotnet", "flink-proxy.dll"]
