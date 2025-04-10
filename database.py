import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# Get database URL from Render's environment
DATABASE_URL = os.getenv("DATABASE_URL")

# Fix common Render PostgreSQL URL format issue
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Free tier fallback to SQLite (only for local testing)
if not DATABASE_URL:
    DATABASE_URL = "sqlite:///./local.db"

engine = create_engine(DATABASE_URL)
Base = declarative_base()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Database models
class Product(Base):
    __tablename__ = 'products'
    id = Column(Integer, primary_key=True, index=True)
    product_number = Column(String(50), unique=True, index=True)
    canonical_name = Column(String(100))
    category = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)

class Supplier(Base):
    __tablename__ = 'suppliers'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True)

class PriceEntry(Base):
    __tablename__ = 'price_entries'
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey('products.id'))
    supplier_id = Column(Integer, ForeignKey('suppliers.id'))
    price = Column(Float)
    currency = Column(String(3), default="EUR")
    available = Column(Integer)
    timestamp = Column(DateTime, default=datetime.utcnow)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()