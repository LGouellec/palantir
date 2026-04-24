FROM debian:stable-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y squid certbot apache2-utils ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Squid config + entrypoint
COPY squid.conf /etc/squid/squid.conf
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Dossier pour auth (optionnel)
RUN mkdir -p /etc/squid/auth

EXPOSE 3128 80 443

CMD ["/entrypoint.sh"]
