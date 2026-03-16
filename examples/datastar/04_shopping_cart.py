"""
Datastar Example 4: Shopping Cart (Reactive Signals)

Demonstrates reactive state management with client-side calculations.
Cart total updates automatically when quantity changes - no server round-trip needed!
"""

from gobstopper import Gobstopper
from gobstopper.extensions.datastar import Datastar
from gobstopper.middleware.security import SecurityMiddleware

app = Gobstopper(name="shopping_cart", debug=True)

# Security with Datastar auto-configuration
security = SecurityMiddleware(
    enable_csrf=False,
    datastar_enabled=True,
    cookie_secure=False,
)
app.add_middleware(security)

@app.get("/")
async def index(request):
    """Render the shopping cart page."""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Shopping Cart - Datastar Example</title>
        <script type="module" src="https://cdn.jsdelivr.net/gh/starfederation/datastar@v1.0.0-RC.8/bundles/datastar.js"></script>
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                max-width: 600px;
                margin: 2rem auto;
                padding: 0 1rem;
                background: #f5f5f5;
            }
            .card {
                background: white;
                padding: 2rem;
                border-radius: 0.5rem;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                margin-bottom: 1rem;
            }
            h1 { margin-top: 0; color: #333; }
            .item {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 1rem 0;
                border-bottom: 1px solid #eee;
            }
            .item:last-child { border-bottom: none; }
            .item-name { font-weight: 500; }
            .item-price { color: #667eea; }
            input[type="number"] {
                width: 60px;
                padding: 0.25rem;
                text-align: center;
                border: 2px solid #ddd;
                border-radius: 0.25rem;
            }
            .totals {
                margin-top: 1rem;
                padding-top: 1rem;
                border-top: 2px solid #ddd;
            }
            .total-row {
                display: flex;
                justify-content: space-between;
                margin-bottom: 0.5rem;
            }
            .total-row.final {
                font-size: 1.2rem;
                font-weight: 600;
                color: #667eea;
            }
            button {
                width: 100%;
                padding: 1rem;
                background: #667eea;
                color: white;
                border: none;
                border-radius: 0.5rem;
                font-size: 1.1rem;
                cursor: pointer;
                margin-top: 1rem;
            }
            button:hover { background: #5568d3; }
            button:disabled {
                background: #ccc;
                cursor: not-allowed;
            }
        </style>
    </head>
    <body>
        <div class="card">
            <h1>🛒 Shopping Cart</h1>
            
            <!-- Initialize reactive signals -->
            <div data-signals="{
                qty1: 1,
                qty2: 1,
                price1: 29.99,
                price2: 49.99,
                taxRate: 0.08
            }">
                <!-- Computed values (auto-calculate!) -->
                <div 
                    data-computed:subtotal="($qty1 * $price1) + ($qty2 * $price2)"
                    data-computed:tax="$subtotal * $taxRate"
                    data-computed:total="$subtotal + $tax"
                >
                    <div class="item">
                        <div>
                            <div class="item-name">Wireless Mouse</div>
                            <div class="item-price">$<span data-text="$price1.toFixed(2)"></span></div>
                        </div>
                        <input type="number" min="0" max="99" data-bind:qty1 />
                    </div>
                    
                    <div class="item">
                        <div>
                            <div class="item-name">Mechanical Keyboard</div>
                            <div class="item-price">$<span data-text="$price2.toFixed(2)"></span></div>
                        </div>
                        <input type="number" min="0" max="99" data-bind:qty2 />
                    </div>
                    
                    <div class="totals">
                        <div class="total-row">
                            <span>Subtotal:</span>
                            <span>$<span data-text="$subtotal.toFixed(2)"></span></span>
                        </div>
                        <div class="total-row">
                            <span>Tax (8%):</span>
                            <span>$<span data-text="$tax.toFixed(2)"></span></span>
                        </div>
                        <div class="total-row final">
                            <span>Total:</span>
                            <span>$<span data-text="$total.toFixed(2)"></span></span>
                        </div>
                    </div>
                    
                    <button 
                        data-attr:disabled="$total < 1"
                        data-on:click="alert('Checkout with total: $' + $total.toFixed(2))"
                    >
                        Checkout
                    </button>
                </div>
            </div>
        </div>
        
        <div class="card" style="background: #fffbea; border-left: 4px solid #f59e0b;">
            <strong>💡 Try it:</strong> Change the quantities and watch the totals update instantly - no server requests needed!
        </div>
    </body>
    </html>
    """
    return html

if __name__ == "__main__":
    print("🛒 Shopping Cart Example")
    print("Visit: http://localhost:8000")
    print("Change quantities to see reactive calculations!")
