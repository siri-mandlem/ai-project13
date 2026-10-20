import logging
import os
import secrets
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from sqlalchemy import inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import generate_password_hash

from backend.config import cors_origins
from backend.extensions import db
from backend.models import Appointment, MedicalRecord, User


PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_ROOT = PROJECT_ROOT / "frontend"

load_dotenv(PROJECT_ROOT / ".env")


def _database_uri() -> str:
    configured_uri = os.environ.get("DATABASE_URL", "").strip()

    if not configured_uri:
        production = (
            os.environ.get("APP_ENV", "").lower() == "production"
            or os.environ.get("RENDER", "").lower() == "true"
        )
        if production:
            raise RuntimeError(
                "DATABASE_URL is missing. Configure the Neon PostgreSQL "
                "connection string in the deployment environment."
            )
        return "sqlite:///instance/hospital.sqlite3"

    url = make_url(configured_uri)

    if url.drivername in {"postgres", "postgresql"}:
        url = url.set(drivername="postgresql+psycopg2")

    if url.drivername not in {"postgresql+psycopg2", "sqlite"}:
        raise RuntimeError(
            "This application requires PostgreSQL in production (SQLite is "
            "supported for local development). "
            "Check your DATABASE_URL."
        )

    production = (
        os.environ.get("APP_ENV", "").lower() == "production"
        or os.environ.get("RENDER", "").lower() == "true"
    )
    if production and url.drivername != "postgresql+psycopg2":
        raise RuntimeError(
            "Production DATABASE_URL must point to a PostgreSQL database."
        )

    if url.drivername == "postgresql+psycopg2" and "sslmode" not in url.query:
        url = url.update_query_dict({"sslmode": "require"})

    return url.render_as_string(hide_password=False)

def _upgrade_legacy_user_columns() -> None:
    """Safely add columns missing from older users tables."""
    inspector = inspect(db.engine)

    if not inspector.has_table("users"):
        return

    existing_columns = {
        column["name"] for column in inspector.get_columns("users")
    }

    missing_columns = {
        "phone": "VARCHAR(40)",
        "specialty": "VARCHAR(120)",
        "is_active": "BOOLEAN NOT NULL DEFAULT TRUE",
    }

    dialect = db.engine.dialect.name

    with db.engine.begin() as connection:
        for column_name, column_type in missing_columns.items():
            if column_name in existing_columns:
                continue

            if dialect == "postgresql":
                connection.execute(
                    text(
                        f"ALTER TABLE users ADD COLUMN IF NOT EXISTS "
                        f"{column_name} {column_type}"
                    )
                )
            elif dialect == "sqlite":
                connection.execute(
                    text(
                        f"ALTER TABLE users ADD COLUMN "
                        f"{column_name} {column_type}"
                    )
                )
            else:
                raise RuntimeError(
                    f"Unsupported database dialect: {dialect}"
                )


def _create_application_tables() -> None:
    db.create_all()
    _upgrade_legacy_user_columns()

    expected_tables = {
        User.__tablename__,
        Appointment.__tablename__,
        MedicalRecord.__tablename__,
    }
    existing_tables = set(inspect(db.engine).get_table_names())
    missing_tables = expected_tables - existing_tables
    if missing_tables:
        raise RuntimeError(
            "Database initialization did not create required tables: "
            + ", ".join(sorted(missing_tables))
        )

    app_logger = logging.getLogger(__name__)
    app_logger.info(
        "Database schema ready; required application tables are present: %s",
        ", ".join(sorted(expected_tables)),
    )


def _seed_admin() -> None:
    email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    password = os.environ.get("ADMIN_PASSWORD", "")

    if not email and not password:
        return

    if not email or "@" not in email or len(password) < 12:
        raise RuntimeError(
            "Set both ADMIN_EMAIL and ADMIN_PASSWORD; "
            "the password must be at least 12 characters."
        )

    existing = db.session.scalar(
        select(User).where(User.email == email)
    )

    if existing is not None:
        if existing.role != "admin":
            raise RuntimeError(
                "ADMIN_EMAIL is already registered to a non-admin account."
            )
        return

    admin = User(
        name=os.environ.get(
            "ADMIN_NAME", "Hospital Administrator"
        ).strip() or "Hospital Administrator",
        email=email,
        password_hash=generate_password_hash(password),
        role="admin",
    )

    db.session.add(admin)
    db.session.commit()


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(
        __name__,
        instance_path=str(PROJECT_ROOT / "instance"),
    )
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    production = (
        os.environ.get("APP_ENV", "").lower() == "production"
        or os.environ.get("RENDER", "").lower() == "true"
    )

    secret_key = os.environ.get("SECRET_KEY", "").strip()

    if production and not secret_key:
        raise RuntimeError(
            "SECRET_KEY must be configured in production."
        )

    app.config.update(
        SECRET_KEY=secret_key or secrets.token_urlsafe(32),
        SQLALCHEMY_DATABASE_URI=_database_uri(),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True},
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=production,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
        MAX_CONTENT_LENGTH=1024 * 1024,
    )

    if test_config:
        app.config.update(test_config)

    db.init_app(app)

    origins = cors_origins()
    if origins:
        CORS(
            app,
            resources={r"/api/*": {"origins": origins}},
            supports_credentials=True,
        )

    from backend.routes import api
    app.register_blueprint(api)

    @app.get("/")
    def index():
        return send_from_directory(FRONTEND_ROOT, "index.html")

    @app.get("/assets/<path:filename>")
    def assets(filename: str):
        return send_from_directory(FRONTEND_ROOT, filename)

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.get("/ready")
    def ready():
        db.session.execute(text("SELECT 1"))
        return jsonify({"status": "ready"})

    @app.errorhandler(SQLAlchemyError)
    def handle_database_error(error):
        db.session.rollback()
        app.logger.exception("Database operation failed")

        if app.config.get("TESTING"):
            raise error

        return jsonify(
            {"error": "The database request could not be completed."}
        ), 503

    with app.app_context():
        # Importing each model registers its table before metadata creation.
        _create_application_tables()

        # Create the initial administrator if one does not exist.
        _seed_admin()

    if not production:
        app.logger.setLevel(logging.INFO)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "5000")),
        debug=False,
    )
