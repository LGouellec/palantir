#!/bin/bash
set -e

DOMAIN="${DOMAIN:-proxy.example.com}"
EMAIL="${EMAIL:-admin@example.com}"

# 1. Certificat Let's Encrypt si absent
# if [ ! -f /etc/letsencrypt/live/$DOMAIN/fullchain.pem ]; then
#   certbot certonly --standalone \
#     --preferred-challenges http \
#     -d "$DOMAIN" \
#     --email "$EMAIL" \
#     --agree-tos \
#     --non-interactive
# fi

# 2. Lancer Squid
/usr/sbin/squid -N -f /etc/squid/squid.conf
