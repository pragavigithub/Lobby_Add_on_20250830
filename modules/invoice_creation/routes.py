"""
Invoice Creation Routes
Handles invoice creation workflow including serial number lookup and SAP integration
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import login_required, current_user
from app import db
from modules.invoice_creation.models import InvoiceDocument, InvoiceLine, InvoiceSerialNumber, SerialNumberLookup
from sap_integration import SAPIntegration
from datetime import datetime
import logging
import requests
import json
from datetime import datetime, timedelta

invoice_bp = Blueprint('invoice_creation', __name__, url_prefix='/invoice_creation')

@invoice_bp.route('/')
@login_required
def index():
    """Invoice creation main page - list all invoices for current user with pagination and filtering"""
    if not current_user.has_permission('invoice_creation'):
        flash('Access denied - Invoice Creation permissions required', 'error')
        return redirect(url_for('dashboard'))
    
    # Get filter parameters
    search = request.args.get('search', '').strip()
    status_filter = request.args.get('status', '').strip()
    customer_filter = request.args.get('customer', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    
    # Get pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    
    # Ensure per_page is within reasonable limits
    per_page = min(max(per_page, 5), 100)
    
    # Start with base query for current user
    query = InvoiceDocument.query.filter_by(user_id=current_user.id)
    
    # Apply search filter (searches invoice number, customer code, and customer name)
    if search:
        search_term = f'%{search}%'
        query = query.filter(
            db.or_(
                InvoiceDocument.invoice_number.ilike(search_term),
                InvoiceDocument.customer_code.ilike(search_term),
                InvoiceDocument.customer_name.ilike(search_term)
            )
        )
    
    # Apply status filter
    if status_filter:
        query = query.filter(InvoiceDocument.status == status_filter)
    
    # Apply customer filter
    if customer_filter:
        customer_term = f'%{customer_filter}%'
        query = query.filter(
            db.or_(
                InvoiceDocument.customer_code.ilike(customer_term),
                InvoiceDocument.customer_name.ilike(customer_term)
            )
        )
    
    # Apply date filters
    if date_from:
        try:
            from_date = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(InvoiceDocument.created_at >= from_date)
        except ValueError:
            pass
    
    if date_to:
        try:
            to_date = datetime.strptime(date_to, '%Y-%m-%d')
            # Add one day to include the entire end date
            to_date = to_date + timedelta(days=1)
            query = query.filter(InvoiceDocument.created_at < to_date)
        except ValueError:
            pass
    
    # Order by creation date (newest first)
    query = query.order_by(InvoiceDocument.created_at.desc())
    
    # Apply pagination
    invoices_pagination = query.paginate(
        page=page, 
        per_page=per_page, 
        error_out=False
    )
    
    # Get unique statuses for filter dropdown
    status_options = db.session.query(InvoiceDocument.status).filter_by(user_id=current_user.id).distinct().all()
    status_options = [status[0] for status in status_options if status[0]]
    
    # Get unique customers for filter dropdown
    customer_options = db.session.query(
        InvoiceDocument.customer_code, 
        InvoiceDocument.customer_name
    ).filter_by(user_id=current_user.id).filter(
        InvoiceDocument.customer_code.isnot(None)
    ).distinct().all()
    
    return render_template('invoice_creation/index.html', 
                         invoices=invoices_pagination.items,
                         pagination=invoices_pagination,
                         search=search,
                         status_filter=status_filter,
                         customer_filter=customer_filter,
                         date_from=date_from,
                         date_to=date_to,
                         per_page=per_page,
                         status_options=status_options,
                         customer_options=customer_options)

@invoice_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    """Create new invoice page and handle creation"""
    if not current_user.has_permission('invoice_creation'):
        flash('Access denied - Invoice Creation permissions required', 'error')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        try:
            # Handle JSON data from the new interface
            if request.is_json:
                data = request.get_json()
                customer_code = data.get('customer_code')
                invoice_date = data.get('invoice_date')
                serial_items = data.get('serial_items', [])
                
                if not customer_code:
                    return jsonify({'success': False, 'error': 'Please select a customer'}), 400
                
                if not serial_items:
                    return jsonify({'success': False, 'error': 'Please add at least one serial item'}), 400
                
                # Create invoice document
                invoice = InvoiceDocument()
                invoice.user_id = current_user.id
                invoice.customer_code = customer_code
                invoice.doc_date = datetime.strptime(invoice_date, '%Y-%m-%d').date() if invoice_date else datetime.now().date()
                invoice.status = 'draft'
                invoice.total_amount = 0.0
                
                db.session.add(invoice)
                db.session.flush()  # Get the invoice ID
                
                # Add invoice items
                total_amount = 0.0
                line_number = 1
                for item_data in serial_items:
                    # Store serial number lookup data first
                    serial_lookup = SerialNumberLookup()
                    serial_lookup.serial_number = item_data.get('serial_number')
                    serial_lookup.item_code = item_data.get('item_code')
                    serial_lookup.item_name = item_data.get('item_name')
                    serial_lookup.warehouse_code = item_data.get('warehouse')
                    serial_lookup.lookup_status = 'validated'
                    serial_lookup.sap_response = json.dumps(item_data)
                    serial_lookup.last_updated = datetime.utcnow()
                    db.session.add(serial_lookup)
                    
                    # Create invoice line
                    invoice_line = InvoiceLine()
                    invoice_line.invoice_id = invoice.id
                    invoice_line.line_number = line_number
                    invoice_line.item_code = item_data.get('item_code', 'UNKNOWN')
                    invoice_line.item_description = item_data.get('item_name', 'Unknown Item')
                    invoice_line.quantity = 1.0
                    invoice_line.warehouse_code = item_data.get('warehouse', '')
                    invoice_line.tax_code = 'IGST0'
                    db.session.add(invoice_line)
                    db.session.flush()  # Get the line ID
                    
                    # Create serial number record
                    serial_item = InvoiceSerialNumber()
                    serial_item.invoice_line_id = invoice_line.id
                    serial_item.serial_number = item_data.get('serial_number')
                    serial_item.item_code = item_data.get('item_code', 'UNKNOWN')
                    serial_item.item_description = item_data.get('item_name', 'Unknown Item')
                    serial_item.warehouse_code = item_data.get('warehouse', '')
                    serial_item.customer_code = customer_code
                    serial_item.quantity = 1.0
                    serial_item.validation_status = 'validated'
                    db.session.add(serial_item)
                    line_number += 1
                
                db.session.commit()
                
                return jsonify({
                    'success': True, 
                    'message': 'Invoice created successfully',
                    'invoice_id': invoice.id
                })
                
        except Exception as e:
            db.session.rollback()
            logging.error(f"Error creating invoice: {str(e)}")
            if request.is_json:
                return jsonify({'success': False, 'error': f'Error creating invoice: {str(e)}'}), 500
            else:
                flash(f'Error creating invoice: {str(e)}', 'error')
    
    return render_template('invoice_creation/create.html')

@invoice_bp.route('/detail/<int:invoice_id>')
@login_required
def detail(invoice_id):
    """Invoice detail page"""
    invoice = InvoiceDocument.query.get_or_404(invoice_id)
    
    # Check permissions
    if invoice.user_id != current_user.id and current_user.role not in ['admin', 'manager']:
        flash('Access denied - You can only view your own invoices', 'error')
        return redirect(url_for('invoice_creation.index'))
    
    return render_template('invoice_creation/detail.html', invoice=invoice)

@invoice_bp.route('/api/business-partners')
@login_required
def get_business_partners():
    """API endpoint to get business partners for customer selection"""
    try:
        logging.info("🔍 Fetching business partners...")
        sap = SAPIntegration()
        
        # Check SAP configuration first
        if not sap.base_url or not sap.username or not sap.password:
            logging.warning("⚠️ SAP B1 configuration missing - returning fallback customers")
            # Return fallback customer data for offline mode
            fallback_customers = [

            ]
            return jsonify({
                'success': True,
                'business_partners': fallback_customers,
                'offline_mode': True
            })
        
        if not sap.ensure_logged_in():
            logging.error("❌ SAP login failed - returning fallback customers")
            fallback_customers = [

            ]
            return jsonify({
                'success': True,
                'business_partners': fallback_customers,
                'offline_mode': True
            })
        
        try:
            url = f"{sap.base_url}/b1s/v1/BusinessPartners?$select=CardCode,CardName&$filter=CardType eq 'cCustomer'"
            logging.info(f"🌐 SAP API URL: {url}")
            headers={"Prefer":"odata.maxpagesize=0"}
            response = sap.session.get(url, headers=headers,timeout=10)
            
            if response.status_code == 200:
                data = response.json()

                business_partners = data.get('value', [])
                logging.info(f"✅ Retrieved {len(business_partners)} business partners from SAP")
                return jsonify({
                    'success': True,
                    'business_partners': business_partners,
                    'offline_mode': False
                })
            else:
                logging.error(f"❌ SAP API error: {response.status_code} - {response.text}")
                # Return fallback on API error
                fallback_customers = [

                ]
                return jsonify({
                    'success': True,
                    'business_partners': fallback_customers,
                    'offline_mode': True,
                    'error': f'SAP API error: {response.status_code}'
                })
        except Exception as e:
            logging.error(f"❌ SAP request failed: {str(e)}")
            fallback_customers = [

            ]
            return jsonify({
                'success': True,
                'business_partners': fallback_customers,
                'offline_mode': True,
                'error': f'Request failed: {str(e)}'
            })
    except Exception as e:
        logging.error(f"❌ Business partners API error: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500

@invoice_bp.route('/api/validate-serial-number')
@login_required
def validate_serial_number():
    """API endpoint to validate serial number and fetch item details from SAP B1"""
    serial_number = request.args.get('serial_number', '').strip()
    cusCode = request.args.get('cusCode', '').strip()
    print (cusCode)
    if not serial_number:
        return jsonify({
            'success': False,
            'error': 'Serial number is required'
        }), 400
    
    try:
        logging.info(f"🔍 Validating serial number: {serial_number}")
        sap = SAPIntegration()
        
        # Check SAP configuration first
        if not sap.base_url or not sap.username or not sap.password:
            logging.warning("⚠️ SAP B1 configuration missing - using fallback validation")
            # Return fallback serial validation data for offline mode
            fallback_data = {

            }
            return jsonify({
                'success': True,
                'item_data': fallback_data,
                'offline_mode': True
            })
        
        if not sap.ensure_logged_in():
            logging.error("❌ SAP login failed - using fallback validation")
            # Return fallback serial validation data for offline mode
            fallback_data = {

            }
            return jsonify({
                'success': True,
                'item_data': fallback_data,
                'offline_mode': True
            })
        
        try:
            # Use SAP SQL Query for Invoice Creation serial number validation (Note: SAP query name is 'Invoice_creation')
            url = f"{sap.base_url}/b1s/v1/SQLQueries('Invoise_creation')/List"
            payload = {
                "ParamList": f"serial_number='{serial_number}'"
            }
            
            response = sap.session.post(url, json=payload, timeout=30)

            if response.status_code == 200:
                data = response.json()
                results = data.get('value', [])
                print(f"transfer_itemss (repr) --> {repr(data)}")
                if results:
                    # Return the first result with item details AND customer information
                    item_data = results[0]
                    # Enhanced response with auto-customer detection
                    response_data = {
                        'ItemCode': item_data.get('ItemCode', ''),
                        'ItemName': item_data.get('itemName', ''),
                        'DistNumber': item_data.get('DistNumber', ''),
                        'WhsCode': item_data.get('WhsCode', ''),
                        'WhsName': item_data.get('WhsName', ''),
                        'BPLName': item_data.get('BPLName', ''),
                        'BPLid': item_data.get('BPLid', ''),
                        'CardCode': item_data.get('CardCode', ''),
                        'CardName': (cusCode, ''),
                        'CustomerCode': (cusCode, ''),
                        'CustomerName': (cusCode, '')
                    }
                    
                    # If no customer found from serial, add a common customer for demo
                    if not response_data['CardCode']:
                        response_data['CardCode'] = ''
                        response_data['CardName'] = ''
                        response_data['CustomerCode'] = ''
                        response_data['CustomerName'] = ''
                    
                    return jsonify({
                        'success': True,
                        'item_data': response_data
                    })
                else:
                    return jsonify({
                        'success': False,
                        'error': 'Serial number not found or has no available quantity'
                    })
            else:
                return jsonify({
                    'success': False,
                    'error': f'SAP API error: {response.status_code} - {response.text}'
                }), 500
                
        except Exception as e:
            logging.error(f"❌ SAP validation failed: {str(e)} - using fallback validation")
            # Return fallback serial validation data on SAP error
            fallback_data = {

            }
            return jsonify({
                'success': True,
                'item_data': fallback_data,
                'offline_mode': True,
                'error': f'SAP unavailable, using fallback data'
            })
    except Exception as e:
        logging.error(f"❌ Serial number validation API error: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500

@invoice_bp.route('/api/lookup_serial', methods=['POST'])
@login_required
def lookup_serial():
    """API endpoint to lookup serial number details from SAP"""
    try:
        data = request.get_json()
        serial_number = data.get('serial_number', '').strip()
        
        if not serial_number:
            return jsonify({
                'success': False,
                'message': 'Serial number is required'
            }), 400
        
        logging.info(f"🔍 Looking up serial number: {serial_number}")
        
        # Check cache first
        cached_lookup = SerialNumberLookup.query.filter_by(serial_number=serial_number).first()
        if cached_lookup and (datetime.utcnow() - cached_lookup.last_updated) < timedelta(hours=1):
            logging.info(f"✅ Found cached data for serial number: {serial_number}")
            return jsonify({
                'success': True,
                'data': {
                    'ItemCode': cached_lookup.item_code,
                    'itemName': cached_lookup.item_name,
                    'DistNumber': serial_number,
                    'WhsCode': cached_lookup.warehouse_code,
                    'WhsName': cached_lookup.warehouse_name,
                    'BPLid': cached_lookup.branch_id,
                    'BPLName': cached_lookup.branch_name
                },
                'cached': True
            })
        
        # Lookup from SAP
        sap = SAPIntegration()
        if not sap.ensure_logged_in():
            return jsonify({
                'success': False,
                'message': 'SAP connection failed'
            }), 500
        
        try:
            # Use the SQL Query API as specified by user (Note: SAP query name is 'Invoice_creation')
            url = f"{sap.base_url}/b1s/v1/SQLQueries('Invoise_creation')/List"
            payload = {
                "ParamList": f"serial_number='{serial_number}'"
            }
            
            response = sap.session.post(url, json=payload, timeout=30)
            logging.info(f"SAP SQL Query Response Status: {response.status_code}")
            
            if response.status_code == 200:
                sap_data = response.json()
                logging.info(f"SAP SQL Query Response: {json.dumps(sap_data, indent=2)}")
                
                values = sap_data.get('value', [])
                if values:
                    item_data = values[0]  # Take first result
                    
                    # Cache the result
                    if cached_lookup:
                        cached_lookup.item_code = item_data.get('ItemCode')
                        cached_lookup.item_name = item_data.get('itemName')
                        cached_lookup.warehouse_code = item_data.get('WhsCode')
                        cached_lookup.warehouse_name = item_data.get('WhsName')
                        cached_lookup.branch_id = item_data.get('BPLid')
                        cached_lookup.branch_name = item_data.get('BPLName')
                        cached_lookup.lookup_status = 'validated'
                        cached_lookup.sap_response = json.dumps(item_data)
                        cached_lookup.last_updated = datetime.utcnow()
                    else:
                        cached_lookup = SerialNumberLookup()
                        cached_lookup.serial_number = serial_number
                        cached_lookup.item_code = item_data.get('ItemCode')
                        cached_lookup.item_name = item_data.get('itemName')
                        cached_lookup.warehouse_code = item_data.get('WhsCode')
                        cached_lookup.warehouse_name = item_data.get('WhsName')
                        cached_lookup.branch_id = item_data.get('BPLid')
                        cached_lookup.branch_name = item_data.get('BPLName')
                        cached_lookup.lookup_status = 'validated'
                        cached_lookup.sap_response = json.dumps(item_data)
                        cached_lookup.last_updated = datetime.utcnow()
                        db.session.add(cached_lookup)
                    
                    db.session.commit()
                    
                    return jsonify({
                        'success': True,
                        'data': item_data,
                        'cached': False
                    })
                else:
                    return jsonify({
                        'success': False,
                        'message': f'Serial number {serial_number} not found in SAP'
                    }), 404
            else:
                logging.error(f"SAP SQL Query failed: {response.status_code} - {response.text}")
                return jsonify({
                    'success': False,
                    'message': f'SAP query failed: {response.status_code}'
                }), 500
        
        except Exception as e:
            logging.error(f"Error during SAP lookup: {str(e)}")
            return jsonify({
                'success': False,
                'message': f'SAP lookup error: {str(e)}'
            }), 500
            
    except Exception as e:
        logging.error(f"Error in lookup_serial API: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Internal error: {str(e)}'
        }), 500


@invoice_bp.route('/create_draft', methods=['POST'])
@login_required
def create_draft():
    """Create a draft invoice for line-by-line entry"""
    try:
        if not current_user.has_permission('invoice_creation'):
            return jsonify({'success': False, 'error': 'Access denied - Invoice Creation permissions required'}), 403
        
        # Create draft invoice
        invoice = InvoiceDocument()
        invoice.user_id = current_user.id
        invoice.status = 'draft'
        invoice.doc_date = datetime.now().date()
        invoice.total_amount = 0.0
        
        db.session.add(invoice)
        db.session.commit()
        
        logging.info(f"✅ Draft invoice {invoice.id} created for user {current_user.username}")
        
        return jsonify({
            'success': True,
            'message': 'Draft invoice created successfully',
            'invoice_id': invoice.id
        })
        
    except Exception as e:
        logging.error(f"Error creating draft invoice: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@invoice_bp.route('/lines/<int:line_id>/delete', methods=['POST'])
@login_required
def delete_line_item(line_id):
    """Delete invoice line item"""
    try:
        line_item = InvoiceLine.query.get_or_404(line_id)
        invoice = line_item.invoice
        
        # Check permissions
        if invoice.user_id != current_user.id and current_user.role not in ['admin', 'manager']:
            return jsonify({'success': False, 'error': 'Access denied'}), 403
            
        if invoice.status != 'draft':
            return jsonify({'success': False, 'error': 'Cannot delete items from non-draft invoice'}), 400
            
        line_id_num = line_item.id
        serial_numbers = [sn.serial_number for sn in line_item.serial_numbers]
        
        # Delete associated serial numbers first (cascade should handle this, but being explicit)
        for serial_num in line_item.serial_numbers:
            db.session.delete(serial_num)
            
        db.session.delete(line_item)
        db.session.commit()
        
        logging.info(f"🗑️ Invoice line item {line_id_num} deleted from invoice {invoice.id}")
        return jsonify({
            'success': True, 
            'message': f'Line item with serials {", ".join(serial_numbers)} deleted'
        })
        
    except Exception as e:
        logging.error(f"Error deleting line item: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@invoice_bp.route('/api/create_invoice', methods=['POST'])
@login_required
def create_invoice():
    """API endpoint to create invoice in SAP"""
    try:
        data = request.get_json()
        customer_code = data.get('customer_code', '').strip()
        serial_numbers = data.get('serial_numbers', [])
        
        if not customer_code:
            return jsonify({
                'success': False,
                'message': 'Customer code is required'
            }), 400
        
        if not serial_numbers:
            return jsonify({
                'success': False,
                'message': 'At least one serial number is required'
            }), 400
        
        logging.info(f"🏗️ Creating invoice for customer: {customer_code} with {len(serial_numbers)} serial numbers")
        
        # Create local invoice record
        invoice = InvoiceDocument()
        invoice.customer_code = customer_code
        invoice.user_id = current_user.id
        invoice.status = 'draft'
        db.session.add(invoice)
        db.session.flush()  # Get the ID
        
        # Group serial numbers by item and warehouse
        items_data = {}
        line_number = 0
        
        for serial_number in serial_numbers:
            # Get serial number details from cache or SAP
            cached_lookup = SerialNumberLookup.query.filter_by(serial_number=serial_number).first()
            if not cached_lookup:
                return jsonify({
                    'success': False,
                    'message': f'Serial number {serial_number} not found. Please lookup first.'
                }), 400
            
            # Group by item code and warehouse
            key = f"{cached_lookup.item_code}_{cached_lookup.warehouse_code}"
            if key not in items_data:
                items_data[key] = {
                    'ItemCode': cached_lookup.item_code,
                    'ItemDescription': cached_lookup.item_name,
                    'WarehouseCode': cached_lookup.warehouse_code,
                    # 'TaxCode': 'IGST0',
                    'Quantity': 0,
                    'SerialNumbers': [],
                    'BPL_IDAssignedToInvoice': cached_lookup.branch_id,
                    'BPLName': cached_lookup.branch_name
                }
            
            items_data[key]['Quantity'] += 1
            items_data[key]['SerialNumbers'].append({
                'InternalSerialNumber': serial_number,
                'BaseLineNumber': line_number,
                'Quantity': 1.0
            })
        
        # Build SAP invoice JSON
        current_date = datetime.now()
        sap_invoice = {
            "DocDate": current_date.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "DocDueDate": (current_date + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "CardCode": customer_code,
            "DocumentLines": []
        }
        
        # Set BPL_IDAssignedToInvoice from first item
        first_item = list(items_data.values())[0]
        sap_invoice["BPL_IDAssignedToInvoice"] = first_item['BPL_IDAssignedToInvoice']
        sap_invoice["BPLName"] = first_item['BPLName']
        
        # Add document lines
        for key, item_data in items_data.items():
            document_line = {
                "ItemCode": item_data['ItemCode'],
                "ItemDescription": item_data['ItemDescription'],
                "Quantity": float(item_data['Quantity']),
                "WarehouseCode": item_data['WarehouseCode'],
                # "TaxCode": item_data['TaxCode'],
                "SerialNumbers": item_data['SerialNumbers']
            }
            sap_invoice["DocumentLines"].append(document_line)
            
            # Create local invoice line
            invoice_line = InvoiceLine()
            invoice_line.invoice_id = invoice.id
            invoice_line.line_number = line_number
            invoice_line.item_code = item_data['ItemCode']
            invoice_line.item_description = item_data['ItemDescription']
            invoice_line.quantity = item_data['Quantity']
            invoice_line.warehouse_code = item_data['WarehouseCode']
            # invoice_line.tax_code = item_data['TaxCode']
            db.session.add(invoice_line)
            db.session.flush()
            
            # Add serial numbers
            for serial_data in item_data['SerialNumbers']:
                invoice_serial = InvoiceSerialNumber()
                invoice_serial.invoice_line_id = invoice_line.id
                invoice_serial.serial_number = serial_data['InternalSerialNumber']
                invoice_serial.base_line_number = serial_data['BaseLineNumber']
                invoice_serial.quantity = serial_data['Quantity']
                db.session.add(invoice_serial)
            
            line_number += 1
        
        # Store JSON payload
        invoice.json_payload = json.dumps(sap_invoice, indent=2)
        
        # Create invoice in SAP
        sap = SAPIntegration()
        if not sap.ensure_logged_in():
            return jsonify({
                'success': False,
                'message': 'SAP connection failed'
            }), 500
        
        try:
            url = f"{sap.base_url}/b1s/v1/Invoices"
            response = sap.session.post(url, json=sap_invoice, timeout=60)
            
            logging.info(f"SAP Invoice Creation Response Status: {response.status_code}")
            logging.info(f"SAP Invoice Creation Response: {response.text}")
            
            if response.status_code == 201:
                sap_response = response.json()
                invoice.sap_response = json.dumps(sap_response, indent=2)
                invoice.sap_doc_entry = sap_response.get('DocEntry')
                invoice.sap_doc_num = sap_response.get('DocNum')
                invoice.invoice_number = str(sap_response.get('DocNum'))
                invoice.status = 'created'
                invoice.total_amount = sap_response.get('DocTotal', 0)
                
                db.session.commit()
                
                logging.info(f"✅ Invoice created successfully: DocEntry={invoice.sap_doc_entry}, DocNum={invoice.sap_doc_num}")
                
                return jsonify({
                    'success': True,
                    'message': f'Invoice {invoice.invoice_number} created successfully',
                    'invoice_id': invoice.id,
                    'sap_doc_entry': invoice.sap_doc_entry,
                    'sap_doc_num': invoice.sap_doc_num,
                    'total_amount': float(invoice.total_amount or 0)
                })
            else:
                error_message = f"SAP invoice creation failed: {response.status_code}"
                if response.text:
                    try:
                        error_data = response.json()
                        error_message = error_data.get('error', {}).get('message', {}).get('value', error_message)
                    except:
                        error_message = response.text
                
                invoice.sap_response = response.text
                invoice.status = 'failed'
                db.session.commit()
                
                logging.error(f"SAP invoice creation failed: {error_message}")
                return jsonify({
                    'success': False,
                    'message': error_message
                }), 500
        
        except Exception as e:
            invoice.sap_response = str(e)
            invoice.status = 'failed'
            db.session.commit()
            
            logging.error(f"Error during SAP invoice creation: {str(e)}")
            return jsonify({
                'success': False,
                'message': f'SAP invoice creation error: {str(e)}'
            }), 500
            
    except Exception as e:
        logging.error(f"Error in create_invoice API: {str(e)}")
        if 'invoice' in locals():
            try:
                db.session.rollback()
            except:
                pass
        return jsonify({
            'success': False,
            'message': f'Internal error: {str(e)}'
        }), 500

# REMOVED: Duplicate get_customers endpoint - using business-partners instead

# Additional AJAX endpoints for invoice creation
@invoice_bp.route('/create', methods=['POST'])
@login_required
def create_invoice_ajax():
    """AJAX endpoint to create invoice document"""
    try:
        data = request.get_json()
        logging.info(f"📝 Creating invoice with data: {data}")
        
        customer_code = data.get('customer_code')
        invoice_date = data.get('invoice_date')
        serial_items = data.get('serial_items', [])
        
        if not customer_code or not serial_items:
            return jsonify({
                'success': False,
                'error': 'Customer code and serial items are required'
            }), 400
        
        # Create invoice document in local database
        invoice_number = generate_invoice_number()
        
        invoice_doc = InvoiceDocument()
        invoice_doc.invoice_number = invoice_number
        invoice_doc.customer_code = customer_code
        invoice_doc.customer_name = data.get('customer_name', '')
        invoice_doc.user_id = current_user.id
        invoice_doc.status = 'pending_qc'
        invoice_doc.doc_date = datetime.strptime(invoice_date, '%Y-%m-%d').date()
        invoice_doc.branch_id = current_user.branch_id
        invoice_doc.branch_name = current_user.branch_name
        
        db.session.add(invoice_doc)
        db.session.flush()  # Get the ID
        
        # Create invoice lines and serial numbers
        line_number = 1
        for item in serial_items:
            # Create invoice line
            invoice_line = InvoiceLine()
            invoice_line.invoice_id = invoice_doc.id
            invoice_line.line_number = line_number
            invoice_line.item_code = item.get('item_code')
            invoice_line.item_description = item.get('item_name')
            invoice_line.quantity = item.get('quantity', 1)
            invoice_line.warehouse_code = item.get('warehouse')
            invoice_line.unit_price = 0.00  # Will be updated when posted to SAP
            invoice_line.line_total = 0.00
            
            db.session.add(invoice_line)
            db.session.flush()  # Get the line ID
            
            # Add serial number
            serial_number = InvoiceSerialNumber()
            serial_number.invoice_line_id = invoice_line.id
            serial_number.serial_number = item.get('serial_number')
            serial_number.item_code = item.get('item_code')
            serial_number.warehouse_code = item.get('warehouse')
            
            db.session.add(serial_number)
            line_number += 1
        
        db.session.commit()
        
        logging.info(f"✅ Invoice {invoice_number} created successfully")
        return jsonify({
            'success': True,
            'invoice_number': invoice_number,
            'message': f'Invoice {invoice_number} created and sent for QC approval'
        })
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"❌ Invoice creation failed: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Failed to create invoice: ' + str(e)
        }), 500

# Helper functions for SAP B1 integration
def generate_invoice_number():
    """Generate next invoice number"""
    try:
        # Simple sequential numbering
        import time
        timestamp = str(int(time.time()))[-6:]
        invoice_number = f"INV-{timestamp}"
        
        return invoice_number
        
    except Exception as e:
        logging.error(f"❌ Number generation failed: {str(e)}")
        from datetime import datetime
        return f"INV-{datetime.now().strftime('%Y%m%d%H%M%S')}"

def build_sap_invoice_data(invoice):
    """Build SAP B1 Invoice JSON structure with proper BaseLineNumber grouping by ItemCode"""
    try:
        # Get invoice lines with serial numbers
        invoice_lines = InvoiceLine.query.filter_by(invoice_id=invoice.id).all()
        
        # Group by ItemCode to assign proper BaseLineNumber (0, 1, 2, etc.)
        grouped_items = {}
        base_line_counter = 0
        
        for line in invoice_lines:
            # Get serial numbers for this line
            serial_numbers = InvoiceSerialNumber.query.filter_by(invoice_line_id=line.id).all()
            
            item_key = line.item_code
            
            # If this ItemCode hasn't been seen before, create new group
            if item_key not in grouped_items:
                grouped_items[item_key] = {
                    "ItemCode": line.item_code,
                    "ItemDescription": line.item_description,
                    "WarehouseCode": line.warehouse_code,
                    # '"TaxCode": line.tax_code or "IGST0",
                    "BaseLineNumber": base_line_counter,
                    "SerialNumbers": [],
                    "TotalQuantity": 0
                }
                base_line_counter += 1
            
            # Add serial numbers to this item group
            for serial in serial_numbers:
                grouped_items[item_key]["SerialNumbers"].append({
                    "InternalSerialNumber": serial.serial_number,
                    "BaseLineNumber": grouped_items[item_key]["BaseLineNumber"],
                    "Quantity": 1.0
                })
                grouped_items[item_key]["TotalQuantity"] += 1
        
        # Build DocumentLines from grouped items
        document_lines = []
        for item_data in grouped_items.values():
            line_data = {
                "ItemCode": item_data["ItemCode"],
                "ItemDescription": item_data["ItemDescription"],
                "Quantity": float(item_data["TotalQuantity"]),
                "WarehouseCode": item_data["WarehouseCode"],
                # "TaxCode": item_data["TaxCode"]
            }
            
            if item_data["SerialNumbers"]:
                line_data["SerialNumbers"] = item_data["SerialNumbers"]
            
            document_lines.append(line_data)
        
        # Build complete invoice structure as per user JSON specification
        from datetime import datetime, timedelta
        doc_date = invoice.doc_date.isoformat() + "T16:02:10.653271Z"
        due_date = (invoice.doc_date + timedelta(days=30)).isoformat() + "T16:02:10.653271Z"
        
        sap_data = {
            "DocDate": doc_date,
            "DocDueDate": due_date,
            "BPL_IDAssignedToInvoice": 5,
            "BPLName": invoice.branch_name ,
            "CardCode": invoice.customer_code,
            "DocumentLines": document_lines
        }
        
        logging.info(f"📄 Built SAP invoice data with {len(document_lines)} document lines grouped by ItemCode:")
        logging.info(f"📄 SAP Invoice JSON: {json.dumps(sap_data, indent=2)}")
        return sap_data
        
    except Exception as e:
        logging.error(f"❌ Failed to build SAP invoice data: {str(e)}")
        raise

@invoice_bp.route('/add-serial-item', methods=['POST'])
@login_required
def add_serial_item():
    """Add serial item to invoice (session-based storage like Serial Item Transfer)"""
    try:
        data = request.get_json()
        serial_number = data.get('serial_number', '').strip()
        
        if not serial_number:
            return jsonify({
                'success': False,
                'error': 'Serial number is required'
            }), 400
        
        # Get session-based temporary invoice items (similar to Serial Item Transfer workflow)
        if 'invoice_items' not in session:
            session['invoice_items'] = []
        
        # Check if serial number already exists in session
        existing_items = session['invoice_items']
        if any(item['serial_number'] == serial_number for item in existing_items):
            return jsonify({
                'success': False,
                'error': 'Serial number already added to this invoice'
            }), 400
        
        # Validate serial number with SAP B1 (reuse existing validation)
        logging.info(f"🔍 Validating serial number for adding: {serial_number}")
        sap = SAPIntegration()
        
        # Get item data from validation
        item_code = data.get('item_code', '')
        item_description = data.get('item_description', '')
        warehouse_code = data.get('warehouse_code', '')
        customer_code = data.get('customer_code', '')
        customer_name = data.get('customer_name', '')
        
        # If validation data not provided, try to validate again
        if not item_code:
            # Use the same validation logic as the validate-serial-number endpoint
            try:
                if sap.base_url and sap.username and sap.password and sap.ensure_logged_in():
                    url = f"{sap.base_url}/b1s/v1/SQLQueries('Invoice_creation')/List"
                    payload = {"ParamList": f"serial_number='{serial_number}'"}
                    
                    response = sap.session.post(url, json=payload, timeout=15)
                    
                    if response.status_code == 200:
                        results = response.json().get('value', [])
                        if results:
                            validation_data = results[0]
                            item_code = validation_data.get('ItemCode', item_code)
                            item_description = validation_data.get('itemName', validation_data.get('ItemName', item_description))
                            warehouse_code = validation_data.get('WhsCode', warehouse_code)
                            customer_code = validation_data.get('CardCode', customer_code)
                            customer_name = validation_data.get('CardName', customer_name)
                        else:
                            # Use fallback data if not found in SAP
                            item_code = item_code or 'MI Phone'
                            item_description = item_description or ''
                            warehouse_code = warehouse_code or ''
                            customer_code = customer_code or ''
                            customer_name = customer_name or ''
            except Exception as e:
                logging.warning(f"⚠️ Validation during add failed, using provided data: {e}")
                # Use provided data or fallback
                item_code = item_code or ''
                item_description = item_description or ''
                warehouse_code = warehouse_code or ''
                customer_code = customer_code or ''
                customer_name = customer_name or ''
        
        # Create item data structure
        item_data = {
            'id': len(existing_items) + 1,  # Simple ID for frontend
            'serial_number': serial_number,
            'item_code': item_code,
            'item_description': item_description,
            'warehouse_code': warehouse_code,
            'customer_code': customer_code,
            'customer_name': customer_name,
            'quantity': 1,
            'validation_status': 'validated',
            'line_number': len(existing_items) + 1,
            'created_at': datetime.now().isoformat()
        }
        
        # Add to session
        existing_items.append(item_data)
        session['invoice_items'] = existing_items
        session.modified = True
        
        logging.info(f"✅ Added serial item to session: {serial_number}")
        
        return jsonify({
            'success': True,
            'message': f'Serial number {serial_number} added successfully',
            'item_added': True,
            'validation_status': 'validated',
            'item_data': item_data
        })
        
    except Exception as e:
        logging.error(f"❌ Error adding serial item: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to add serial item: {str(e)}'
        }), 500

@invoice_bp.route('/remove-serial-item/<int:item_id>', methods=['POST'])
@login_required
def remove_serial_item(item_id):
    """Remove serial item from session (like Serial Item Transfer delete)"""
    try:
        if 'invoice_items' not in session:
            return jsonify({
                'success': False,
                'error': 'No items to remove'
            }), 400
        
        # Find and remove item by ID
        existing_items = session['invoice_items']
        original_length = len(existing_items)
        
        # Filter out the item with matching ID
        session['invoice_items'] = [item for item in existing_items if item.get('id') != item_id]
        session.modified = True
        
        if len(session['invoice_items']) < original_length:
            logging.info(f"🗑️ Removed serial item with ID: {item_id}")
            return jsonify({
                'success': True,
                'message': 'Serial item removed successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Item not found'
            }), 404
            
    except Exception as e:
        logging.error(f"❌ Error removing serial item: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to remove serial item: {str(e)}'
        }), 500

@invoice_bp.route('/clear-session-items', methods=['POST'])
@login_required  
def clear_session_items():
    """Clear all session items (for Clear All button)"""
    try:
        session.pop('invoice_items', None)
        session.modified = True
        
        logging.info("🧹 Cleared all session invoice items")
        return jsonify({
            'success': True,
            'message': 'All items cleared'
        })
        
    except Exception as e:
        logging.error(f"❌ Error clearing session items: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to clear items: {str(e)}'
        }), 500

# New line-by-line endpoints for immediate database persistence
@invoice_bp.route('/<int:invoice_id>/add_line_item', methods=['POST'])
@login_required
def add_line_item(invoice_id):
    """Add serial item to Invoice with real-time SAP B1 validation (like Serial Item Transfer)"""
    try:
        invoice = InvoiceDocument.query.get_or_404(invoice_id)
        
        # Check permissions
        if invoice.user_id != current_user.id and current_user.role not in ['admin', 'manager']:
            return jsonify({'success': False, 'error': 'Access denied'}), 403
        
        if invoice.status not in ['draft', 'pending_qc']:
            return jsonify({'success': False, 'error': 'Cannot add items to this invoice status'}), 400
        
        # Get form data (support both JSON and form data)
        if request.is_json:
            data = request.get_json()
            serial_number = data.get('serial_number', '').strip()
            cusCode = data.get('custCode', '').strip()
            print(cusCode +""+serial_number)
        else:
            serial_number = request.form.get('serial_number', '').strip()
        
        if not serial_number:
            return jsonify({'success': False, 'error': 'Serial number is required'}), 400
        
        # Check for duplicate serial number in this invoice
        existing_item = InvoiceSerialNumber.query.join(InvoiceLine).filter(
            InvoiceLine.invoice_id == invoice.id,
            InvoiceSerialNumber.serial_number == serial_number
        ).first()
        
        if existing_item:
            return jsonify({
                'success': False,
                'error': f'Serial number {serial_number} already exists in this invoice',
                'duplicate': True
            }), 400
        
        # Validate serial number with SAP B1 (using same logic as validate-serial-number endpoint)
        sap = SAPIntegration()
        validation_result = {}
        validation_status = 'failed'
        validation_error = None
        
        # Check SAP configuration and validate
        if sap.base_url and sap.username and sap.password and sap.ensure_logged_in():
            try:
                # Use SAP SQL Query for Invoice Creation serial number validation
                url = f"{sap.base_url}/b1s/v1/SQLQueries('Invoise_creation')/List"
                payload = {
                    "ParamList": f"serial_number='{serial_number}'"
                }
                
                response = sap.session.post(url, json=payload, timeout=30)
                
                if response.status_code == 200:
                    data = response.json()
                    results = data.get('value', [])
                    
                    if results:
                        validation_result = results[0]
                        print(f"transfer_itemssssssss (repr) --> {repr(validation_result)}")
                        validation_status = 'validated'
                        logging.info(f"✅ Serial {serial_number} validated successfully with SAP")
                    else:
                        validation_error = f'Serial number {serial_number} not found in SAP B1 inventory'
                        logging.warning(f"⚠️ Serial {serial_number} not found in SAP")
                else:
                    validation_error = f'SAP API error: {response.status_code}'
                    logging.error(f"❌ SAP API error for {serial_number}: {response.status_code}")
            except Exception as e:
                validation_error = f'SAP connection error: {str(e)}'
                logging.error(f"❌ SAP validation error for {serial_number}: {str(e)}")
        else:
            # Fallback data for offline mode
            validation_result = {

            }
            validation_status = 'validated'
            logging.info(f"🔄 Using offline mode for {serial_number}")
        
        # Create invoice line and serial number record immediately
        # Get next line number
        max_line = db.session.query(db.func.max(InvoiceLine.line_number)).filter_by(invoice_id=invoice.id).scalar()
        next_line_number = (max_line or 0) + 1
        
        # Create invoice line
        invoice_line = InvoiceLine()
        invoice_line.invoice_id = invoice.id
        invoice_line.line_number = next_line_number
        invoice_line.item_code = validation_result.get('ItemCode', 'UNKNOWN')
        invoice_line.item_description = validation_result.get('itemName', validation_result.get('ItemName', 'Unknown Item'))
        invoice_line.quantity = 1.0
        invoice_line.warehouse_code = validation_result.get('WhsCode', '')
        invoice_line.warehouse_name = validation_result.get('WhsName', '')
        
        db.session.add(invoice_line)
        db.session.flush()  # Get the line ID
        
        # Create serial number record
        serial_item = InvoiceSerialNumber()
        serial_item.invoice_line_id = invoice_line.id
        serial_item.serial_number = serial_number
        serial_item.item_code = validation_result.get('ItemCode', 'UNKNOWN')
        serial_item.item_description = validation_result.get('itemName', validation_result.get('ItemName', 'Unknown Item'))
        serial_item.warehouse_code = validation_result.get('WhsCode', '')
        serial_item.customer_name = validation_result.get('CardName', '')
        serial_item.quantity = 1.0
        serial_item.customer_code = request.args.get('cusCode', '')
        serial_item.validation_status = validation_status
        serial_item.validation_error = validation_error
        serial_item.bpl_id=validation_result.get('BPLid', '')
        serial_item.bpl_name=validation_result.get('BPLName','')
        db.session.add(serial_item)
        
        # CUSTOMER CODE FREEZE LOGIC - once any line items exist, customer cannot be changed
        existing_lines_count = InvoiceLine.query.filter_by(invoice_id=invoice.id).count()
        
        if validation_result.get('CardCode') and not invoice.customer_code and existing_lines_count == 0:
            # Only set customer on first line item - customer code becomes FROZEN after this
            invoice.customer_code = validation_result.get('CardCode')
            invoice.customer_name = validation_result.get('CardName', '')
            logging.info(f"🔒 Customer locked to {invoice.customer_code} after first line item")
        elif invoice.customer_code and existing_lines_count > 0:
            # Validate that serial belongs to the locked customer - REJECT if different
            detected_customer = validation_result.get('CardCode', '')
            if detected_customer and detected_customer != invoice.customer_code:
                return jsonify({
                    'success': False,
                    'error': f'Customer code is FROZEN to {invoice.customer_code}. Cannot add items for different customer {detected_customer}',
                    'customer_locked': True
                }), 400
        
        db.session.commit()
        
        logging.info(f"✅ Added serial item {serial_number} to invoice {invoice.id}")
        
        return jsonify({
            'success': True,
            'item_added': True,
            'item_data': {
                'id': serial_item.id,
                'line_number': next_line_number,
                'serial_number': serial_number,
                'item_code': serial_item.item_code,
                'item_description': serial_item.item_description,
                'warehouse_code': serial_item.warehouse_code,
                'warehouse_name': invoice_line.warehouse_name,
                'customer_code': serial_item.customer_code,
                'customer_name': serial_item.customer_name,
                'quantity': serial_item.quantity,
                'validation_status': validation_status,
                'validation_error': validation_error,
                'customer_locked': bool(invoice.customer_code)  # Indicate if customer is locked
            }
        })
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"❌ Error adding serial item: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Internal error: {str(e)}'
        }), 500

@invoice_bp.route('/<int:invoice_id>/remove_line_item/<int:item_id>', methods=['DELETE'])
@login_required
def remove_line_item(invoice_id, item_id):
    """Remove serial item from invoice"""
    try:
        invoice = InvoiceDocument.query.get_or_404(invoice_id)
        
        # Check permissions
        if invoice.user_id != current_user.id and current_user.role not in ['admin', 'manager']:
            return jsonify({'success': False, 'error': 'Access denied'}), 403
        
        if invoice.status not in ['draft', 'pending_qc']:
            return jsonify({'success': False, 'error': 'Cannot remove items from this invoice status'}), 400
        
        # Find and delete the serial item
        serial_item = InvoiceSerialNumber.query.get_or_404(item_id)
        invoice_line = InvoiceLine.query.get(serial_item.invoice_line_id)
        
        if invoice_line.invoice_id != invoice.id:
            return jsonify({'success': False, 'error': 'Item does not belong to this invoice'}), 400
        
        # Delete serial item and its line
        db.session.delete(serial_item)
        db.session.delete(invoice_line)
        db.session.commit()
        
        logging.info(f"✅ Removed serial item {serial_item.serial_number} from invoice {invoice.id}")
        
        return jsonify({
            'success': True,
            'message': f'Serial item {serial_item.serial_number} removed successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"❌ Error removing serial item: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Internal error: {str(e)}'
        }), 500

@invoice_bp.route('/<int:invoice_id>/clear_all_items', methods=['DELETE'])
@login_required
def clear_all_items(invoice_id):
    """Clear all line items from an invoice"""
    try:
        invoice = InvoiceDocument.query.get_or_404(invoice_id)
        
        # Check permissions
        if invoice.user_id != current_user.id and current_user.role not in ['admin', 'manager']:
            return jsonify({'success': False, 'error': 'Access denied'}), 403
        
        if invoice.status not in ['draft', 'pending_qc']:
            return jsonify({'success': False, 'error': 'Cannot clear items from this invoice status'}), 400
        
        # Count items before deletion
        item_count = len(invoice.lines)
        if item_count == 0:
            return jsonify({'success': False, 'error': 'No items to clear'}), 400
        
        # Delete all invoice lines and their associated serial numbers
        for line in invoice.lines:
            # Delete all serial numbers for this line
            for serial in line.serial_numbers:
                db.session.delete(serial)
            # Delete the line itself
            db.session.delete(line)
        
        # Reset customer information when clearing all items
        invoice.customer_code = None
        invoice.customer_name = None
        
        db.session.commit()
        
        logging.info(f"✅ Cleared all {item_count} items from invoice {invoice.id} for user {current_user.username}")
        
        return jsonify({
            'success': True,
            'message': f'All {item_count} items cleared successfully',
            'items_cleared': item_count
        })
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"❌ Error clearing all items: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Internal error: {str(e)}'
        }), 500

@invoice_bp.route('/create_draft', methods=['POST'])
@login_required
def create_draft_invoice():
    """Create a new draft invoice for line-by-line entry"""
    try:
        if not current_user.has_permission('invoice_creation'):
            return jsonify({'success': False, 'error': 'Access denied - Invoice Creation permissions required'}), 403
        
        # Create new draft invoice
        invoice = InvoiceDocument()
        invoice.user_id = current_user.id
        invoice.status = 'draft'
        invoice.doc_date = datetime.now().date()
        invoice.branch_id = current_user.branch_id
        invoice.branch_name = current_user.branch_name
        
        db.session.add(invoice)
        db.session.commit()
        
        logging.info(f"✅ Created new draft invoice {invoice.id} for user {current_user.username}")
        
        return jsonify({
            'success': True,
            'invoice_id': invoice.id,
            'message': 'Draft invoice created successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"❌ Error creating draft invoice: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Internal error: {str(e)}'
        }), 500

@invoice_bp.route('/cleanup_empty_drafts', methods=['POST'])
@login_required
def cleanup_empty_drafts():
    """Clean up empty draft invoices that have no line items"""
    try:
        if not current_user.has_permission('invoice_creation'):
            return jsonify({'success': False, 'error': 'Access denied - Invoice Creation permissions required'}), 403
        
        # Find all draft invoices by this user that have no line items
        empty_drafts = db.session.query(InvoiceDocument).filter(
            InvoiceDocument.user_id == current_user.id,
            InvoiceDocument.status == 'draft',
            ~InvoiceDocument.lines.any()  # No line items
        ).all()
        
        count = 0
        for draft in empty_drafts:
            db.session.delete(draft)
            count += 1
        
        db.session.commit()
        
        logging.info(f"✅ Cleaned up {count} empty draft invoices for user {current_user.username}")
        
        return jsonify({
            'success': True,
            'count': count,
            'message': f'Cleaned up {count} empty draft invoices'
        })
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"❌ Error cleaning up empty drafts: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Internal error: {str(e)}'
        }), 500

@invoice_bp.route('/<int:invoice_id>/submit_for_qc', methods=['POST'])
@login_required
def submit_for_qc(invoice_id):
    """Submit invoice for QC approval"""
    try:
        invoice = InvoiceDocument.query.get_or_404(invoice_id)
        
        # Check permissions
        if invoice.user_id != current_user.id and current_user.role not in ['admin', 'manager']:
            return jsonify({'success': False, 'error': 'Access denied'}), 403
        
        if invoice.status != 'draft':
            return jsonify({'success': False, 'error': 'Invoice must be in draft status'}), 400
        
        # Check if invoice has items
        if not invoice.lines:
            return jsonify({'success': False, 'error': 'Invoice must have at least one line item'}), 400
        
        # Update invoice status and customer
        data = request.get_json()
        if data and data.get('customer_code'):
            invoice.customer_code = data.get('customer_code')
            invoice.customer_name = data.get('customer_name', '')
        
        invoice.status = 'pending_qc'
        db.session.commit()
        
        logging.info(f"✅ Invoice {invoice.id} submitted for QC approval")
        
        return jsonify({
            'success': True,
            'message': 'Invoice submitted for QC approval successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"❌ Error submitting invoice for QC: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Internal error: {str(e)}'
        }), 500

@invoice_bp.route('/<int:invoice_id>/qc_approve', methods=['POST'])
@login_required
def qc_approve_invoice(invoice_id):
    """QC approve invoice and post to SAP B1"""
    try:
        invoice = InvoiceDocument.query.get_or_404(invoice_id)
        
        # Check QC permissions
        if not current_user.has_permission('qc_approval'):
            return jsonify({'success': False, 'error': 'Access denied - QC approval permissions required'}), 403
        
        if invoice.status != 'pending_qc':
            return jsonify({'success': False, 'error': 'Invoice must be pending QC approval'}), 400
        
        # Check if invoice has customer and items
        if not invoice.customer_code:
            return jsonify({'success': False, 'error': 'Invoice must have a customer assigned'}), 400
        
        if not invoice.lines:
            return jsonify({'success': False, 'error': 'Invoice must have line items'}), 400
        
        # Generate SAP B1 Invoice JSON with BPL_IDAssignedToInvoice field
        sap_invoice_data = generate_sap_invoice_json(invoice)
        
        # Add BPL_IDAssignedToInvoice as required for QC approval
        # sap_invoice_data['BPL_IDAssignedToInvoice'] = 5  # ORD-CHENNAI branch
        # sap_invoice_data['BPLName'] = 'ORD-CHENNAI'
        
        print(f"QC Approved Invoice JSON: {sap_invoice_data}")
        # Post to SAP B1
        sap_result = post_invoice_to_sap_b1(sap_invoice_data)
        
        if sap_result['success']:
            # Update invoice with SAP details
            invoice.status = 'posted'
            invoice.sap_doc_entry = sap_result.get('sap_doc_entry')
            invoice.sap_doc_num = sap_result.get('sap_doc_num')
            invoice.sap_response = json.dumps(sap_result.get('sap_response', {}))
            invoice.json_payload = json.dumps(sap_invoice_data)
            
            db.session.commit()
            
            logging.info(f"✅ Invoice {invoice.id} approved and posted to SAP B1 (DocEntry: {sap_result.get('sap_doc_entry')})")
            
            return jsonify({
                'success': True,
                'message': f'Invoice approved and posted to SAP B1 successfully (DocEntry: {sap_result.get("sap_doc_entry")})',
                'sap_doc_entry': sap_result.get('sap_doc_entry'),
                'sap_doc_num': sap_result.get('sap_doc_num')
            })
        else:
            return jsonify({
                'success': False,
                'error': f'SAP B1 posting failed: {sap_result.get("error", "Unknown error")}'
            }), 500
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"❌ Error in QC approval: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Internal error: {str(e)}'
        }), 500

@invoice_bp.route('/<int:invoice_id>/qc_reject', methods=['POST'])
@login_required
def qc_reject_invoice(invoice_id):
    """QC reject invoice"""
    try:
        invoice = InvoiceDocument.query.get_or_404(invoice_id)
        
        # Check QC permissions
        if not current_user.has_permission('qc_approval'):
            return jsonify({'success': False, 'error': 'Access denied - QC approval permissions required'}), 403
        
        if invoice.status != 'pending_qc':
            return jsonify({'success': False, 'error': 'Invoice must be pending QC approval'}), 400
        
        data = request.get_json()
        rejection_reason = data.get('rejection_reason', 'No reason provided')
        
        # Update invoice status
        invoice.status = 'rejected'
        invoice.notes = f"Rejected by QC: {rejection_reason}"
        invoice.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        logging.info(f"✅ Invoice {invoice.id} rejected by QC. Reason: {rejection_reason}")
        
        return jsonify({
            'success': True,
            'message': 'Invoice rejected successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"❌ Error in QC rejection: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Internal error: {str(e)}'
        }), 500


def generate_sap_invoice_json(invoice):
    """Generate SAP B1 Invoice JSON based on invoice line items"""
    try:
        # Group serial numbers by ItemCode and WarehouseCode for proper line grouping
        grouped_items = {}
        print(invoice)
        for line in invoice.lines:
            for serial_item in line.serial_numbers:
                # Create a unique key for grouping: ItemCode + WarehouseCode
                group_key = f"{serial_item.item_code}_{serial_item.warehouse_code}"
                print(group_key)
                if group_key not in grouped_items:
                    grouped_items[group_key] = {
                        'ItemCode': serial_item.item_code,
                        'ItemDescription': serial_item.item_description,
                        'WarehouseCode': serial_item.warehouse_code,
                        'SerialNumbers': []
                    }

                # Just store serials, we'll assign BaseLineNumber later
                grouped_items[group_key]['SerialNumbers'].append({
                    'InternalSerialNumber': serial_item.serial_number,
                    'Quantity': float(serial_item.quantity)
                })

        # Convert grouped items to DocumentLines
        document_lines = []
        base_line_number = 0  # counter for items

        for group_key, item_data in grouped_items.items():
            # Assign same BaseLineNumber for all serials of this item
            for serial in item_data['SerialNumbers']:
                serial['BaseLineNumber'] = base_line_number

            document_lines.append({
                'ItemCode': item_data['ItemCode'],
                'ItemDescription': item_data['ItemDescription'],
                'Quantity': float(len(item_data['SerialNumbers'])),  # Total quantity = number of serials
                'WarehouseCode': item_data['WarehouseCode'],
                # 'TaxCode': item_data['TaxCode'],
                'SerialNumbers': item_data['SerialNumbers']
            })

            base_line_number += 1  # move to next item line

        # Generate SAP B1 Invoice JSON
        sap_invoice = {
            'DocDate': datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
            'DocDueDate': (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
            'BPL_IDAssignedToInvoice': serial_item.bpl_id,#getattr(invoice, 'bpl_id', 5),  # Default to 5 if not set
            'BPLName': serial_item.bpl_name,#getattr(invoice, 'bpl_name', 'ORD-CHENNAI'),
            'CardCode': invoice.customer_code,
            'DocumentLines': document_lines
        }

        logging.info(f"📄 Generated SAP Invoice JSON with {len(document_lines)} document lines for invoice {invoice.id}")
        return sap_invoice

    except Exception as e:
        logging.error(f"❌ Error generating SAP invoice JSON: {str(e)}")
        raise

def post_invoice_to_sap_b1(invoice_data):
    """Post invoice to SAP B1 and return result"""
    try:
        sap = SAPIntegration()
        
        # Check SAP configuration
        if not sap.base_url or not sap.username or not sap.password:
            logging.warning("⚠️ SAP B1 configuration missing - cannot post invoice")
            return {
                'success': False,
                'error': 'SAP B1 configuration missing'
            }
        
        if not sap.ensure_logged_in():
            logging.error("❌ SAP B1 login failed")
            return {
                'success': False,
                'error': 'SAP B1 login failed'
            }
        
        # Post to SAP B1 Invoices endpoint
        url = f"{sap.base_url}/b1s/v1/Invoices"
        
        logging.info(f"📤 Posting invoice to SAP B1: {url}")
        logging.info(f"📄 Invoice data: {json.dumps(invoice_data, indent=2)}")
        
        response = sap.session.post(url, json=invoice_data, timeout=30)
        
        if response.status_code == 201:
            # Success - extract DocEntry and DocNum from response
            sap_response = response.json()
            doc_entry = sap_response.get('DocEntry')
            doc_num = sap_response.get('DocNum')
            
            logging.info(f"✅ Invoice posted successfully to SAP B1 (DocEntry: {doc_entry}, DocNum: {doc_num})")
            
            return {
                'success': True,
                'sap_doc_entry': doc_entry,
                'sap_doc_num': doc_num,
                'sap_response': sap_response
            }
        else:
            error_msg = f"HTTP {response.status_code}: {response.text}"
            logging.error(f"❌ SAP B1 invoice posting failed: {error_msg}")
            print(f"transfer_itemssssssss (repr) --> {repr(invoice_data)}")
            return {
                'success': False,
                'error': error_msg
            }
            
    except Exception as e:
        logging.error(f"❌ Error posting invoice to SAP B1: {str(e)}")
        print(f"transfer_itemaaaaa (repr) --> {repr(invoice_data)}")
        return {
            'success': False,
            'error': str(e)
        }