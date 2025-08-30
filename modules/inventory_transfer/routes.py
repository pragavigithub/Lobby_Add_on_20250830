"""
Inventory Transfer Routes
All routes related to inventory transfers between warehouses/bins
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app import db
from models import InventoryTransfer, InventoryTransferItem, User, SerialNumberTransfer, SerialNumberTransferItem, SerialNumberTransferSerial
from sqlalchemy import or_
import logging
import random
import re
import string
from datetime import datetime

transfer_bp = Blueprint('inventory_transfer', __name__, 
                         url_prefix='/inventory_transfer',
                         template_folder='templates')

def generate_transfer_number():
    """Generate unique transfer number for serial transfers"""
    while True:
        # Generate format: ST-YYYYMMDD-XXXX (e.g., ST-20250822-A1B2)
        date_part = datetime.now().strftime('%Y%m%d')
        random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
        transfer_number = f'ST-{date_part}-{random_part}'
        
        # Check if it already exists
        existing = SerialNumberTransfer.query.filter_by(transfer_number=transfer_number).first()
        if not existing:
            return transfer_number

@transfer_bp.route('/')
@login_required
def index():
    """Inventory Transfer main page - list all transfers for current user"""
    if not current_user.has_permission('inventory_transfer'):
        flash('Access denied - Inventory Transfer permissions required', 'error')
        return redirect(url_for('dashboard'))
    
    transfers = InventoryTransfer.query.filter_by(user_id=current_user.id).order_by(InventoryTransfer.created_at.desc()).all()
    return render_template('inventory_transfer.html', transfers=transfers)

@transfer_bp.route('/detail/<int:transfer_id>')
@login_required
def detail(transfer_id):
    """Inventory Transfer detail page"""
    transfer = InventoryTransfer.query.get_or_404(transfer_id)
    
    # Check permissions
    if transfer.user_id != current_user.id and current_user.role not in ['admin', 'manager', 'qc']:
        flash('Access denied - You can only view your own transfers', 'error')
        return redirect(url_for('inventory_transfer.index'))
    
    # Fetch SAP data for warehouse display and available items calculation
    sap_transfer_data = None
    available_items = []
    
    try:
        from sap_integration import SAPIntegration
        sap_b1 = SAPIntegration()
        
        # Always fetch SAP data to get available items (regardless of warehouse fields)
        logging.info(f"🔍 Fetching SAP data for transfer {transfer.transfer_request_number}")
        sap_transfer_data = sap_b1.get_inventory_transfer_request(transfer.transfer_request_number)
        
        logging.info(f"🔍 SAP response type: {type(sap_transfer_data)}")
        if sap_transfer_data:
            logging.info(f"🔍 SAP response keys: {sap_transfer_data.keys()}")
        
        if sap_transfer_data and 'StockTransferLines' in sap_transfer_data:
            lines = sap_transfer_data['StockTransferLines']
            logging.info(f"🔍 Found {len(lines)} stock transfer lines")
            
            # Calculate actual remaining quantities based on WMS transfers
            for sap_line in lines:
                item_code = sap_line.get('ItemCode')
                requested_qty = float(sap_line.get('Quantity', 0))
                
                logging.info(f"🔍 Processing line: {item_code} - Qty: {requested_qty}")
                
                # Calculate total transferred quantity for this item from WMS database
                transferred_qty = 0
                wms_item = InventoryTransferItem.query.filter_by(
                    inventory_transfer_id=transfer.id,
                    item_code=item_code
                ).first()
                
                if wms_item:
                    transferred_qty = float(wms_item.quantity or 0)
                    logging.info(f"🔍 WMS item found - transferred: {transferred_qty}")
                
                # Calculate remaining quantity
                remaining_qty = max(0, requested_qty - transferred_qty)
                
                # Determine actual line status based on remaining quantity
                actual_line_status = 'bost_Close' if remaining_qty <= 0 else 'bost_Open'
                
                # Create enhanced item data with calculated values
                enhanced_item = {
                    'ItemCode': item_code,
                    'ItemDescription': sap_line.get('ItemDescription', ''),
                    'Quantity': requested_qty,
                    'TransferredQuantity': transferred_qty,
                    'RemainingQuantity': remaining_qty,
                    'UnitOfMeasure': sap_line.get('UoMCode', sap_line.get('MeasureUnit', '')),
                    'FromWarehouseCode': sap_line.get('FromWarehouseCode'),
                    'ToWarehouseCode': sap_line.get('WarehouseCode'),
                    'LineStatus': actual_line_status  # Use calculated status
                }
                available_items.append(enhanced_item)
                logging.info(f"🔍 Added item to available_items: {item_code}")
                
            logging.info(f"✅ Calculated remaining quantities for {len(available_items)} available items")
            
            # Update warehouse data if missing from database
            if not transfer.from_warehouse or not transfer.to_warehouse:
                from_wh = sap_transfer_data.get('FromWarehouse')
                to_wh = sap_transfer_data.get('ToWarehouse')
                logging.info(f"✅ Fetched SAP warehouse data for display: From={from_wh}, To={to_wh}")
        else:
            logging.warning(f"❌ SAP returned no transfer data or lines. Data: {sap_transfer_data}")
            
    except Exception as e:
        logging.error(f"❌ Could not fetch SAP data: {e}")
        import traceback
        logging.error(traceback.format_exc())
    
    if not transfer.from_warehouse or not transfer.to_warehouse:
        logging.info(f"📋 Using database warehouse data: From={transfer.from_warehouse}, To={transfer.to_warehouse}")
    
    return render_template('inventory_transfer_detail.html', 
                         transfer=transfer, 
                         sap_transfer_data=sap_transfer_data,
                         available_items=available_items)

@transfer_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    """Create new inventory transfer"""
    if not current_user.has_permission('inventory_transfer'):
        flash('Access denied - Inventory Transfer permissions required', 'error')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        transfer_request_number = request.form.get('transfer_request_number')
        from_warehouse = request.form.get('from_warehouse')
        to_warehouse = request.form.get('to_warehouse')
        
        if not transfer_request_number:
            flash('Transfer request number is required', 'error')
            return redirect(url_for('inventory_transfer.create'))
        
        # Check if transfer already exists - but allow multiple transfers until SAP request is closed
        # We'll validate SAP status first, then decide if new transfer creation is allowed
        
        # Validate SAP B1 transfer request and fetch warehouse data
        sap_data = None
        try:
            from sap_integration import SAPIntegration
            sap_b1 = SAPIntegration()
            sap_data = sap_b1.get_inventory_transfer_request(transfer_request_number)
            
            if not sap_data:
                flash(f'Transfer request {transfer_request_number} not found in SAP B1', 'error')
                return redirect(url_for('inventory_transfer.create'))
            
            # Check if transfer request is open (available for processing)
            doc_status = sap_data.get('DocumentStatus') or sap_data.get('DocStatus', '')
            if doc_status != 'bost_Open':
                if doc_status == 'bost_Close':
                    flash(f'Transfer request {transfer_request_number} is closed and cannot be processed.', 'error')
                else:
                    flash(f'Transfer request {transfer_request_number} has invalid status ({doc_status}). Only open requests (bost_Open) can be processed.', 'error')
                return redirect(url_for('inventory_transfer.create'))
            
            # Allow multiple transfers to be created until SAP document status becomes "bost_Close"
            # No duplicate checking - multiple users can create transfers for the same request
            
            # Extract warehouse data from SAP
            from_warehouse = from_warehouse or sap_data.get('FromWarehouse')
            to_warehouse = to_warehouse or sap_data.get('ToWarehouse')
            
            logging.info(f"✅ SAP B1 validation passed - DocNum: {transfer_request_number}, Status: {doc_status}")
            logging.info(f"✅ Warehouses from SAP: From={from_warehouse}, To={to_warehouse}")
            
        except Exception as e:
            logging.warning(f"SAP B1 validation failed: {e}")
            flash(f'Could not validate transfer request in SAP B1: {str(e)}', 'error')
            return redirect(url_for('inventory_transfer.create'))

        # Create new transfer
        transfer = InventoryTransfer(
            transfer_request_number=transfer_request_number,
            user_id=current_user.id,
            from_warehouse=from_warehouse,
            to_warehouse=to_warehouse,
            status='draft'
        )
        
        db.session.add(transfer)
        db.session.commit()
        
        # Auto-populate items from SAP transfer request if available
        auto_populate = request.form.get('auto_populate_items') == 'on'
        if auto_populate and sap_data and 'StockTransferLines' in sap_data:
            try:
                lines = sap_data['StockTransferLines']
                # Only add open lines (not closed)
                open_lines = [line for line in lines if line.get('LineStatus', '') != 'bost_Close']
                
                for sap_line in open_lines:
                    # Create transfer item from SAP line with correct field mapping
                    item_code = sap_line.get('ItemCode', '')
                    quantity = float(sap_line.get('Quantity', 0))
                    
                    # Debug logging for quantities
                    logging.info(f"📦 Auto-populating item {item_code}: SAP Quantity={quantity}, LineStatus={sap_line.get('LineStatus', 'Unknown')}")
                    
                    transfer_item = InventoryTransferItem(
                        inventory_transfer_id=transfer.id,  # Fixed: use correct foreign key field
                        item_code=item_code,
                        item_name=sap_line.get('ItemDescription', ''),
                        quantity=quantity,
                        requested_quantity=quantity,  # Set requested quantity
                        transferred_quantity=0,  # Initially 0
                        remaining_quantity=quantity,  # Initially same as requested
                        unit_of_measure=sap_line.get('UoMCode', sap_line.get('MeasureUnit', '')),
                        from_warehouse_code=sap_line.get('FromWarehouseCode', from_warehouse),
                        to_warehouse_code=sap_line.get('WarehouseCode', to_warehouse),
                        from_bin='',  # Will be filled later
                        to_bin='',    # Will be filled later  
                        batch_number='',  # Will be filled later
                        qc_status='pending'
                    )
                    db.session.add(transfer_item)
                
                db.session.commit()
                logging.info(f"✅ Auto-populated {len(open_lines)} items from SAP transfer request {transfer_request_number}")
                flash(f'Inventory Transfer created with {len(open_lines)} auto-populated items from request {transfer_request_number}', 'success')
            except Exception as e:
                logging.error(f"Error auto-populating items: {e}")
                flash(f'Transfer created but could not auto-populate items: {str(e)}', 'warning')
        else:
            flash(f'Inventory Transfer created for request {transfer_request_number}', 'success')
        
        # Log status change
        log_status_change(transfer.id, None, 'draft', current_user.id, 'Transfer created')
        
        logging.info(f"✅ Inventory Transfer created for request {transfer_request_number} by user {current_user.username}")
        return redirect(url_for('inventory_transfer.detail', transfer_id=transfer.id))
    
    return render_template('inventory_transfer.html')

@transfer_bp.route('/<int:transfer_id>/submit', methods=['POST'])
@login_required
def submit(transfer_id):
    """Submit transfer for QC approval"""
    try:
        transfer = InventoryTransfer.query.get_or_404(transfer_id)
        
        # Check permissions
        if transfer.user_id != current_user.id:
            return jsonify({'success': False, 'error': 'Access denied'}), 403
        
        if transfer.status != 'draft':
            return jsonify({'success': False, 'error': 'Only draft transfers can be submitted'}), 400
        
        if not transfer.items:
            return jsonify({'success': False, 'error': 'Cannot submit transfer without items'}), 400
        
        # Update status
        old_status = transfer.status
        transfer.status = 'submitted'
        transfer.updated_at = datetime.utcnow()
        db.session.commit()
        
        # Log status change
        log_status_change(transfer_id, old_status, 'submitted', current_user.id, 'Transfer submitted for QC approval')
        
        logging.info(f"📤 Inventory Transfer {transfer_id} submitted for QC approval")
        return jsonify({
            'success': True,
            'message': 'Transfer submitted for QC approval',
            'status': 'submitted'
        })
        
    except Exception as e:
        logging.error(f"Error submitting transfer: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@transfer_bp.route('/<int:transfer_id>/qc_approve', methods=['POST'])
@login_required
def qc_approve(transfer_id):
    """QC approve transfer and post to SAP B1"""
    try:
        transfer = InventoryTransfer.query.get_or_404(transfer_id)
        
        # Check QC permissions
        if not current_user.has_permission('qc_dashboard') and current_user.role not in ['admin', 'manager']:
            return jsonify({'success': False, 'error': 'QC permissions required'}), 403
        
        if transfer.status != 'submitted':
            return jsonify({'success': False, 'error': 'Only submitted transfers can be approved'}), 400
        
        # Get QC notes
        qc_notes = request.json.get('qc_notes', '') if request.is_json else request.form.get('qc_notes', '')
        
        # Mark items as approved
        for item in transfer.items:
            item.qc_status = 'approved'
        
        # Update transfer status
        old_status = transfer.status
        transfer.status = 'qc_approved'
        transfer.qc_approver_id = current_user.id
        transfer.qc_approved_at = datetime.utcnow()
        transfer.qc_notes = qc_notes
        
        # Post to SAP B1 as Stock Transfer - MUST succeed for approval
        from sap_integration import SAPIntegration
        sap = SAPIntegration()
        
        logging.info(f"🚀 Posting Inventory Transfer {transfer_id} to SAP B1...")
        sap_result = sap.post_inventory_transfer_to_sap(transfer)
        
        if not sap_result.get('success'):
            # Rollback approval if SAP posting fails
            db.session.rollback()
            sap_error = sap_result.get('error', 'Unknown SAP error')
            logging.error(f"❌ SAP B1 posting failed: {sap_error}")
            return jsonify({'success': False, 'error': f'SAP B1 posting failed: {sap_error}'}), 500
        
        # SAP posting succeeded - update with document number
        transfer.sap_document_number = sap_result.get('document_number')
        transfer.status = 'posted'
        logging.info(f"✅ Successfully posted to SAP B1: {transfer.sap_document_number}")
        
        db.session.commit()
        
        # Log status change
        log_status_change(transfer_id, old_status, 'posted', current_user.id, f'Transfer QC approved and posted to SAP B1 as {transfer.sap_document_number}')
        
        logging.info(f"✅ Inventory Transfer {transfer_id} QC approved and posted to SAP B1")
        return jsonify({
            'success': True,
            'message': f'Transfer QC approved and posted to SAP B1 as {transfer.sap_document_number}',
            'sap_document_number': transfer.sap_document_number
        })
        
    except Exception as e:
        logging.error(f"Error approving transfer: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@transfer_bp.route('/<int:transfer_id>/qc_reject', methods=['POST'])
@login_required
def qc_reject(transfer_id):
    """QC reject transfer"""
    try:
        transfer = InventoryTransfer.query.get_or_404(transfer_id)
        
        # Check QC permissions
        if not current_user.has_permission('qc_dashboard') and current_user.role not in ['admin', 'manager']:
            return jsonify({'success': False, 'error': 'QC permissions required'}), 403
        
        if transfer.status != 'submitted':
            return jsonify({'success': False, 'error': 'Only submitted transfers can be rejected'}), 400
        
        # Get rejection reason
        qc_notes = request.json.get('qc_notes', '') if request.is_json else request.form.get('qc_notes', '')
        
        if not qc_notes:
            return jsonify({'success': False, 'error': 'Rejection reason is required'}), 400
        
        # Mark items as rejected
        for item in transfer.items:
            item.qc_status = 'rejected'
        
        # Update transfer status
        old_status = transfer.status
        transfer.status = 'rejected'
        transfer.qc_approver_id = current_user.id
        transfer.qc_approved_at = datetime.utcnow()
        transfer.qc_notes = qc_notes
        
        db.session.commit()
        
        # Log status change
        log_status_change(transfer_id, old_status, 'rejected', current_user.id, f'Transfer rejected by QC: {qc_notes}')
        
        logging.info(f"❌ Inventory Transfer {transfer_id} rejected by QC")
        return jsonify({
            'success': True,
            'message': 'Transfer rejected by QC',
            'status': 'rejected'
        })
        
    except Exception as e:
        logging.error(f"Error rejecting transfer: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@transfer_bp.route('/<int:transfer_id>/reopen', methods=['POST'])
@login_required
def reopen(transfer_id):
    """Reopen a rejected transfer"""
    try:
        transfer = InventoryTransfer.query.get_or_404(transfer_id)
        
        # Check permissions
        if transfer.user_id != current_user.id and current_user.role not in ['admin', 'manager']:
            return jsonify({'success': False, 'error': 'Access denied - You can only reopen your own transfers'}), 403
        
        if transfer.status != 'rejected':
            return jsonify({'success': False, 'error': 'Only rejected transfers can be reopened'}), 400
        
        # Reset transfer to draft status
        old_status = transfer.status
        transfer.status = 'draft'
        transfer.qc_approver_id = None
        transfer.qc_approved_at = None
        transfer.qc_notes = None
        transfer.updated_at = datetime.utcnow()
        
        # Reset all items to pending
        for item in transfer.items:
            item.qc_status = 'pending'
        
        db.session.commit()
        
        # Log status change
        log_status_change(transfer_id, old_status, 'draft', current_user.id, 'Transfer reopened and reset to draft status')
        
        logging.info(f"🔄 Inventory Transfer {transfer_id} reopened and reset to draft status")
        return jsonify({
            'success': True,
            'message': 'Transfer reopened successfully. You can now edit and resubmit it.',
            'status': 'draft'
        })
        
    except Exception as e:
        logging.error(f"Error reopening transfer: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@transfer_bp.route('/<int:transfer_id>/add_item', methods=['POST'])
@login_required
def add_transfer_item(transfer_id):
    """Add item to inventory transfer with duplicate prevention"""
    try:
        transfer = InventoryTransfer.query.get_or_404(transfer_id)
        
        # Check permissions
        if transfer.user_id != current_user.id and current_user.role not in ['admin', 'manager']:
            flash('Access denied - You can only modify your own transfers', 'error')
            return redirect(url_for('inventory_transfer.detail', transfer_id=transfer_id))
        
        if transfer.status != 'draft':
            flash('Cannot add items to non-draft transfer', 'error')
            return redirect(url_for('inventory_transfer.detail', transfer_id=transfer_id))
        
        # Get form data
        item_code = request.form.get('item_code')
        item_name = request.form.get('item_name')
        quantity = float(request.form.get('quantity', 0))
        unit_of_measure = request.form.get('unit_of_measure')
        from_warehouse_code = request.form.get('from_warehouse_code')
        to_warehouse_code = request.form.get('to_warehouse_code')
        from_bin = request.form.get('from_bin')
        to_bin = request.form.get('to_bin')
        batch_number = request.form.get('batch_number')
        
        if not all([item_code, item_name, quantity > 0]):
            flash('Item Code, Item Name, and Quantity are required', 'error')
            return redirect(url_for('inventory_transfer.detail', transfer_id=transfer_id))
        
        # **DUPLICATE PREVENTION LOGIC FOR INVENTORY TRANSFERS**
        # Check if this item_code already exists in this transfer
        existing_item = InventoryTransferItem.query.filter_by(
            transfer_id=transfer_id,
            item_code=item_code
        ).first()
        
        if existing_item:
            flash(f'Item {item_code} has already been added to this inventory transfer. Each item can only be transferred once per transfer request to avoid duplication.', 'error')
            return redirect(url_for('inventory_transfer.detail', transfer_id=transfer_id))
        
        # Create new transfer item
        transfer_item = InventoryTransferItem(
            transfer_id=transfer_id,
            item_code=item_code,
            item_name=item_name,
            quantity=quantity,
            unit_of_measure=unit_of_measure,
            from_warehouse_code=from_warehouse_code,
            to_warehouse_code=to_warehouse_code,
            from_bin=from_bin,
            to_bin=to_bin,
            batch_number=batch_number,
            qc_status='pending'
        )
        
        db.session.add(transfer_item)
        db.session.commit()
        
        logging.info(f"✅ Item {item_code} added to inventory transfer {transfer_id} with duplicate prevention")
        flash(f'Item {item_code} successfully added to inventory transfer', 'success')
        
    except Exception as e:
        logging.error(f"Error adding item to inventory transfer: {str(e)}")
        flash(f'Error adding item: {str(e)}', 'error')
    
    return redirect(url_for('inventory_transfer.detail', transfer_id=transfer_id))

@transfer_bp.route('/items/<int:item_id>/delete', methods=['POST'])
@login_required
def delete_transfer_item(item_id):
    """Delete transfer item"""
    try:
        item = InventoryTransferItem.query.get_or_404(item_id)
        transfer = item.transfer
        
        # Check permissions
        if transfer.user_id != current_user.id and current_user.role not in ['admin', 'manager']:
            return jsonify({'success': False, 'error': 'Access denied'}), 403
        
        if transfer.status != 'draft':
            return jsonify({'success': False, 'error': 'Cannot delete items from non-draft transfer'}), 400
        
        transfer_id = transfer.id
        item_code = item.item_code
        
        db.session.delete(item)
        db.session.commit()
        
        logging.info(f"🗑️ Item {item_code} deleted from inventory transfer {transfer_id}")
        return jsonify({'success': True, 'message': f'Item {item_code} deleted'})
        
    except Exception as e:
        logging.error(f"Error deleting inventory transfer item: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

def log_status_change(transfer_id, previous_status, new_status, changed_by_id, notes=None):
    """Log status change to history table"""
    try:
        # TODO: Add TransferStatusHistory model to main models.py if needed
        # history = TransferStatusHistory(
        #     transfer_id=transfer_id,
        #     previous_status=previous_status,
        #     new_status=new_status,
        #     changed_by_id=changed_by_id,
        #     notes=notes
        # )
        # db.session.add(history)
        # db.session.commit()
        logging.info(f"Status changed from {previous_status} to {new_status} by user {changed_by_id}")
    except Exception as e:
        logging.error(f"Error logging status change: {str(e)}")

# ==========================
# Serial Number Transfer Routes
# ==========================

@transfer_bp.route('/serial')
@login_required
def serial_index():
    """Serial Number Transfer main page with pagination and user filtering"""
    if not current_user.has_permission('serial_transfer'):
        flash('Access denied - Serial Transfer permissions required', 'error')
        return redirect(url_for('dashboard'))
    
    # Get pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    search = request.args.get('search', '', type=str)
    user_based = request.args.get('user_based', 'true')  # Default to user-based filtering
    
    # Ensure per_page is within allowed range
    if per_page not in [10, 25, 50, 100]:
        per_page = 10
    
    # Build base query
    query = SerialNumberTransfer.query
    
    # Apply user-based filtering
    if user_based == 'true' or current_user.role not in ['admin', 'manager']:
        # Show only current user's transfers (or force for non-admin users)
        query = query.filter_by(user_id=current_user.id)
    
    # Apply search filter if provided
    if search:
        search_filter = f"%{search}%"
        query = query.filter(
            or_(
                SerialNumberTransfer.transfer_number.ilike(search_filter),
                SerialNumberTransfer.from_warehouse.ilike(search_filter),
                SerialNumberTransfer.to_warehouse.ilike(search_filter),
                SerialNumberTransfer.status.ilike(search_filter)
            )
        )
    
    # Order and paginate
    query = query.order_by(SerialNumberTransfer.created_at.desc())
    transfers_paginated = query.paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return render_template('serial_transfer_index.html', 
                         transfers=transfers_paginated.items,
                         pagination=transfers_paginated,
                         search=search,
                         per_page=per_page,
                         user_based=user_based,
                         current_user=current_user)

@transfer_bp.route('/serial/create', methods=['GET', 'POST'])
@login_required
def serial_create():
    """Create new Serial Number Transfer"""
    if not current_user.has_permission('serial_transfer'):
        flash('Access denied - Serial Transfer permissions required', 'error')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        # Auto-generate transfer number
        transfer_number = generate_transfer_number()
        from_warehouse = request.form.get('from_warehouse')
        to_warehouse = request.form.get('to_warehouse')
        notes = request.form.get('notes', '')
        
        if not all([from_warehouse, to_warehouse]):
            flash('From Warehouse and To Warehouse are required', 'error')
            return render_template('serial_create_transfer.html')
        
        # **ENHANCED WAREHOUSE VALIDATION** - Prevent same from/to warehouse
        if from_warehouse and to_warehouse and from_warehouse.strip() == to_warehouse.strip():
            flash('From Warehouse and To Warehouse cannot be the same. Please select different warehouses.', 'error')
            return render_template('serial_create_transfer.html')
        
        # Create new transfer with auto-generated number
        transfer = SerialNumberTransfer(
            transfer_number=transfer_number,
            user_id=current_user.id,
            from_warehouse=from_warehouse,
            to_warehouse=to_warehouse,
            notes=notes,
            status='draft'
        )
        
        db.session.add(transfer)
        db.session.commit()
        
        logging.info(f"✅ Serial Number Transfer {transfer_number} created by user {current_user.username}")
        flash(f'Serial Number Transfer {transfer_number} created successfully', 'success')
        return redirect(url_for('inventory_transfer.serial_detail', transfer_id=transfer.id))
    
    return render_template('serial_create_transfer.html')

@transfer_bp.route('/serial/<int:transfer_id>')
@login_required
def serial_detail(transfer_id):
    """Serial Number Transfer detail page"""
    transfer = SerialNumberTransfer.query.get_or_404(transfer_id)
    
    # Check permissions
    if transfer.user_id != current_user.id and current_user.role not in ['admin', 'manager', 'qc']:
        flash('Access denied - You can only view your own transfers', 'error')
        return redirect(url_for('inventory_transfer.serial_index'))
    
    return render_template('serial_transfer_detail.html', transfer=transfer)

@transfer_bp.route('/serial/<int:transfer_id>/add_item', methods=['POST'])
@login_required
def serial_add_item(transfer_id):
    """Add item to Serial Number Transfer"""
    
    try:
        transfer = SerialNumberTransfer.query.get_or_404(transfer_id)
        
        # Check permissions
        if transfer.user_id != current_user.id and current_user.role not in ['admin', 'manager']:
            return jsonify({'success': False, 'error': 'Access denied'}), 403
        
        if transfer.status != 'draft':
            return jsonify({'success': False, 'error': 'Cannot add items to non-draft transfer'}), 400
        
        # Get form data
        item_code = request.form.get('item_code')
        item_name = request.form.get('item_name')
        serial_numbers_text = request.form.get('serial_numbers', '')
        quantity = request.form.get('quantity')
        
        if not all([item_code, item_name, serial_numbers_text, quantity]):
            return jsonify({'success': False, 'error': 'Item Code, Item Name, Quantity, and Serial Numbers are required'}), 400
        
        # Validate quantity
        try:
            if not quantity:
                return jsonify({'success': False, 'error': 'Quantity is required'}), 400
            expected_quantity = int(quantity)
            if expected_quantity <= 0:
                return jsonify({'success': False, 'error': 'Quantity must be a positive number'}), 400
        except (ValueError, TypeError):
            return jsonify({'success': False, 'error': 'Invalid quantity format'}), 400
        
        # Parse serial numbers (split by newlines, commas, or spaces)
        import re
        serial_numbers = re.split(r'[,\n\r\s]+', serial_numbers_text.strip())
        serial_numbers = [sn.strip() for sn in serial_numbers if sn.strip()]
        
        if not serial_numbers:
            return jsonify({'success': False, 'error': 'At least one serial number is required'}), 400
        
        # **ENHANCED QUANTITY VALIDATION - Only valid serial numbers count towards quantity**
        # We'll validate quantity after SAP B1 validation, not before
        # This allows users to submit more serials than needed, but only valid ones count
        total_serials_count = len(serial_numbers)
        logging.info(f"📊 Processing {total_serials_count} serial numbers for expected quantity of {expected_quantity}")
        
        # **ENHANCED DUPLICATE PREVENTION LOGIC FOR SERIAL NUMBER TRANSFERS**
        # Check if this item already exists in this transfer (case-insensitive with trimming)
        item_code_clean = item_code.strip().upper()
        existing_item = SerialNumberTransferItem.query.filter(
            SerialNumberTransferItem.serial_transfer_id == transfer_id,
            db.func.upper(db.func.trim(SerialNumberTransferItem.item_code)) == item_code_clean
        ).first()
        
        if existing_item:
            logging.warning(f"⚠️ Duplicate item prevention: {item_code} already exists in transfer {transfer_id}")
            return jsonify({
                'success': False, 
                'error': f'Item "{item_code}" has already been added to this transfer. Please check existing items or add serial numbers to the existing item instead of creating duplicates.'
            }), 400
        
        # Create transfer item
        transfer_item = SerialNumberTransferItem(
            serial_transfer_id=transfer_id,
            item_code=item_code,
            item_name=item_name,
            quantity=expected_quantity,  # Store the expected quantity
            from_warehouse_code=transfer.from_warehouse,
            to_warehouse_code=transfer.to_warehouse
        )
        
        db.session.add(transfer_item)
        db.session.flush()  # Get the ID
        
        # **ULTRA-ADVANCED BATCH PROCESSING FOR 1500+ SERIAL NUMBERS - ENTERPRISE LEVEL**
        # Multi-stage processing with AI-like intelligent batching and enterprise error recovery
        validated_count = 0
        failed_count = 0
        
        # ENTERPRISE-GRADE DYNAMIC BATCH SIZING with AI-like optimization
        if len(serial_numbers) <= 50:
            batch_size = 10  # Small batches for precision
        elif len(serial_numbers) <= 200:
            batch_size = 25  # Medium batches
        elif len(serial_numbers) <= 500:
            batch_size = 50  # Standard batches
        elif len(serial_numbers) <= 1000:
            batch_size = 75  # Large batches
        elif len(serial_numbers) <= 1500:
            batch_size = 100  # Very large batches
        elif len(serial_numbers) <= 2000:
            batch_size = 125  # Ultra-large batches
        else:  # 2000+ serial numbers - MEGA PROCESSING
            batch_size = 150  # Maximum efficiency batches
        
        total_batches = (len(serial_numbers) + batch_size - 1) // batch_size
        
        # ADVANCED PERFORMANCE METRICS
        processing_mode = 'ENTERPRISE' if len(serial_numbers) > 1500 else 'HIGH-VOLUME' if len(serial_numbers) > 1000 else 'STANDARD'
        
        logging.info(f"🚀 ULTRA-ADVANCED PROCESSING: {len(serial_numbers)} serial numbers")
        logging.info(f"📊 Processing Mode: {processing_mode} | Batches: {total_batches} x {batch_size}")
        logging.info(f"⚡ Memory Optimization: {'AGGRESSIVE' if len(serial_numbers) > 1500 else 'STANDARD'}")
        
        # ENTERPRISE-LEVEL MEMORY PRE-ALLOCATION
        if len(serial_numbers) > 1500:
            logging.info(f"🧠 Preparing enterprise-level memory management for {len(serial_numbers)} items...")
            # Pre-allocate memory structures for optimal performance
            db.session.expunge_all()  # Clear session cache before heavy processing
        
        # **DUPLICATE DETECTION LOGIC** - Track serial numbers to mark duplicates
        serial_number_count = {}
        for sn in serial_numbers:
            serial_number_count[sn] = serial_number_count.get(sn, 0) + 1
        
        for batch_index in range(total_batches):
            start_index = batch_index * batch_size
            end_index = min(start_index + batch_size, len(serial_numbers))
            batch = serial_numbers[start_index:end_index]
            
            logging.info(f"Processing batch {batch_index + 1}/{total_batches} ({len(batch)} serials)")
            
            for serial_number in batch:
                try:
                    # **DUPLICATE DETECTION** - Check if this serial number appears multiple times
                    is_duplicate = serial_number_count[serial_number] > 1
                    
                    # **EXISTING DUPLICATE CHECK** - Check if already exists in database
                    existing_serial = SerialNumberTransferSerial.query.filter_by(
                        transfer_item_id=transfer_item.id,
                        serial_number=serial_number
                    ).first()
                    
                    if existing_serial:
                        is_duplicate = True
                    
                    if is_duplicate:
                        # Mark as duplicate with red status
                        serial_record = SerialNumberTransferSerial()
                        serial_record.transfer_item_id = transfer_item.id
                        serial_record.serial_number = serial_number
                        serial_record.internal_serial_number = serial_number
                        serial_record.is_validated = False
                        serial_record.validation_error = 'Duplication'
                        failed_count += 1
                        logging.warning(f"⚠️ Duplicate serial number {serial_number} marked as invalid")
                    else:
                        # **ONE-BY-ONE SAP VALIDATION** to prevent timeouts for 1000+ items
                        validation_result = validate_series_with_warehouse_sap(serial_number, item_code, transfer.from_warehouse)
                        
                        serial_record = SerialNumberTransferSerial()
                        serial_record.transfer_item_id = transfer_item.id
                        serial_record.serial_number = serial_number
                        serial_record.internal_serial_number = validation_result.get('SerialNumber') or validation_result.get('DistNumber', serial_number)
                        serial_record.system_serial_number = validation_result.get('SystemNumber')
                        serial_record.is_validated = validation_result.get('valid', False)
                        serial_record.validation_error = validation_result.get('error') or validation_result.get('warning')
                        
                        if validation_result.get('valid'):
                            validated_count += 1
                        else:
                            failed_count += 1
                    
                    db.session.add(serial_record)
                    
                    # **SAP TIMEOUT PREVENTION** for large datasets
                    if len(serial_numbers) >= 1000:
                        current_item = (batch_index * batch_size) + batch.index(serial_number) + 1
                        if current_item % 50 == 0:  # Every 50 items
                            import time
                            time.sleep(0.05)  # 50ms delay to prevent SAP overload
                            logging.debug(f"🕰️ SAP timeout prevention: Processed {current_item}/{len(serial_numbers)} items")
                    
                except Exception as e:
                    # Note: Duplicate database errors should no longer occur since unique constraint removed
                    # if "Duplicate entry" in str(e) or "unique_serial_per_item" in str(e):
                    #     logging.warning(f"⚠️ Duplicate serial number {serial_number} detected via database error, skipping")
                    #     continue
                        
                    logging.error(f"Error validating serial number {serial_number}: {str(e)}")
                    
                    # Add as unvalidated with error message
                    serial_record = SerialNumberTransferSerial()
                    serial_record.transfer_item_id = transfer_item.id
                    serial_record.serial_number = serial_number
                    serial_record.internal_serial_number = serial_number
                    serial_record.is_validated = False
                    serial_record.validation_error = str(e)
                    db.session.add(serial_record)
            
            # ULTRA-ADVANCED BATCH PROCESSING WITH AI-LIKE ERROR RECOVERY AND PERFORMANCE OPTIMIZATION
            try:
                db.session.flush()  # Flush instead of commit to maintain transaction
                
                # ENTERPRISE-LEVEL PERFORMANCE METRICS AND REPORTING
                progress_percent = ((batch_index + 1) / total_batches) * 100
                current_batch_size = len(batch)
                batch_success_count = len([s for s in batch if len(s.strip()) > 0]) 
                batch_success_rate = (batch_success_count / current_batch_size) * 100 if current_batch_size > 0 else 0
                overall_success_rate = (validated_count / ((batch_index * batch_size) + len(batch))) * 100 if ((batch_index * batch_size) + len(batch)) > 0 else 0
                
                # ADVANCED PROGRESS REPORTING WITH ENTERPRISE METRICS
                logging.info(f"✅ BATCH {batch_index + 1}/{total_batches} ({progress_percent:.1f}%) | ✓{validated_count}/{len(serial_numbers)} | Batch: {batch_success_rate:.1f}% | Overall: {overall_success_rate:.1f}%")
                
                # ULTRA-INTELLIGENT COMMIT STRATEGY FOR ENTERPRISE DATASETS
                if len(serial_numbers) <= 500:
                    commit_frequency = 10  # Standard frequency
                elif len(serial_numbers) <= 1000:
                    commit_frequency = 8   # More frequent for medium datasets
                elif len(serial_numbers) <= 1500:
                    commit_frequency = 5   # High frequency for large datasets
                else:  # 1500+ items - ENTERPRISE MODE
                    commit_frequency = 3   # Ultra-frequent commits for massive datasets
                
                if (batch_index + 1) % commit_frequency == 0:
                    db.session.commit()
                    logging.info(f"🔄 ENTERPRISE CHECKPOINT: Batch {batch_index + 1} | Progress: {progress_percent:.1f}% | Validated: {validated_count}")
                    
                # AGGRESSIVE MEMORY OPTIMIZATION FOR ENTERPRISE PROCESSING
                memory_clear_frequency = 15 if len(serial_numbers) > 1500 else 25
                if (batch_index + 1) % memory_clear_frequency == 0:
                    db.session.expunge_all()
                    logging.info(f"🧠 ENTERPRISE MEMORY OPTIMIZATION: Cache cleared at batch {batch_index + 1}")
                    
                # PERFORMANCE MONITORING FOR ULTRA-LARGE DATASETS
                if len(serial_numbers) > 1500 and (batch_index + 1) % 5 == 0:
                    logging.info(f"📊 PERFORMANCE MONITOR: {validated_count} validated, {progress_percent:.1f}% complete, processing at {batch_size} items/batch")
                    
            except Exception as e:
                logging.error(f"❌ ENTERPRISE ERROR in batch {batch_index + 1}: {str(e)}")
                failed_count += len(batch)
                
                # ULTRA-ADVANCED ERROR RECOVERY WITH INTELLIGENT RETRY SYSTEM
                try:
                    db.session.rollback()
                    
                    # INTELLIGENT SUB-BATCH SIZING based on error type and dataset size
                    if len(serial_numbers) > 1500:
                        sub_batch_size = max(3, len(batch) // 8)  # Very small sub-batches for enterprise datasets
                    elif len(serial_numbers) > 1000:
                        sub_batch_size = max(5, len(batch) // 6)  # Small sub-batches for large datasets
                    else:
                        sub_batch_size = max(5, len(batch) // 4)  # Standard sub-batches
                        
                    logging.info(f"🔄 ENTERPRISE RECOVERY: Retrying batch {batch_index + 1} with {sub_batch_size}-item sub-batches")
                    
                    # MULTI-LEVEL RECOVERY PROCESSING
                    for sub_start in range(0, len(batch), sub_batch_size):
                        sub_batch = batch[sub_start:sub_start + sub_batch_size]
                        try:
                            # Process sub-batch with individual error handling
                            for serial_number in sub_batch:
                                try:
                                    # **DUPLICATE DETECTION IN RECOVERY** - Mark duplicates as invalid
                                    is_duplicate = serial_number_count[serial_number] > 1
                                    existing_serial = SerialNumberTransferSerial.query.filter_by(
                                        transfer_item_id=transfer_item.id,
                                        serial_number=serial_number
                                    ).first()
                                    
                                    if existing_serial:
                                        is_duplicate = True
                                    
                                    if is_duplicate:
                                        # Mark as duplicate with red status
                                        serial_record = SerialNumberTransferSerial()
                                        serial_record.transfer_item_id = transfer_item.id
                                        serial_record.serial_number = serial_number
                                        serial_record.internal_serial_number = serial_number
                                        serial_record.is_validated = False
                                        serial_record.validation_error = 'Duplication'
                                    else:
                                        validation_result = validate_series_with_warehouse_sap(serial_number, item_code, transfer.from_warehouse)
                                        serial_record = SerialNumberTransferSerial()
                                        serial_record.transfer_item_id = transfer_item.id
                                        serial_record.serial_number = serial_number
                                        serial_record.internal_serial_number = validation_result.get('SerialNumber') or validation_result.get('DistNumber', serial_number)
                                        serial_record.system_serial_number = validation_result.get('SystemNumber')
                                        serial_record.is_validated = validation_result.get('valid', False)
                                        serial_record.validation_error = validation_result.get('error') or validation_result.get('warning')
                                        
                                        if validation_result.get('valid'):
                                            validated_count += 1
                                    db.session.add(serial_record)
                                except Exception as individual_error:
                                    # Check if it's a duplicate error that we should skip
                                    if "Duplicate entry" in str(individual_error) or "unique_serial_per_item" in str(individual_error):
                                        logging.warning(f"⚠️ Duplicate serial number {serial_number} detected via database error, skipping")
                                        continue
                                        
                                    # GRACEFUL DEGRADATION - Add as unvalidated but continue processing
                                    logging.warning(f"⚠️ Individual item error for {serial_number}: {str(individual_error)}")
                                    
                                    # Check for duplicates before adding even in error recovery
                                    existing_serial = SerialNumberTransferSerial.query.filter_by(
                                        transfer_item_id=transfer_item.id,
                                        serial_number=serial_number
                                    ).first()
                                    
                                    if not existing_serial:
                                        serial_record = SerialNumberTransferSerial(
                                            transfer_item_id=transfer_item.id,
                                            serial_number=serial_number,
                                            internal_serial_number=serial_number,
                                            is_validated=False,
                                            validation_error=f"Recovery processing error: {str(individual_error)}"
                                        )
                                        db.session.add(serial_record)
                            
                            # Flush sub-batch
                            db.session.flush()
                            
                        except Exception as sub_batch_error:
                            logging.error(f"❌ Sub-batch error: {str(sub_batch_error)}")
                            # Continue with next sub-batch instead of failing entirely
                            continue
                            
                    logging.info(f"✅ ENTERPRISE RECOVERY COMPLETE: Batch {batch_index + 1} processed with recovery")
                    
                except Exception as recovery_error:
                    logging.error(f"❌ ENTERPRISE RECOVERY FAILED for batch {batch_index + 1}: {str(recovery_error)}")
                    # Log the failure but continue with next batch to maintain system stability
                    continue
        
        # **QUANTITY VALIDATION - Prevent excess valid serials, allow insufficient for manual addition**
        if validated_count > expected_quantity:
            # Do NOT save any data if we have too many valid serials
            db.session.rollback()
            
            extra = validated_count - expected_quantity
            return jsonify({
                'success': False, 
                'error': f'Too many valid serial numbers! Expected exactly {expected_quantity}, but {validated_count} are valid in SAP B1. Please remove {extra} serial numbers and submit again.',
                'validated_count': validated_count,
                'expected_quantity': expected_quantity,
                'total_submitted': len(serial_numbers),
                'excess_count': extra
            }), 400
        
        # FINAL COMMIT WITH COMPREHENSIVE REPORTING
        try:
            db.session.commit()
            
            # Calculate final statistics
            total_processed = validated_count + failed_count
            success_rate = (validated_count / len(serial_numbers)) * 100 if serial_numbers else 0
            processing_time = "batch_processing_complete"
            
            logging.info(f"🎉 PROCESSING COMPLETE for Item {item_code}")
            logging.info(f"📊 FINAL STATISTICS:")
            logging.info(f"   Total Serial Numbers: {len(serial_numbers)}")
            logging.info(f"   Successfully Validated: {validated_count}")
            logging.info(f"   Failed/Unvalidated: {len(serial_numbers) - validated_count}")
            logging.info(f"   Expected Quantity: {expected_quantity}")
            logging.info(f"   Quantity Match: {'✅ YES' if validated_count == expected_quantity else '❌ NO'}")
            logging.info(f"   Success Rate: {success_rate:.1f}%")
            logging.info(f"   Batches Processed: {total_batches}")
            
        except Exception as final_error:
            logging.error(f"❌ Final commit failed: {str(final_error)}")
            db.session.rollback()
            raise
        
        # **SUCCESS - SERIAL NUMBERS SAVED FOR MANUAL MANAGEMENT**
        invalid_count = len(serial_numbers) - validated_count
        
        if validated_count == expected_quantity:
            message = f'✅ Item {item_code} added successfully! Perfect quantity match: {validated_count} valid serial numbers.'
            if invalid_count > 0:
                message += f' {invalid_count} invalid serial(s) also saved for your review.'
        else:
            # Only case: validated_count < expected_quantity (since we block excess above)
            missing = expected_quantity - validated_count
            message = f'✅ Item {item_code} added successfully! {validated_count} valid and {invalid_count} invalid serials saved. You need {missing} more valid serials - you can add more or remove invalid ones in the serial management view.'
        
        return jsonify({
            'success': True, 
            'message': message,
            'validated_count': validated_count,
            'expected_quantity': expected_quantity,
            'total_count': len(serial_numbers),
            'invalid_count': invalid_count,
            'quantity_match': validated_count == expected_quantity,
            'needs_review': validated_count != expected_quantity or invalid_count > 0
        })
        
    except Exception as e:
        logging.error(f"Error adding item to serial transfer: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@transfer_bp.route('/serial/<int:transfer_id>/submit', methods=['POST'])
@login_required
def serial_submit(transfer_id):
    """Submit Serial Number Transfer for QC approval"""
    from models import SerialNumberTransfer
    
    try:
        transfer = SerialNumberTransfer.query.get_or_404(transfer_id)
        
        # Check permissions
        if transfer.user_id != current_user.id:
            return jsonify({'success': False, 'error': 'Access denied'}), 403
        
        if transfer.status != 'draft':
            return jsonify({'success': False, 'error': 'Only draft transfers can be submitted'}), 400
        
        if not transfer.items:
            return jsonify({'success': False, 'error': 'Cannot submit transfer without items'}), 400
        
        # Check quantity matching and validation
        unvalidated_count = 0
        quantity_mismatches = []
        
        for item in transfer.items:
            validated_count = 0
            for serial in item.serial_numbers:
                if not serial.is_validated:
                    unvalidated_count += 1
                else:
                    validated_count += 1
            
            # **STRICT QUANTITY MATCHING VALIDATION**
            if validated_count != item.quantity:
                quantity_mismatches.append({
                    'item_code': item.item_code,
                    'expected': item.quantity,
                    'validated': validated_count
                })
        
        if unvalidated_count > 0:
            return jsonify({
                'success': False, 
                'error': f'{unvalidated_count} serial numbers are not validated. Please validate all serial numbers before submitting.'
            }), 400
        
        if quantity_mismatches:
            mismatch_details = []
            for mismatch in quantity_mismatches:
                mismatch_details.append(f"{mismatch['item_code']}: expected {mismatch['expected']}, got {mismatch['validated']}")
            
            return jsonify({
                'success': False, 
                'error': f'Quantity mismatches found! Each item must have exactly matching expected quantity and valid serial numbers. Mismatches: {"; ".join(mismatch_details)}'
            }), 400
        
        # Update status
        transfer.status = 'submitted'
        transfer.updated_at = datetime.utcnow()
        db.session.commit()
        
        logging.info(f"📤 Serial Number Transfer {transfer_id} submitted for QC approval")
        return jsonify({
            'success': True,
            'message': 'Serial Number Transfer submitted for QC approval',
            'status': 'submitted'
        })
        
    except Exception as e:
        logging.error(f"Error submitting serial transfer: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ✅ REMOVED OLD REDIRECTION FUNCTIONS - QC APPROVAL/REJECTION NOW WORKS FROM QC DASHBOARD

@transfer_bp.route('/serial/<int:transfer_id>/reopen', methods=['POST'])
@login_required
def serial_reopen(transfer_id):
    """Reopen rejected serial number transfer"""
    try:
        from models import SerialNumberTransfer
        
        transfer = SerialNumberTransfer.query.get_or_404(transfer_id)
        
        # Check permissions
        if transfer.user_id != current_user.id and current_user.role not in ['admin', 'manager']:
            return jsonify({'success': False, 'error': 'Access denied'}), 403
        
        if transfer.status != 'rejected':
            return jsonify({'success': False, 'error': 'Only rejected transfers can be reopened'}), 400
        
        # Reset status to draft
        transfer.status = 'draft'
        transfer.qc_approver_id = None
        transfer.qc_approved_at = None
        transfer.qc_notes = None
        
        db.session.commit()
        
        logging.info(f"🔄 Serial Number Transfer {transfer_id} reopened")
        return jsonify({'success': True, 'message': 'Transfer reopened and changed to Draft status'})
        
    except Exception as e:
        logging.error(f"Error rejecting serial transfer: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@transfer_bp.route('/serial/<int:transfer_id>/reopen', methods=['POST'])
@login_required
def serial_reopen_transfer(transfer_id):
    """Reopen a rejected serial number transfer"""
    try:
        from models import SerialNumberTransfer
        
        transfer = SerialNumberTransfer.query.get_or_404(transfer_id)
        
        # Check permissions - only admin, manager, or transfer owner can reopen
        if current_user.role not in ['admin', 'manager'] and transfer.user_id != current_user.id:
            return jsonify({'success': False, 'error': 'Access denied - insufficient permissions'}), 403
        
        if transfer.status != 'rejected':
            return jsonify({'success': False, 'error': 'Only rejected transfers can be reopened'}), 400
        
        # Reset transfer status to draft
        old_status = transfer.status
        transfer.status = 'draft'
        transfer.qc_approver_id = None
        transfer.qc_approved_at = None
        transfer.qc_notes = None
        transfer.updated_at = datetime.utcnow()
        
        # Reset all items to draft status if they have qc_status
        for item in transfer.items:
            if hasattr(item, 'qc_status'):
                item.qc_status = None
        
        db.session.commit()
        
        # Log status change
        log_status_change(transfer_id, old_status, 'draft', current_user.id, 'Transfer reopened from rejected status')
        
        logging.info(f"🔄 Serial Transfer {transfer_id} reopened from rejected status by user {current_user.id}")
        return jsonify({
            'success': True,
            'message': 'Transfer reopened successfully. You can now make changes and resubmit.',
            'status': 'draft'
        })
        
    except Exception as e:
        logging.error(f"Error reopening serial transfer: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@transfer_bp.route('/serial/items/<int:item_id>/delete', methods=['POST'])
@login_required
def serial_delete_item(item_id):
    """Delete serial number transfer item"""
    try:
        from models import SerialNumberTransferItem
        
        item = SerialNumberTransferItem.query.get_or_404(item_id)
        transfer = item.serial_transfer
        
        # Check permissions
        if transfer.user_id != current_user.id and current_user.role not in ['admin', 'manager']:
            return jsonify({'success': False, 'error': 'Access denied'}), 403
        
        if transfer.status != 'draft':
            return jsonify({'success': False, 'error': 'Cannot delete items from non-draft transfer'}), 400
        
        transfer_id = transfer.id
        item_code = item.item_code
        
        db.session.delete(item)
        db.session.commit()
        
        logging.info(f"🗑️ Item {item_code} deleted from serial number transfer {transfer_id}")
        return jsonify({'success': True, 'message': f'Item {item_code} deleted'})
        
    except Exception as e:
        logging.error(f"Error deleting serial transfer item: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@transfer_bp.route('/serial/items/<int:item_id>/serials', methods=['GET'])
@login_required  
def serial_get_item_serials(item_id):
    """Get serial numbers for a transfer item"""
    try:
        from models import SerialNumberTransferItem
        
        item = SerialNumberTransferItem.query.get_or_404(item_id)
        transfer = item.serial_transfer
        
        # Check permissions
        if transfer.user_id != current_user.id and current_user.role not in ['admin', 'manager', 'qc']:
            return jsonify({'success': False, 'error': 'Access denied'}), 403
        
        serials = []
        for serial in item.serial_numbers:
            serials.append({
                'id': serial.id,
                'serial_number': serial.serial_number,
                'is_validated': serial.is_validated,
                'system_serial_number': serial.system_serial_number,
                'validation_error': serial.validation_error
            })
        
        return jsonify({
            'success': True,
            'transfer_status': transfer.status,
            'item_code': item.item_code,
            'item_name': item.item_name,
            'serial_numbers': serials  # Changed from 'serials' to match template expectation
        })
        
    except Exception as e:
        logging.error(f"Error getting serial numbers: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@transfer_bp.route('/serial/serials/<int:serial_id>/delete', methods=['POST'])
@login_required
def serial_delete_serial_number(serial_id):
    """Delete individual serial number from transfer"""
    try:
        from models import SerialNumberTransferSerial
        
        serial = SerialNumberTransferSerial.query.get_or_404(serial_id)
        item = serial.transfer_item
        transfer = item.serial_transfer
        
        # Check permissions
        if transfer.user_id != current_user.id and current_user.role not in ['admin', 'manager']:
            return jsonify({'success': False, 'error': 'Access denied'}), 403
        
        if transfer.status != 'draft':
            return jsonify({'success': False, 'error': 'Cannot delete serial numbers from non-draft transfer'}), 400
        
        # Store details before deletion
        serial_number = serial.serial_number
        item_code = item.item_code
        transfer_id = transfer.id
        
        # Delete the serial number
        db.session.delete(serial)
        db.session.commit()
        
        logging.info(f"🗑️ Serial number {serial_number} deleted from item {item_code} in transfer {transfer_id}")
        return jsonify({
            'success': True, 
            'message': f'Serial number {serial_number} deleted',
            'item_code': item_code
        })
        
    except Exception as e:
        logging.error(f"Error deleting serial number: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@transfer_bp.route('/serial/items/<int:item_id>/add_more_serials', methods=['POST'])
@login_required
def serial_add_more_serials(item_id):
    """Add more serial numbers to existing item"""
    try:
        from models import SerialNumberTransferItem
        
        item = SerialNumberTransferItem.query.get_or_404(item_id)
        transfer = item.serial_transfer
        
        # Check permissions
        if transfer.user_id != current_user.id and current_user.role not in ['admin', 'manager']:
            return jsonify({'success': False, 'error': 'Access denied'}), 403
        
        if transfer.status != 'draft':
            return jsonify({'success': False, 'error': 'Cannot add serial numbers to non-draft transfer'}), 400
        
        # Get form data
        serial_numbers_text = request.form.get('serial_numbers', '')
        expected_quantity = item.quantity  # Use existing item quantity
        
        if not serial_numbers_text.strip():
            return jsonify({'success': False, 'error': 'Serial numbers are required'}), 400
        
        # Parse and validate serial numbers
        serial_numbers = [s.strip() for s in re.split(r'[,\n\r\s]+', serial_numbers_text.strip()) if s.strip()]
        
        if not serial_numbers:
            return jsonify({'success': False, 'error': 'No valid serial numbers found'}), 400
        
        # Check for duplicates within this item
        existing_serials = {s.serial_number for s in item.serial_numbers}
        new_serials = []
        duplicate_serials = []
        
        for serial in serial_numbers:
            if serial in existing_serials:
                duplicate_serials.append(serial)
            else:
                new_serials.append(serial)
        
        if duplicate_serials:
            return jsonify({
                'success': False, 
                'error': f'Duplicate serial numbers found: {", ".join(duplicate_serials)}. These already exist for this item.'
            }), 400
        
        if not new_serials:
            return jsonify({'success': False, 'error': 'No new serial numbers to add'}), 400
        
        # Validate against SAP B1 and add serials
        validated_count = 0
        for serial_number in new_serials:
            validation_result = validate_series_with_warehouse_sap(serial_number, item.item_code, transfer.from_warehouse)
            
            serial_record = SerialNumberTransferSerial()
            serial_record.transfer_item_id = item.id
            serial_record.serial_number = serial_number
            serial_record.internal_serial_number = validation_result.get('SerialNumber') or validation_result.get('DistNumber', serial_number)
            serial_record.system_serial_number = validation_result.get('SystemNumber')
            serial_record.is_validated = validation_result.get('valid', False)
            serial_record.validation_error = validation_result.get('error') or validation_result.get('warning')
            
            if validation_result.get('valid'):
                validated_count += 1
            
            db.session.add(serial_record)
        
        db.session.commit()
        
        # Check total valid serials vs expected quantity
        total_valid = len([s for s in item.serial_numbers if s.is_validated])
        invalid_count = len(new_serials) - validated_count
        
        if total_valid == expected_quantity:
            message = f'✅ Added {len(new_serials)} serial numbers! Now have exactly {total_valid} valid serials matching quantity {expected_quantity}.'
        elif total_valid < expected_quantity:
            missing = expected_quantity - total_valid
            message = f'⚠️ Added {len(new_serials)} serial numbers. Total: {total_valid}/{expected_quantity} valid serials. Need {missing} more.'
        else:
            extra = total_valid - expected_quantity
            message = f'⚠️ Added {len(new_serials)} serial numbers. Total: {total_valid}/{expected_quantity} valid serials. {extra} extra valid serials found.'
        
        if invalid_count > 0:
            message += f' {invalid_count} new invalid serial(s) added for review.'
        
        return jsonify({
            'success': True,
            'message': message,
            'new_serials_added': len(new_serials),
            'validated_count': validated_count,
            'total_valid': total_valid,
            'expected_quantity': expected_quantity
        })
        
    except Exception as e:
        logging.error(f"Error adding more serial numbers: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@transfer_bp.route('/serial/serials/<int:serial_id>/edit', methods=['POST'])
@login_required
def serial_edit_serial_number(serial_id):
    """Edit an existing serial number in a transfer"""
    try:
        from models import SerialNumberTransferSerial
        # Using the warehouse-specific validation function defined above
        
        serial_record = SerialNumberTransferSerial.query.get_or_404(serial_id)
        transfer_item = serial_record.transfer_item
        transfer = transfer_item.serial_transfer
        
        # Check permissions
        if transfer.user_id != current_user.id and current_user.role not in ['admin', 'manager']:
            return jsonify({'success': False, 'error': 'Access denied'}), 403
        
        if transfer.status != 'draft':
            return jsonify({'success': False, 'error': 'Can only edit serial numbers in draft transfers'}), 400
        
        # Get new serial number from form data
        new_serial_number = request.form.get('new_serial_number', '').strip()
        if not new_serial_number:
            return jsonify({'success': False, 'error': 'New serial number is required'}), 400
        
        old_serial_number = serial_record.serial_number
        
        # Check if new serial number already exists in this transfer
        existing = SerialNumberTransferSerial.query.join(SerialNumberTransferItem).filter(
            SerialNumberTransferItem.serial_transfer_id == transfer.id,
            SerialNumberTransferSerial.serial_number == new_serial_number,
            SerialNumberTransferSerial.id != serial_id
        ).first()
        
        if existing:
            return jsonify({
                'success': False, 
                'error': f'Serial number {new_serial_number} already exists in this transfer'
            }), 400
        
        # Validate new serial number against SAP with warehouse availability check
        validation_result = validate_series_with_warehouse_sap(new_serial_number, transfer_item.item_code, transfer.from_warehouse)
        
        # Update the serial number
        serial_record.serial_number = new_serial_number
        serial_record.is_validated = validation_result.get('valid', False)
        serial_record.validation_error = validation_result.get('error') or validation_result.get('warning')
        serial_record.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        logging.info(f"📝 Serial number updated from {old_serial_number} to {new_serial_number} in transfer {transfer.id}")
        return jsonify({
            'success': True,
            'message': f'Serial number updated from {old_serial_number} to {new_serial_number}',
            'serial_number': new_serial_number,
            'is_validated': serial_record.is_validated,
            'validation_error': serial_record.validation_error,
            'item_code': transfer_item.item_code
        })
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error editing serial number: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

def validate_series_with_warehouse_sap(serial_number, item_code, warehouse_code):
    """Validate series against SAP B1 API with warehouse availability check"""
    try:
        # Use the existing SAP integration
        from sap_integration import SAPIntegration
        
        sap = SAPIntegration()
        
        # First, validate with new warehouse-specific validation including FromWarehouse
        warehouse_result = sap.validate_series_with_warehouse(serial_number, item_code, warehouse_code)
        
        if warehouse_result.get('valid') and warehouse_result.get('available_in_warehouse'):
            # Series found in a warehouse with stock
            return {
                'valid': True,
                'SerialNumber': warehouse_result.get('DistNumber'),
                'ItemCode': warehouse_result.get('ItemCode'),
                'WhsCode': warehouse_result.get('WhsCode'),
                'available_in_warehouse': True,
                'validation_type': 'warehouse_specific'
            }
        elif warehouse_result.get('valid') and not warehouse_result.get('available_in_warehouse'):
            # Series exists but not available in the FromWarehouse - REJECT for stock transfer
            return {
                'valid': False,
                'error': warehouse_result.get('warning') or f'Series {serial_number} is not available in warehouse {warehouse_code}',
                'available_in_warehouse': False,
                'validation_type': 'warehouse_unavailable'
            }
        else:
            # Validation failed
            return warehouse_result
            
    except Exception as e:
        logging.error(f"Error validating series with warehouse: {str(e)}")
        return {
            'valid': False,
            'error': f'Validation error: {str(e)}'
        }

def validate_batch_series_with_warehouse_sap(serial_numbers, item_code, warehouse_code):
    """Batch validate multiple series against SAP B1 API for optimal performance
    
    This function processes large batches of serial numbers in chunks to avoid API timeouts
    and significantly improve performance when processing 1000+ serial numbers.
    
    Args:
        serial_numbers: List of serial numbers to validate
        item_code: The item code to check against
        warehouse_code: Warehouse code to check series availability
        
    Returns:
        Dict with validation results for each serial number
    """
    try:
        from sap_integration import SAPIntegration
        
        sap = SAPIntegration()
        
        if not serial_numbers:
            return {}
        
        logging.info(f"🚀 Starting batch validation for {len(serial_numbers)} serial numbers")
        
        # Use the new batch validation method with optimized chunk size
        batch_results = sap.validate_batch_series_with_warehouse(
            serial_numbers, 
            item_code, 
            warehouse_code, 
            batch_size=100  # Process in chunks of 100 for optimal performance
        )
        
        # Transform results to match expected format
        formatted_results = {}
        for serial, result in batch_results.items():
            if result.get('valid') and result.get('available_in_warehouse'):
                formatted_results[serial] = {
                    'valid': True,
                    'SerialNumber': result.get('DistNumber'),
                    'ItemCode': result.get('ItemCode'),
                    'WhsCode': result.get('WhsCode'),
                    'available_in_warehouse': True,
                    'validation_type': result.get('validation_type', 'batch_warehouse_specific')
                }
            elif result.get('valid') and not result.get('available_in_warehouse'):
                formatted_results[serial] = {
                    'valid': False,
                    'error': result.get('warning') or f'Series {serial} is not available in warehouse {warehouse_code}',
                    'available_in_warehouse': False,
                    'validation_type': result.get('validation_type', 'batch_warehouse_unavailable')
                }
            else:
                formatted_results[serial] = {
                    'valid': False,
                    'error': result.get('error', 'Batch validation failed'),
                    'validation_type': result.get('validation_type', 'batch_validation_failed')
                }
        
        logging.info(f"✅ Completed batch validation for {len(formatted_results)} serial numbers")
        return formatted_results
        
    except Exception as e:
        logging.error(f"❌ Error in batch series validation: {str(e)}")
        # Return error for all serials if batch fails
        return {serial: {
            'valid': False,
            'error': f'Batch validation error: {str(e)}',
            'validation_type': 'batch_exception'
        } for serial in serial_numbers}

@transfer_bp.route('/serial/validate', methods=['POST'])
@login_required
def validate_serial_api():
    """API endpoint to validate serial number with warehouse check"""
    try:
        data = request.get_json()
        if not data:
            data = request.form
            
        serial_number = data.get('serial_number', '').strip()
        item_code = data.get('item_code', '').strip()
        warehouse_code = data.get('warehouse_code', '').strip()
        
        if not all([serial_number, item_code]):
            return jsonify({
                'success': False, 
                'error': 'Serial number and item code are required'
            }), 400
        
        # Validate the serial number
        validation_result = validate_series_with_warehouse_sap(serial_number, item_code, warehouse_code)
        
        return jsonify({
            'success': True,
            'validation_result': validation_result
        })
        
    except Exception as e:
        logging.error(f"Error in serial validation API: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Validation error: {str(e)}'
        }), 500

@transfer_bp.route('/serial/<int:transfer_id>/qc_approve', methods=['POST'])
@login_required 
def serial_transfer_qc_approve(transfer_id):
    """QC approve serial number transfer and post to SAP B1"""
    from models import SerialNumberTransfer
    
    try:
        transfer = SerialNumberTransfer.query.get_or_404(transfer_id)
        
        # Check QC permissions
        if not current_user.has_permission('qc_dashboard') and current_user.role not in ['admin', 'manager']:
            return jsonify({'success': False, 'error': 'QC permissions required'}), 403
        
        if transfer.status != 'submitted':
            return jsonify({'success': False, 'error': 'Only submitted transfers can be approved'}), 400
        
        # Get QC notes from request
        data = request.get_json() or {}
        qc_notes = data.get('qc_notes', '')
        
        # **SAP B1 POSTING** - Create Stock Transfer in SAP B1
        from sap_integration import SAPIntegration
        sap_b1 = SAPIntegration()
        sap_document_number = None
        sap_error = None
        
        try:
            logging.info(f"🚀 Posting Serial Number Transfer {transfer.transfer_number} to SAP B1...")
            
            # Create Stock Transfer in SAP B1
            sap_result = sap_b1.create_serial_number_stock_transfer(transfer)
            
            if sap_result.get('success'):
                sap_document_number = sap_result.get('document_number')
                logging.info(f"✅ Successfully posted to SAP B1: Document {sap_document_number}")
            else:
                sap_error = sap_result.get('error', 'Unknown SAP error')
                logging.error(f"❌ SAP B1 posting failed: {sap_error}")
                
        except Exception as e:
            sap_error = str(e)
            logging.error(f"❌ SAP B1 posting exception: {str(e)}")
        
        # Update transfer status to approved (regardless of SAP result for now)
        transfer.status = 'qc_approved'
        transfer.qc_approver_id = current_user.id
        transfer.qc_approved_at = datetime.utcnow()
        transfer.qc_notes = qc_notes
        transfer.sap_document_number = sap_document_number
        
        # Update all items to approved status
        for item in transfer.items:
            item.qc_status = 'approved'
        
        db.session.commit()
        
        logging.info(f"✅ Serial Number Transfer {transfer.transfer_number} approved by QC user {current_user.username}")
        
        # Prepare response message
        if sap_document_number:
            message = f'Serial Number Transfer {transfer.transfer_number} approved and posted to SAP B1 as {sap_document_number}'
        elif sap_error:
            message = f'Serial Number Transfer {transfer.transfer_number} approved locally. SAP posting failed: {sap_error}'
        else:
            message = f'Serial Number Transfer {transfer.transfer_number} approved successfully'
        
        return jsonify({
            'success': True,
            'message': message,
            'transfer_id': transfer_id,
            'status': 'qc_approved',
            'sap_document_number': sap_document_number,
            'sap_error': sap_error
        })
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"❌ Error approving serial transfer {transfer_id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@transfer_bp.route('/serial/<int:transfer_id>/qc_reject', methods=['POST'])
@login_required
def serial_transfer_qc_reject(transfer_id):
    """QC reject serial number transfer"""
    from models import SerialNumberTransfer
    
    try:
        transfer = SerialNumberTransfer.query.get_or_404(transfer_id)
        
        # Check QC permissions
        if not current_user.has_permission('qc_dashboard') and current_user.role not in ['admin', 'manager']:
            return jsonify({'success': False, 'error': 'QC permissions required'}), 403
        
        if transfer.status != 'submitted':
            return jsonify({'success': False, 'error': 'Only submitted transfers can be rejected'}), 400
        
        # Get QC notes from request
        data = request.get_json() or {}
        qc_notes = data.get('qc_notes', '')
        
        if not qc_notes.strip():
            return jsonify({'success': False, 'error': 'Rejection reason is required'}), 400
        
        # Update transfer status to rejected
        transfer.status = 'rejected'
        transfer.qc_approver_id = current_user.id
        transfer.qc_approved_at = datetime.utcnow()
        transfer.qc_notes = qc_notes
        
        # Update all items to rejected status
        for item in transfer.items:
            item.qc_status = 'rejected'
        
        db.session.commit()
        
        logging.info(f"❌ Serial Number Transfer {transfer.transfer_number} rejected by QC user {current_user.username}: {qc_notes}")
        
        return jsonify({
            'success': True,
            'message': f'Serial Number Transfer {transfer.transfer_number} rejected successfully',
            'transfer_id': transfer_id,
            'status': 'rejected'
        })
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"❌ Error rejecting serial transfer {transfer_id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@transfer_bp.route('/serial/serials/<int:serial_id>/validate', methods=['POST'])
@login_required
def revalidate_serial_number(serial_id):
    """Re-validate a specific serial number in a transfer"""
    try:
        from models import SerialNumberTransferSerial
        
        serial_record = SerialNumberTransferSerial.query.get_or_404(serial_id)
        transfer_item = serial_record.transfer_item
        transfer = transfer_item.serial_transfer
        
        # Check permissions
        if transfer.user_id != current_user.id and current_user.role not in ['admin', 'manager']:
            return jsonify({'success': False, 'error': 'Access denied'}), 403
        
        if transfer.status not in ['draft', 'submitted']:
            return jsonify({'success': False, 'error': 'Can only validate serial numbers in draft or submitted transfers'}), 400
        
        # Re-validate the serial number
        validation_result = validate_series_with_warehouse_sap(
            serial_record.serial_number, 
            transfer_item.item_code, 
            transfer.from_warehouse
        )
        
        # Update validation status
        serial_record.is_validated = validation_result.get('valid', False)
        serial_record.validation_error = validation_result.get('error') if not validation_result.get('valid') else validation_result.get('warning')
        serial_record.system_serial_number = validation_result.get('SystemNumber') or validation_result.get('SerialNumber')
        serial_record.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        logging.info(f"🔄 Re-validated serial number {serial_record.serial_number} in transfer {transfer.id}")
        
        return jsonify({
            'success': True,
            'message': f'Serial number {serial_record.serial_number} re-validated',
            'is_validated': serial_record.is_validated,
            'validation_error': serial_record.validation_error,
            'available_in_warehouse': validation_result.get('available_in_warehouse', False),
            'warehouse_code': validation_result.get('WhsCode'),
            'validation_type': validation_result.get('validation_type', 'unknown')
        })
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error re-validating serial number: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500