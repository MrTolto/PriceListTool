import pandas as pd
from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from io import BytesIO
import re
import traceback
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from datetime import datetime
from database import SessionLocal, Product, Supplier, PriceEntry, Base, engine, get_db

app = FastAPI()
# Add this right after your FastAPI app initialization
@app.on_event("startup")
async def startup_db():
    print("Database URL:", os.getenv("DATABASE_URL")) 
    Base.metadata.create_all(bind=engine)
    print("Database tables created/verified")
    
app.mount("/static", StaticFiles(directory="static"), name="static")

# Initialize database
Base.metadata.create_all(bind=engine)

# Database dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/")
async def index():
    return HTMLResponse(content=open("static/upload.html").read())

@app.post("/upload")
async def upload_file(
    file: UploadFile = File(None),
    text_data: str = Form(None),
    supplier_id: int = Form(...),
    db: Session = Depends(get_db)
):
    try:
        if file:
            if file.filename.endswith(".xlsx"):
                contents = await file.read()
                parsed_data = parse_xlsx(contents)
            else:
                raise HTTPException(status_code=400, detail="Only .xlsx files are allowed.")
        elif text_data:
            parsed_data = parse_text(text_data)
        else:
            raise HTTPException(status_code=400, detail="No file or text data provided.")

        # Store parsed data
        added_count = 0
        for item in parsed_data:
            # Check if product exists
            product = db.query(Product).filter_by(product_number=item['product_number']).first()
            
            if not product:
                product = Product(
                    product_number=item['product_number'],
                    canonical_name=item['product_name'],
                    category=determine_category(item['product_name'])
                )
                db.add(product)
                db.commit()
            
            # Add price entry
            entry = PriceEntry(
                product_id=product.id,
                supplier_id=supplier_id,
                price=item['price'],
                currency=item['currency'],
                available=item['available_pcs'],
                timestamp=datetime.utcnow()
            )
            db.add(entry)
            added_count += 1
        
        db.commit()
        return {"message": f"Successfully added {added_count} price entries"}

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@app.get("/products/search")
async def search_products(
    query: str,
    db: Session = Depends(get_db)
):
    results = db.query(Product).filter(
        (Product.product_number.contains(query)) |
        (Product.canonical_name.contains(query))
    ).all()
    
    return {"results": [
        {
            "id": p.id,
            "number": p.product_number,
            "name": p.canonical_name,
            "category": p.category
        } for p in results
    ]}

@app.get("/products/{product_id}/prices")
async def get_product_prices(
    product_id: int,
    db: Session = Depends(get_db)
):
    product = db.query(Product).filter_by(id=product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    entries = db.query(PriceEntry).filter_by(product_id=product_id).order_by(PriceEntry.price).all()
    
    return {
        "product": {
            "id": product.id,
            "number": product.product_number,
            "name": product.canonical_name,
            "category": product.category
        },
        "offers": [
            {
                "supplier": db.query(Supplier).get(e.supplier_id).name,
                "price": e.price,
                "currency": e.currency,
                "available": e.available,
                "updated": e.timestamp.isoformat()
            } for e in entries
        ]
    }

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

# Your existing parsing functions (keep them exactly as you had them)
def parse_text(text: str) -> List[Dict]:
    """Parse tab-separated text data with product information"""
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if not lines:
        return []
    
    # Skip header if it exists
    if "product number\tProduct Name\tPcs\tPrice" in lines[0]:
        lines = lines[1:]
    
    parsed_data = []
    for line in lines:
        try:
            # Split on tabs, but be careful with extra spaces
            parts = re.split(r'\t+', line.strip())
            if len(parts) < 4:
                continue
                
            product_number = parts[0].strip()
            product_name = parts[1].strip()
            available = int(parts[2].strip()) if parts[2].strip().isdigit() else 0
            price_info = extract_price(parts[3])
            
            parsed_data.append({
                "product_number": product_number,
                "product_name": product_name,
                "available_pcs": available,
                "price": price_info["amount"],
                "currency": price_info["currency"],
                "price_original": parts[3].strip()
            })
        except Exception as e:
            print(f"Error parsing line: {line}\nError: {str(e)}")
            continue
            
    return parsed_data

def parse_xlsx(content: bytes) -> List[Dict]:
    """Parse Excel file with product information"""
    try:
        df = pd.read_excel(BytesIO(content))
        df = df.rename(columns=str)  # Ensure columns are strings
        
        # Find relevant columns (case insensitive)
        col_map = {}
        for col in df.columns:
            lower_col = str(col).lower()
            if 'number' in lower_col:
                col_map['product_number'] = col
            elif 'name' in lower_col:
                col_map['product_name'] = col
            elif 'pcs' in lower_col or 'quantity' in lower_col or 'stock' in lower_col:
                col_map['available'] = col
            elif 'price' in lower_col:
                col_map['price'] = col
        
        if not col_map:
            raise ValueError("Could not identify required columns in Excel file")
        
        parsed_data = []
        for _, row in df.iterrows():
            try:
                product_number = str(row[col_map['product_number']]).strip()
                product_name = str(row[col_map['product_name']]).strip()
                
                available = 0
                if pd.notna(row[col_map['available']]):
                    try:
                        available = int(float(row[col_map['available']]))
                    except (ValueError, TypeError):
                        available = 0
                
                price_str = str(row[col_map['price']]).strip() if pd.notna(row[col_map['price']]) else ""
                price_info = extract_price(price_str)
                
                parsed_data.append({
                    "product_number": product_number,
                    "product_name": product_name,
                    "available_pcs": available,
                    "price": price_info["amount"],
                    "currency": price_info["currency"],
                    "price_original": price_str
                })
            except Exception as e:
                print(f"Error parsing row: {row}\nError: {str(e)}")
                continue
                
        return parsed_data
    except Exception as e:
        raise ValueError(f"Excel parsing error: {str(e)}")

def extract_price(price_str: str) -> Dict:
    """Improved price extraction that handles:
    - '€ 552,08' → 552.08
    - '€ 1 052,08' → 1052.08
    - '€ 1 339,58' → 1339.58
    """
    if not price_str or not isinstance(price_str, str):
        return {"amount": None, "currency": "UNKNOWN"}
    
    # Normalize the string - keep spaces for now
    normalized = price_str.strip().upper()
    
    # Detect currency
    currency = "EUR"  # default based on your examples
    if "$" in normalized:
        currency = "USD"
    elif "£" in normalized:
        currency = "GBP"
    
    # Extract numeric parts (digits, commas, periods, spaces)
    amount_str = re.sub(r"[^\d\s,.]", "", normalized)
    
    # Replace comma with period for decimal
    amount_str = amount_str.replace(",", ".")
    
    # Remove all spaces (they were thousand separators)
    amount_str = amount_str.replace(" ", "")
    
    try:
        amount = float(amount_str) if amount_str else None
    except ValueError:
        amount = None
    
    return {
        "amount": amount,
        "currency": currency
    }