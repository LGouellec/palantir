REGISTRY ?= palantiracr.azurecr.io/palantir
WORKER_IMAGE ?= $(REGISTRY)/longbridge-worker
OPERATOR_IMAGE ?= $(REGISTRY)/longbridge-operator
TAG ?= 0.0.1
K8S_DIR ?= ../../infra/fetchers/longbridge-k8s

build: build-worker build-operator

build-worker:
	docker build -f worker/Dockerfile -t $(WORKER_IMAGE):$(TAG) .

build-operator:
	docker build -f operator/Dockerfile -t $(OPERATOR_IMAGE):$(TAG) .
