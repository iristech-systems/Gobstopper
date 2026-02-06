"""
Datastar Example 3: Click-to-Edit

Demonstrates inline editing pattern with view/edit mode switching.
Click "Edit" to modify contact details, then save or cancel.
"""

from gobstopper import Gobstopper
from gobstopper.ext.datastar import Datastar, MergeMode
from gobstopper.middleware.security import SecurityMiddleware

app = Gobstopper(name="click_to_edit", debug=True)

# Security with Datastar auto-configuration
security = SecurityMiddleware(
    enable_csrf=False,
    datastar_enabled=True,
    cookie_secure=False,
)
app.add_middleware(security)

# Mock contact data
contact = {
    "first_name": "John",
    "last_name": "Doe",
    "email": "john.doe@example.com"
}

@app.get("/")
async def index(request):
    """Render the main page."""
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Click-to-Edit - Datastar Example</title>
        <script type="module" src="https://cdn.jsdelivr.net/gh/starfederation/datastar@1.0.0-RC.7/bundles/datastar.js"></script>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                max-width: 500px;
                margin: 2rem auto;
                padding: 0 1rem;
            }}
            .card {{
                background: white;
                padding: 2rem;
                border-radius: 0.5rem;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            }}
            h1 {{ margin-top: 0; color: #333; }}
            .field {{ margin-bottom: 1rem; }}
            .label {{ font-weight: 600; color: #666; font-size: 0.9rem; }}
            .value {{ color: #333; font-size: 1.1rem; }}
            input {{
                width: 100%;
                padding: 0.5rem;
                font-size: 1rem;
                border: 2px solid #ddd;
                border-radius: 0.25rem;
                box-sizing: border-box;
            }}
            button {{
                padding: 0.5rem 1rem;
                margin-right: 0.5rem;
                border: none;
                border-radius: 0.25rem;
                cursor: pointer;
                font-size: 1rem;
            }}
            .btn-primary {{ background: #667eea; color: white; }}
            .btn-secondary {{ background: #ddd; color: #333; }}
            .btn-primary:hover {{ background: #5568d3; }}
            .btn-secondary:hover {{ background: #ccc; }}
        </style>
    </head>
    <body>
        <div class="card">
            <h1>👤 Contact Details</h1>
            <div id="contact">
                <div class="field">
                    <div class="label">First Name</div>
                    <div class="value">{contact['first_name']}</div>
                </div>
                <div class="field">
                    <div class="label">Last Name</div>
                    <div class="value">{contact['last_name']}</div>
                </div>
                <div class="field">
                    <div class="label">Email</div>
                    <div class="value">{contact['email']}</div>
                </div>
                <button class="btn-primary" data-on:click="@get('/edit')">Edit</button>
            </div>
        </div>
    </body>
    </html>
    """
    return html

@app.get("/edit")
async def edit(request):
    """Return edit form."""
    html = f'''
    <div id="contact">
        <div class="field">
            <div class="label">First Name</div>
            <input type="text" data-bind:firstName value="{contact['first_name']}" />
        </div>
        <div class="field">
            <div class="label">Last Name</div>
            <input type="text" data-bind:lastName value="{contact['last_name']}" />
        </div>
        <div class="field">
            <div class="label">Email</div>
            <input type="email" data-bind:email value="{contact['email']}" />
        </div>
        <button class="btn-primary" data-on:click="@put('/save')">Save</button>
        <button class="btn-secondary" data-on:click="@get('/cancel')">Cancel</button>
    </div>
    '''
    return Datastar.merge_fragments(html, merge_mode=MergeMode.OUTER)

@app.put("/save")
async def save(request):
    """Save changes and return to view mode."""
    # Get data from request
    data = await request.json()
    contact["first_name"] = data.get("firstName", contact["first_name"])
    contact["last_name"] = data.get("lastName", contact["last_name"])
    contact["email"] = data.get("email", contact["email"])
    
    # Return view mode
    html = f'''
    <div id="contact">
        <div class="field">
            <div class="label">First Name</div>
            <div class="value">{contact['first_name']}</div>
        </div>
        <div class="field">
            <div class="label">Last Name</div>
            <div class="value">{contact['last_name']}</div>
        </div>
        <div class="field">
            <div class="label">Email</div>
            <div class="value">{contact['email']}</div>
        </div>
        <button class="btn-primary" data-on:click="@get('/edit')">Edit</button>
    </div>
    '''
    return Datastar.merge_fragments(html, merge_mode=MergeMode.OUTER)

@app.get("/cancel")
async def cancel(request):
    """Cancel editing and return to view mode."""
    html = f'''
    <div id="contact">
        <div class="field">
            <div class="label">First Name</div>
            <div class="value">{contact['first_name']}</div>
        </div>
        <div class="field">
            <div class="label">Last Name</div>
            <div class="value">{contact['last_name']}</div>
        </div>
        <div class="field">
            <div class="label">Email</div>
            <div class="value">{contact['email']}</div>
        </div>
        <button class="btn-primary" data-on:click="@get('/edit')">Edit</button>
    </div>
    '''
    return Datastar.merge_fragments(html, merge_mode=MergeMode.OUTER)

if __name__ == "__main__":
    print("✏️  Click-to-Edit Example")
    print("Visit: http://localhost:8000")
    print("Click 'Edit' to modify contact details")
