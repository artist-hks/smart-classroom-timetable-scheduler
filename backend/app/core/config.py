import os

# Standard 12-factor config: never hardcode credentials.
# Local dev default matches the `scheduler_dev` DB created during setup (see README/commands doc).
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://scheduler_app:scheduler_dev_pw@localhost:5432/scheduler_dev",
)
