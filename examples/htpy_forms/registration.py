from gobstopper import Gobstopper
from gobstopper.forms import BaseForm, TextField
from gobstopper.middleware.security import SecurityMiddleware
from gobstopper.html import html, head, body, div, h1, form, button, script, link, meta, style, a
from gobstopper.html.datastar import signals, on_input
from gobstopper.ext.datastar import Datastar
# ...

app = Gobstopper(name="htpy_registration")

# Enable security with Datastar support
security = SecurityMiddleware(
    secret_key="dev-secret-key",
    enable_csrf=True,
    datastar_enabled=True,
    cookie_secure=False,  # Dev mode
    debug=True
)
app.add_middleware(security)

class RegistrationForm(BaseForm):
    def _init_fields(self):
        self.add_field(TextField(
            name="username",
            label="Username",
            required=True,
            placeholder="Choose a username",
            attrs=on_input("@post('/validate/username')")
        ))
        self.add_field(TextField(
            name="email",
            label="Email",
            input_type="email",
            required=True,
            placeholder="you@example.com"
        ))
        self.add_field(TextField(
            name="password",
            label="Password",
            input_type="password",
            required=True
        ))

# Create validation endpoints
@app.post("/validate/username")
async def validate_username(request):
    data = await request.json()
    username = data.get("username")
    
    # Simulate DB check
    valid = len(username) >= 3
    error = "Username must be at least 3 chars" if not valid else ""
    if valid and username == "taken":
        valid = False
        error = "Username already taken"
        
    return Datastar.patch_signals({
        "errors.username": error
    })

@app.get("/")
async def registration_page(request):
    # Auto-creates form with CSRF token from request
    form_obj = RegistrationForm(request)
    
    # Build page with htpy
    page = html[
        head[
            meta(charset="utf-8"),
            meta(name="viewport", content="width=device-width, initial-scale=1.0"),
            script(type="module", src="https://cdn.jsdelivr.net/gh/starfederation/datastar@1.0.0-RC.7/bundles/datastar.js"),
            # Simple styles
            link(rel="stylesheet", href="https://cdn.jsdelivr.net/npm/@picocss/pico@2/css/pico.min.css"),
            style["""
                .error { color: red; font-size: 0.8em; margin-top: 5px; display: block; }
                .field { margin-bottom: 20px; }
            """],
            # Inject CSRF token into Datastar requests
            script["""
                document.addEventListener('datastar-request', (evt) => {
                    const csrf = document.querySelector('input[name="csrf_token"]');
                    if (csrf) {
                        evt.detail.headers['X-CSRF-Token'] = csrf.value;
                    }
                });
            """]
        ],
        body[
            div(class_="container", **signals({"errors": {}}))[
                h1["Register"],
                # Form auto-renders!
                form_obj
            ]
        ]
    ]
    
    return page  # Response auto-detects __html__

@app.post("/")
async def register(request):
    form_data = await request.get_form()
    form_obj = RegistrationForm(request, data=form_data)
    
    if form_obj.is_valid():
        data = form_obj.get_cleaned_data()
        return html[
            head[
                link(rel="stylesheet", href="https://cdn.jsdelivr.net/npm/@picocss/pico@2/css/pico.min.css")
            ],
            body[
                div(class_="container")[
                    h1["Success!"],
                    div[f"Registered user: {data['username']} ({data['email']})"],
                    a(href="/")["Back"]
                ]
            ]
        ]
    
    # Re-render with errors
    page = html[
        head[
            meta(charset="utf-8"),
            script(type="module", src="https://cdn.jsdelivr.net/gh/starfederation/datastar@1.0.0-RC.7/bundles/datastar.js"),
            link(rel="stylesheet", href="https://cdn.jsdelivr.net/npm/@picocss/pico@2/css/pico.min.css")
        ],
        body[
            div(class_="container", **signals({"errors": {}}))[
                h1["Register"],
                form_obj  # Renders with errors populated
            ]
        ]
    ]
    return page
