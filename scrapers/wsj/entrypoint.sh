#!/bin/bash
set -e

# Run CA installation script first
/usr/local/bin/install_ca_in_container.sh

# Execute python with all passed arguments
exec python "$@"
