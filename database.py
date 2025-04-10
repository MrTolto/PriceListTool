import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from pathlib import Path

# Use Render's PostgreSQL URL (free tier uses "Internal Database URL")
DATABASE_URL = os.getenv("DATABASE_URL")  # Render auto-injects this

engine = create_engine(DATABASE_URL)
Base = declarative_base()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Special handling for SQLite on Render
if DATABASE_URL.startswith("sqlite"):
    # Use persistent storage in Render's /tmp directory
    db_path = Path("/tmp/prices.db") if "RENDER" in os.environ else Path("./prices.db")
    DATABASE_URL = f"sqlite:///{db_path}"
    
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True
    )
else:
    # PostgreSQL or other databases
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# Database models
class Product(Base):
    __tablename__ = 'products'
    
    id = Column(Integer, primary_key=True, index=True)
    product_number = Column(String, unique=True, index=True)
    canonical_name = Column(String)
    category = Column(String)
    description = Column(String, nullable=True)

class Supplier(Base):
    __tablename__ = 'suppliers'
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True)
    contact_email = Column(String)
    phone = Column(String, nullable=True)

class PriceEntry(Base):
    __tablename__ = 'price_entries'
    
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey('products.id'))
    supplier_id = Column(Integer, ForeignKey('suppliers.id'))
    price = Column(Float)
    currency = Column(String(3), default="EUR")
    available = Column(Integer)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

# Utility function for database sessions
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Self-healing functions
def find_similar_products(db: Session, product_number: str):
    """Find products with similar numbers (self-healing)"""
    base_number = product_number.split('/')[0]  # Handle variants like MD1Q4HX/A
    return db.query(Product).filter(Product.product_number.startswith(base_number)).all()

def determine_category(product_name: str) -> str:
    """Auto-categorize products based on name patterns"""
    name = product_name.lower()
    if 'iphone' in name:
        return 'Smartphone'
    elif 'macbook' in name:
        return 'Laptop'
    elif 'ipad' in name:
        return 'Tablet'
    return 'Other'