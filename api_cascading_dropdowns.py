"""
Cascading Dropdown API Routes for GRPO
Provides warehouses, bin locations, and batch data for dynamic dropdowns
"""
from flask import jsonify, request
from app import app
from flask_login import login_required
from sap_integration import SAPIntegration
import logging

@app.route('/api/warehouses', methods=['GET'])
@login_required
def cascading_get_warehouses():
    """Get all available warehouses"""
    try:
        sap = SAPIntegration()
        
        # Try to get warehouses from SAP B1
        if sap.ensure_logged_in():
            try:
                url = f"{sap.base_url}/b1s/v1/Warehouses"
                response = sap.session.get(url, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    warehouses = data.get('value', [])
                    logging.info(f"Retrieved {len(warehouses)} warehouses from SAP B1")
                    return jsonify({
                        'success': True,
                        'warehouses': warehouses
                    })
            except Exception as e:
                logging.error(f"Error getting warehouses from SAP: {str(e)}")
        
        # Return mock data for offline mode or on error
        return jsonify({
            'success': True,

        })
            
    except Exception as e:
        logging.error(f"Error in get_warehouses API: {str(e)}")
        # Return fallback data on error
        return jsonify({
            'success': True,
            'warehouses': [
                {'WarehouseCode': 'WH001', 'WarehouseName': 'Main Warehouse'},
                {'WarehouseCode': 'WH002', 'WarehouseName': 'Secondary Warehouse'}
            ]
        })

@app.route('/api/bin-locations', methods=['GET'])
@login_required
def cascading_get_bin_locations():
    """Get bin locations for a specific warehouse"""
    try:
        warehouse_code = request.args.get('warehouse')
        if not warehouse_code:
            return jsonify({'success': False, 'error': 'Warehouse code required'}), 400
        
        sap = SAPIntegration()
        
        # Try to get bin locations from SAP B1
        if sap.ensure_logged_in():
            try:
                url = f"{sap.base_url}/b1s/v1/BinLocations?$filter=Warehouse eq '{warehouse_code}'"
                response = sap.session.get(url, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    bins = data.get('value', [])
                    logging.info(f"Retrieved {len(bins)} bin locations for warehouse {warehouse_code}")
                    return jsonify({
                        'success': True,
                        'bins': bins
                    })
            except Exception as e:
                logging.error(f"Error getting bin locations from SAP: {str(e)}")
        
        # Return mock data for offline mode or on error
        return jsonify({
            'success': True,

        })
            
    except Exception as e:
        logging.error(f"Error in get_bin_locations API: {str(e)}")
        warehouse_code = request.args.get('warehouse', 'WH001')
        return jsonify({
            'success': True,
            'bins': [

            ]
        })

@app.route('/api/batches', methods=['GET'])
@login_required
def cascading_get_batches():
    """Get batches for a specific item code and optionally warehouse"""
    try:
        item_code = request.args.get('item_code')
        warehouse_code = request.args.get('warehouse')
        
        if not item_code:
            return jsonify({'success': False, 'error': 'Item code is required'}), 400
        
        sap = SAPIntegration()
        
        # Try to get batches from SAP B1
        if sap.ensure_logged_in():
            try:
                # Use BatchNumberDetails API to get batch information
                url = f"{sap.base_url}/b1s/v1/BatchNumberDetails?$filter=ItemCode eq '{item_code}'"
                if warehouse_code:
                    url += f" and WarehouseCode eq '{warehouse_code}'"
                
                response = sap.session.get(url, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    batches = data.get('value', [])
                    
                    # Format batch data for dropdown using correct SAP B1 field names
                    formatted_batches = []
                    for batch in batches:
                        expiry_date = batch.get('ExpirationDate')
                        if expiry_date:
                            # Format date from SAP (remove time part if present)
                            expiry_date = expiry_date.split('T')[0] if 'T' in expiry_date else expiry_date
                        
                        formatted_batches.append({
                            'BatchNumber': batch.get('Batch'),  # SAP B1 uses 'Batch' not 'BatchNumber'
                            'Quantity': batch.get('Quantity', 0),
                            'ExpiryDate': expiry_date,  # Use ExpiryDate for consistency
                            'ItemCode': batch.get('ItemCode', item_code),
                            'Status': batch.get('Status', 'bdsStatus_Released')
                        })
                    
                    logging.info(f"Retrieved {len(formatted_batches)} batches for item {item_code}")
                    return jsonify({
                        'success': True,
                        'batches': formatted_batches
                    })
            except Exception as e:
                logging.error(f"Error getting batches from SAP: {str(e)}")
        
        # Return mock data for offline mode or on error
        import datetime
        future_date = (datetime.datetime.now() + datetime.timedelta(days=365)).strftime('%Y-%m-%d')
        
        return jsonify({
            'success': True,

        })
            
    except Exception as e:
        logging.error(f"Error in get_batches API: {str(e)}")
        item_code = request.args.get('item_code', 'ITEM001')
        # Return fallback data on error
        return jsonify({
            'success': True,
            'batches': [
                {'BatchNumber': f'BATCH-{item_code}-001', 'Quantity': 100, 'ExpiryDate': '2025-12-31'}
            ]
        })