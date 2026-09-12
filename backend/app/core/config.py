import os

# Standard 12-factor config: never hardcode credentials.
# Local dev default matches the `scheduler_dev` DB created during setup (see README/commands doc).
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://scheduler_app:scheduler_dev_pw@localhost:5432/scheduler_dev",
)

# --- Auth / JWT settings (SB2/US7/T1) -------------------------------------
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-only-insecure-secret-change-me")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
