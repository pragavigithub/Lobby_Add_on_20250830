from datetime import datetime
from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship
from app import db


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    first_name = db.Column(db.String(80), nullable=True)
    last_name = db.Column(db.String(80), nullable=True)
    role = db.Column(db.String(20), nullable=False,
                  default='user')  # admin, manager, user, qc
    branch_id = db.Column(db.String(10), nullable=True)
    branch_name = db.Column(db.String(100), nullable=True)
    default_branch_id = db.Column(
        db.String(10), nullable=True)  # Default branch if none selected
    active = db.Column(db.Boolean, default=True)
    must_change_password = db.Column(
        db.Boolean, default=False)  # Force password change on next login
    last_login = db.Column(db.DateTime, nullable=True)
    permissions = db.Column(db.Text,
                         nullable=True)  # JSON string of screen permissions
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime,
                        default=datetime.utcnow,
                        onupdate=datetime.utcnow)

    def get_permissions(self):
        """Get user permissions as a dictionary"""
        import json
        if self.permissions:
            try:
                return json.loads(self.permissions)
            except:
                return {}
        return self.get_default_permissions()

    def set_permissions(self, perms_dict):
        """Set user permissions from a dictionary"""
        import json
        self.permissions = json.dumps(perms_dict)

    def get_default_permissions(self):
        """Get default permissions based on role"""
        permissions = {
            'dashboard': True,
            'inventory_transfer': False,
            'serial_item_transfer': False,
            'serial_transfer': False,
            'user_management': False,
            'qc_dashboard': False,
            'invoice_creation': False
        }

        if self.role == 'admin':
            # Admin has access to everything
            for key in permissions:
                permissions[key] = True
        elif self.role == 'manager':
            permissions.update({
                'inventory_transfer': True,
                'serial_item_transfer': True,
                'serial_transfer': True,
                'user_management': True,
                'qc_dashboard': True,
                'invoice_creation': True
            })
        elif self.role == 'qc':
            permissions.update({
                'qc_dashboard': True
            })
        elif self.role == 'user':
            permissions.update({
                'inventory_transfer': True,
                'serial_item_transfer': True,
                'serial_transfer': True,
                'invoice_creation': True
            })

        return permissions

    def has_permission(self, screen):
        """Check if user has permission for a specific screen"""
        if self.role == 'admin':
            return True
        return self.get_permissions().get(screen, False)

    # Relationships
    grpo_documents = relationship('GRPODocument',
                                  back_populates='user',
                                  foreign_keys='GRPODocument.user_id')
    inventory_transfers = relationship('InventoryTransfer',
                                       back_populates='user',
                                       foreign_keys='InventoryTransfer.user_id')
    pick_lists = relationship('PickList',
                              back_populates='user',
                              foreign_keys='PickList.user_id')
    inventory_counts = relationship('InventoryCount', back_populates='user')
    bin_scanning_logs = relationship('BinScanningLog', back_populates='user')
    qr_code_labels = relationship('QRCodeLabel', back_populates='user')


class GRPODocument(db.Model):
    __tablename__ = 'grpo_documents'

    id = db.Column(db.Integer, primary_key=True)
    po_number = db.Column(db.String(20), nullable=False)
    sap_document_number = db.Column(db.String(20), nullable=True)
    supplier_code = db.Column(db.String(50), nullable=True)  # CardCode from SAP
    supplier_name = db.Column(db.String(200), nullable=True)
    po_date = db.Column(db.DateTime, nullable=True)
    po_total = db.Column(db.Float, nullable=True)
    status = db.Column(
        db.String(20),
        default='draft')  # draft, submitted, approved, posted, rejected
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    qc_user_id = db.Column(db.Integer, db.ForeignKey('users.id'),
                        nullable=True)  # QC approver
    qc_approved_at = db.Column(db.DateTime, nullable=True)  # QC approval timestamp
    qc_notes = db.Column(db.Text, nullable=True)
    notes = db.Column(db.Text, nullable=True)  # General notes/comments for the GRPO
    draft_or_post = db.Column(db.String(10), default='draft')  # draft, post
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime,
                        default=datetime.utcnow,
                        onupdate=datetime.utcnow)

    # Relationships
    user = relationship('User',
                        back_populates='grpo_documents',
                        foreign_keys=[user_id])
    qc_user = relationship('User', foreign_keys=[qc_user_id])
    items = relationship('GRPOItem', back_populates='grpo_document')


