import os
from pathlib import Path
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Database configuration - Render automatically provides DATABASE_URL for PostgreSQL
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./prices.db")

# Special handling for SQLite (development and Render's ephemeral storage)
if DATABASE_URL.startswith("sqlite"):
    # On Render, store SQLite in /tmp for persistence between deploys
    db_path = Path("/tmp/prices.db") if "RENDER" in os.environ else Path("./prices.db")
    DATABASE_URL = f"sqlite:///{db_path}"
    
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},  # Needed for SQLite
        pool_pre_ping=True
    )
else:
    # PostgreSQL configuration
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

Base = declarative_base()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Database models
class Product(Base):
    __tablename__ = 'products'
    
    id = Column(Integer, primary_key=True, index=True)
    product_number = Column(String(50), unique=True, index=True)  # Added max length
    canonical_name = Column(String(100))
    category = Column(String(50))
    description = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Supplier(Base):
    __tablename__ = 'suppliers'
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True)
    contact_email = Column(String(100))
    phone = Column(String(20), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class PriceEntry(Base):
    __tablename__ = 'price_entries'
    
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey('products.id'))
    supplier_id = Column(Integer, ForeignKey('suppliers.id'))
    price = Column(Float)
    currency = Column(String(3), default="EUR")
    available = Column(Integer)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

# Database session dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Self-healing helper functions
def determine_category(product_name: str) -> str:
    """Automatically categorize products based on name patterns"""
    name = product_name.lower()
    if 'iphone' in name:
        return 'Smartphone'
    elif 'macbook' in name:
        return 'Laptop'
    elif 'ipad' in name:
        return 'Tablet'
    return 'Other'

def find_similar_products(db: Session, product_number: str):
    """Find products with similar numbers (self-healing functionality)"""
    base_number = product_number.split('/')[0]  # Handle variants like MD1Q4HX/A
    return db.query(Product).filter(Product.product_number.startswith(base_number)).all()