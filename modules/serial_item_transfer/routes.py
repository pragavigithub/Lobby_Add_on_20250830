from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime
import logging
import json
import re

from app import db
from models import SerialItemTransfer, SerialItemTransferItem, DocumentNumberSeries
from sap_integration import SAPIntegration
from sqlalchemy import or_

# Create blueprint for Serial Item Transfer module
serial_item_bp = Blueprint('serial_item_transfer', __name__, url_prefix='/serial-item-transfer')


def generate_serial_item_transfer_number():
    """Generate unique transfer number for Serial Item Transfer"""
    return DocumentNumberSeries.get_next_number('SERIAL_ITEM_TRANSFER')


@serial_item_bp.route('/', methods=['GET'])
@login_required
def index():
    """Serial Item Transfer main page with pagination and user filtering"""
    if not current_user.has_permission('serial_item_transfer'):
        flash('Access denied - Serial Item Transfer permissions required', 'error')
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
    query = SerialItemTransfer.query

    # Apply user-based filtering
    if user_based == 'true' or current_user.role not in ['admin', 'manager']:
        # Show only current user's transfers (or force for non-admin users)
        query = query.filter_by(user_id=current_user.id)

    # Apply search filter if provided
    if search:
        search_filter = f"%{search}%"
        query = query.filter(
            or_(
                SerialItemTransfer.transfer_number.ilike(search_filter),
                SerialItemTransfer.from_warehouse.ilike(search_filter),
                SerialItemTransfer.to_warehouse.ilike(search_filter),
                SerialItemTransfer.status.ilike(search_filter)
            )
        )

    # Order and paginate
    query = query.order_by(SerialItemTransfer.created_at.desc())
    transfers_paginated = query.paginate(
        page=page, per_page=per_page, error_out=False
    )

    return render_template('serial_item_transfer/index.html',
                           transfers=transfers_paginated.items,
                           pagination=transfers_paginated,
                           search=search,
                           per_page=per_page,
                           user_based=user_based,
                           current_user=current_user)


@serial_item_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    """Create new Serial Item Transfer"""
    if not current_user.has_permission('serial_item_transfer'):
        flash('Access denied - Serial Item Transfer permissions required', 'error')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        # Auto-generate transfer number
        transfer_number = generate_serial_item_transfer_number()
        from_warehouse = request.form.get('from_warehouse')
        to_warehouse = request.form.get('to_warehouse')
        priority = request.form.get('priority', 'normal')
        notes = request.form.get('notes', '')

        if not all([from_warehouse, to_warehouse]):
            flash('From Warehouse and To Warehouse are required', 'error')
            return render_template('serial_item_transfer/create.html')

        if from_warehouse == to_warehouse:
            flash('From Warehouse and To Warehouse must be different', 'error')
            return render_template('serial_item_transfer/create.html')

        # Create new Serial Item Transfer
        transfer = SerialItemTransfer(
            transfer_number=transfer_number,
            user_id=current_user.id,
            from_warehouse=from_warehouse,
            to_warehouse=to_warehouse,
            priority=priority,
            notes=notes,
            status='draft'
        )

        db.session.add(transfer)
        db.session.commit()

        flash(f'Serial Item Transfer {transfer_number} created successfully', 'success')
        return redirect(url_for('serial_item_transfer.detail', transfer_id=transfer.id))

    return render_template('serial_item_transfer/create.html')


@serial_item_bp.route('/<int:transfer_id>', methods=['GET'])
@login_required
def detail(transfer_id):
    """Serial Item Transfer detail page"""
    transfer = SerialItemTransfer.query.get_or_404(transfer_id)

    # Check permissions
    if transfer.user_id != current_user.id and current_user.role not in ['admin', 'manager', 'qc']:
        flash('Access denied - You can only view your own transfers', 'error')
        return redirect(url_for('serial_item_transfer.index'))

    return render_template('serial_item_transfer/detail.html', transfer=transfer)


