"""Entry point — creates the Sanic application and registers blueprints.

No business logic or database code belongs here.  This file:
1. Creates the Sanic app instance and configures CORS.
2. Registers the API route blueprint.
3. Attaches the global error handler.
4. Initializes the database schema at startup.

Start command (from root):
cd app-sanic && sanic server.app
"""

from sanic import Sanic
from sanic_ext import Extend

from config.settings import CORS_ORIGINS
from models.database import init_db
from routes.api_routes import api
from utils.error_handler import register_error_handlers

app = Sanic("Transaction-Management-App")
app.config.CORS_ORIGINS = CORS_ORIGINS
# "Swagger/OpenAPI is enabled for development convenience. 
# In production, OAS should be disabled or protected behind authentication."
app.config.OAS = True           
app.config.OAS_UI_DEFAULT = "swagger"  
Extend(app)

app.blueprint(api)
register_error_handlers(app)
init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)