from gobstopper import Gobstopper
from gobstopper.http import Response

# Enable debug mode to see the Error Prism
app = Gobstopper(name="error_demo", debug=True)

@app.get("/")
async def home(request):
    return Response("""
        <h1>Error Prism Demo</h1>
        <p>Click the button below to crash the server and see the new error page.</p>
        <div style="margin-top: 2rem;">
            <a href="/crash" style="font-size: 2rem; background: #ff4757; color: white; text-decoration: none; padding: 1rem 2rem; border-radius: 8px;">
                💥 BOOM!
            </a>
        </div>
    """, content_type="text/html")

@app.get("/crash")
async def crash(request):
    # This seemingly innocent dictionary lookup will fail...
    # simulating a common bug!
    user_data = {"name": "Neo"}
    return f"Hello, {user_data['username']}"  # KeyError: 'username'

if __name__ == "__main__":
    print("Run with: gobstopper run examples/error_demo:app")