class GRPOItem(db.Model):
    __tablename__ = 'grpo_items'

    id = db.Column(db.Integer, primary_key=True)
    grpo_document_id = db.Column(db.Integer,
                              db.ForeignKey('grpo_documents.id'),
                              nullable=False)
    po_line_number = db.Column(db.Integer, nullable=True)  # Line number from PO
    item_code = db.Column(db.String(50), nullable=False)
    item_name = db.Column(db.String(200), nullable=False)
    po_quantity = db.Column(db.Float, nullable=True)  # Original PO quantity
    open_quantity = db.Column(db.Float, nullable=True)  # Remaining open quantity
    received_quantity = db.Column(db.Float,
                               nullable=False)  # Quantity being received
    unit_of_measure = db.Column(db.String(10), nullable=False)
    unit_price = db.Column(db.Float, nullable=True)
    bin_location = db.Column(db.String(20), nullable=False)
    batch_number = db.Column(db.String(50), nullable=True)
    serial_number = db.Column(db.String(50), nullable=True)  # Serial number for serial-managed items
    expiration_date = db.Column(db.DateTime, nullable=True)
    supplier_barcode = db.Column(db.String(100),
                              nullable=True)  # Original supplier barcode
    generated_barcode = db.Column(db.String(100),
                               nullable=True)  # WMS generated barcode
    barcode_printed = db.Column(db.Boolean, default=False)
    qc_status = db.Column(db.String(20),
                       default='pending')  # pending, approved, rejected
    qc_notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    grpo_document = relationship('GRPODocument', back_populates='items')
    qr_code_labels = relationship('QRCodeLabel', back_populates='grpo_item')


class InventoryTransfer(db.Model):
    __tablename__ = 'inventory_transfers'

    id = db.Column(db.Integer, primary_key=True)
    transfer_request_number = db.Column(db.String(20), nullable=False)
    sap_document_number = db.Column(db.String(20), nullable=True)
    status = db.Column(db.String(20),
                    default='draft')  # draft, submitted, qc_approved, posted, rejected
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    qc_approver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    qc_approved_at = db.Column(db.DateTime, nullable=True)
    qc_notes = db.Column(db.Text, nullable=True)
    from_warehouse = db.Column(db.String(20), nullable=True)
    to_warehouse = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime,
                        default=datetime.utcnow,
                        onupdate=datetime.utcnow)

    # Relationships
    user = relationship('User', back_populates='inventory_transfers', foreign_keys=[user_id])
    qc_approver = relationship('User', foreign_keys=[qc_approver_id])
    items = relationship('InventoryTransferItem',
                         back_populates='inventory_transfer')


class InventoryTransferItem(db.Model):
    __tablename__ = 'inventory_transfer_items'

    id = db.Column(db.Integer, primary_key=True)
    inventory_transfer_id = db.Column(db.Integer,
                                   db.ForeignKey('inventory_transfers.id'),
                                   nullable=False)
    item_code = db.Column(db.String(50), nullable=False)
    item_name = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    requested_quantity = db.Column(db.Float, nullable=False)  # Original requested quantity
    transferred_quantity = db.Column(db.Float, default=0)  # Actually transferred quantity
    remaining_quantity = db.Column(db.Float, nullable=False)  # Remaining to transfer
    unit_of_measure = db.Column(db.String(10), nullable=False)
    from_bin = db.Column(db.String(20), nullable=True)  # Made nullable for better compatibility
    to_bin = db.Column(db.String(20), nullable=True)    # Made nullable for better compatibility
    from_bin_location = db.Column(db.String(50), nullable=True)  # New field for detailed bin location
    to_bin_location = db.Column(db.String(50), nullable=True)    # New field for detailed bin location
    batch_number = db.Column(db.String(50), nullable=True)
    available_batches = db.Column(db.Text, nullable=True)  # JSON list of available batches
    qc_status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    qc_notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    inventory_transfer = relationship('InventoryTransfer',
                                      back_populates='items')


