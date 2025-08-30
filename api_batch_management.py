"""
Batch Management API Endpoints
============================

API endpoints for managing batch numbers and stock levels
"""

from flask import jsonify, request
from app import app
# Import SAPIntegration dynamically to avoid circular imports
# from sap_integration import SAPIntegration
import logging

@app.route('/api/get_available_batches/<item_code>')
def get_available_batches(item_code):
    """Get available batches for an item code with stock levels"""
    try:
        from_warehouse = request.args.get('from_warehouse', '')
        
        # Import SAPIntegration dynamically to avoid circular imports
        from sap_integration import SAPIntegration
        sap = SAPIntegration()
        
        # Get batch details from SAP B1
        batches = sap.get_item_batches(item_code)
        print(batches)
        if batches:
            # Filter batches with available stock
            available_batches = []
            for batch in batches:
                if batch.get('Batch', 0) > 0:
                    available_batches.append({
                        'BatchNumber': batch.get('Batch', ''),
                        'ExpiryDate': batch.get('ExpirationDate', ''),
                        'ManufacturingDate': batch.get('ManufacturingDate', ''),

                    })
            
            return jsonify({
                'success': True,
                'batches': available_batches
            })
        else:
            # Return empty batch option for non-batch managed items
            return jsonify({
                'success': True,
                'batches': [{'BatchNumber': '', 'OnHandQuantity': 0, 'ExpiryDate': '', 'ManufacturingDate': '', 'Warehouse': from_warehouse}]
            })
            
    except Exception as e:
        logging.error(f"Error getting available batches for {item_code}: {str(e)}")
        return jsonify({
            'success': False,

        })

@app.route('/api/get_batch_stock/<item_code>/<batch_number>')
def get_batch_stock(item_code, batch_number):
    """Get stock level for a specific batch"""
    try:
        warehouse = request.args.get('warehouse', '')
        
        # Import SAPIntegration dynamically to avoid circular imports
        from sap_integration import SAPIntegration
        sap = SAPIntegration()
        
        # Get specific batch stock from SAP B1
        stock_info = sap.get_batch_stock(item_code, batch_number, warehouse)
        
        if stock_info:
            return jsonify({
                'success': True,
                'stock': stock_info.get('OnHandQuantity', 0),
                'warehouse': stock_info.get('Warehouse', warehouse),
                'expiry_date': stock_info.get('ExpiryDate', ''),
                'manufacturing_date': stock_info.get('ManufacturingDate', '')
            })
        else:
            return jsonify({
                'success': False,
                'error': f'Batch {batch_number} not found for item {item_code}',
                'stock': 0
            })
            
    except Exception as e:
        logging.error(f"Error getting batch stock for {item_code}/{batch_number}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'stock': 0
        })

@app.route('/api/validate_batch_quantity')
def validate_batch_quantity():
    """Validate if requested quantity is available in batch"""
    try:
        item_code = request.args.get('item_code', '')
        batch_number = request.args.get('batch_number', '')
        warehouse = request.args.get('warehouse', '')
        requested_qty = float(request.args.get('quantity', 0))
        
        # Import SAPIntegration dynamically to avoid circular imports
        from sap_integration import SAPIntegration
        sap = SAPIntegration()
        
        # Get batch stock
        stock_info = sap.get_batch_stock(item_code, batch_number, warehouse)
        
        if stock_info:
            available_qty = float(stock_info.get('OnHandQuantity', 0))
            
            return jsonify({
                'success': True,
                'valid': requested_qty <= available_qty,
                'available_quantity': available_qty,
                'requested_quantity': requested_qty,
                'message': f'Available: {available_qty}, Requested: {requested_qty}'
            })
        else:
            return jsonify({
                'success': False,
                'valid': False,
                'error': f'Batch {batch_number} not found',
                'available_quantity': 0,
                'requested_quantity': requested_qty
            })
            
    except Exception as e:
        logging.error(f"Error validating batch quantity: {str(e)}")
        return jsonify({
            'success': False,
            'valid': False,
            'error': str(e),
            'available_quantity': 0,
            'requested_quantity': 0
        })