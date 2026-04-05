#!/usr/bin/env bash
set -euo pipefail

# Build the Windows .exe inside Docker using Wine + PyInstaller
# Output: dist/ZH-Map-Maker.exe

echo "Building ZH-Map-Maker.exe via Docker..."

# Build and extract the exe
DOCKER_BUILDKIT=1 docker build --output dist/ .

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
