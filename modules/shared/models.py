"""
Shared models used across multiple modules
"""
from app import db
from datetime import datetime

# Import base User model from main models - avoid duplicate definition
# User model is defined in main models.py

class Warehouse(db.Model):
    """Warehouse master data"""
    __tablename__ = 'warehouses'
    
    id = db.Column(db.Integer, primary_key=True)
    warehouse_code = db.Column(db.String(10), unique=True, nullable=False)
    warehouse_name = db.Column(db.String(100), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class BinLocation(db.Model):
    """Bin location master data"""
    __tablename__ = 'bin_locations'
    
    id = db.Column(db.Integer, primary_key=True)
    warehouse_code = db.Column(db.String(10), nullable=False)
    bin_code = db.Column(db.String(20), nullable=False)
    bin_name = db.Column(db.String(100))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class BusinessPartner(db.Model):
    """Business partner (supplier/customer) master data"""
    __tablename__ = 'business_partners'
    
    id = db.Column(db.Integer, primary_key=True)
    card_code = db.Column(db.String(20), unique=True, nullable=False)
    card_name = db.Column(db.String(100), nullable=False)
    card_type = db.Column(db.String(10))  # Supplier, Customer
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)