#!/bin/bash

# Build Linux wheels for Gobstopper framework
# This script uses Docker with manylinux images to build compatible Linux wheels

set -e

echo "🚀 Building Linux wheels for Gobstopper..."

# Create dist directory if it doesn't exist
mkdir -p dist

# Build main package (Python + Rust extension) for x86_64
echo "📦 Building WOPR package for Linux x86_64 (includes Python sources)..."
docker run --rm -v $(pwd):/io \
    --platform linux/amd64 \
    ghcr.io/pyo3/maturin:latest \
    build --release \
    --out /io/dist \
    --interpreter python3.10 python3.11 python3.12 python3.13 \
    --manylinux 2014

# Build main package (Python + Rust extension) for aarch64
echo "📦 Building WOPR package for Linux aarch64 (includes Python sources)..."
docker run --rm -v $(pwd):/io \
    --platform linux/arm64 \
    ghcr.io/pyo3/maturin:latest \
    build --release \
    --out /io/dist \
    --interpreter python3.10 python3.11 python3.12 python3.13 \
    --manylinux 2014

echo "✅ Linux wheels built successfully!"
echo "📁 Wheels are in the dist/ directory:"
ls -la dist/*.whl | grep linux