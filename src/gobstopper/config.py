"""
Centralized configuration management for Gobstopper framework.

This module provides a flexible configuration system that supports:
- Environment variables
- Configuration files (TOML, JSON)
- Environment-based config loading (dev, test, prod)
- Type validation and sensible defaults
- Immutable configuration objects

Usage:
    # Load from environment and config file
    config = Config.load()

    # Load specific environment
    config = Config.load(env="production")

    # Load from specific file
    config = Config.load(config_file="config.toml")

    # Use in application
    app = Gobstopper(config=config)
"""

import os
import json
from pathlib import Path
from typing import Any, Dict, Optional, Union
from dataclasses import dataclass, field, asdict


# Try to import TOML support (tomllib is built-in Python 3.11+)
try:
    import tomllib
    TOML_AVAILABLE = True
except ImportError:
    try:
        import tomli as tomllib
        TOML_AVAILABLE = True
    except ImportError:
        TOML_AVAILABLE = False


@dataclass(frozen=True)
class ServerConfig:
    """Server configuration settings."""

    host: str = "127.0.0.1"
    port: int = 8000
    workers: int = 1
    interface: str = "rsgi"
    log_level: str = "info"


@dataclass(frozen=True)
class SecurityConfig:
    """Security-related configuration."""

    secret_key: Optional[str] = None
    enable_csrf: bool = True
    enable_security_headers: bool = True
    hsts_max_age: int = 31536000  # 1 year
    hsts_include_subdomains: bool = True
    csp_policy: str = "default-src 'self'; object-src 'none'"
    referrer_policy: str = "strict-origin-when-cross-origin"
    coop_policy: str = "same-origin"
    coep_policy: str = "require-corp"
    cookie_secure: bool = True
    cookie_httponly: bool = True
    cookie_samesite: str = "Strict"
    cookie_max_age: int = 3600
    session_storage_type: str = "file"  # file, memory, sql, redis
    session_storage_path: Optional[str] = None


@dataclass(frozen=True)
class CORSConfig:
    """CORS middleware configuration."""

    enabled: bool = False
    allow_origins: list[str] = field(default_factory=lambda: ["*"])
    allow_methods: list[str] = field(default_factory=lambda: ["GET", "POST", "PUT", "DELETE", "OPTIONS"])
    allow_headers: list[str] = field(default_factory=lambda: ["*"])
    allow_credentials: bool = False
    max_age: int = 86400


@dataclass(frozen=True)
class StaticFilesConfig:
    """Static file serving configuration."""

    enabled: bool = True
    url_path: str = "/static"
    directory: str = "static"
    use_rust: bool = True  # Use Rust implementation if available


@dataclass(frozen=True)
class TemplateConfig:
    """Template engine configuration."""

    directory: str = "templates"
    use_rust: bool = True  # Use Rust implementation if available
    auto_reload: bool = False
    cache_size: int = 400


@dataclass(frozen=True)
class TaskConfig:
    """Background task system configuration."""

    enabled: bool = True
    storage_type: str = "duckdb"  # duckdb, memory
    storage_path: Optional[str] = None
    max_workers: int = 4
    default_priority: int = 5
    enable_retries: bool = True
    max_retries: int = 3
    cleanup_days: int = 7


@dataclass(frozen=True)
class RateLimitConfig:
    """Rate limiting configuration."""

    enabled: bool = False
    default_rate: int = 100  # requests
    default_period: int = 60  # seconds
    storage_type: str = "memory"  # memory, redis


@dataclass(frozen=True)
class LoggingConfig:
    """Logging configuration."""

    level: str = "info"
    format: str = "text"  # text, json
    enable_correlation_id: bool = False
    log_file: Optional[str] = None


@dataclass(frozen=True)
class MetricsConfig:
    """Metrics and observability configuration."""

    enabled: bool = False
    export_type: str = "prometheus"  # prometheus, opentelemetry
    endpoint: str = "/metrics"
    include_hostname: bool = True