@serial_item_bp.route('/<int:transfer_id>/add_serial_item', methods=['POST'])
@login_required
def add_serial_item(transfer_id):
    """Add serial item to Serial Item Transfer with real-time SAP B1 validation"""

    try:
        transfer = SerialItemTransfer.query.get_or_404(transfer_id)

        # Check permissions
        if transfer.user_id != current_user.id and current_user.role not in ['admin', 'manager']:
            return jsonify({'success': False, 'error': 'Access denied'}), 403

        if transfer.status != 'draft':
            return jsonify({'success': False, 'error': 'Cannot add items to non-draft transfer'}), 400

        # Get form data
        serial_number = request.form.get('serial_number', '').strip()

        if not serial_number:
            return jsonify({'success': False, 'error': 'Serial number is required'}), 400

        # Check for duplicate serial number in this transfer
        existing_item = SerialItemTransferItem.query.filter_by(
            serial_item_transfer_id=transfer.id,
            serial_number=serial_number
        ).first()

        if existing_item:
            return jsonify({
                'success': False,
                'error': f'Serial number {serial_number} already exists in this transfer',
                'duplicate': True
            }), 400

        # Validate serial number with SAP B1
        sap = SAPIntegration()
        validation_result = sap.validate_serial_item_for_transfer(serial_number, transfer.from_warehouse)

        logging.info(f"🔍 SAP B1 validation result for {serial_number}: {validation_result}")

        # Always create line item immediately - even for failed validation
        if not validation_result.get('valid'):
            # Create item with failed validation status
            # transfer_item = SerialItemTransferItem(
            #     serial_item_transfer_id=transfer.id,
            #     serial_number=serial_number,
            #     item_code='UNKNOWN',
            #     item_description='Validation Failed',
            #     warehouse_code=transfer.from_warehouse,
            #     from_warehouse_code=transfer.from_warehouse,
            #     to_warehouse_code=transfer.to_warehouse,
            #     validation_status='failed',
            #     validation_error=validation_result.get('error', 'Unknown validation error')
            # )
            #
            # db.session.add(transfer_item)
            # db.session.commit()

            # Return item details for live table update
            return jsonify({
                'success': False,
                'error': validation_result.get('error',
                                               'Serial number validation failed - invalid serial numbers are not added to the transfer'),
                'item_added': False,
                'validation_status': 'rejected'
            }), 400

        # Create transfer item with validated data
        transfer_item = SerialItemTransferItem(
            serial_item_transfer_id=transfer.id,
            serial_number=serial_number,
            item_code=validation_result.get('item_code', ''),
            item_description=validation_result.get('item_description', ''),
            warehouse_code=validation_result.get('warehouse_code', transfer.from_warehouse),
            from_warehouse_code=transfer.from_warehouse,
            to_warehouse_code=transfer.to_warehouse,
            quantity=1,  # Always 1 for serial items
            validation_status='validated',
            validation_error=None
        )

        db.session.add(transfer_item)
        db.session.commit()

        logging.info(f"✅ Serial item {serial_number} added to transfer {transfer_id}")

        # Return complete item data for live table update
        return jsonify({
            'success': True,
            'message': f'Serial number {serial_number} added successfully',
            'item_added': True,
            'validation_status': 'validated',
            'item_data': {
                'id': transfer_item.id,
                'serial_number': transfer_item.serial_number,
                'item_code': transfer_item.item_code,
                'item_description': transfer_item.item_description,
                'from_warehouse_code': transfer_item.from_warehouse_code,
                'to_warehouse_code': transfer_item.to_warehouse_code,
                'validation_status': transfer_item.validation_status,
                'validation_error': transfer_item.validation_error,
                'quantity': transfer_item.quantity,
                'line_number': len(transfer.items)
            }
        })

    except Exception as e:
        logging.error(f"Error adding serial item: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@serial_item_bp.route('/items/<int:item_id>/delete', methods=['POST'])
@login_required
def delete_item(item_id):
    """Delete serial item transfer item"""
    try:
        item = SerialItemTransferItem.query.get_or_404(item_id)
        transfer = item.serial_item_transfer

        # Check permissions
        if transfer.user_id != current_user.id and current_user.role not in ['admin', 'manager']:
            return jsonify({'success': False, 'error': 'Access denied'}), 403

        if transfer.status != 'draft':
            return jsonify({'success': False, 'error': 'Cannot delete items from non-draft transfer'}), 400

        transfer_id = transfer.id
        serial_number = item.serial_number

        db.session.delete(item)
        db.session.commit()

        logging.info(f"🗑️ Serial item {serial_number} deleted from transfer {transfer_id}")
        return jsonify({'success': True, 'message': f'Serial item {serial_number} deleted'})

    except Exception as e:
        logging.error(f"Error deleting serial item: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@serial_item_bp.route('/<int:transfer_id>/submit', methods=['POST'])
@login_required
def submit_transfer(transfer_id):
    """Submit Serial Item Transfer for QC approval"""
    try:
        transfer = SerialItemTransfer.query.get_or_404(transfer_id)

        # Check permissions
        if transfer.user_id != current_user.id and current_user.role not in ['admin', 'manager']:
            return jsonify({'success': False, 'error': 'Access denied'}), 403

        if transfer.status != 'draft':
            return jsonify({'success': False, 'error': 'Only draft transfers can be submitted'}), 400

        # Check if transfer has items
        if not transfer.items:
            return jsonify({'success': False, 'error': 'Cannot submit transfer without items'}), 400

        # Check if all items are validated
        failed_items = [item for item in transfer.items if item.validation_status == 'failed']
        if failed_items:
            return jsonify({
                'success': False,
                'error': f'Cannot submit transfer with {len(failed_items)} failed validation items'
            }), 400

        # Update status
        transfer.status = 'submitted'
        transfer.updated_at = datetime.utcnow()

        db.session.commit()

        logging.info(f"📤 Serial Item Transfer {transfer_id} submitted for QC approval")
        return jsonify({'success': True, 'message': 'Transfer submitted for QC approval'})

    except Exception as e:
        logging.error(f"Error submitting transfer: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@serial_item_bp.route('/items/<int:item_id>/revalidate', methods=['POST'])
@login_required
def revalidate_item(item_id):
    """Re-validate a failed serial item against SAP B1"""
    try:
        item = SerialItemTransferItem.query.get_or_404(item_id)
        transfer = item.serial_item_transfer

        # Check permissions
        if transfer.user_id != current_user.id and current_user.role not in ['admin', 'manager']:
            return jsonify({'success': False, 'error': 'Access denied'}), 403

        if transfer.status != 'draft':
            return jsonify({'success': False, 'error': 'Cannot revalidate items in non-draft transfer'}), 400

        # Validate serial number with SAP B1
        sap = SAPIntegration()
        validation_result = sap.validate_serial_item_for_transfer(item.serial_number, transfer.from_warehouse)

        if validation_result.get('valid'):
            # Update item with validated data
            item.item_code = validation_result.get('item_code', '')
            item.item_description = validation_result.get('item_description', '')
            item.warehouse_code = validation_result.get('warehouse_code', transfer.from_warehouse)
            item.validation_status = 'validated'
            item.validation_error = None
            item.updated_at = datetime.utcnow()

            db.session.commit()

            return jsonify({
                'success': True,
                'message': f'Serial number {item.serial_number} revalidated successfully',
                'item_code': item.item_code,
                'item_description': item.item_description
            })
        else:
            # Update validation error
            item.validation_error = validation_result.get('error', 'Unknown validation error')
            item.updated_at = datetime.utcnow()

            db.session.commit()

            return jsonify({
                'success': False,
                'error': validation_result.get('error', 'Serial number validation failed')
            })

    except Exception as e:
        logging.error(f"Error revalidating serial item: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@serial_item_bp.route('/<int:transfer_id>/approve', methods=['POST'])
@login_required
def approve_transfer(transfer_id):
    """Approve Serial Item Transfer for QC"""
    try:
        transfer = SerialItemTransfer.query.get_or_404(transfer_id)

        # Check QC permissions
        if not current_user.has_permission('qc_dashboard') and current_user.role not in ['admin', 'manager']:
            flash('Access denied - QC permissions required', 'error')
            return redirect(url_for('qc_dashboard'))

        if transfer.status != 'submitted':
            flash('Only submitted transfers can be approved', 'error')
            return redirect(url_for('qc_dashboard'))

        # Get QC notes
        qc_notes = request.form.get('qc_notes', '').strip()

        # Update transfer status
        transfer.status = 'qc_approved'
        transfer.qc_approver_id = current_user.id
        transfer.qc_approved_at = datetime.utcnow()
        transfer.qc_notes = qc_notes
        transfer.updated_at = datetime.utcnow()

        # Update all items to approved status
        for item in transfer.items:
            item.qc_status = 'approved'
            item.updated_at = datetime.utcnow()

        db.session.commit()

        logging.info(f"✅ Serial Item Transfer {transfer_id} approved by {current_user.username}")
        flash(f'Serial Item Transfer {transfer.transfer_number} approved successfully!', 'success')

        # Try to post to SAP B1 (optional - based on your business process)
        try:
            sap = SAPIntegration()
            if sap.ensure_logged_in():
                # Add SAP posting logic here if needed
                logging.info(f"📤 Serial Item Transfer {transfer_id} ready for SAP posting")
        except Exception as e:
            logging.warning(f"SAP posting preparation failed: {str(e)}")

        return redirect(url_for('qc_dashboard'))

    except Exception as e:
        logging.error(f"Error approving serial item transfer: {str(e)}")
        db.session.rollback()
        flash('Error approving transfer', 'error')
        return redirect(url_for('qc_dashboard'))


@serial_item_bp.route('/<int:transfer_id>/reject', methods=['POST'])
@login_required
def reject_transfer(transfer_id):
    """Reject Serial Item Transfer for QC"""
    try:
        transfer = SerialItemTransfer.query.get_or_404(transfer_id)

        # Check QC permissions
        if not current_user.has_permission('qc_dashboard') and current_user.role not in ['admin', 'manager']:
            flash('Access denied - QC permissions required', 'error')
            return redirect(url_for('qc_dashboard'))

        if transfer.status != 'submitted':
            flash('Only submitted transfers can be rejected', 'error')
            return redirect(url_for('qc_dashboard'))

        # Get rejection reason (required)
        qc_notes = request.form.get('qc_notes', '').strip()
        if not qc_notes:
            flash('Rejection reason is required', 'error')
            return redirect(url_for('qc_dashboard'))

        # Update transfer status
        transfer.status = 'rejected'
        transfer.qc_approver_id = current_user.id
        transfer.qc_approved_at = datetime.utcnow()
        transfer.qc_notes = qc_notes
        transfer.updated_at = datetime.utcnow()

        # Update all items to rejected status
        for item in transfer.items:
            item.qc_status = 'rejected'
            item.updated_at = datetime.utcnow()

        db.session.commit()

        logging.info(f"❌ Serial Item Transfer {transfer_id} rejected by {current_user.username}")
        flash(f'Serial Item Transfer {transfer.transfer_number} rejected.', 'warning')
        return redirect(url_for('qc_dashboard'))

    except Exception as e:
        logging.error(f"Error rejecting serial item transfer: {str(e)}")
        db.session.rollback()
        flash('Error rejecting transfer', 'error')
        return redirect(url_for('qc_dashboard'))


@serial_item_bp.route('/<int:transfer_id>/validate_serial_only', methods=['POST'])
@login_required
def validate_serial_only(transfer_id):
    """Validate serial number without adding to transfer (for line-by-line validation)"""
    try:
        transfer = SerialItemTransfer.query.get_or_404(transfer_id)

        # Check permissions
        if transfer.user_id != current_user.id and current_user.role not in ['admin', 'manager']:
            return jsonify({'success': False, 'error': 'Access denied'}), 403

        if transfer.status != 'draft':
            return jsonify({'success': False, 'error': 'Cannot validate items for non-draft transfer'}), 400

        # Get form data
        serial_number = request.form.get('serial_number', '').strip()

        if not serial_number:
            return jsonify({'success': False, 'error': 'Serial number is required'}), 400

        # Check for duplicate serial number in this transfer
        existing_item = SerialItemTransferItem.query.filter_by(
            serial_item_transfer_id=transfer.id,
            serial_number=serial_number
        ).first()

        if existing_item:
            return jsonify({
                'success': False,
                'error': f'Serial number {serial_number} already exists in this transfer'
            }), 400

        # Validate serial number with SAP B1
        sap = SAPIntegration()
        validation_result = sap.validate_serial_item_for_transfer(serial_number, transfer.from_warehouse)

        logging.info(f"🔍 SAP B1 validation result for {serial_number}: {validation_result}")

        if not validation_result.get('valid'):
            return jsonify({
                'success': False,
                'error': validation_result.get('error', 'Serial number validation failed')
            }), 400

        # Return validation success without adding to database
        return jsonify({
            'success': True,
            'message': f'Serial number {serial_number} validated successfully',
            'item_code': validation_result.get('item_code'),
            'item_description': validation_result.get('item_description'),
            'warehouse_code': validation_result.get('warehouse_code')
        })

    except Exception as e:
        logging.error(f"Error validating serial item: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@serial_item_bp.route('/<int:transfer_id>/add_multiple_serials', methods=['POST'])
@login_required
def add_multiple_serials(transfer_id):
    """Add multiple validated serial items to transfer"""
    try:
        transfer = SerialItemTransfer.query.get_or_404(transfer_id)

        # Check permissions
        if transfer.user_id != current_user.id and current_user.role not in ['admin', 'manager']:
            return jsonify({'success': False, 'error': 'Access denied'}), 403

        if transfer.status != 'draft':
            return jsonify({'success': False, 'error': 'Cannot add items to non-draft transfer'}), 400

        # Get validated serials data
        validated_serials_json = request.form.get('validated_serials', '[]')

        try:
            validated_serials = json.loads(validated_serials_json)
        except json.JSONDecodeError:
            return jsonify({'success': False, 'error': 'Invalid validated serials data'}), 400

        if not validated_serials:
            return jsonify({'success': False, 'error': 'No validated serials provided'}), 400

        items_added = 0
        failed_items = []

        for serial_data in validated_serials:
            try:
                serial_number = serial_data.get('serial_number', '').strip()

                if not serial_number:
                    failed_items.append({'serial': serial_number, 'error': 'Empty serial number'})
                    continue

                # Check for duplicate
                existing_item = SerialItemTransferItem.query.filter_by(
                    serial_item_transfer_id=transfer.id,
                    serial_number=serial_number
                ).first()

                if existing_item:
                    failed_items.append({'serial': serial_number, 'error': 'Already exists in transfer'})
                    continue

                # Create transfer item
                transfer_item = SerialItemTransferItem(
                    serial_item_transfer_id=transfer.id,
                    serial_number=serial_number,
                    item_code=serial_data.get('item_code', ''),
                    item_description=serial_data.get('item_description', ''),
                    warehouse_code=serial_data.get('warehouse_code', transfer.from_warehouse),
                    from_warehouse_code=transfer.from_warehouse,
                    to_warehouse_code=transfer.to_warehouse,
                    quantity=1,  # Always 1 for serial items
                    validation_status='validated',
                    validation_error=None
                )

                db.session.add(transfer_item)
                items_added += 1

            except Exception as e:
                failed_items.append({'serial': serial_data.get('serial_number', 'Unknown'), 'error': str(e)})

        db.session.commit()

        logging.info(f"✅ Added {items_added} serial items to transfer {transfer_id}")

        if failed_items:
            return jsonify({
                'success': True,
                'message': f'{items_added} items added successfully, {len(failed_items)} failed',
                'items_added': items_added,
                'failed_items': failed_items
            })
        else:
            return jsonify({
                'success': True,
                'message': f'{items_added} serial items added successfully',
                'items_added': items_added
            })

    except Exception as e:
        logging.error(f"Error adding multiple serial items: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@serial_item_bp.route('/<int:transfer_id>/post_to_sap', methods=['POST'])
@login_required
def post_to_sap(transfer_id):
    """Post approved Serial Item Transfer to SAP B1 as Stock Transfer"""
    try:
        transfer = SerialItemTransfer.query.get_or_404(transfer_id)

        # Check QC permissions
        if not current_user.has_permission('qc_dashboard') and current_user.role not in ['admin', 'manager']:
            return jsonify({'success': False, 'error': 'Access denied - QC permissions required'}), 403

        if transfer.status != 'qc_approved':
            return jsonify({'success': False, 'error': 'Only QC approved transfers can be posted to SAP'}), 400

        # Build SAP B1 Stock Transfer JSON
        sap_transfer_data = {
            "DocDate": datetime.now().strftime('%Y-%m-%d'),
            "DueDate": datetime.now().strftime('%Y-%m-%d'),
            "CardCode": "",
            "CardName": "",
            "Address": "",
            "U_EA_CREATEDBy": current_user.username,
            "U_EA_Approved": current_user.username,
            "Comments": f"Serial Number Item Transfer from WMS - {current_user.username}",
            "JournalMemo": f"Serial Number Item Transfer - {transfer.transfer_number}",
            "PriceList": -1,
            "SalesPersonCode": -1,
            "FromWarehouse": transfer.from_warehouse,
            "ToWarehouse": transfer.to_warehouse,
            "AuthorizationStatus": "sasWithout",
            "StockTransferLines": []
        }

        # Group items by ItemCode for line consolidation
        item_groups = {}
        for item in transfer.items:
            if item.qc_status == 'approved' and item.validation_status == 'validated':
                if item.item_code not in item_groups:
                    item_groups[item.item_code] = {
                        'item_code': item.item_code,
                        'item_description': item.item_description,
                        'serials': [],
                        'quantity': 0
                    }

                item_groups[item.item_code]['serials'].append({
                    "SystemSerialNumber": 0,
                    "InternalSerialNumber": item.serial_number,
                    "ManufacturerSerialNumber": item.serial_number,
                    "ExpiryDate": None,
                    "ManufactureDate": None,
                    "ReceptionDate": None,
                    "WarrantyStart": None,
                    "WarrantyEnd": None,
                    "Location": None,
                    "Notes": None
                })
                item_groups[item.item_code]['quantity'] += 1

        # Create stock transfer lines
        line_num = 0
        for item_code, group_data in item_groups.items():
            sap_transfer_data["StockTransferLines"].append({
                "LineNum": line_num,
                "ItemCode": item_code,
                "Quantity": group_data['quantity'],
                "WarehouseCode": transfer.to_warehouse,
                "FromWarehouseCode": transfer.from_warehouse,
                "UoMCode": "",
                "SerialNumbers": group_data['serials']
            })
            line_num += 1

        # Post to SAP B1
        sap = SAPIntegration()
        if not sap.ensure_logged_in():
            return jsonify({'success': False, 'error': 'SAP B1 connection failed'}), 500

        # Post directly to SAP B1 StockTransfers endpoint
        try:
            url = f"{sap.base_url}/b1s/v1/StockTransfers"
            response = sap.session.post(url, json=sap_transfer_data, timeout=30)

            if response.status_code == 201:
                sap_doc = response.json()
                sap_result = {
                    'success': True,
                    'document_number': sap_doc.get('DocNum'),
                    'doc_entry': sap_doc.get('DocEntry')
                }
            else:
                error_text = response.text
                logging.error(f"SAP B1 API error: {response.status_code} - {error_text}")
                sap_result = {
                    'success': False,
                    'error': f'SAP B1 API error: {response.status_code} - {error_text}'
                }
        except Exception as api_error:
            logging.error(f"SAP B1 connection error: {str(api_error)}")
            sap_result = {
                'success': False,
                'error': f'SAP B1 connection error: {str(api_error)}'
            }

        if sap_result.get('success'):
            # Update transfer status and SAP document info
            transfer.status = 'posted'
            transfer.sap_document_number = sap_result.get('document_number')
            transfer.updated_at = datetime.utcnow()

            db.session.commit()

            logging.info(f"📤 Serial Item Transfer {transfer_id} posted to SAP B1: {sap_result.get('document_number')}")
            return jsonify({
                'success': True,
                'message': f'Transfer posted to SAP B1 successfully. Document Number: {sap_result.get("document_number")}',
                'sap_document_number': sap_result.get('document_number'),
                'doc_entry': sap_result.get('doc_entry'),
                'status': 'posted'
            })
        else:
            # Reject document and send back for editing when SAP posting fails
            transfer.status = 'rejected'
            transfer.qc_notes = f"SAP B1 posting failed: {sap_result.get('error', 'Unknown error')}. Document rejected for editing."
            transfer.updated_at = datetime.utcnow()
            
            # Reset QC approval to allow re-editing
            for item in transfer.items:
                item.qc_status = 'pending'
                item.updated_at = datetime.utcnow()
            
            db.session.commit()
            
            logging.error(f"SAP B1 posting failed for transfer {transfer_id}: {sap_result.get('error')} - Document rejected for editing")
            return jsonify({
                'success': False,
                'error': f'SAP B1 posting failed: {sap_result.get("error", "Unknown error")}. Document has been rejected and sent back for editing.',
                'status': 'rejected',
                'redirect_to_edit': True
            }), 500

    except Exception as e:
        logging.error(f"Error posting serial item transfer to SAP: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
