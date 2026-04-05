#!/usr/bin/env bash
set -euo pipefail

# Build the Windows .exe inside Docker using Wine + PyInstaller
# Output: dist/ZH-Map-Maker.exe

echo "Building ZH-Map-Maker.exe via Docker..."

# Use --platform flag on non-amd64 hosts (e.g. Apple Silicon)
PLATFORM_FLAG=""
if [ "$(uname -m)" != "x86_64" ]; then
    PLATFORM_FLAG="--platform linux/amd64"
fi

mkdir -p dist
docker build $PLATFORM_FLAG -t zh-map-builder .
docker create --name zh-extract zh-map-builder true 2>/dev/null && \
    docker cp zh-extract:/app/dist/ZH-Map-Maker.exe dist/ZH-Map-Maker.exe && \
    docker rm zh-extract

if [ -f dist/ZH-Map-Maker.exe ]; then
    echo ""
    echo "========================================="
    echo "  Build complete!"
    echo "  Output: dist/ZH-Map-Maker.exe"
    echo "  Size: $(du -h dist/ZH-Map-Maker.exe | cut -f1)"
    echo "========================================="
else
    echo "Build failed - no exe produced"
    exit 1
fi
