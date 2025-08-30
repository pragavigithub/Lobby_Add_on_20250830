"""
GRPO (Goods Receipt PO) Models
Contains all models related to goods receipt against purchase orders
"""
from app import db
from datetime import datetime
# User model imported from main models.py
from models import User

class GRPODocument(db.Model):
    """Main GRPO document header"""
    __tablename__ = 'grpo_documents'
    
    id = db.Column(db.Integer, primary_key=True)
    po_number = db.Column(db.String(50), nullable=False)
    supplier_code = db.Column(db.String(20))
    supplier_name = db.Column(db.String(100))
    warehouse_code = db.Column(db.String(10))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    qc_approver_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    qc_approved_at = db.Column(db.DateTime)
    qc_notes = db.Column(db.Text)
    status = db.Column(db.String(20), default='draft')  # draft, submitted, qc_approved, posted, rejected
    po_total = db.Column(db.Numeric(15, 2))
    sap_document_number = db.Column(db.String(50))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = db.relationship('User', foreign_keys=[user_id], backref='grpo_documents')
    qc_approver = db.relationship('User', foreign_keys=[qc_approver_id])
    items = db.relationship('GRPOItem', backref='grpo_document', lazy=True, cascade='all, delete-orphan')

class GRPOItem(db.Model):
    """GRPO line items"""
    __tablename__ = 'grpo_items'
    
    id = db.Column(db.Integer, primary_key=True)
    grpo_id = db.Column(db.Integer, db.ForeignKey('grpo_documents.id'), nullable=False)
    item_code = db.Column(db.String(50), nullable=False)
    item_name = db.Column(db.String(200))
    quantity = db.Column(db.Numeric(15, 3), nullable=False)
    received_quantity = db.Column(db.Numeric(15, 3), default=0)
    unit_price = db.Column(db.Numeric(15, 4))
    line_total = db.Column(db.Numeric(15, 2))
    unit_of_measure = db.Column(db.String(10))
    warehouse_code = db.Column(db.String(10))
    bin_location = db.Column(db.String(20))
    batch_number = db.Column(db.String(50))
    serial_number = db.Column(db.String(50))
    expiry_date = db.Column(db.Date)
    barcode = db.Column(db.String(100))
    qc_status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    po_line_number = db.Column(db.Integer)
    base_entry = db.Column(db.Integer)  # SAP PO DocEntry
    base_line = db.Column(db.Integer)   # SAP PO Line Number
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class PurchaseDeliveryNote(db.Model):
    """Purchase Delivery Note for SAP B1 posting"""
    __tablename__ = 'purchase_delivery_notes'
    
    id = db.Column(db.Integer, primary_key=True)
    grpo_id = db.Column(db.Integer, db.ForeignKey('grpo_documents.id'), nullable=False)
    external_reference = db.Column(db.String(50), unique=True)
    sap_document_number = db.Column(db.String(50))
    supplier_code = db.Column(db.String(20))
    warehouse_code = db.Column(db.String(10))
    document_date = db.Column(db.Date)
    due_date = db.Column(db.Date)
    total_amount = db.Column(db.Numeric(15, 2))
    status = db.Column(db.String(20), default='draft')  # draft, posted, cancelled
    json_payload = db.Column(db.Text)  # Store the JSON sent to SAP
    sap_response = db.Column(db.Text)  # Store SAP response
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    posted_at = db.Column(db.DateTime)

    # Relationships
    grpo_document = db.relationship('GRPODocument', backref='delivery_notes')