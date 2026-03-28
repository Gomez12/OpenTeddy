#!/usr/bin/env bash
#
# Build the custom OpenTeddy sandbox Docker image and register it
# with Docker Desktop so the agent can use it.
#
# Usage:
#   ./createdockerimage.sh            # build with default tag
#   ./createdockerimage.sh v1.2.3     # build with custom version tag
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
IMAGE_NAME="openteddy/sandbox"
VERSION="${1:-latest}"
TAG="${IMAGE_NAME}:${VERSION}"

export DOCKER_HOST="unix://$HOME/.docker/run/docker.sock"

echo "Building Docker image: ${TAG}"
echo "================================================"

docker build \
    -t "${TAG}" \
    -f "${SCRIPT_DIR}/docker/dockerfile" \
    "${SCRIPT_DIR}/docker"

# Also tag as latest if a version was given
if [ "${VERSION}" != "latest" ]; then
    docker tag "${TAG}" "${IMAGE_NAME}:latest"
    echo "Also tagged as: ${IMAGE_NAME}:latest"
fi

echo ""
echo "================================================"
echo "Image built successfully: ${TAG}"
echo ""
echo "Image size:"
docker images "${IMAGE_NAME}" --format "  {{.Repository}}:{{.Tag}}\t{{.Size}}"
echo ""
echo "To use this image, set in .env:"
echo "  SANDBOX_IMAGE=${TAG}"
echo ""
echo "Or run the agent directly:"
echo "  SANDBOX_IMAGE=${TAG} uv run agentic/agent.py \"your query\""
