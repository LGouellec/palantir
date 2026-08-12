REGISTRY ?= palantiracr.azurecr.io/palantir
WORKER_IMAGE ?= $(REGISTRY)/trading-agent
TAG ?= 0.0.1
K8S_DIR ?= ../infra/agent-k8s

build:
	docker build -f Dockerfile -t $(WORKER_IMAGE):$(TAG) .

push:
	docker push $(WORKER_IMAGE):$(TAG)
