"""
Invoice Creation Models
Contains all models related to invoice creation and serial number management
"""
from app import db
from datetime import datetime
from models import User

class InvoiceDocument(db.Model):
    """Main Invoice document header"""
    __tablename__ = 'invoice_documents'
    
    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(50))
    customer_code = db.Column(db.String(20))
    customer_name = db.Column(db.String(100))
    branch_id = db.Column(db.Integer)
    branch_name = db.Column(db.String(100))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.String(20))  # draft, pending_qc, created, posted, cancelled, rejected
    bpl_id = db.Column(db.Integer, default=5)  # BPL_IDAssignedToInvoice for SAP B1
    bpl_name = db.Column(db.String(100))  # Branch/Location name
    doc_date = db.Column(db.DateTime, default=datetime.utcnow)
    due_date = db.Column(db.DateTime)
    total_amount = db.Column(db.Numeric(15, 2))
    sap_doc_entry = db.Column(db.Integer)
    sap_doc_num = db.Column(db.String(50))
    notes = db.Column(db.Text)
    json_payload = db.Column(db.Text)  # Store the JSON sent to SAP
    sap_response = db.Column(db.Text)  # Store SAP response
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = db.relationship('User', foreign_keys=[user_id], backref='invoice_documents')
    lines = db.relationship('InvoiceLine', backref='invoice_document', lazy=True, cascade='all, delete-orphan')

class InvoiceLine(db.Model):
    """Invoice line items"""
    __tablename__ = 'invoice_lines'
    
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoice_documents.id'), nullable=False)
    line_number = db.Column(db.Integer, nullable=False)
    item_code = db.Column(db.String(50), nullable=False)
    item_description = db.Column(db.String(200))
    quantity = db.Column(db.Numeric(15, 3), nullable=False, default=1.0)
    unit_price = db.Column(db.Numeric(15, 4))
    line_total = db.Column(db.Numeric(15, 2))
    warehouse_code = db.Column(db.String(10))
    warehouse_name = db.Column(db.String(100))
    tax_code = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    serial_numbers = db.relationship('InvoiceSerialNumber', backref='invoice_line', lazy=True, cascade='all, delete-orphan')

class InvoiceSerialNumber(db.Model):
    """Serial numbers for invoice lines"""
    __tablename__ = 'invoice_serial_numbers'
    
    id = db.Column(db.Integer, primary_key=True)
    invoice_line_id = db.Column(db.Integer, db.ForeignKey('invoice_lines.id'), nullable=False)
    serial_number = db.Column(db.String(100), nullable=False)
    item_code = db.Column(db.String(50), nullable=False)  # Auto-populated from SAP validation
    item_description = db.Column(db.String(200))  # Auto-populated from SAP validation
    warehouse_code = db.Column(db.String(10))  # From SAP validation
    customer_code = db.Column(db.String(20))  # Auto-populated from SAP validation
    customer_name = db.Column(db.String(100))  # Auto-populated from SAP validation
    bpl_id = db.Column(db.Integer, default=5)  # BPL_IDAssignedToInvoice for SAP B1
    bpl_name = db.Column(db.String(100))  # Branch/Location name
    base_line_number = db.Column(db.Integer, default=0)
    quantity = db.Column(db.Numeric(15, 3), default=1.0)
    validation_status = db.Column(db.String(20), default='pending')  # pending, validated, failed
    validation_error = db.Column(db.Text)  # Error message if validation fails
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class SerialNumberLookup(db.Model):
    """Cache for serial number lookups from SAP"""
    __tablename__ = 'serial_number_lookups'
    
    id = db.Column(db.Integer, primary_key=True)
    serial_number = db.Column(db.String(100), nullable=False, unique=True)
    item_code = db.Column(db.String(50))
    item_name = db.Column(db.String(200))
    warehouse_code = db.Column(db.String(10))
    warehouse_name = db.Column(db.String(100))
    branch_id = db.Column(db.Integer)
    branch_name = db.Column(db.String(100))
    lookup_status = db.Column(db.String(20), default='pending')  # pending, validated, failed
    lookup_error = db.Column(db.Text)
    sap_response = db.Column(db.Text)  # Store SAP response JSON
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)