class PickList(db.Model):
    __tablename__ = 'pick_lists'

    id = db.Column(db.Integer, primary_key=True)
    # SAP B1 fields
    absolute_entry = db.Column(db.Integer, nullable=True)  # From SAP B1 Absoluteentry
    name = db.Column(db.String(50), nullable=False)  # From SAP B1 Name field
    owner_code = db.Column(db.Integer, nullable=True)  # From SAP B1 OwnerCode
    owner_name = db.Column(db.String(100), nullable=True)  # From SAP B1 OwnerName
    pick_date = db.Column(db.DateTime, nullable=True)  # From SAP B1 PickDate
    remarks = db.Column(db.Text, nullable=True)  # From SAP B1 Remarks
    status = db.Column(db.String(20), default='pending')  # SAP B1: ps_Open, ps_Closed, ps_Released
    object_type = db.Column(db.String(10), nullable=True, default='156')  # From SAP B1 ObjectType
    use_base_units = db.Column(db.String(5), nullable=True, default='tNO')  # From SAP B1 UseBaseUnits
    
    # Legacy fields for backward compatibility
    sales_order_number = db.Column(db.String(20), nullable=True)
    pick_list_number = db.Column(db.String(20), nullable=True)
    
    # WMS specific fields
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    approver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    priority = db.Column(db.String(10), nullable=True, default='normal')  # low, normal, high, urgent
    warehouse_code = db.Column(db.String(10), nullable=True)
    customer_code = db.Column(db.String(20), nullable=True)
    customer_name = db.Column(db.String(100), nullable=True)
    total_items = db.Column(db.Integer, nullable=True, default=0)
    picked_items = db.Column(db.Integer, nullable=True, default=0)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime,
                        default=datetime.utcnow,
                        onupdate=datetime.utcnow)

    # Relationships
    user = relationship('User',
                        back_populates='pick_lists',
                        foreign_keys=[user_id])
    approver = relationship('User', foreign_keys=[approver_id])
    items = relationship('PickListItem', back_populates='pick_list', cascade='all, delete-orphan')
    lines = relationship('PickListLine', back_populates='pick_list', cascade='all, delete-orphan', lazy='dynamic')


class PickListItem(db.Model):
    """Legacy PickListItem for backward compatibility"""
    __tablename__ = 'pick_list_items'

    id = db.Column(db.Integer, primary_key=True)
    pick_list_id = db.Column(db.Integer, db.ForeignKey('pick_lists.id'), nullable=False)
    item_code = db.Column(db.String(50), nullable=False)
    item_name = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    picked_quantity = db.Column(db.Float, default=0)
    unit_of_measure = db.Column(db.String(10), nullable=False)
    bin_location = db.Column(db.String(20), nullable=False)
    batch_number = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    pick_list = relationship('PickList', back_populates='items')


