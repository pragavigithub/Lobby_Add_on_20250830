"""
GRPO (Goods Receipt PO) Routes
All routes related to goods receipt against purchase orders
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app import db
from modules.grpo.models import GRPODocument, GRPOItem
from modules.shared.models import User
import logging
from datetime import datetime

grpo_bp = Blueprint('grpo', __name__, url_prefix='/grpo')

@grpo_bp.route('/')
@login_required
def index():
    """GRPO main page - list all GRPOs for current user"""
    if not current_user.has_permission('grpo'):
        flash('Access denied - GRPO permissions required', 'error')
        return redirect(url_for('dashboard'))
    
    grpos = GRPODocument.query.filter_by(user_id=current_user.id).order_by(GRPODocument.created_at.desc()).all()
    return render_template('grpo/grpo.html', grpos=grpos)

@grpo_bp.route('/detail/<int:grpo_id>')
@login_required
def detail(grpo_id):
    """GRPO detail page"""
    grpo = GRPODocument.query.get_or_404(grpo_id)
    
    # Check permissions
    if grpo.user_id != current_user.id and current_user.role not in ['admin', 'manager', 'qc']:
        flash('Access denied - You can only view your own GRPOs', 'error')
        return redirect(url_for('grpo.index'))
    
    return render_template('grpo/grpo_detail.html', grpo=grpo)

@grpo_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    """Create new GRPO"""
    if not current_user.has_permission('grpo'):
        flash('Access denied - GRPO permissions required', 'error')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        po_number = request.form.get('po_number')
        
        if not po_number:
            flash('PO number is required', 'error')
            return redirect(url_for('grpo.create'))
        
        # Check if GRPO already exists for this PO
        existing_grpo = GRPODocument.query.filter_by(po_number=po_number, user_id=current_user.id).first()
        if existing_grpo:
            flash(f'GRPO already exists for PO {po_number}', 'warning')
            return redirect(url_for('grpo.detail', grpo_id=existing_grpo.id))
        
        # Create new GRPO
        grpo = GRPODocument(
            po_number=po_number,
            user_id=current_user.id,
            status='draft'
        )
        
        db.session.add(grpo)
        db.session.commit()
        
        logging.info(f"✅ GRPO created for PO {po_number} by user {current_user.username}")
        flash(f'GRPO created for PO {po_number}', 'success')
        return redirect(url_for('grpo.detail', grpo_id=grpo.id))
    
    return render_template('grpo/create_grpo.html')

@grpo_bp.route('/<int:grpo_id>/submit', methods=['POST'])
@login_required
def submit(grpo_id):
    """Submit GRPO for QC approval"""
    try:
        grpo = GRPODocument.query.get_or_404(grpo_id)
        
        # Check permissions
        if grpo.user_id != current_user.id:
            return jsonify({'success': False, 'error': 'Access denied'}), 403
        
        if grpo.status != 'draft':
            return jsonify({'success': False, 'error': 'Only draft GRPOs can be submitted'}), 400
        
        if not grpo.items:
            return jsonify({'success': False, 'error': 'Cannot submit GRPO without items'}), 400
        
        # Update status
        grpo.status = 'submitted'
        grpo.updated_at = datetime.utcnow()
        db.session.commit()
        
        logging.info(f"📤 GRPO {grpo_id} submitted for QC approval")
        return jsonify({
            'success': True,
            'message': 'GRPO submitted for QC approval',
            'status': 'submitted'
        })
        
    except Exception as e:
        logging.error(f"Error submitting GRPO: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@grpo_bp.route('/<int:grpo_id>/approve', methods=['POST'])
@login_required
def approve(grpo_id):
    """QC approve GRPO and post to SAP B1"""
    try:
        grpo = GRPODocument.query.get_or_404(grpo_id)
        
        # Check QC permissions
        if not current_user.has_permission('qc_dashboard') and current_user.role not in ['admin', 'manager']:
            return jsonify({'success': False, 'error': 'QC permissions required'}), 403
        
        if grpo.status != 'submitted':
            return jsonify({'success': False, 'error': 'Only submitted GRPOs can be approved'}), 400
        
        # Get QC notes
        qc_notes = ''
        if request.form:
            qc_notes = request.form.get('qc_notes', '')
        elif request.json:
            qc_notes = request.json.get('qc_notes', '')
        
        # Mark items as approved
        for item in grpo.items:
            item.qc_status = 'approved'
        
        # Update GRPO status
        grpo.status = 'qc_approved'
        grpo.qc_approver_id = current_user.id
        grpo.qc_approved_at = datetime.utcnow()
        grpo.qc_notes = qc_notes
        
        # Initialize SAP integration and post to SAP B1
        from sap_integration import SAPIntegration
        sap = SAPIntegration()
        
        # Log the posting attempt
        logging.info(f"🚀 Attempting to post GRPO {grpo_id} to SAP B1...")
        logging.info(f"GRPO Items: {len(grpo.items)} items, QC Approved: {len([i for i in grpo.items if i.qc_status == 'approved'])}")
        
        # Post GRPO to SAP B1 as Purchase Delivery Note
        sap_result = sap.post_grpo_to_sap(grpo)
        
        # Log the result
        logging.info(f"📡 SAP B1 posting result: {sap_result}")
        
        if sap_result.get('success'):
            grpo.sap_document_number = sap_result.get('sap_document_number')
            grpo.status = 'posted'
            db.session.commit()
            
            logging.info(f"✅ GRPO {grpo_id} QC approved and posted to SAP B1 as {grpo.sap_document_number}")
            return jsonify({
                'success': True,
                'message': f'GRPO approved and posted to SAP B1 as {grpo.sap_document_number}',
                'sap_document_number': grpo.sap_document_number
            })
        else:
            # If SAP posting fails, still mark as QC approved but not posted
            db.session.commit()
            error_msg = sap_result.get('error', 'Unknown SAP error')
            
            logging.warning(f"⚠️ GRPO {grpo_id} QC approved but SAP posting failed: {error_msg}")
            return jsonify({
                'success': False,
                'error': f'GRPO approved but SAP posting failed: {error_msg}',
                'status': 'qc_approved'
            })
        
    except Exception as e:
        logging.error(f"Error approving GRPO: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@grpo_bp.route('/<int:grpo_id>/reject', methods=['POST'])
@login_required
def reject(grpo_id):
    """QC reject GRPO"""
    try:
        grpo = GRPODocument.query.get_or_404(grpo_id)
        
        # Check QC permissions
        if not current_user.has_permission('qc_dashboard') and current_user.role not in ['admin', 'manager']:
            return jsonify({'success': False, 'error': 'QC permissions required'}), 403
        
        if grpo.status != 'submitted':
            return jsonify({'success': False, 'error': 'Only submitted GRPOs can be rejected'}), 400
        
        # Get rejection reason
        qc_notes = ''
        if request.form:
            qc_notes = request.form.get('qc_notes', '')
        elif request.json:
            qc_notes = request.json.get('qc_notes', '')
        
        if not qc_notes:
            return jsonify({'success': False, 'error': 'Rejection reason is required'}), 400
        
        # Mark items as rejected
        for item in grpo.items:
            item.qc_status = 'rejected'
        
        # Update GRPO status
        grpo.status = 'rejected'
        grpo.qc_approver_id = current_user.id
        grpo.qc_approved_at = datetime.utcnow()
        grpo.qc_notes = qc_notes
        
        db.session.commit()
        
        logging.info(f"❌ GRPO {grpo_id} rejected by QC")
        return jsonify({
            'success': True,
            'message': 'GRPO rejected by QC',
            'status': 'rejected'
        })
        
    except Exception as e:
        logging.error(f"Error rejecting GRPO: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@grpo_bp.route('/<int:grpo_id>/add_item', methods=['POST'])
@login_required
def add_grpo_item(grpo_id):
    """Add item to GRPO with duplicate prevention"""
    try:
        grpo = GRPODocument.query.get_or_404(grpo_id)
        
        # Check permissions
        if grpo.user_id != current_user.id and current_user.role not in ['admin', 'manager']:
            flash('Access denied - You can only modify your own GRPOs', 'error')
            return redirect(url_for('grpo.detail', grpo_id=grpo_id))
        
        if grpo.status != 'draft':
            flash('Cannot add items to non-draft GRPO', 'error')
            return redirect(url_for('grpo.detail', grpo_id=grpo_id))
        
        # Get form data
        item_code = request.form.get('item_code')
        item_name = request.form.get('item_name')
        quantity = float(request.form.get('quantity', 0))
        unit_of_measure = request.form.get('unit_of_measure')
        warehouse_code = request.form.get('warehouse_code')
        bin_location = request.form.get('bin_location')
        batch_number = request.form.get('batch_number')
        expiry_date = request.form.get('expiry_date')
        
        if not all([item_code, item_name, quantity > 0]):
            flash('Item Code, Item Name, and Quantity are required', 'error')
            return redirect(url_for('grpo.detail', grpo_id=grpo_id))
        
        # **DUPLICATE PREVENTION LOGIC**
        # Check if this item_code already exists in this GRPO
        existing_item = GRPOItem.query.filter_by(
            grpo_id=grpo_id,
            item_code=item_code
        ).first()
        
        if existing_item:
            flash(f'Item {item_code} has already been added to this GRPO. Each item can only be received once per GRPO to avoid duplication.', 'error')
            return redirect(url_for('grpo.detail', grpo_id=grpo_id))
        
        # Parse expiry date if provided
        expiry_date_obj = None
        if expiry_date:
            try:
                from datetime import datetime
                expiry_date_obj = datetime.strptime(expiry_date, '%Y-%m-%d').date()
            except ValueError:
                flash('Invalid expiry date format. Use YYYY-MM-DD', 'error')
                return redirect(url_for('grpo.detail', grpo_id=grpo_id))
        
        # Create new GRPO item
        grpo_item = GRPOItem(
            grpo_id=grpo_id,
            item_code=item_code,
            item_name=item_name,
            quantity=quantity,
            received_quantity=quantity,
            unit_of_measure=unit_of_measure,
            warehouse_code=warehouse_code,
            bin_location=bin_location,
            batch_number=batch_number,
            expiry_date=expiry_date_obj,
            qc_status='pending'
        )
        
        db.session.add(grpo_item)
        db.session.commit()
        
        logging.info(f"✅ Item {item_code} added to GRPO {grpo_id} with duplicate prevention")
        flash(f'Item {item_code} successfully added to GRPO', 'success')
        
    except Exception as e:
        logging.error(f"Error adding item to GRPO: {str(e)}")
        flash(f'Error adding item: {str(e)}', 'error')
    
    return redirect(url_for('grpo.detail', grpo_id=grpo_id))

@grpo_bp.route('/items/<int:item_id>/delete', methods=['POST'])
@login_required
def delete_grpo_item(item_id):
    """Delete GRPO item"""
    try:
        item = GRPOItem.query.get_or_404(item_id)
        grpo = item.grpo_document
        
        # Check permissions
        if grpo.user_id != current_user.id and current_user.role not in ['admin', 'manager']:
            return jsonify({'success': False, 'error': 'Access denied'}), 403
        
        if grpo.status != 'draft':
            return jsonify({'success': False, 'error': 'Cannot delete items from non-draft GRPO'}), 400
        
        grpo_id = grpo.id
        item_code = item.item_code
        
        db.session.delete(item)
        db.session.commit()
        
        logging.info(f"🗑️ Item {item_code} deleted from GRPO {grpo_id}")
        return jsonify({'success': True, 'message': f'Item {item_code} deleted'})
        
    except Exception as e:
        logging.error(f"Error deleting GRPO item: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500