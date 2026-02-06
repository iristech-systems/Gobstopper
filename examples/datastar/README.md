# Datastar Examples Gallery

A collection of practical Datastar examples demonstrating the most powerful patterns for building reactive, real-time web applications with Gobstopper.

## 🚀 Quick Start

Each example is a standalone application. Run any example with:

```bash
uv run gobstopper run examples/datastar/01_live_clock:app
```

Then visit `http://localhost:8000` in your browser.

## 📚 Examples

### 1. Live Clock (SSE Streaming)
**File:** `01_live_clock.py`  
**Pattern:** Real-time server-sent events

Demonstrates true server push with SSE. The clock updates 10 times per second showing millisecond precision. This is the foundation for any real-time dashboard, live feed, or streaming data visualization.

**Key Features:**
- Server-Sent Events (SSE) streaming
- High-frequency updates (10 Hz)
- Auto-reconnection on disconnect

**Run:**
```bash
uv run gobstopper run examples/datastar/01_live_clock:app
```

---

### 2. Debounced Search
**File:** `02_debounced_search.py`  
**Pattern:** Live search with automatic debouncing

Search-as-you-type with built-in debouncing. The search only fires after the user stops typing for 300ms, dramatically reducing server load.

**Key Features:**
- `data-on:input__debounce.300ms` modifier
- Live filtering without page reload
- Efficient server usage

**Run:**
```bash
uv run gobstopper run examples/datastar/02_debounced_search:app
```

---

### 3. Click-to-Edit
**File:** `03_click_to_edit.py`  
**Pattern:** Inline editing with view/edit modes

Edit content in-place without navigation. Click "Edit" to switch to edit mode, make changes, then save or cancel. Perfect for admin interfaces, profile pages, and content management.

**Key Features:**
- Seamless view/edit switching
- Two-way data binding with `data-bind`
- Optimistic UI updates

**Run:**
```bash
uv run gobstopper run examples/datastar/03_click_to_edit:app
```

---

### 4. Shopping Cart (Reactive Signals)
**File:** `04_shopping_cart.py`  
**Pattern:** Client-side reactive state management

A shopping cart with automatic total calculation. Change quantities and watch subtotal, tax, and total update instantly - **no server round-trips needed!**

**Key Features:**
- Reactive signals (`data-signals`)
- Computed values (`data-computed`)
- Client-side calculations
- Conditional button states

**Run:**
```bash
uv run gobstopper run examples/datastar/04_shopping_cart:app
```

---

## 🎯 Key Datastar Concepts

### Reactive Signals
Client-side state that automatically updates the UI:
```html
<div data-signals="{count: 0, name: 'John'}">
    <span data-text="$count"></span>
    <span data-text="$name"></span>
</div>
```

### Computed Values
Derived values that auto-recalculate:
```html
<div data-computed:total="$quantity * $price">
    <span data-text="$total"></span>
</div>
```

### Event Modifiers
Powerful built-in modifiers for common patterns:
- `__debounce.300ms` - Wait 300ms after last event
- `__throttle.1s` - Max once per second
- `__once` - Execute only once
- `__prevent` - Call preventDefault()

### SSE Streaming
Server-push updates without polling:
```python
async def generator():
    while True:
        yield Datastar.merge_fragments(html)
        await asyncio.sleep(0.1)

return Datastar.stream(generator())
```

## 🛠️ Gobstopper Integration

All examples use the new `datastar_enabled` flag for automatic security configuration:

```python
from gobstopper.middleware.security import SecurityMiddleware

security = SecurityMiddleware(
    datastar_enabled=True,  # ✨ One flag enables everything!
    cookie_secure=False,     # For development
)
```

This automatically:
- Disables COEP and COOP headers
- Adds `'unsafe-eval'` to CSP for Datastar expressions
- Adds Datastar CDN to CSP allowlist

## 📖 Learn More

- **Datastar Documentation:** https://data-star.dev
- **Gobstopper Docs:** (link to your docs)
- **Top 10 Use Cases:** See `datastar_top_10_use_cases.md` in the artifacts

## 💡 Tips

1. **Start Simple:** Begin with Example 1 (Live Clock) to understand SSE basics
2. **Use Modifiers:** Leverage `__debounce`, `__throttle` for better UX
3. **Reactive First:** Use computed values for client-side calculations
4. **Security:** Always use `datastar_enabled=True` in development

## 🐛 Troubleshooting

**Clock not updating?**
- Check browser console for CSP errors
- Verify `datastar_enabled=True` in SecurityMiddleware
- Ensure Datastar CDN is accessible

**Search not debouncing?**
- Verify the modifier syntax: `__debounce.300ms` (double underscore)
- Check that `data-bind:search` is present

**Signals not reactive?**
- Ensure signals are defined with `data-signals`
- Use `$` prefix when referencing signals: `$count`, not `count`

## 🎨 Customization

Each example includes inline CSS for easy customization. Feel free to:
- Modify colors and styling
- Adjust update intervals
- Add more features
- Combine patterns

Happy coding! 🚀