class PickListLine(db.Model):
    """SAP B1 compatible PickListLine model based on PickListsLines structure"""
    __tablename__ = 'pick_list_lines'

    id = db.Column(db.Integer, primary_key=True)
    pick_list_id = db.Column(db.Integer, db.ForeignKey('pick_lists.id'), nullable=False)
    
    # SAP B1 PickListsLines fields
    absolute_entry = db.Column(db.Integer, nullable=True)  # From SAP B1 AbsoluteEntry
    line_number = db.Column(db.Integer, nullable=False)  # From SAP B1 LineNumber
    order_entry = db.Column(db.Integer, nullable=True)  # From SAP B1 OrderEntry
    order_row_id = db.Column(db.Integer, nullable=True)  # From SAP B1 OrderRowID
    picked_quantity = db.Column(db.Float, nullable=True, default=0)  # From SAP B1 PickedQuantity
    pick_status = db.Column(db.String(20), nullable=True, default='ps_Open')  # From SAP B1 PickStatus
    released_quantity = db.Column(db.Float, nullable=True, default=0)  # From SAP B1 ReleasedQuantity
    previously_released_quantity = db.Column(db.Float, nullable=True, default=0)  # From SAP B1 PreviouslyReleasedQuantity
    base_object_type = db.Column(db.Integer, nullable=True, default=17)  # From SAP B1 BaseObjectType
    
    # WMS specific fields
    item_code = db.Column(db.String(50), nullable=True)
    item_name = db.Column(db.String(200), nullable=True)
    unit_of_measure = db.Column(db.String(10), nullable=True)
    serial_numbers = db.Column(db.Text, nullable=True)  # JSON array of serial numbers
    batch_numbers = db.Column(db.Text, nullable=True)  # JSON array of batch numbers
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    pick_list = relationship('PickList', back_populates='lines')
    bin_allocations = relationship('PickListBinAllocation', back_populates='pick_list_line', cascade='all, delete-orphan', lazy='dynamic')


class PickListBinAllocation(db.Model):
    """SAP B1 compatible bin allocation model based on DocumentLinesBinAllocations structure"""
    __tablename__ = 'pick_list_bin_allocations'

    id = db.Column(db.Integer, primary_key=True)
    pick_list_line_id = db.Column(db.Integer, db.ForeignKey('pick_list_lines.id'), nullable=False)
    
    # SAP B1 DocumentLinesBinAllocations fields
    bin_abs_entry = db.Column(db.Integer, nullable=True)  # From SAP B1 BinAbsEntry
    quantity = db.Column(db.Float, nullable=False)  # From SAP B1 Quantity
    allow_negative_quantity = db.Column(db.String(5), nullable=True, default='tNO')  # From SAP B1 AllowNegativeQuantity
    serial_and_batch_numbers_base_line = db.Column(db.Integer, nullable=True, default=0)  # From SAP B1 SerialAndBatchNumbersBaseLine
    base_line_number = db.Column(db.Integer, nullable=True)  # From SAP B1 BaseLineNumber
    
    # WMS specific fields
    bin_code = db.Column(db.String(20), nullable=True)
    bin_location = db.Column(db.String(50), nullable=True)
    warehouse_code = db.Column(db.String(10), nullable=True)
    picked_quantity = db.Column(db.Float, nullable=True, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    pick_list_line = relationship('PickListLine', back_populates='bin_allocations')


class InventoryCount(db.Model):
    __tablename__ = 'inventory_counts'

    id = db.Column(db.Integer, primary_key=True)
    count_number = db.Column(db.String(20), nullable=False)
    warehouse_code = db.Column(db.String(10), nullable=False)
    bin_location = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20),
                    default='assigned')  # assigned, in_progress, completed
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime,
                        default=datetime.utcnow,
                        onupdate=datetime.utcnow)

    # Relationships
    user = relationship('User', back_populates='inventory_counts')
    items = relationship('InventoryCountItem',
                         back_populates='inventory_count')


class InventoryCountItem(db.Model):
    __tablename__ = 'inventory_count_items'

    id = db.Column(db.Integer, primary_key=True)
    inventory_count_id = db.Column(db.Integer,
                                db.ForeignKey('inventory_counts.id'),
                                nullable=False)
    item_code = db.Column(db.String(50), nullable=False)
    item_name = db.Column(db.String(200), nullable=False)
    system_quantity = db.Column(db.Float, nullable=False)
    counted_quantity = db.Column(db.Float, nullable=False)
    variance = db.Column(db.Float, nullable=False)
    unit_of_measure = db.Column(db.String(10), nullable=False)
    batch_number = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    inventory_count = relationship('InventoryCount', back_populates='items')


