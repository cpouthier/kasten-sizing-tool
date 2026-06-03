#!/bin/bash
# build-push.sh — Build and push sizing-tool image to Harbor
set -euo pipefail

REGISTRY="192.168.1.206"
IMAGE="${REGISTRY}/library/sizing-tool"
TAG="${1:-latest}"

echo "==> Building image ${IMAGE}:${TAG}..."
docker build -t "${IMAGE}:${TAG}" .

echo "==> Pushing to Harbor..."
docker push "${IMAGE}:${TAG}"

echo "==> Image available: ${IMAGE}:${TAG}"