@dataclass(frozen=True)
class Config:
    """
    Main configuration class for Gobstopper framework.

    This class provides centralized configuration management with sensible
    defaults, environment-based overrides, and support for configuration files.

    Configuration precedence (highest to lowest):
    1. Environment variables
    2. Configuration file
    3. Default values

    Attributes:
        env: Environment name (development, test, production)
        debug: Debug mode flag
        server: Server configuration
        security: Security settings
        cors: CORS middleware settings
        static_files: Static file serving settings
        templates: Template engine settings
        tasks: Background task settings
        rate_limit: Rate limiting settings
        logging: Logging configuration
        metrics: Metrics configuration
        custom: Custom application-specific configuration
    """

    env: str = "development"
    debug: bool = True
    server: ServerConfig = field(default_factory=ServerConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    cors: CORSConfig = field(default_factory=CORSConfig)
    static_files: StaticFilesConfig = field(default_factory=StaticFilesConfig)
    templates: TemplateConfig = field(default_factory=TemplateConfig)
    tasks: TaskConfig = field(default_factory=TaskConfig)
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    metrics: MetricsConfig = field(default_factory=MetricsConfig)
    custom: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(
        cls,
        config_file: Optional[Union[str, Path]] = None,
        env: Optional[str] = None,
        auto_detect: bool = True,
    ) -> "Config":
        """
        Load configuration from multiple sources.

        Configuration is loaded in the following order:
        1. Default values (from dataclass definitions)
        2. Configuration file (if provided or auto-detected)
        3. Environment variables (highest precedence)

        Args:
            config_file: Path to configuration file (TOML or JSON).
                If None and auto_detect is True, searches for:
                - config.{env}.toml
                - config.toml
                - config.{env}.json
                - config.json
            env: Environment name (overrides ENV environment variable)
            auto_detect: Automatically search for config files

        Returns:
            Loaded configuration object

        Raises:
            ValueError: If config file format is not supported
            FileNotFoundError: If specified config file doesn't exist

        Example:
            >>> config = Config.load()
            >>> config = Config.load(env="production")
            >>> config = Config.load(config_file="config.toml")
        """
        # Determine environment
        env = env or os.getenv("ENV", os.getenv("ENVIRONMENT", "development"))
        debug = env != "production"

        # Start with defaults
        config_data: Dict[str, Any] = {
            "env": env,
            "debug": debug,
        }

        # Load from config file
        if config_file or auto_detect:
            file_data = cls._load_config_file(config_file, env, auto_detect)
            if file_data:
                config_data.update(file_data)

        # Override with environment variables
        env_data = cls._load_from_env()
        config_data = cls._deep_merge(config_data, env_data)

        # Build config objects
        return cls._build_config(config_data, env, debug)

    @classmethod
    def _load_config_file(
        cls,
        config_file: Optional[Union[str, Path]],
        env: str,
        auto_detect: bool,
    ) -> Optional[Dict[str, Any]]:
        """Load configuration from file."""
        if config_file:
            path = Path(config_file)
            if not path.exists():
                raise FileNotFoundError(f"Config file not found: {config_file}")
            return cls._parse_config_file(path)

        if auto_detect:
            # Search for config files
            search_files = [
                f"config.{env}.toml",
                "config.toml",
                f"config.{env}.json",
                "config.json",
            ]

            for filename in search_files:
                path = Path(filename)
                if path.exists():
                    return cls._parse_config_file(path)

        return None

    @classmethod
    def _parse_config_file(cls, path: Path) -> Dict[str, Any]:
        """Parse TOML or JSON config file."""
        suffix = path.suffix.lower()

        if suffix == ".toml":
            if not TOML_AVAILABLE:
                raise ImportError(
                    "TOML support not available. Install tomli for Python < 3.11"
                )
            with open(path, "rb") as f:
                return tomllib.load(f)

        elif suffix == ".json":
            with open(path, "r") as f:
                return json.load(f)

        else:
            raise ValueError(f"Unsupported config file format: {suffix}")

    @classmethod
    def _load_from_env(cls) -> Dict[str, Any]:
        """Load configuration from environment variables."""
        config: Dict[str, Any] = {}

        # Top-level settings
        if env_val := os.getenv("WOPR_ENV"):
            config["env"] = env_val
        if debug := os.getenv("WOPR_DEBUG"):
            config["debug"] = debug.lower() in ("true", "1", "yes")

        # Server settings
        server = {}
        if host := os.getenv("WOPR_SERVER_HOST"):
            server["host"] = host
        if port := os.getenv("WOPR_SERVER_PORT"):
            server["port"] = int(port)
        if workers := os.getenv("WOPR_SERVER_WORKERS"):
            server["workers"] = int(workers)
        if log_level := os.getenv("WOPR_SERVER_LOG_LEVEL"):
            server["log_level"] = log_level
        if server:
            config["server"] = server

        # Security settings
        security = {}
        if secret_key := os.getenv("WOPR_SECRET_KEY"):
            security["secret_key"] = secret_key
        if csrf := os.getenv("WOPR_ENABLE_CSRF"):
            security["enable_csrf"] = csrf.lower() in ("true", "1", "yes")
        if session_type := os.getenv("WOPR_SESSION_STORAGE_TYPE"):
            security["session_storage_type"] = session_type
        if session_path := os.getenv("WOPR_SESSION_STORAGE_PATH"):
            security["session_storage_path"] = session_path
        if security:
            config["security"] = security

        # CORS settings
        cors = {}
        if cors_enabled := os.getenv("WOPR_CORS_ENABLED"):
            cors["enabled"] = cors_enabled.lower() in ("true", "1", "yes")
        if origins := os.getenv("WOPR_CORS_ALLOW_ORIGINS"):
            cors["allow_origins"] = origins.split(",")
        if cors:
            config["cors"] = cors

        # Static files
        static = {}
        if static_enabled := os.getenv("WOPR_STATIC_ENABLED"):
            static["enabled"] = static_enabled.lower() in ("true", "1", "yes")
        if static_path := os.getenv("WOPR_STATIC_URL_PATH"):
            static["url_path"] = static_path
        if static_dir := os.getenv("WOPR_STATIC_DIRECTORY"):
            static["directory"] = static_dir
        if static:
            config["static_files"] = static

        # Templates
        templates = {}
        if template_dir := os.getenv("WOPR_TEMPLATE_DIRECTORY"):
            templates["directory"] = template_dir
        if auto_reload := os.getenv("WOPR_TEMPLATE_AUTO_RELOAD"):
            templates["auto_reload"] = auto_reload.lower() in ("true", "1", "yes")
        if templates:
            config["templates"] = templates

        # Tasks
        tasks = {}
        if tasks_enabled := os.getenv("WOPR_TASKS_ENABLED"):
            tasks["enabled"] = tasks_enabled.lower() in ("true", "1", "yes")
        if max_workers := os.getenv("WOPR_TASKS_MAX_WORKERS"):
            tasks["max_workers"] = int(max_workers)
        if storage_path := os.getenv("WOPR_TASKS_STORAGE_PATH"):
            tasks["storage_path"] = storage_path
        if tasks:
            config["tasks"] = tasks

        # Rate limiting
        rate_limit = {}
        if rate_enabled := os.getenv("WOPR_RATE_LIMIT_ENABLED"):
            rate_limit["enabled"] = rate_enabled.lower() in ("true", "1", "yes")
        if default_rate := os.getenv("WOPR_RATE_LIMIT_DEFAULT_RATE"):
            rate_limit["default_rate"] = int(default_rate)
        if rate_limit:
            config["rate_limit"] = rate_limit

        # Logging
        logging_config = {}
        if log_level := os.getenv("WOPR_LOG_LEVEL"):
            logging_config["level"] = log_level
        if log_format := os.getenv("WOPR_LOG_FORMAT"):
            logging_config["format"] = log_format
        if log_file := os.getenv("WOPR_LOG_FILE"):
            logging_config["log_file"] = log_file
        if logging_config:
            config["logging"] = logging_config

        # Metrics
        metrics = {}
        if metrics_enabled := os.getenv("WOPR_METRICS_ENABLED"):
            metrics["enabled"] = metrics_enabled.lower() in ("true", "1", "yes")
        if metrics_endpoint := os.getenv("WOPR_METRICS_ENDPOINT"):
            metrics["endpoint"] = metrics_endpoint
        if metrics:
            config["metrics"] = metrics

        return config

    @classmethod
    def _deep_merge(cls, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """Deep merge two dictionaries."""
        result = base.copy()

        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = cls._deep_merge(result[key], value)
            else:
                result[key] = value

        return result

    @classmethod
    def _build_config(cls, data: Dict[str, Any], env: str, debug: bool) -> "Config":
        """Build Config object from merged data."""
        # Build nested config objects
        server = ServerConfig(**data.get("server", {}))
        security = SecurityConfig(**data.get("security", {}))
        cors = CORSConfig(**data.get("cors", {}))
        static_files = StaticFilesConfig(**data.get("static_files", {}))
        templates = TemplateConfig(**data.get("templates", {}))
        tasks = TaskConfig(**data.get("tasks", {}))
        rate_limit = RateLimitConfig(**data.get("rate_limit", {}))
        logging_config = LoggingConfig(**data.get("logging", {}))
        metrics = MetricsConfig(**data.get("metrics", {}))
        custom = data.get("custom", {})

        return cls(
            env=env,
            debug=debug,
            server=server,
            security=security,
            cors=cors,
            static_files=static_files,
            templates=templates,
            tasks=tasks,
            rate_limit=rate_limit,
            logging=logging_config,
            metrics=metrics,
            custom=custom,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return asdict(self)

    def validate(self) -> list[str]:
        """
        Validate configuration and return list of warnings/errors.

        Returns:
            List of validation messages (empty if valid)
        """
        issues = []

        # Production checks
        if self.env == "production":
            if not self.security.secret_key:
                issues.append("CRITICAL: secret_key is required in production")
            elif len(self.security.secret_key) < 32:
                issues.append("WARNING: secret_key should be at least 32 characters")

            if self.debug:
                issues.append("WARNING: debug mode enabled in production")

            if not self.security.cookie_secure:
                issues.append("WARNING: cookie_secure should be True in production")

            if self.templates.auto_reload:
                issues.append("WARNING: template auto_reload should be False in production")

        # Port validation
        if not (1 <= self.server.port <= 65535):
            issues.append(f"ERROR: Invalid port number: {self.server.port}")

        # Worker validation
        if self.server.workers < 1:
            issues.append("ERROR: workers must be at least 1")

        # Task worker validation
        if self.tasks.enabled and self.tasks.max_workers < 1:
            issues.append("ERROR: tasks.max_workers must be at least 1")

        # Directory existence checks (warnings only)
        if self.static_files.enabled:
            static_path = Path(self.static_files.directory)
            if not static_path.exists():
                issues.append(f"WARNING: static directory not found: {static_path}")

        template_path = Path(self.templates.directory)
        if not template_path.exists():
            issues.append(f"WARNING: template directory not found: {template_path}")

        return issues

    def __repr__(self) -> str:
        """String representation (safe for logging, hides secrets)."""
        safe_dict = self.to_dict()
        if "security" in safe_dict and "secret_key" in safe_dict["security"]:
            if safe_dict["security"]["secret_key"]:
                safe_dict["security"]["secret_key"] = "***REDACTED***"
        return f"Config({safe_dict})"