class BarcodeLabel(db.Model):
    __tablename__ = 'barcode_labels'

    id = db.Column(db.Integer, primary_key=True)
    item_code = db.Column(db.String(50), nullable=False)
    barcode = db.Column(db.String(100), nullable=False)
    label_format = db.Column(db.String(20), nullable=False)
    print_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_printed = db.Column(db.DateTime, nullable=True)

    def __repr__(self):
        return f'<BarcodeLabel {self.id}>'


class BinLocation(db.Model):
    __tablename__ = 'bin_locations'
    
    id = db.Column(db.Integer, primary_key=True)
    bin_code = db.Column(db.String(100), unique=True, nullable=False)
    warehouse_code = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    active = db.Column(db.Boolean, default=True)
    is_system_bin = db.Column(db.Boolean, default=False)
    sap_abs_entry = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    bin_items = relationship('BinItem', back_populates='bin_location')
    
    def __repr__(self):
        return f'<BinLocation {self.bin_code}>'


class BinItem(db.Model):
    __tablename__ = 'bin_items'
    
    id = db.Column(db.Integer, primary_key=True)
    bin_code = db.Column(db.String(100), db.ForeignKey('bin_locations.bin_code'), nullable=False)
    item_code = db.Column(db.String(100), nullable=False)
    item_name = db.Column(db.String(255), nullable=True)
    batch_number = db.Column(db.String(100), nullable=True)
    quantity = db.Column(db.Float, default=0)
    available_quantity = db.Column(db.Float, default=0)
    committed_quantity = db.Column(db.Float, default=0)
    uom = db.Column(db.String(20), default='EA')
    expiry_date = db.Column(db.Date, nullable=True)
    manufacturing_date = db.Column(db.Date, nullable=True)
    admission_date = db.Column(db.Date, nullable=True)
    warehouse_code = db.Column(db.String(50), nullable=True)
    sap_abs_entry = db.Column(db.Integer, nullable=True)
    sap_system_number = db.Column(db.Integer, nullable=True)
    sap_doc_entry = db.Column(db.Integer, nullable=True)
    batch_attribute1 = db.Column(db.String(100), nullable=True)
    batch_attribute2 = db.Column(db.String(100), nullable=True)
    batch_status = db.Column(db.String(50), default='bdsStatus_Released')
    last_sap_sync = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    bin_location = relationship('BinLocation', back_populates='bin_items')
    
    def __repr__(self):
        return f'<BinItem {self.item_code} in {self.bin_code}>'


class BinScanningLog(db.Model):
    __tablename__ = 'bin_scanning_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    bin_code = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    scan_type = db.Column(db.String(50), nullable=False)  # BIN_SCAN, ITEM_SCAN, etc.
    scan_data = db.Column(db.Text, nullable=True)
    items_found = db.Column(db.Integer, default=0)
    scan_timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship('User', back_populates='bin_scanning_logs')
    
    def __repr__(self):
        return f'<BinScanningLog {self.bin_code} by {self.user_id}>'


