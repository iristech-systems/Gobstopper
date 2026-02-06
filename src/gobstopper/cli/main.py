"""
Main CLI interface for Gobstopper framework
"""

import os
import sys
import shutil
import platform
import subprocess
import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from .sdk import sdk

try:
    import click
    CLICK_AVAILABLE = True
except ImportError:
    CLICK_AVAILABLE = False
    click = None


def load_config_file(config_name: str) -> Dict[str, Any]:
    """Load configuration from JSON or TOML file.

    Args:
        config_name: Config file name without extension (e.g., 'dev', 'production')

    Returns:
        Dictionary of configuration values
    """
    config_data = {}

    # Try JSON first
    json_path = Path(f"{config_name}.json")
    if json_path.exists():
        try:
            with open(json_path, 'r') as f:
                config_data = json.load(f)
            return config_data
        except json.JSONDecodeError as e:
            if CLICK_AVAILABLE:
                click.echo(f"⚠️  Warning: Invalid JSON in {json_path}: {e}", err=True)

    # Try TOML
    toml_path = Path(f"{config_name}.toml")
    if toml_path.exists():
        try:
            # Try to import tomllib (Python 3.11+) or tomli
            try:
                import tomllib
                with open(toml_path, 'rb') as f:
                    config_data = tomllib.load(f)
            except ImportError:
                try:
                    import tomli
                    with open(toml_path, 'rb') as f:
                        config_data = tomli.load(f)
                except ImportError:
                    if CLICK_AVAILABLE:
                        click.echo(f"⚠️  Warning: tomli/tomllib not available for TOML support", err=True)
                    return {}
            return config_data
        except Exception as e:
            if CLICK_AVAILABLE:
                click.echo(f"⚠️  Warning: Invalid TOML in {toml_path}: {e}", err=True)

    # Config file not found
    if not config_data and CLICK_AVAILABLE:
        click.echo(f"⚠️  Warning: Config file '{config_name}.json' or '{config_name}.toml' not found", err=True)

    return config_data


if not CLICK_AVAILABLE:
    def cli():
        raise ImportError("Click is required for CLI tools. Install: uv add click")
