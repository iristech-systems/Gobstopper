"""
Template engine for generating Gobstopper projects based on use cases and structures
"""

import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any

try:
    from jinja2 import Environment, FileSystemLoader, Template
    JINJA2_AVAILABLE = True
except ImportError:
    JINJA2_AVAILABLE = False
    Environment = None
    FileSystemLoader = None
    Template = None


@dataclass
class ProjectConfig:
    """Configuration for a project template"""
    name: str
    usecase: str
    structure: str
    python_module: str
    dependencies: List[str] = field(default_factory=list)
    dev_dependencies: List[str] = field(default_factory=list)
    features: List[str] = field(default_factory=list)
    environment_vars: Dict[str, str] = field(default_factory=dict)
    docker: bool = False
    kubernetes: bool = False
    
    def __post_init__(self):
        # Ensure python module name is valid
        self.python_module = self.name.replace("-", "_").replace(" ", "_").lower()


@dataclass
class UseCase:
    """Defines a use case template"""
    name: str
    display_name: str
    description: str
    dependencies: List[str]
    dev_dependencies: List[str]
    default_features: List[str]
    directory_structure: Dict[str, Any]
    file_templates: Dict[str, str]
    tasks: List[str] = field(default_factory=list)
    endpoints: List[str] = field(default_factory=list)
    websocket_routes: List[str] = field(default_factory=list)
    
    
@dataclass
class Structure:
    """Defines a project structure pattern"""
    name: str
    display_name: str
    description: str
    supports_blueprints: bool = False
    supports_modules: bool = False
    supports_microservices: bool = False
    additional_files: Dict[str, str] = field(default_factory=dict)


