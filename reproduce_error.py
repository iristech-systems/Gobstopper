from gobstopper import Gobstopper
from gobstopper.http import Response
import os

# Enable debug mode to see the Error Prism
app = Gobstopper(name="reproduce_error", debug=True)
app.init_templates("examples/templates")

@app.get("/")
async def home(request):
    return Response("""
        <h1>reproduce_error</h1>
        <p>Click the button below to trigger a template render error.</p>
        <div style="margin-top: 2rem;">
            <a href="/error" style="background: #ff4757; color: white; text-decoration: none; padding: 1rem 2rem; border-radius: 8px;">
                Trigger Error
            </a>
        </div>
    """, content_type="text/html")

@app.get("/error")
async def trigger_error(request):
    # Ensure the template directory exists
    os.makedirs("examples/templates", exist_ok=True)
    error_template = "examples/templates/error_syntax.html"
    
    # Write a template with a syntax error (invalid filter/variable usage)
    # Note: we use a known syntax error that Tera catches during render if possible
    with open(error_template, "w") as f:
        f.write("Hello, {{ name }}!\n\n")
        f.write("This is a test of structured error reporting.\n")
        f.write("The next line has a deliberate syntax error:\n")
        f.write("{{ \"test\" | unknown_filter_name }}\n")
        f.write("\nGoodbye!")

    # Try to render it. If it fails (which it should), Rust engine will raise TemplateRenderError.
    # We catch it here just to be sure we are testing what we want.
    async def render_it():
        # Using render_string with a name allows us to simulate a file render 
        # while ensuring the engine has the content even if it didn't reload yet.
        with open(error_template, "r") as f:
            content = f.read()
        return await app.render_string(content, name="World", __name__="error_syntax.html")

    return await render_it()

if __name__ == "__main__":
    import asyncio
    import sys
    
    async def test():
        print("🔍 Testing template rendering error...")
        # Ensure the template directory exists
        os.makedirs("examples/templates", exist_ok=True)
        error_template = "examples/templates/error_syntax.html"
        
        # Write a template with a PARSING error (invalid tag)
        with open(error_template, "w") as f:
            f.write("Hello, {{ name }}!\n\n")
            f.write("{% if %}\n") # Invalid syntax
            f.write("\nGoodbye!")
        
        # Reload templates to pick up change
        app.template_engine.reload()
            
        try:
            # Test 1: render_template (file-based)
            print("\n--- Test 1: render_template (file-based) ---")
            await app.render_template("error_syntax.html", name="World")
            print("❌ Error: rendering should have failed but succeeded!")
        except Exception as e:
            print(f"✅ Caught expected error type: {type(e).__name__}")
            print(f"Error Message:\n{str(e)}")
            print(f"Template: {getattr(e, 'template_name', 'None')}")
            print(f"Line: {getattr(e, 'line', 'None')}")
            print(f"Column: {getattr(e, 'column', 'None')}")

        try:
            # Test 2: render_string
            print("\n--- Test 2: render_string ---")
            with open(error_template, "r") as f:
                content = f.read()
            await app.render_string(content, name="World", __name__="error_syntax.html")
            print("❌ Error: rendering should have failed but succeeded!")
        except Exception as e:
            print(f"✅ Caught expected error type: {type(e).__name__}")
            print(f"Error Message:\n{str(e)}")
            print(f"Template: {getattr(e, 'template_name', 'None')}")
            print(f"Line: {getattr(e, 'line', 'None')}")
            print(f"Column: {getattr(e, 'column', 'None')}")
                
    asyncio.run(test())
