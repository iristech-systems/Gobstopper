"""
Example demonstrating Gobstopper configuration system.

This example shows how to:
1. Load configuration from multiple sources
2. Validate configuration
3. Access configuration values
4. Use config with Gobstopper app

Run:
    uv run python examples/config_example.py
"""

from gobstopper import Gobstopper, Config


def example_basic_loading():
    """Basic configuration loading."""
    print("\n=== Basic Configuration Loading ===")

    # Auto-detect config file and environment
    config = Config.load()

    print(f"Environment: {config.env}")
    print(f"Debug mode: {config.debug}")
    print(f"Server: {config.server.host}:{config.server.port}")
    print(f"Workers: {config.server.workers}")


def example_environment_specific():
    """Load environment-specific configuration."""
    print("\n=== Environment-Specific Config ===")

    # Load development config
    dev_config = Config.load(env="development")
    print(f"Development - Debug: {dev_config.debug}")
    print(f"Development - Workers: {dev_config.server.workers}")

    # Load production config
    prod_config = Config.load(env="production")
    print(f"Production - Debug: {prod_config.debug}")
    print(f"Production - Workers: {prod_config.server.workers}")


def example_validation():
    """Validate configuration."""
    print("\n=== Configuration Validation ===")

    # Load config
    config = Config.load()

    # Validate
    issues = config.validate()

    if issues:
        print("Configuration issues found:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("✅ Configuration is valid!")

    # Check for critical issues
    critical = [i for i in issues if "CRITICAL" in i]
    if critical:
        print("\n⚠️  Critical issues that must be fixed:")
        for issue in critical:
            print(f"  - {issue}")


def example_custom_config():
    """Access custom configuration."""
    print("\n=== Custom Configuration ===")

    config = Config.load()

    # Access custom config with defaults
    app_name = config.custom.get("app_name", "My Gobstopper App")
    max_upload = config.custom.get("max_upload_size", 10 * 1024 * 1024)

    print(f"App name: {app_name}")
    print(f"Max upload size: {max_upload:,} bytes")

    # Show all custom config
    if config.custom:
        print("Custom config:")
        for key, value in config.custom.items():
            print(f"  {key}: {value}")


def example_config_dict():
    """Convert config to dictionary."""
    print("\n=== Config as Dictionary ===")

    config = Config.load()
    config_dict = config.to_dict()

    # Show selected sections
    print(f"Server config: {config_dict['server']}")
    print(f"Template config: {config_dict['templates']}")


def example_with_app():
    """Use configuration with Gobstopper app."""
    print("\n=== Using Config with Gobstopper App ===")

    # Load config
    config = Config.load()

    # Validate first
    issues = config.validate()
    if any("CRITICAL" in issue for issue in issues):
        print("❌ Cannot start app - critical configuration issues")
        return

    print(f"✅ Config ready for app: {config.env}")
    print(f"Server will run on: {config.server.host}:{config.server.port}")
    print(f"Workers: {config.server.workers}")
    print(f"Debug mode: {config.debug}")
    print("\nFeatures enabled:")
    print(f"  - Tasks: {config.tasks.enabled}")
    print(f"  - CORS: {config.cors.enabled}")
    print(f"  - Metrics: {config.metrics.enabled}")
    print(f"  - CSRF: {config.security.enable_csrf}")
    print(f"  - Security Headers: {config.security.enable_security_headers}")

    print("\nYou can now create your Gobstopper app:")
    print("  app = Gobstopper()")
    print("  # Config is automatically available")


if __name__ == "__main__":
    print("Gobstopper Configuration System Examples")
    print("=" * 50)

    # Run all examples
    example_basic_loading()
    example_environment_specific()
    example_validation()
    example_custom_config()
    example_config_dict()
    example_with_app()

    print("\n" + "=" * 50)
    print("Examples completed!")
    print("\nNext steps:")
    print("1. Copy config.example.toml to config.toml")
    print("2. Customize your config")
    print("3. Set ENV variable for different environments")
    print("4. Use GOBSTOPPER_ environment variables for overrides")