class TemplateEngine:
    """Engine for generating Gobstopper projects from templates"""

    def __init__(self):
        if not JINJA2_AVAILABLE:
            raise ImportError(
                "Jinja2 is required for the CLI project generator. "
                "Install it with: pip install 'gobstopper[cli]' or pip install jinja2>=3.1.0"
            )

        self.templates_dir = Path(__file__).parent / "templates"
        self.use_cases = self._load_use_cases()
        self.structures = self._load_structures()

        # Setup Jinja2 environment
        self.jinja_env = Environment(
            loader=FileSystemLoader(str(self.templates_dir)),
            trim_blocks=True,
            lstrip_blocks=True
        )
        
    def _load_use_cases(self) -> Dict[str, UseCase]:
        """Load all available use case templates"""
        return {
            "data-science": UseCase(
                name="data-science",
                display_name="Data Science API",
                description="Machine learning models, data processing, and analytics APIs",
                dependencies=[
                    "wopr[all]",
                    "pandas>=2.0.0",
                    "numpy>=1.24.0",
                    "scikit-learn>=1.3.0",
                    "matplotlib>=3.7.0",
                    "seaborn>=0.12.0",
                    "jupyterlab>=4.0.0",
                    "asyncpg>=0.29.0",
                    "redis>=5.0.0",
                    "pydantic>=2.0.0",
                ],
                dev_dependencies=[
                    "pytest>=7.0.0",
                    "pytest-asyncio>=0.21.0",
                    "pytest-cov>=4.0.0",
                    "black>=23.0.0",
                    "ruff>=0.1.0",
                    "mypy>=1.0.0",
                ],
                default_features=["auth", "rate_limiting", "monitoring", "api_docs"],
                directory_structure={
                    "models": {
                        "__init__.py": "",
                        "ml_models.py": "ml_models",
                        "schemas.py": "data_schemas",
                    },
                    "data": {
                        "__init__.py": "",
                        "processors.py": "data_processors",
                        "validators.py": "data_validators",
                        "connectors": {
                            "__init__.py": "",
                            "database.py": "db_connector",
                            "redis_cache.py": "redis_connector",
                        }
                    },
                    "api": {
                        "__init__.py": "",
                        "endpoints": {
                            "__init__.py": "",
                            "predict.py": "predict_endpoint",
                            "train.py": "train_endpoint",
                            "data.py": "data_endpoint",
                        },
                        "middleware": {
                            "__init__.py": "",
                            "model_versioning.py": "model_version_middleware",
                        }
                    },
                    "tasks": {
                        "__init__.py": "",
                        "training.py": "training_tasks",
                        "data_sync.py": "data_sync_tasks",
                        "feature_engineering.py": "feature_engineering_tasks",
                    },
                    "notebooks": {},
                    "tests": {
                        "__init__.py": "",
                        "test_models.py": "test_models",
                        "test_api.py": "test_api",
                        "test_data.py": "test_data",
                    },
                    "config": {
                        "__init__.py": "",
                        "settings.py": "settings",
                    }
                },
                file_templates={
                    "app.py": "data_science_app.py.j2",
                    ".env.example": "data_science_env.j2",
                    "README.md": "data_science_readme.md.j2",
                },
                tasks=["train_model", "preprocess_data", "feature_engineering", "evaluate_model"],
                endpoints=["/api/v1/predict", "/api/v1/train", "/api/v1/models", "/api/v1/data/upload"],
            ),
            
            "real-time-dashboard": UseCase(
                name="real-time-dashboard",
                display_name="Real-time Dashboard",
                description="Live data monitoring with WebSocket streaming and interactive visualizations",
                dependencies=[
                    "wopr[all]",
                    "redis>=5.0.0",
                    "asyncpg>=0.29.0",
                    "plotly>=5.0.0",
                    "dash>=2.0.0",
                    "websockets>=12.0",
                ],
                dev_dependencies=[
                    "pytest>=7.0.0",
                    "pytest-asyncio>=0.21.0",
                    "black>=23.0.0",
                ],
                default_features=["websockets", "caching", "monitoring", "auth"],
                directory_structure={
                    "websockets": {
                        "__init__.py": "",
                        "dashboard_manager.py": "dashboard_ws_manager",
                        "data_streams.py": "data_streams",
                        "notifications.py": "notifications_ws",
                    },
                    "data": {
                        "__init__.py": "",
                        "collectors": {
                            "__init__.py": "",
                            "metrics_collector.py": "metrics_collector",
                        },
                        "aggregators.py": "data_aggregators",
                        "cache.py": "redis_cache",
                    },
                    "api": {
                        "__init__.py": "",
                        "metrics.py": "metrics_api",
                        "alerts.py": "alerts_api",
                        "historical.py": "historical_api",
                    },
                    "frontend": {
                        "js": {},
                        "css": {},
                        "templates": {
                            "dashboard.html": "dashboard_template",
                        }
                    },
                    "tasks": {
                        "__init__.py": "",
                        "data_ingestion.py": "ingestion_tasks",
                        "cleanup.py": "cleanup_tasks",
                    },
                    "tests": {
                        "__init__.py": "",
                        "test_websockets.py": "test_websockets",
                        "test_streaming.py": "test_streaming",
                    }
                },
                file_templates={
                    "app.py": "dashboard_app.py.j2",
                    ".env.example": "dashboard_env.j2",
                    "README.md": "dashboard_readme.md.j2",
                },
                tasks=["collect_metrics", "aggregate_data", "cleanup_old_data"],
                websocket_routes=["/ws/dashboard", "/ws/notifications", "/ws/metrics"],
                endpoints=["/api/metrics", "/api/alerts", "/api/config"],
            ),
            
            "content-management": UseCase(
                name="content-management",
                display_name="Content Management System",
                description="Blog, CMS, and content-heavy applications with admin interface",
                dependencies=[
                    "wopr[all]",
                    "asyncpg>=0.29.0",
                    "redis>=5.0.0",
                    "markdown>=3.0.0",
                    "pillow>=10.0.0",
                    "python-multipart>=0.0.6",
                ],
                dev_dependencies=[
                    "pytest>=7.0.0",
                    "pytest-asyncio>=0.21.0",
                    "black>=23.0.0",
                ],
                default_features=["auth", "admin", "media_upload", "search", "caching"],
                directory_structure={
                    "models": {
                        "__init__.py": "",
                        "content.py": "content_models",
                        "users.py": "user_models",
                        "media.py": "media_models",
                    },
                    "admin": {
                        "__init__.py": "",
                        "dashboard.py": "admin_dashboard",
                        "content_editor.py": "content_editor",
                        "user_management.py": "user_management",
                    },
                    "api": {
                        "__init__.py": "",
                        "content.py": "content_api",
                        "auth.py": "auth_api",
                        "media.py": "media_api",
                    },
                    "frontend": {
                        "templates": {
                            "base.html": "base_template",
                            "blog": {},
                            "admin": {},
                        },
                        "static": {
                            "css": {},
                            "js": {},
                            "uploads": {},
                        }
                    },
                    "tasks": {
                        "__init__.py": "",
                        "content_indexing.py": "indexing_tasks",
                        "image_processing.py": "image_tasks",
                        "email_notifications.py": "email_tasks",
                    },
                    "middleware": {
                        "__init__.py": "",
                        "auth.py": "auth_middleware",
                        "content_security.py": "content_security",
                    },
                    "tests": {
                        "__init__.py": "",
                        "test_content.py": "test_content",
                        "test_auth.py": "test_auth",
                    }
                },
                file_templates={
                    "app.py": "cms_app.py.j2",
                    ".env.example": "cms_env.j2",
                    "README.md": "cms_readme.md.j2",
                },
                tasks=["index_content", "process_images", "send_notifications"],
                endpoints=["/api/content", "/api/auth/login", "/api/media/upload", "/admin"],
            ),
            
            "microservice": UseCase(
                name="microservice",
                display_name="Microservice",
                description="Single-responsibility service with health checks, monitoring, and container deployment",
                dependencies=[
                    "wopr[all]",
                    "asyncpg>=0.29.0",
                    "redis>=5.0.0",
                    "opentelemetry-api>=1.0.0",
                    "opentelemetry-instrumentation>=0.40b0",
                    "prometheus-client>=0.19.0",
                ],
                dev_dependencies=[
                    "pytest>=7.0.0",
                    "pytest-asyncio>=0.21.0",
                    "black>=23.0.0",
                    "testcontainers>=3.0.0",
                ],
                default_features=["health_checks", "metrics", "tracing", "circuit_breaker"],
                directory_structure={
                    "models": {
                        "__init__.py": "",
                        "domain.py": "domain_models",
                    },
                    "api": {
                        "__init__.py": "",
                        "endpoints.py": "service_endpoints",
                        "health.py": "health_checks",
                        "metrics.py": "metrics_endpoint",
                    },
                    "services": {
                        "__init__.py": "",
                        "business_logic.py": "business_logic",
                        "external_api.py": "external_integrations",
                    },
                    "middleware": {
                        "__init__.py": "",
                        "tracing.py": "tracing_middleware",
                        "circuit_breaker.py": "circuit_breaker",
                    },
                    "config": {
                        "__init__.py": "",
                        "settings.py": "service_settings",
                        "observability.py": "observability_config",
                    },
                    "deployment": {
                        "Dockerfile": "dockerfile",
                        "docker-compose.yml": "docker_compose",
                        "k8s": {
                            "deployment.yaml": "k8s_deployment",
                            "service.yaml": "k8s_service",
                            "configmap.yaml": "k8s_configmap",
                        }
                    },
                    "tests": {
                        "__init__.py": "",
                        "integration": {
                            "__init__.py": "",
                            "test_api.py": "test_integration",
                        },
                        "unit": {
                            "__init__.py": "",
                            "test_services.py": "test_services",
                        }
                    }
                },
                file_templates={
                    "app.py": "microservice_app.py.j2",
                    ".env.example": "microservice_env.j2",
                    "README.md": "microservice_readme.md.j2",
                    "Makefile": "microservice_makefile.j2",
                },
                tasks=["process_queue", "sync_data"],
                endpoints=["/health", "/metrics", "/api/v1/resource"],
            ),
        }
        
    def _load_structures(self) -> Dict[str, Structure]:
        """Load all available structure patterns"""
        return {
            "modular": Structure(
                name="modular",
                display_name="Modular",
                description="Domain-driven modules with clear separation of concerns",
                supports_modules=True,
                additional_files={
                    "modules/__init__.py": "modules_init.py.j2",
                }
            ),
            "blueprints": Structure(
                name="blueprints",
                display_name="Blueprints",
                description="Flask-style blueprints for organized routing",
                supports_blueprints=True,
                additional_files={
                    "blueprints/__init__.py": "blueprints_init.py.j2",
                }
            ),
            "microservices": Structure(
                name="microservices",
                display_name="Microservices",
                description="Service-oriented architecture with container support",
                supports_microservices=True,
                additional_files={
                    "docker-compose.yml": "docker_compose.yml.j2",
                    "Dockerfile": "dockerfile.j2",
                    ".dockerignore": "dockerignore.j2",
                }
            ),
            "single": Structure(
                name="single",
                display_name="Single File",
                description="Simple single-file application for small projects",
                additional_files={}
            ),
        }
        
    def generate_project(
        self,
        name: str,
        usecase: str,
        structure: str,
        features: Optional[List[str]] = None,
        **options
    ) -> Path:
        """Generate a complete project based on templates"""
        
        # Validate inputs
        if usecase not in self.use_cases:
            raise ValueError(f"Unknown use case: {usecase}")
        if structure not in self.structures:
            raise ValueError(f"Unknown structure: {structure}")
            
        # Create project config
        use_case_template = self.use_cases[usecase]
        structure_template = self.structures[structure]
        
        config = ProjectConfig(
            name=name,
            usecase=usecase,
            structure=structure,
            python_module=name.replace("-", "_"),
            dependencies=use_case_template.dependencies.copy(),
            dev_dependencies=use_case_template.dev_dependencies.copy(),
            features=features or use_case_template.default_features,
            docker="docker" in (features or []),
            kubernetes="kubernetes" in (features or []),
        )
        
        # Add feature-specific dependencies
        self._add_feature_dependencies(config)
        
        # Create project directory
        project_path = Path(name)
        if project_path.exists():
            raise FileExistsError(f"Directory {name} already exists")
        project_path.mkdir(parents=True)
        
        # Generate directory structure
        self._create_directory_structure(
            project_path,
            use_case_template.directory_structure
        )
        
        # Generate files from templates
        self._generate_files(project_path, config, use_case_template, structure_template)
        
        # Add structure-specific files
        if structure_template.additional_files:
            self._generate_additional_files(
                project_path,
                config,
                structure_template.additional_files
            )
        
        # Create requirements files
        self._create_requirements(project_path, config)
        
        # Create .gitignore
        self._create_gitignore(project_path)
        
        # Create .env.example
        self._create_env_example(project_path, config)
        
        return project_path
        
    def _add_feature_dependencies(self, config: ProjectConfig):
        """Add dependencies based on selected features"""
        feature_deps = {
            "auth": ["pyjwt>=2.8.0", "passlib>=1.7.4", "python-jose>=3.3.0"],
            "admin": ["wtforms>=3.0.0"],
            "rate_limiting": ["slowapi>=0.1.9"],
            "monitoring": ["prometheus-client>=0.19.0"],
            "api_docs": ["pydantic>=2.0.0"],
            "websockets": ["websockets>=12.0"],
            "caching": ["redis>=5.0.0"],
            "search": ["elasticsearch>=8.0.0"],
            "media_upload": ["python-multipart>=0.0.6", "pillow>=10.0.0"],
        }
        
        for feature in config.features:
            if feature in feature_deps:
                for dep in feature_deps[feature]:
                    if dep not in config.dependencies:
                        config.dependencies.append(dep)
                        
    def _create_directory_structure(self, base_path: Path, structure: Dict[str, Any]):
        """Recursively create directory structure"""
        for name, content in structure.items():
            path = base_path / name
            
            if isinstance(content, dict):
                # It's a directory
                path.mkdir(parents=True, exist_ok=True)
                self._create_directory_structure(path, content)
            elif isinstance(content, str):
                # It's a file with a template name
                # Will be handled in _generate_files
                pass
            else:
                # Empty file
                path.touch()
                
    def _generate_files(
        self,
        project_path: Path,
        config: ProjectConfig,
        use_case: UseCase,
        structure: Structure
    ):
        """Generate files from templates"""
        
        # Prepare template context
        context = {
            "project": config,
            "usecase": use_case,
            "structure": structure,
        }
        
        # Generate main app file based on structure
        app_template = self._get_app_template(config.structure, use_case.name)
        if app_template:
            self._render_template_file(
                project_path / "app.py",
                app_template,
                context
            )
            
        # Generate other template files
        for file_path, template_name in use_case.file_templates.items():
            if file_path != "app.py":  # Already handled
                self._render_template_file(
                    project_path / file_path,
                    template_name,
                    context
                )
                
        # Generate structure files from directory mapping
        self._generate_structure_files(
            project_path,
            use_case.directory_structure,
            context
        )
        
    def _generate_structure_files(
        self,
        base_path: Path,
        structure: Dict[str, Any],
        context: Dict[str, Any]
    ):
        """Generate files based on directory structure mapping"""
        for name, content in structure.items():
            path = base_path / name
            
            if isinstance(content, dict):
                # Recursively handle subdirectories
                self._generate_structure_files(path, content, context)
            elif isinstance(content, str) and content:
                # Generate file from template
                template_name = f"{content}.py.j2"
                if self._template_exists(template_name):
                    self._render_template_file(path, template_name, context)
                else:
                    # Create empty file with basic structure
                    path.write_text(f'"""\n{content.replace("_", " ").title()}\n"""\n\n')
                    
    def _get_app_template(self, structure: str, usecase: str) -> str:
        """Get the appropriate app template based on structure and use case"""
        # Structure-specific templates take precedence
        if structure == "single":
            return "single_app.py.j2"
        elif structure == "blueprints":
            return "blueprints_app.py.j2"
        elif structure == "modular":
            return "modular_app.py.j2"
        elif structure == "microservices":
            return "microservices_app.py.j2"
        else:
            # Fall back to use case specific template
            template_map = {
                "data-science": "data_science_app.py.j2",
                "real-time-dashboard": "dashboard_app.py.j2",
                "content-management": "cms_app.py.j2",
                "microservice": "microservice_app.py.j2"
            }
            return template_map.get(usecase, "microservice_app.py.j2")
    
    def _template_exists(self, template_name: str) -> bool:
        """Check if a template file exists"""
        template_path = self.templates_dir / template_name
        return template_path.exists()
        
    def _render_template_file(
        self,
        output_path: Path,
        template_name: str,
        context: Dict[str, Any]
    ):
        """Render a template file"""
        try:
            template = self.jinja_env.get_template(template_name)
            content = template.render(**context)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(content)
        except Exception as e:
            # If template doesn't exist, create a placeholder
            print(f"Template rendering error for {template_name}: {e}")
            output_path.write_text(f"# TODO: Implement {output_path.name}\n# Error: {e}\n")
            
    def _generate_additional_files(
        self,
        project_path: Path,
        config: ProjectConfig,
        files: Dict[str, str]
    ):
        """Generate additional files for specific structures"""
        context = {"project": config}
        
        for file_path, template_name in files.items():
            self._render_template_file(
                project_path / file_path,
                template_name,
                context
            )
            
    def _create_requirements(self, project_path: Path, config: ProjectConfig):
        """Create requirements.txt and requirements-dev.txt"""
        
        # Main requirements
        requirements = ["granian[rsgi]>=1.0.0"] + config.dependencies
        (project_path / "requirements.txt").write_text("\n".join(requirements) + "\n")
        
        # Dev requirements
        if config.dev_dependencies:
            (project_path / "requirements-dev.txt").write_text(
                "\n".join(config.dev_dependencies) + "\n"
            )
            
    def _create_gitignore(self, project_path: Path):
        """Create .gitignore file"""
        gitignore_content = """# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
venv/
ENV/
.venv/

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# Testing
.coverage
.pytest_cache/
htmlcov/

# Logs
*.log

# Database
*.db
*.duckdb
*.sqlite

# Environment
.env
.env.local

# Static files
/static/uploads/
/media/

# Distribution
dist/
build/
*.egg-info/

# OS
.DS_Store
Thumbs.db

# Gobstopper specific
wopr_tasks.duckdb
wopr_tasks.duckdb.wal
"""
        (project_path / ".gitignore").write_text(gitignore_content)
        
    def _create_env_example(self, project_path: Path, config: ProjectConfig):
        """Create .env.example file"""
        env_content = f"""# {config.name.upper()} Configuration

# Application
APP_NAME={config.name}
DEBUG=false
SECRET_KEY=your-secret-key-here

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/{config.python_module}

# Redis
REDIS_URL=redis://localhost:6379/0

# API Keys (if needed)
# API_KEY=your-api-key

# Feature Flags
"""
        
        for feature in config.features:
            env_content += f"ENABLE_{feature.upper()}=true\n"
            
        (project_path / ".env.example").write_text(env_content)
        
    def list_use_cases(self) -> List[Dict[str, str]]:
        """List all available use cases"""
        return [
            {
                "name": uc.name,
                "display_name": uc.display_name,
                "description": uc.description,
            }
            for uc in self.use_cases.values()
        ]
        
    def list_structures(self) -> List[Dict[str, str]]:
        """List all available structures"""
        return [
            {
                "name": st.name,
                "display_name": st.display_name,
                "description": st.description,
            }
            for st in self.structures.values()
        ]