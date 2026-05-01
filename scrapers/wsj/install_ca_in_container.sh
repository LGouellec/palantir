#!/bin/bash
# Install mitmproxy CA certificate in the container
# This script is run automatically if the CA cert is available

CA_CERT="/root/.mitmproxy/mitmproxy-ca-cert.pem"

if [ -f "$CA_CERT" ]; then
    echo "📜 Installing mitmproxy CA certificate..."

    # Install in system CA store
    cp "$CA_CERT" /usr/local/share/ca-certificates/mitmproxy-ca.crt
    update-ca-certificates

    # For Node/Playwright
    export NODE_EXTRA_CA_CERTS="$CA_CERT"

    echo "✅ CA certificate installed"
else
    echo "⚠️  CA certificate not found at $CA_CERT"
    echo "   Using NODE_TLS_REJECT_UNAUTHORIZED=0 instead"
fi