class QRCodeLabel(db.Model):
    __tablename__ = 'qr_code_labels'
    
    id = db.Column(db.Integer, primary_key=True)
    label_type = db.Column(db.String(50), nullable=False)  # GRN_ITEM, INVENTORY_ITEM, etc.
    item_code = db.Column(db.String(100), nullable=False)
    item_name = db.Column(db.String(200), nullable=True)
    po_number = db.Column(db.String(100), nullable=True)
    batch_number = db.Column(db.String(100), nullable=True)
    warehouse_code = db.Column(db.String(50), nullable=True)
    bin_code = db.Column(db.String(100), nullable=True)
    quantity = db.Column(db.Numeric(15, 4), nullable=True)
    uom = db.Column(db.String(20), nullable=True)
    expiry_date = db.Column(db.Date, nullable=True)
    
    # QR Code content and metadata
    qr_content = db.Column(db.Text, nullable=False)  # The actual string that gets encoded
    qr_format = db.Column(db.String(20), default='TEXT')  # TEXT, JSON, CSV
    
    # Reference to source document
    grpo_item_id = db.Column(db.Integer, db.ForeignKey('grpo_items.id'), nullable=True)
    inventory_transfer_item_id = db.Column(db.Integer, db.ForeignKey('inventory_transfer_items.id'), nullable=True)
    
    # Audit fields
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship('User', back_populates='qr_code_labels')
    grpo_item = relationship('GRPOItem', back_populates='qr_code_labels')
    
    def __repr__(self):
        return f'<QRCodeLabel {self.label_type} - {self.item_code}>'
    
    @classmethod
    def generate_grn_qr_content(cls, item_code, item_name, po_number, batch_number=None, format_type='TEXT'):
        """Generate QR code content for GRN items"""
        if format_type == 'JSON':
            import json
            content = json.dumps({
                'type': 'GRN_ITEM',
                'item_code': item_code,
                'item_name': item_name,
                'po_number': po_number,
                'batch_number': batch_number or 'N/A',
                'generated_at': datetime.utcnow().isoformat()
            })
        elif format_type == 'CSV':
            content = f"GRN_ITEM,{item_code},{item_name},{po_number},{batch_number or 'N/A'}"
        else:  # TEXT format
            lines = [
                f"Item Code: {item_code}",
                f"Item Name: {item_name}",
                f"PO Number: {po_number}"
            ]
            if batch_number:
                lines.append(f"Batch Number: {batch_number}")
            content = '\n'.join(lines)
        
        return content



