from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.core.auth import get_password_hash
from app.models import *  # Import all models to ensure they are registered
from app.core.database import Base
from migrations.archive.postgresql_migration_manager import PostgreSQLMigrationManager as MigrationManager
import logging
import sys
import os
from pathlib import Path
import os

# Add database path for migration manager
# sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "database"))
# from migration_manager import MigrationManager

logger = logging.getLogger(__name__)


def init_db():
    """Initialize database with tables and default data."""
    # Create storage directory if it doesn't exist
    storage_dir = Path("./storage")
    storage_dir.mkdir(exist_ok=True)
    
    uploads_dir = storage_dir / "uploads"
    uploads_dir.mkdir(exist_ok=True)
    
    engine = create_engine(
        settings.DATABASE_URL,
        # Use configuration from .env file
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_pre_ping=settings.DB_POOL_PRE_PING,
        pool_recycle=settings.DB_POOL_RECYCLE,
        connect_args={
            "connect_timeout": settings.DB_CONNECTION_TIMEOUT,
        } if "postgresql" in settings.DATABASE_URL else {}
    )
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    
    # Run database migrations - PostgreSQL is now the primary database
    if "postgresql" in settings.DATABASE_URL:
        logger.info("PostgreSQL database detected - using PostgreSQL migration")
        try:
            from migrations.archive.postgresql_migration_manager import PostgreSQLMigrationManager
            migration_manager = PostgreSQLMigrationManager()
            migration_manager.migrate()
        except ImportError:
            logger.info("PostgreSQL migration manager not found, using standard initialization")
    else:
        # Fallback to SQLite migrations (deprecated)
        logger.warning("SQLite detected - consider migrating to PostgreSQL for better performance")
        migration_manager = MigrationManager()
        if hasattr(migration_manager, 'migrate'):
            migration_manager.migrate()
    
    # Create session
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    try:
        # Create default organizations first
        default_orgs = [
            {
                "name": "System Administration",
                "slug": "system-admin",
                "description": "Default organization for system administrators",
                "type": OrganizationType.ENTERPRISE,
                "is_active": True
            },
            {
                "name": "Demo Organization",
                "slug": "demo-org",
                "description": "A demo organization for testing purposes",
                "type": OrganizationType.SMALL_BUSINESS,
                "is_active": True
            },
            {
                "name": "Open Source Community",
                "slug": "open-source",
                "description": "Community for open source projects",
                "type": OrganizationType.NONPROFIT,
                "is_active": True
            }
        ]
        
        admin_org = None
        for org_data in default_orgs:
            # Check for existing organization by both slug and name to avoid duplicates
            existing_org = db.query(Organization).filter(
                (Organization.slug == org_data["slug"]) | 
                (Organization.name == org_data["name"])
            ).first()
            
            if not existing_org:
                org = Organization(**org_data)
                db.add(org)
                db.flush()  # Get the ID
                if org_data["slug"] == "system-admin":
                    admin_org = org
                print(f"Created organization: {org_data['name']}")
            else:
                if org_data["slug"] == "system-admin":
                    admin_org = existing_org
                print(f"Organization already exists: {existing_org.name}")
        
        # Create superuser if it doesn't exist
        user = db.query(User).filter(User.email == settings.FIRST_SUPERUSER).first()
        if not user:
            user = User(
                email=settings.FIRST_SUPERUSER,
                hashed_password=get_password_hash(settings.FIRST_SUPERUSER_PASSWORD),
                full_name="Super Admin",
                is_active=True,
                is_superuser=True,
                organization_id=admin_org.id if admin_org else None,
                role="admin"
            )
            db.add(user)
            print(f"Superuser created: {settings.FIRST_SUPERUSER}")
        else:
            # Update existing admin to have organization if missing
            if not user.organization_id and admin_org:
                user.organization_id = admin_org.id
                user.role = "admin"
                print(f"Updated admin user with organization: {admin_org.name}")
            print(f"Superuser already exists: {settings.FIRST_SUPERUSER}")
        
        # Create permanent test user for testing purposes
        test_user_email = "testuser@demo.com"
        test_user = db.query(User).filter(User.email == test_user_email).first()
        if not test_user:
            # Get demo organization for test user
            demo_org = db.query(Organization).filter(Organization.slug == "demo-org").first()
            test_user = User(
                email=test_user_email,
                hashed_password=get_password_hash("testpassword123"),
                full_name="Test User",
                is_active=True,
                is_superuser=False,
                organization_id=demo_org.id if demo_org else None,
                role="member"
            )
            db.add(test_user)
            print(f"Test user created: {test_user_email}")
        else:
            print(f"Test user already exists: {test_user_email}")
        
        # Create additional test user
        test_user2_email = "test@mailinator.com"
        test_user2 = db.query(User).filter(User.email == test_user2_email).first()
        if not test_user2:
            # Get demo organization for test user
            demo_org = db.query(Organization).filter(Organization.slug == "demo-org").first()
            test_user2 = User(
                email=test_user2_email,
                hashed_password=get_password_hash("test123"),
                full_name="Test User 2",
                is_active=True,
                is_superuser=False,
                organization_id=demo_org.id if demo_org else None,
                role="member"
            )
            db.add(test_user2)
            print(f"Test user 2 created: {test_user2_email}")
        else:
            print(f"Test user 2 already exists: {test_user2_email}")
        
        # Create default configurations
        default_configs = [
            {
                "key": "google_api_key",
                "value": None,
                "description": "Google API key for Gemini Flash integration"
            },
            {
                "key": "mindsdb_url", 
                "value": settings.MINDSDB_URL,
                "description": "MindsDB server URL"
            }
        ]
        
        for config_data in default_configs:
            existing_config = db.query(Configuration).filter(
                Configuration.key == config_data["key"]
            ).first()

            if not existing_config:
                config = Configuration(**config_data)
                db.add(config)

        db.commit()

        # Seed agricultural reference data (idempotent). Runs after the
        # config commit so a seed failure can't roll back unrelated work.
        try:
            from app.services.agri_data import AgriDataService
            seed_counts = AgriDataService(db).seed_reference_data()
            if seed_counts["regions_created"] or seed_counts["crops_created"]:
                print(
                    "Agri reference data seeded: "
                    f"{seed_counts['regions_created']} regions, "
                    f"{seed_counts['crops_created']} crops"
                )
        except Exception as e:
            db.rollback()
            print(f"Error seeding agri reference data: {e}")
        print("Database initialized successfully!")
        
    except Exception as e:
        print(f"Error initializing database: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    init_db()