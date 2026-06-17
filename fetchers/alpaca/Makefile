REGISTRY ?= palantiracr.azurecr.io/palantir
WORKER_IMAGE ?= $(REGISTRY)/alpaca-news-fetcher
TAG ?= 0.0.1
K8S_DIR ?= ../../infra/fetchers/alpaca-k8s

build:
	docker build -f worker/Dockerfile -t $(WORKER_IMAGE):$(TAG) .

push:
	docker push $(WORKER_IMAGE):$(TAG)
