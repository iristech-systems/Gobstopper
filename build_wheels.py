#!/usr/bin/env python3
"""
Cross-platform wheel builder for Gobstopper framework
Supports macOS, Linux (x86_64 and ARM64), and Windows
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path

def run_command(cmd, check=True):
    """Run a command and print the output."""
    print(f"🔨 Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, check=check, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr)
    return result

def build_rust_wheels_local(python_versions, platform=None, features: str | None = None):
    """Build Rust extension wheels locally using maturin.
    Respects Cargo features via --features or MATURIN_FEATURES env.
    """
    manifest_path = "rust/wopr_core_rs/Cargo.toml"
    features = features or os.environ.get("MATURIN_FEATURES")

    cmd = [
        "maturin", "build", "--release",
        "--out", "dist",
        "--manifest-path", manifest_path,
        "--interpreter"
    ] + [f"python{v}" for v in python_versions]

    if platform:
        cmd.extend(["--target", platform])
    if features:
        cmd.extend(["--features", features])

    run_command(cmd)

def build_rust_wheels_docker(python_versions, arch="x86_64", features: str | None = None):
    """Build Rust extension wheels using Docker and manylinux."""
    platform_flag = ""
    if arch == "aarch64":
        platform_flag = "--platform linux/arm64"

    features = features or os.environ.get("MATURIN_FEATURES")

    # Build Rust extension
    docker_cmd = [
        "docker", "run", "--rm", "-v", f"{os.getcwd()}:/io"
    ]

    if platform_flag:
        docker_cmd.extend(platform_flag.split())

    docker_cmd.extend([
        "ghcr.io/pyo3/maturin:latest",
        "build", "--release",
        "--out", "/io/dist",
        "--interpreter"
    ])
    docker_cmd.extend([f"python{v}" for v in python_versions])
    docker_cmd.extend([
        "--manylinux", "2014",
        "--manifest-path", "/io/rust/wopr_core_rs/Cargo.toml"
    ])
    if features:
        docker_cmd.extend(["--features", features])

    run_command(docker_cmd)

def build_main_package_local():
    """Build the main Python package locally."""
    run_command(["uv", "build", "--out-dir", "dist"])

def build_main_package_docker(python_versions=None, arch: str | None = None):
    """Build the main Python package using Docker for a specific architecture (or default)."""
    python_versions = python_versions or ["3.10", "3.11", "3.12", "3.13"]
    docker_cmd = [
        "docker", "run", "--rm", "-v", f"{os.getcwd()}:/io",
    ]
    if arch == "aarch64":
        docker_cmd.extend(["--platform", "linux/arm64"])
    elif arch == "x86_64":
        docker_cmd.extend(["--platform", "linux/amd64"])
    docker_cmd.extend([
        "ghcr.io/pyo3/maturin:latest",
        "build", "--release",
        "--out", "/io/dist",
        "--interpreter",
    ])
    docker_cmd.extend([f"python{v}" for v in python_versions])
    docker_cmd.extend(["--manylinux", "2014"])
    run_command(docker_cmd)

def main():
    parser = argparse.ArgumentParser(description="Build Gobstopper wheels")
    parser.add_argument("--platform", choices=["local", "macos", "linux", "windows", "all"], 
                       default="local", help="Target platform")
    parser.add_argument("--arch", choices=["x86_64", "aarch64", "both"], 
                       default="x86_64", help="Target architecture (Linux only)")
    parser.add_argument("--python-versions", nargs="+", default=["3.10", "3.11", "3.12", "3.13"],
                       help="Python versions to build for")
    parser.add_argument("--features", default=os.environ.get("MATURIN_FEATURES", None),
                       help="Comma-separated Cargo features to enable for the Rust core (defaults to MATURIN_FEATURES env or Cargo defaults)")
    parser.add_argument("--rust-only", action="store_true",
                       help="Build only Rust extension, not main package")
    parser.add_argument("--main-only", action="store_true", 
                       help="Build only main package, not Rust extension")
    
    args = parser.parse_args()
    
    # Create dist directory
    os.makedirs("dist", exist_ok=True)
    
    print(f"🚀 Building wheels for platform: {args.platform}")
    print(f"📋 Python versions: {', '.join(args.python_versions)}")
    if args.features:
        print(f"🧩 Cargo features: {args.features}")
    
    if args.platform == "local" or args.platform == "macos":
        if not args.main_only:
            print("📦 Building Rust extension wheels (local)...")
            build_rust_wheels_local(args.python_versions, features=args.features)
        
        if not args.rust_only:
            print("📦 Building main package (local)...")
            build_main_package_local()
            
    elif args.platform == "linux":
        if not args.main_only:
            if args.arch == "both":
                for arch in ["x86_64", "aarch64"]:
                    print(f"📦 Building Rust extension wheels for Linux {arch}...")
                    build_rust_wheels_docker(args.python_versions, arch, features=args.features)
            else:
                print(f"📦 Building Rust extension wheels for Linux {args.arch}...")
                build_rust_wheels_docker(args.python_versions, args.arch, features=args.features)
        
        if not args.rust_only:
            if args.arch == "both":
                for arch in ["x86_64", "aarch64"]:
                    print(f"📦 Building main package for Linux {arch} (Docker)...")
                    build_main_package_docker(args.python_versions, arch=arch)
            else:
                print(f"📦 Building main package for Linux {args.arch} (Docker)...")
                build_main_package_docker(args.python_versions, arch=args.arch)
            
    elif args.platform == "all":
        # Build for all platforms
        print("📦 Building for all platforms...")
        
        # macOS (local)
        if not args.main_only:
            print("📦 Building Rust extension for macOS...")
            build_rust_wheels_local(args.python_versions, features=args.features)
        
        # Linux x86_64 and ARM64
        if not args.main_only:
            for arch in ["x86_64", "aarch64"]:
                print(f"📦 Building Rust extension for Linux {arch}...")
                build_rust_wheels_docker(args.python_versions, arch, features=args.features)
        
        # Main package
        if not args.rust_only:
            print("📦 Building main package...")
            build_main_package_local()
    
    print("✅ Build complete!")
    print("📁 Built packages:")
    
    # List all wheel files
    dist_path = Path("dist")
    for wheel in sorted(dist_path.glob("*.whl")):
        print(f"  - {wheel.name}")
    
    # List source distributions
    for sdist in sorted(dist_path.glob("*.tar.gz")):
        print(f"  - {sdist.name}")

if __name__ == "__main__":
    main()