class SalesOrder(db.Model):
    """SAP B1 Sales Order model for Pick List integration"""
    __tablename__ = 'sales_orders'

    id = db.Column(db.Integer, primary_key=True)
    # SAP B1 Sales Order fields
    doc_entry = db.Column(db.Integer, nullable=False, unique=True)  # From SAP B1 DocEntry
    doc_num = db.Column(db.Integer, nullable=True)  # From SAP B1 DocNum
    doc_type = db.Column(db.String(20), nullable=True)  # From SAP B1 DocType
    doc_date = db.Column(db.DateTime, nullable=True)  # From SAP B1 DocDate
    doc_due_date = db.Column(db.DateTime, nullable=True)  # From SAP B1 DocDueDate
    card_code = db.Column(db.String(50), nullable=True)  # From SAP B1 CardCode
    card_name = db.Column(db.String(200), nullable=True)  # From SAP B1 CardName
    address = db.Column(db.Text, nullable=True)  # From SAP B1 Address
    doc_total = db.Column(db.Float, nullable=True)  # From SAP B1 DocTotal
    doc_currency = db.Column(db.String(10), nullable=True)  # From SAP B1 DocCurrency
    comments = db.Column(db.Text, nullable=True)  # From SAP B1 Comments
    document_status = db.Column(db.String(20), nullable=True)  # From SAP B1 DocumentStatus
    
    # Additional fields for tracking
    last_sap_sync = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    order_lines = relationship('SalesOrderLine', back_populates='sales_order', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<SalesOrder DocEntry={self.doc_entry} CardCode={self.card_code}>'


class SalesOrderLine(db.Model):
    """SAP B1 Sales Order Lines model for Pick List item lookup"""
    __tablename__ = 'sales_order_lines'

    id = db.Column(db.Integer, primary_key=True)
    sales_order_id = db.Column(db.Integer, db.ForeignKey('sales_orders.id'), nullable=False)
    
    # SAP B1 Sales Order Line fields
    line_num = db.Column(db.Integer, nullable=False)  # From SAP B1 LineNum
    item_code = db.Column(db.String(50), nullable=True)  # From SAP B1 ItemCode
    item_description = db.Column(db.String(200), nullable=True)  # From SAP B1 ItemDescription/Dscription
    quantity = db.Column(db.Float, nullable=True)  # From SAP B1 Quantity
    open_quantity = db.Column(db.Float, nullable=True)  # From SAP B1 OpenQuantity
    delivered_quantity = db.Column(db.Float, nullable=True)  # From SAP B1 DeliveredQuantity
    unit_price = db.Column(db.Float, nullable=True)  # From SAP B1 UnitPrice
    line_total = db.Column(db.Float, nullable=True)  # From SAP B1 LineTotal
    warehouse_code = db.Column(db.String(10), nullable=True)  # From SAP B1 WarehouseCode
    unit_of_measure = db.Column(db.String(10), nullable=True)  # From SAP B1 UoMCode
    line_status = db.Column(db.String(20), nullable=True)  # From SAP B1 LineStatus
    
    # Additional tracking fields
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    sales_order = relationship('SalesOrder', back_populates='order_lines')

    def __repr__(self):
        return f'<SalesOrderLine {self.item_code} Line={self.line_num}>'


class DocumentNumberSeries(db.Model):
    __tablename__ = 'document_number_series'

    id = db.Column(db.Integer, primary_key=True)
    document_type = db.Column(db.String(20), nullable=False, unique=True)  # GRPO, TRANSFER, PICKLIST
    prefix = db.Column(db.String(10), nullable=False)  # GRPO-, TR-, PL-
    current_number = db.Column(db.Integer, default=1)
    year_suffix = db.Column(db.Boolean, default=True)  # Include year in numbering
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @classmethod
    def get_next_number(cls, document_type):
        """Generate next document number for given document type"""
        series = cls.query.filter_by(document_type=document_type).first()
        
        if not series:
            # Create default series if not exists
            prefixes = {
                'GRPO': 'GRPO-',
                'TRANSFER': 'TR-',
                'PICKLIST': 'PL-'
            }
            series = cls(
                document_type=document_type,
                prefix=prefixes.get(document_type, 'DOC-'),
                current_number=1
            )
            db.session.add(series)
        
        # Generate document number
        year_suffix = datetime.now().strftime('%Y') if series.year_suffix else ''
        doc_number = f"{series.prefix}{series.current_number:04d}{'-' + year_suffix if year_suffix else ''}"
        
        # Increment counter
        series.current_number += 1
        series.updated_at = datetime.utcnow()
        db.session.commit()
        
        return doc_number

# ================================
# Serial Number Transfer Models
# ================================

class SerialNumberTransfer(db.Model):
    """Serial Number-wise Stock Transfer Document Header"""
    __tablename__ = 'serial_number_transfers'
    
    id = db.Column(db.Integer, primary_key=True)
    transfer_number = db.Column(db.String(50), nullable=False, unique=True)
    sap_document_number = db.Column(db.String(50))
    status = db.Column(db.String(20), default='draft')  # draft, submitted, qc_approved, posted, rejected
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    qc_approver_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    qc_approved_at = db.Column(db.DateTime)
    qc_notes = db.Column(db.Text)
    from_warehouse = db.Column(db.String(10), nullable=False)
    to_warehouse = db.Column(db.String(10), nullable=False)
    priority = db.Column(db.String(10), default='normal')  # low, normal, high, urgent
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', foreign_keys=[user_id], backref='serial_transfers')
    qc_approver = db.relationship('User', foreign_keys=[qc_approver_id])
    items = db.relationship('SerialNumberTransferItem', backref='serial_transfer', lazy=True, cascade='all, delete-orphan')

class SerialNumberTransferItem(db.Model):
    """Serial Number Transfer Line Items"""
    __tablename__ = 'serial_number_transfer_items'
    
    id = db.Column(db.Integer, primary_key=True)
    serial_transfer_id = db.Column(db.Integer, db.ForeignKey('serial_number_transfers.id'), nullable=False)
    item_code = db.Column(db.String(50), nullable=False)
    item_name = db.Column(db.String(200))
    quantity = db.Column(db.Integer, nullable=False)  # Expected quantity for this item
    unit_of_measure = db.Column(db.String(10), default='EA')
    from_warehouse_code = db.Column(db.String(10), nullable=False)
    to_warehouse_code = db.Column(db.String(10), nullable=False)
    qc_status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    serial_numbers = db.relationship('SerialNumberTransferSerial', backref='transfer_item', lazy=True, cascade='all, delete-orphan')

class SerialNumberTransferSerial(db.Model):
    """Individual Serial Numbers for Transfer Items"""
    __tablename__ = 'serial_number_transfer_serials'
    
    id = db.Column(db.Integer, primary_key=True)
    transfer_item_id = db.Column(db.Integer, db.ForeignKey('serial_number_transfer_items.id'), nullable=False)
    serial_number = db.Column(db.String(100), nullable=False)
    internal_serial_number = db.Column(db.String(100), nullable=False)  # From SAP SerialNumberDetails
    system_serial_number = db.Column(db.Integer)  # SystemNumber from SAP
    is_validated = db.Column(db.Boolean, default=False)  # Validated against SAP
    validation_error = db.Column(db.Text)  # Error message if validation fails
    manufacturing_date = db.Column(db.Date)
    expiry_date = db.Column(db.Date)
    admission_date = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Note: Unique constraint removed to allow duplicate serial numbers for user review
    # Users can now add duplicates and manually delete unwanted entries from the UI
    # __table_args__ = (db.UniqueConstraint('transfer_item_id', 'serial_number', name='unique_serial_per_item'),)


# ================================
# Serial Item Transfer Models (New Module)
# ================================

class SerialItemTransfer(db.Model):
    """Serial Item Transfer Document Header - New module for serial-driven transfers"""
    __tablename__ = 'serial_item_transfers'
    
    id = db.Column(db.Integer, primary_key=True)
    transfer_number = db.Column(db.String(50), nullable=False, unique=True)
    sap_document_number = db.Column(db.String(50))
    status = db.Column(db.String(20), default='draft')  # draft, submitted, qc_approved, posted, rejected
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    qc_approver_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    qc_approved_at = db.Column(db.DateTime)
    qc_notes = db.Column(db.Text)
    from_warehouse = db.Column(db.String(10), nullable=False)
    to_warehouse = db.Column(db.String(10), nullable=False)
    priority = db.Column(db.String(10), default='normal')  # low, normal, high, urgent
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', foreign_keys=[user_id], backref='serial_item_transfers')
    qc_approver = db.relationship('User', foreign_keys=[qc_approver_id])
    items = db.relationship('SerialItemTransferItem', backref='serial_item_transfer', lazy=True, cascade='all, delete-orphan')

class SerialItemTransferItem(db.Model):
    """Serial Item Transfer Line Items - Auto-populated from serial number validation"""
    __tablename__ = 'serial_item_transfer_items'
    
    id = db.Column(db.Integer, primary_key=True)
    serial_item_transfer_id = db.Column(db.Integer, db.ForeignKey('serial_item_transfers.id'), nullable=False)
    serial_number = db.Column(db.String(100), nullable=False)  # The entered serial number
    item_code = db.Column(db.String(50), nullable=False)  # Auto-populated from SAP B1
    item_description = db.Column(db.String(200), nullable=False)  # Auto-populated from SAP B1
    warehouse_code = db.Column(db.String(10), nullable=False)  # From SAP B1 validation
    quantity = db.Column(db.Integer, default=1, nullable=False)  # Always 1 for serial items
    unit_of_measure = db.Column(db.String(10), default='EA')
    from_warehouse_code = db.Column(db.String(10), nullable=False)
    to_warehouse_code = db.Column(db.String(10), nullable=False)
    qc_status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    validation_status = db.Column(db.String(20), default='pending')  # pending, validated, failed
    validation_error = db.Column(db.Text)  # Error message if validation fails
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Note: Allowing duplicate serial numbers for user review and manual deletion
    # __table_args__ = (db.UniqueConstraint('serial_item_transfer_id', 'serial_number', name='unique_serial_per_transfer'),)