else:
    @click.group()
    @click.version_option()
    def cli():
        """Gobstopper - High-performance async web framework CLI"""
        pass
    
    @cli.command()
    @click.argument('project_name')
    @click.option('--usecase', '-u', 
                  type=click.Choice(['data-science', 'real-time-dashboard', 
                                   'content-management', 'microservice']),
                  default='microservice',
                  help='Project use case template')
    @click.option('--structure', '-s',
                  type=click.Choice(['modular', 'blueprints', 'microservices', 'single']),
                  default='modular',
                  help='Project structure pattern')
    @click.option('--features', '-f', multiple=True,
                  help='Additional features to include')
    @click.option('--interactive', '-i', is_flag=True,
                  help='Interactive project setup')
    def init(project_name: str, usecase: str, structure: str, features: tuple, interactive: bool):
        """Initialize a new Gobstopper project with templates"""
        
        if interactive:
            # Interactive mode
            usecase, structure, features = run_interactive_setup()
        
        from .template_engine import TemplateEngine
        
        engine = TemplateEngine()
        
        try:
            click.echo(f"🚀 Creating {usecase} project: {project_name}")
            click.echo(f"📁 Structure: {structure}")
            
            if features:
                click.echo(f"✨ Features: {', '.join(features)}")
            
            # Generate project
            project_path = engine.generate_project(
                name=project_name,
                usecase=usecase,
                structure=structure,
                features=list(features) if features else None
            )
            
            click.echo(f"\n✅ Project '{project_name}' created successfully!")
            click.echo("\n📖 Next steps:")
            click.echo(f"  1. cd {project_name}")
            click.echo("  2. python -m venv venv")
            click.echo("  3. source venv/bin/activate  # On Windows: venv\\Scripts\\activate")
            click.echo("  4. pip install -r requirements.txt")
            click.echo("  5. cp .env.example .env")
            click.echo("  6. # Edit .env with your configuration")
            click.echo("  7. granian --interface rsgi --reload app:app")
            click.echo(f"\n🌐 Your app will be available at http://localhost:8000")
            
        except FileExistsError:
            click.echo(f"❌ Error: Directory '{project_name}' already exists", err=True)
        except ValueError as e:
            click.echo(f"❌ Error: {e}", err=True)
        except Exception as e:
            click.echo(f"❌ Unexpected error: {e}", err=True)
    
    @cli.group()
    def templates():
        """Manage project templates"""
        pass
    
    @templates.command('list')
    @click.option('--verbose', '-v', is_flag=True, help='Show detailed information')
    def list_templates(verbose: bool):
        """List available templates and structures"""
        from .template_engine import TemplateEngine
        
        engine = TemplateEngine()
        
        click.echo("📚 Available Use Cases:")
        click.echo("=" * 50)
        
        for uc in engine.list_use_cases():
            click.echo(f"\n🎯 {uc['display_name']} ({uc['name']})")
            if verbose:
                click.echo(f"   {uc['description']}")
        
        click.echo("\n\n🏗️ Available Structures:")
        click.echo("=" * 50)
        
        for st in engine.list_structures():
            click.echo(f"\n📐 {st['display_name']} ({st['name']})")
            if verbose:
                click.echo(f"   {st['description']}")
    
    @templates.command('show')
    @click.argument('template_name')
    def show_template(template_name: str):
        """Show details about a specific template"""
        from .template_engine import TemplateEngine
        
        engine = TemplateEngine()
        
        # Check if it's a use case
        if template_name in engine.use_cases:
            uc = engine.use_cases[template_name]
            click.echo(f"🎯 {uc.display_name}")
            click.echo(f"   {uc.description}")
            click.echo(f"\n📦 Dependencies:")
            for dep in uc.dependencies[:5]:
                click.echo(f"   - {dep}")
            if len(uc.dependencies) > 5:
                click.echo(f"   ... and {len(uc.dependencies) - 5} more")
            
            if uc.endpoints:
                click.echo(f"\n🔌 API Endpoints:")
                for endpoint in uc.endpoints[:5]:
                    click.echo(f"   - {endpoint}")
                    
            if uc.tasks:
                click.echo(f"\n⚡ Background Tasks:")
                for task in uc.tasks:
                    click.echo(f"   - {task}")
                    
        # Check if it's a structure
        elif template_name in engine.structures:
            st = engine.structures[template_name]
            click.echo(f"📐 {st.display_name}")
            click.echo(f"   {st.description}")
            click.echo(f"\n🔧 Features:")
            if st.supports_blueprints:
                click.echo("   ✅ Blueprints support")
            if st.supports_modules:
                click.echo("   ✅ Modular architecture")
            if st.supports_microservices:
                click.echo("   ✅ Microservices ready")
        else:
            click.echo(f"❌ Template '{template_name}' not found", err=True)
    
    @cli.group()
    def generate():
        """Generate project components"""
        pass
    
    @generate.command('model')
    @click.argument('model_name')
    @click.option('--fields', '-f', multiple=True, help='Model fields (name:type)')
    def generate_model(model_name: str, fields: tuple):
        """Generate a new data model"""
        click.echo(f"📝 Generating model: {model_name}")
        
        # Parse fields
        field_list = []
        for field in fields:
            if ':' in field:
                name, type_str = field.split(':', 1)
                field_list.append((name, type_str))
            else:
                field_list.append((field, 'str'))
        
        # Generate model code
        model_code = generate_model_code(model_name, field_list)
        
        # Write to file
        model_file = Path("models") / f"{model_name.lower()}.py"
        if not model_file.parent.exists():
            click.echo("❌ Error: Not in a Gobstopper project directory", err=True)
            return
            
        model_file.write_text(model_code)
        click.echo(f"✅ Model created: {model_file}")
    
    @generate.command('endpoint')
    @click.argument('path')
    @click.option('--method', '-m', 
                  type=click.Choice(['GET', 'POST', 'PUT', 'DELETE', 'PATCH']),
                  default='GET', help='HTTP method')
    @click.option('--auth', is_flag=True, help='Require authentication')
    def generate_endpoint(path: str, method: str, auth: bool):
        """Generate a new API endpoint"""
        click.echo(f"🔌 Generating endpoint: {method} {path}")
        
        # Generate endpoint code
        endpoint_code = generate_endpoint_code(path, method, auth)
        
        # Determine file to add to
        if Path("app.py").exists():
            click.echo("📝 Add this to your app.py:")
            click.echo("\n" + endpoint_code)
        else:
            click.echo("❌ Error: Not in a Gobstopper project directory", err=True)
    
    @generate.command('task')
    @click.argument('task_name')
    @click.option('--category', '-c', default='default', help='Task category')
    def generate_task(task_name: str, category: str):
        """Generate a new background task"""
        click.echo(f"⚡ Generating task: {task_name} (category: {category})")
        
        # Generate task code
        task_code = generate_task_code(task_name, category)
        
        # Write to file
        task_file = Path("tasks") / f"{task_name.lower()}.py"
        if not task_file.parent.exists():
            click.echo("❌ Error: Not in a Gobstopper project directory", err=True)
            return
            
        task_file.write_text(task_code)
        click.echo(f"✅ Task created: {task_file}")
        click.echo("\n📝 Add this decorator to your app.py:")
        click.echo(f'@app.task("{task_name}", category="{category}")')
        click.echo(f"async def {task_name}_task(**kwargs):")
        click.echo(f'    from tasks.{task_name.lower()} import {task_name}')
        click.echo(f'    return await {task_name}(**kwargs)')
    
    @cli.command()
    @click.option('--categories', '-c', multiple=True, help='Task categories to run workers for')
    @click.option('--workers', '-w', default=1, help='Number of workers per category')
    def run_tasks(categories, workers):
        """Run background task workers"""
        click.echo("Starting task workers...")
        
        if not categories:
            categories = ['default']
        
        for category in categories:
            click.echo(f"Starting {workers} workers for category: {category}")
        
        click.echo("Task workers started. Press Ctrl+C to stop.")
        # Implementation would start actual workers here
    
    @cli.command()
    @click.option('--days', type=int, help='Clean tasks older than N days')
    @click.option('--months', type=int, help='Clean tasks older than N months')
    def cleanup_tasks(days, months):
        """Clean up old completed tasks"""
        if not days and not months:
            click.echo("Please specify --days or --months", err=True)
            return
        
        from ..tasks.storage import TaskStorage
        
        storage = TaskStorage()
        deleted = storage.cleanup_old_tasks(days=days, months=months)
        
        click.echo(f"✅ Cleaned up {deleted} old tasks")
    
    @cli.command()
    @click.argument('app', required=False, default='app:app')
    @click.option('--host', '-h', default=None, help='Host to bind to')
    @click.option('--port', '-p', default=None, type=int, help='Port to bind to')
    @click.option('--workers', '-w', default=None, type=int, help='Number of workers')
    @click.option('--reload', '-r', is_flag=True, help='Enable auto-reload')
    @click.option('--threads', '-t', default=None, type=int, help='Number of threads per worker')
    @click.option('--config', '-c', default=None, help='Configuration file name (without extension)')
    @click.option('--ssl-cert', default=None, help='Path to SSL certificate file')
    @click.option('--ssl-key', default=None, help='Path to SSL key file')
    @click.option('--loop', default=None, type=click.Choice(['auto', 'asyncio', 'uvloop']), help='Event loop implementation')
    @click.option('--log-level', default=None, type=click.Choice(['debug', 'info', 'warning', 'error', 'critical']), help='Log level')
    @click.option('--access-log/--no-access-log', default=None, help='Enable/disable access log')
    @click.option('--share', is_flag=True, help='Enable Flash Preview (share via local network/QR)')
    def run(app: str, host: Optional[str], port: Optional[int], workers: Optional[int],
            reload: bool, threads: Optional[int], config: Optional[str],
            ssl_cert: Optional[str], ssl_key: Optional[str], loop: Optional[str],
            log_level: Optional[str], access_log: Optional[bool], share: bool):
        """Run Gobstopper application with Granian server (Flask-like interface)

        Example:
            gobstopper run                    # Run app:app on 127.0.0.1:8000
            gobstopper run --reload           # Enable hot reloading
            gobstopper run --ssl-cert cert.pem --ssl-key key.pem  # Enable HTTPS
        """
        # Load config file if specified
        config_data = {}
        if config:
            config_data = load_config_file(config)
            if config_data:
                click.echo(f"📄 Loaded configuration from: {config}.json/toml")

        # Merge config with CLI args (CLI args take precedence)
        # Server settings
        host = host or config_data.get('host', '127.0.0.1')
        port = port or config_data.get('port', 8000)
        workers = workers or config_data.get('workers', 1)
        threads = threads or config_data.get('threads', 1)
        loop = loop or config_data.get('loop', 'uvloop')
        
        # Logging
        log_level = log_level or config_data.get('log_level', 'info')
        if access_log is None:
            access_log = config_data.get('access_log', True)
            
        # SSL
        ssl_cert = ssl_cert or config_data.get('ssl_cert')
        ssl_key = ssl_key or config_data.get('ssl_key')

        # FLASH PREVIEW: Force binding if sharing
        if share and host in ('127.0.0.1', 'localhost'):
            host = '0.0.0.0'

        if not reload:
            reload = config_data.get('reload', False)

        # Allow config to override app if not specified on CLI
        if app == 'app:app' and 'app' in config_data:
            app = config_data['app']

        # Detect platform and set runtime mode
        machine = platform.machine().lower()
        runtime_mode = config_data.get('runtime_mode')
        if not runtime_mode:
            if machine in ('arm64', 'aarch64'):
                runtime_mode = 'st'  # Single-threaded for ARM (Apple Silicon)
                click.echo(f"🍎 Detected ARM architecture ({machine}), using single-threaded mode")
            else:
                runtime_mode = 'mt'  # Multi-threaded for x86_64
                click.echo(f"💻 Detected x86_64 architecture, using multi-threaded mode")
        else:
            click.echo(f"⚙️  Using configured runtime mode: {runtime_mode}")

        # Build granian command
        cmd = [
            'granian',
            '--interface', 'rsgi',
            '--host', host,
            '--port', str(port),
            '--workers', str(workers),
            '--runtime-threads', str(threads),
            '--log-level', log_level,
            '--backlog', '16384',
            '--loop', loop,
            '--respawn-failed-workers',
            '--runtime-mode', runtime_mode,
        ]

        if access_log:
            cmd.append('--access-log')
        else:
            cmd.append('--no-access-log')

        if ssl_cert and ssl_key:
            cmd.extend(['--ssl-certificate', ssl_cert, '--ssl-keyfile', ssl_key])
            scheme = "https"
        else:
            scheme = "http"

        if reload:
            cmd.append('--reload')
            # SMART WATCHER: Auto-detect extra paths to watch
            reload_paths = []
            for path in ['templates', 'static', '.env', 'gobstopper.toml', 'pyproject.toml']:
                if Path(path).exists():
                    reload_paths.append(path)
            
            # Add any extra paths configured in gobstopper.json/toml
            extra_watch = config_data.get('reload_paths', [])
            reload_paths.extend(extra_watch)
            
            if reload_paths:
                # Deduplicate
                reload_paths = list(set(reload_paths))
            if reload_paths:
                # Deduplicate
                reload_paths = list(set(reload_paths))
                # Pass to Granian (separate flag for each path)
                for path in reload_paths:
                    cmd.append('--reload-paths')
                    cmd.append(path)
                click.echo(f"👁️  Smart Watcher active: monitoring {', '.join(reload_paths)}")

        cmd.append(app)

        # FLASH PREVIEW: Share logic
        share_url = None
        if share:
            local_ip = detect_local_ip()
            if local_ip:
                share_url = f"{scheme}://{local_ip}:{port}"
                click.echo("\n📱 Flash Preview Enabled")
                click.echo(f"   Local Network URL: {share_url}")
                click.echo("   Scan to test on mobile:")
                print_qr_code(share_url)
            else:
                click.echo("⚠️  Could not detect local IP for Flash Preview", err=True)

        # Display startup info
        click.echo(f"🚀 Starting Gobstopper application: {app}")
        click.echo(f"📍 Server: {scheme}://{host}:{port}")
        if share_url:
             click.echo(f"📡 Shared: {share_url}")
        click.echo(f"👷 Workers: {workers}")
        click.echo(f"🧵 Threads: {threads}")
        click.echo(f"⚙️  Runtime: {runtime_mode}")
        click.echo(f"🔄 Loop: {loop}")
        if reload:
            click.echo(f"🔄 Auto-reload: enabled")
        click.echo(f"\n💡 Press Ctrl+C to stop\n")

        # Run granian
        try:
            subprocess.run(cmd, check=True)
        except KeyboardInterrupt:
            click.echo("\n\n👋 Shutting down gracefully...")
        except FileNotFoundError:
            click.echo("❌ Error: granian not found. Install with: uv add granian", err=True)
            sys.exit(1)
        except subprocess.CalledProcessError as e:
            click.echo(f"❌ Error running granian: {e}", err=True)
            sys.exit(e.returncode)

    @cli.command()
    def version():
        """Show Gobstopper version"""
        from .. import __version__
        click.echo(f"Gobstopper v{__version__}")
        click.echo("High-performance async web framework")
        click.echo("Built for Granian's RSGI interface")


