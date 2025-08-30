from app import app

# Import routes
import routes

# Import cascading dropdown APIs
import api_cascading_dropdowns

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)