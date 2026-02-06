"""
Datastar Example 2: Debounced Search

Demonstrates live search with automatic debouncing.
Search updates only after user stops typing for 300ms.
"""

from gobstopper import Gobstopper
from gobstopper.ext.datastar import Datastar, MergeMode
from gobstopper.middleware.security import SecurityMiddleware

app = Gobstopper(name="debounced_search", debug=True)

# Security with Datastar auto-configuration
security = SecurityMiddleware(
    enable_csrf=False,
    datastar_enabled=True,
    cookie_secure=False,
)
app.add_middleware(security)

# Mock product database
PRODUCTS = [
    {"id": 1, "name": "Laptop", "price": 999.99},
    {"id": 2, "name": "Mouse", "price": 29.99},
    {"id": 3, "name": "Keyboard", "price": 79.99},
    {"id": 4, "name": "Monitor", "price": 299.99},
    {"id": 5, "name": "Headphones", "price": 149.99},
    {"id": 6, "name": "Webcam", "price": 89.99},
    {"id": 7, "name": "Microphone", "price": 129.99},
    {"id": 8, "name": "Desk Lamp", "price": 39.99},
]

@app.get("/")
async def index(request):
    """Render the search page."""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Debounced Search - Datastar Example</title>
        <script type="module" src="https://cdn.jsdelivr.net/gh/starfederation/datastar@1.0.0-RC.7/bundles/datastar.js"></script>
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                max-width: 600px;
                margin: 2rem auto;
                padding: 0 1rem;
                background: #f5f5f5;
            }
            h1 { color: #333; }
            input {
                width: 100%;
                padding: 1rem;
                font-size: 1.1rem;
                border: 2px solid #ddd;
                border-radius: 0.5rem;
                box-sizing: border-box;
            }
            input:focus {
                outline: none;
                border-color: #667eea;
            }
            #results {
                margin-top: 1rem;
                background: white;
                border-radius: 0.5rem;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            }
            .product {
                padding: 1rem;
                border-bottom: 1px solid #eee;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            .product:last-child { border-bottom: none; }
            .product-name { font-weight: 500; color: #333; }
            .product-price { color: #667eea; font-weight: 600; }
            .no-results {
                padding: 2rem;
                text-align: center;
                color: #999;
            }
        </style>
    </head>
    <body>
        <h1>🔍 Product Search</h1>
        <input 
            type="text" 
            placeholder="Search products..."
            data-bind:search
            data-on:input__debounce.300ms="@get('/search')"
        />
        <div id="results">
            <div class="no-results">Start typing to search...</div>
        </div>
    </body>
    </html>
    """
    return html

@app.get("/search")
async def search(request):
    """Search products and return results."""
    import json
    
    # Datastar sends data as JSON in the 'datastar' query parameter
    # request.args is a dict where values are lists
    datastar_json = request.args.get("datastar", ["{}"])[0]
    data = json.loads(datastar_json)
    query = data.get("search", "").lower()
    
    if not query:
        html = '<div id="results"><div class="no-results">Start typing to search...</div></div>'
    else:
        # Filter products
        results = [p for p in PRODUCTS if query in p["name"].lower()]
        
        if results:
            html = '<div id="results">'
            for product in results:
                html += f'''
                    <div class="product">
                        <span class="product-name">{product["name"]}</span>
                        <span class="product-price">${product["price"]}</span>
                    </div>
                '''
            html += '</div>'
        else:
            html = '<div id="results"><div class="no-results">No products found</div></div>'
    
    return Datastar.merge_fragments(html, merge_mode=MergeMode.OUTER)

if __name__ == "__main__":
    print("🔍 Debounced Search Example")
    print("Visit: http://localhost:8000")
    print("Try searching for: laptop, mouse, keyboard")