def detect_local_ip() -> Optional[str]:
    """Detect the local network IP address"""
    import socket
    try:
        # Use a dummy socket to determine the outward facing interface
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Connect to a public DNS server (doesn't actually send data)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None

def print_qr_code(data: str):
    """Print a simple ASCII QR code to stdout"""
    try:
        # Try to use existing library if available
        import qrcode
        qr = qrcode.QRCode()
        qr.add_data(data)
        qr.print_ascii(invert=True)
    except ImportError:
        # Fallback to simple banner if qrcode lib is missing
        click.echo(f"   (Install 'qrcode' for real QR: pip install qrcode)")
        click.echo(f"   [ {data} ]")



def run_interactive_setup() -> tuple:
    """Run interactive project setup"""
    import inquirer
    
    questions = [
        inquirer.List('usecase',
                     message="What type of application are you building?",
                     choices=[
                         ('Data Science API', 'data-science'),
                         ('Real-time Dashboard', 'real-time-dashboard'),
                         ('Content Management System', 'content-management'),
                         ('Microservice', 'microservice'),
                     ]),
        inquirer.List('structure',
                     message="How would you like to structure your project?",
                     choices=[
                         ('Modular (recommended)', 'modular'),
                         ('Blueprints', 'blueprints'),
                         ('Microservices', 'microservices'),
                         ('Single file', 'single'),
                     ]),
        inquirer.Checkbox('features',
                         message="Which features do you need? (Space to select)",
                         choices=[
                             'auth',
                             'websockets',
                             'admin',
                             'rate_limiting',
                             'monitoring',
                             'api_docs',
                             'docker',
                             'kubernetes',
                         ]),
    ]
    
    try:
        answers = inquirer.prompt(questions)
        return answers['usecase'], answers['structure'], answers['features']
    except:
        # Fallback if inquirer not available
        click.echo("Install 'inquirer' for interactive mode: pip install inquirer")
        return 'microservice', 'modular', []


def generate_model_code(name: str, fields: List[tuple]) -> str:
    """Generate model code"""
    code = f'''"""
{name} model
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class {name}:
    """
    {name} data model
    """
'''
    
    for field_name, field_type in fields:
        python_type = {
            'str': 'str',
            'int': 'int',
            'float': 'float',
            'bool': 'bool',
            'datetime': 'datetime',
            'date': 'date',
            'json': 'dict',
            'list': 'list',
        }.get(field_type, 'str')
        
        code += f"    {field_name}: {python_type}\n"
    
    code += '''
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
'''
    
    for field_name, _ in fields:
        code += f'            "{field_name}": self.{field_name},\n'
    
    code += '''        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "''' + name + '''":
        """Create from dictionary"""
        return cls(**data)
'''
    
    return code


def generate_endpoint_code(path: str, method: str, auth: bool) -> str:
    """Generate endpoint code"""
    func_name = path.replace('/', '_').replace('<', '').replace('>', '').strip('_')
    
    code = f'''
@app.{method.lower()}("{path}")
'''
    
    if auth:
        code += '''@require_auth
'''
    
    code += f'''async def {func_name}(request):
    """
    {method} {path} endpoint
    """
'''
    
    if method in ['POST', 'PUT', 'PATCH']:
        code += '''    data = await request.get_json()
    
    # TODO: Validate and process data
    
'''
    
    code += '''    # TODO: Implement endpoint logic
    
    return {"message": "Not implemented"}
'''
    
    return code


def generate_task_code(name: str, category: str) -> str:
    """Generate task code"""
    code = f'''"""
{name} background task
"""

import asyncio
from datetime import datetime


async def {name}(**kwargs):
    """
    {name} task implementation
    
    Category: {category}
    """
    print(f"Starting {name} task at {{datetime.now()}}")
    
    # TODO: Implement task logic
    await asyncio.sleep(1)  # Simulate work
    
    result = {{
        "task": "{name}",
        "category": "{category}",
        "completed_at": datetime.now().isoformat(),
        "kwargs": kwargs
    }}
    
    print(f"Completed {name} task")
    return result
'''
    
    return code


if CLICK_AVAILABLE:
    cli.add_command(sdk)