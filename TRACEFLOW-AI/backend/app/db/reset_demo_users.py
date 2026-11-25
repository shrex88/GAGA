"""Development-only CLI command to reset demo user credentials."""
import sys
from app.core.config import get_settings
from app.db.seed import seed_initial_data
from app.db.session import Base, SessionLocal, engine


def main() -> None:
    settings = get_settings()
    if settings.APP_ENV.lower() != "development":
        print("ERROR: Demo credential reset is only permitted when APP_ENV=development.", file=sys.stderr)
        sys.exit(1)

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_initial_data(db, reset_demo_passwords=True)
        print("Demo user credentials have been idempotently seeded/reset for development.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
