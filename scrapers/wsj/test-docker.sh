#!/bin/bash

docker-compose build

docker run -v $(pwd)/data:/data -e KAFKA_ENABLED=false -it wsj-coordinator:latest /app/wsj_scraper.py --base-url "https://www.wsj.com/world" --no-pagination --verbose --save-local --output-dir /data/articles