#!/bin/bash
# build-push.sh — Build and push the kasten-sizing-tool image to any container registry.
#
# Usage:
#   ./build-push.sh [TAG] [REGISTRY/IMAGE]
#
# Examples:
#   ./build-push.sh                                        # latest, uses IMAGE env var or prompts
#   ./build-push.sh 1.2.0                                  # tag 1.2.0
#   ./build-push.sh latest docker.io/myorg/kasten-sizing-tool
#   ./build-push.sh latest ghcr.io/myorg/kasten-sizing-tool
#   ./build-push.sh latest 123456789.dkr.ecr.eu-west-1.amazonaws.com/kasten-sizing-tool
#
# Environment variables:
#   IMAGE   — full image name without tag (overrides the second positional argument)
#             e.g.  IMAGE=docker.io/myorg/kasten-sizing-tool ./build-push.sh 1.0.0

set -euo pipefail

# ── Arguments ────────────────────────────────────────────────
# Default image (Docker Hub): docker.io/cpouthier/kasten-toolbox
# Default tag for that image : sizing-tool
#
# Override via env var or positional args to push to your own registry.
TAG="${1:-latest}"
IMAGE="${2:-${IMAGE:-}}"

# ── Resolve image name ────────────────────────────────────────
if [[ -z "${IMAGE}" ]]; then
  echo "No image name provided."
  echo "Set the IMAGE environment variable or pass it as the second argument."
  echo ""
  echo "  Examples:"
  echo "    IMAGE=docker.io/myorg/kasten-sizing-tool ./build-push.sh"
  echo "    ./build-push.sh latest docker.io/myorg/kasten-sizing-tool"
  echo "    ./build-push.sh latest ghcr.io/myorg/kasten-sizing-tool"
  exit 1
fi

FULL="${IMAGE}:${TAG}"

# ── Build ─────────────────────────────────────────────────────
echo "==> Building ${FULL} ..."
docker build -t "${FULL}" .

# ── Push ──────────────────────────────────────────────────────
echo "==> Pushing ${FULL} ..."
docker push "${FULL}"

echo ""
echo "==> Done. Image available: ${FULL}"
echo ""
echo "    Update sizing-tool.yaml with:"
echo "      image: ${FULL}"
