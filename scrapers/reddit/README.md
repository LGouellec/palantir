# Reddit Universal Scraper (wi#th Kafka Plugin)

This repository is a fork of the original `reddit-universal-scraper` created by [ksanjeev284](https://github.com/ksanjeev284/reddit-universal-scraper).
The upstream project provides a flexible, modular Reddit scraping framework, and this fork extends it with Kafka publishing capabilities.

Why this fork exits :
- I implemented a Kafka plugin to allow scraped Reddit data to be streamed directly into a Kafka cluster.
- A [pull request](https://github.com/ksanjeev284/reddit-universal-scraper/pull/10) was submitted to the original repository to contribute this feature back to the community:

## PR: Add Kafka plugin support

As of now, the PR has not yet been merged, so this fork serves as a working version including the Kafka integration.

What’s included in this fork
- Kafka plugin module for publishing scraped items to a Kafka topic
- Configuration options for Kafka brokers, topics, and serialization
- Full compatibility with the upstream scraper architecture
- All existing features from the original project

## Repository

You can find and use this Kafka‑enabled version here:

[👉 LGouellec/reddit-universal-scraper](https://github.com/LGouellec/reddit-universal-scraper/tree/kafka_plugin)

## Docker image

Docker image with the Kafka plugin

`ghcr.io/lgouellec/reddit-universal-scraper:0.0.6` 