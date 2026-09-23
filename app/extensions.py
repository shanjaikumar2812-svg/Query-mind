"""Flask extensions initialization."""

from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

db = SQLAlchemy()
cors = CORS()

# In-memory, per-process rate limiter — deliberately simple (no Redis) since
# QueryMind is a small single-process Flask app. Default limits come from
# app.config (RATE_LIMIT_DEFAULT / RATE_LIMIT_ASK) so they're configurable
# per-deployment without code changes. Actual limit values are applied in
# create_app() once config is loaded, and per-route in app/routes/query.py.
limiter = Limiter(key_func=get_remote_address)
