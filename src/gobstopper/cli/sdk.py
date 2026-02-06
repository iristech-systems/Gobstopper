
import click
import importlib
import inspect
from pathlib import Path
from ..core.app import Gobstopper

def type_to_ts(typ):
    if typ == str: return "string"
    if typ == int: return "number"
    if typ == bool: return "boolean"
    if typ == dict: return "Record<string, any>"
    if typ == list: return "any[]"
    return "any"

@click.command()
@click.option("--app", "-a", required=True, help="Application instance (e.g. app:app)")
@click.option("--out", "-o", default="./client.ts", help="Output file path")
def sdk(app: str, out: str):
    """Generate a typed TypeScript SDK for your API."""
    try:
        module_name, app_name = app.split(":")
        module = importlib.import_module(module_name)
        gob_app = getattr(module, app_name)
    except Exception as e:
        click.echo(f"Error loading app: {e}")
        return

    if not isinstance(gob_app, Gobstopper):
        click.echo("Error: Application instance is not a Gobstopper app.")
        return

    ts_code = []
    ts_code.append("// Generated Gobstopper SDK")
    ts_code.append("// Do not edit manually\n")
    ts_code.append("export class ApiClient {")
    ts_code.append("  constructor(private baseUrl: string = '') {}")
    ts_code.append("  private async request(method: string, path: string, body?: any) {")
    ts_code.append("    const res = await fetch(this.baseUrl + path, {")
    ts_code.append("      method,")
    ts_code.append("      headers: { 'Content-Type': 'application/json' },")
    ts_code.append("      body: body ? JSON.stringify(body) : undefined")
    ts_code.append("    });")
    ts_code.append("    if (!res.ok) throw new Error(res.statusText);")
    ts_code.append("    return res.json();")
    ts_code.append("  }\n")

    # Iterate routes
    # _all_routes contains RouteHandler objects
    # We need to extract method names/signatures
    
    seen_names = set()
    
    for route in gob_app._all_routes:
        # route is RouteHandler(pattern, handler, methods)
        name = getattr(route.handler, "__name__", "unknown")
        if name in seen_names: continue
        seen_names.add(name)
        
        # Determine params from pattern
        # Simple regex for <param>
        import re
        params = re.findall(r"<([^>]+)>", route.pattern)
        # e.g. <id>, <int:id>
        
        args_str = ""
        url_replacer = f"'{route.pattern}'"
        
        ts_params = []
        
        for p in params:
            if ":" in p:
                ptype, pname = p.split(":")
            else:
                ptype, pname = "str", p
                
            ts_type = "string"
            if ptype == "int": ts_type = "number"
            
            ts_params.append(f"{pname}: {ts_type}")
            
            # Replace in URL string: <int:id> -> ${id}
            url_replacer = url_replacer.replace(f"<{p}>", f"${{{pname}}}")
        
        # Check signature for body
        sig = inspect.signature(route.handler)
        has_body = False
        # Heuristic: if params has 'request', ignore. If typed, use it?
        # For now, simple assumption: POST/PUT might have body
        
        method = route.methods[0] # Just take first method
        
        func_name = name
        
        args = ", ".join(ts_params)
        if method in ["POST", "PUT", "PATCH"]:
            if args: args += ", "
            args += "body: any"
            has_body = True
            
        url_fixed = url_replacer.replace("'", "`")
        
        ts_code.append(f"  async {func_name}({args}) {{")
        body_arg = ", body" if has_body else ""
        ts_code.append(f"    return this.request('{method}', {url_fixed}{body_arg});")
        ts_code.append("  }")

    ts_code.append("}")
    
    with open(out, "w") as f:
        f.write("\n".join(ts_code))
        
    click.echo(f"✨ SDK generated at {out}")

