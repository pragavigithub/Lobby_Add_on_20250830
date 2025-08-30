"""
API Routes for GRPO Dropdown Functionality
Warehouse, Bin Location, and Batch selection endpoints
"""
from flask import jsonify, request
from sap_integration import SAPIntegration
import logging

def register_api_routes(app):
    """Register API routes with the Flask app"""
    
    @app.route('/api/get-warehouses', methods=['GET'])
    def get_warehouses():
        """Get all warehouses for dropdown selection"""
        try:
            sap = SAPIntegration()
            result = sap.get_warehouses_list()
            
            if result.get('success'):
                return jsonify(result)
            else:
                # Return mock data for offline mode
                return jsonify({
                    'success': True,

                })
                
        except Exception as e:
            logging.error(f"Error in get_warehouses API: {str(e)}")
            # Return mock data on error
            return jsonify({
                'success': True,

            })

    @app.route('/api/get-bins', methods=['GET'])
    def get_bins():
        """Get bin locations for a specific warehouse"""
        try:
            warehouse_code = request.args.get('warehouse')
            if not warehouse_code:
                return jsonify({'success': False, 'error': 'Warehouse code required'}), 400
            
            sap = SAPIntegration()
            result = sap.get_bin_locations_list(warehouse_code)
            
            if result.get('success'):
                return jsonify(result)
            else:
                # Return mock data for offline mode
                return jsonify({
                    'success': True,

                })
                
        except Exception as e:
            logging.error(f"Error in get_bins API: {str(e)}")
            # Return mock data on error
            warehouse_code = request.args.get('warehouse', 'WH001')
            return jsonify({
                'success': True,

            })

    @app.route('/api/get-batches', methods=['GET'])
    def get_batches():
        """Get available batches for a specific item using SAP B1 BatchNumberDetails API"""
        try:
            item_code = request.args.get('item_code') or request.args.get('item')
            warehouse_code = request.args.get('warehouse')
            
            if not item_code:
                return jsonify({'success': False, 'error': 'Item code required'}), 400
            
            sap = SAPIntegration()
            # Use the specific SAP B1 API for batch details
            result = sap.get_batch_number_details(item_code)
            
            if result.get('success'):
                return jsonify(result)
        except Exception as e:
            logging.error(f"Error in get_batches API: {str(e)}")
            # Return mock data on error
            item_code = request.args.get('item_code') or request.args.get('item', 'ITEM001')
            return jsonify({
                'success': True,
            })

    @app.route('/api/get-item-name', methods=['GET'])
    def get_item_name():
        """Get item name based on item code from SAP B1"""
        try:
            item_code = request.args.get('item_code')
            if not item_code:
                return jsonify({'success': False, 'error': 'Item code required'}), 400
            
            sap = SAPIntegration()
            
            # Try to get item name from SAP B1
            if sap.ensure_logged_in():
                try:
                    # Use the SAP endpoint provided by user: https://192.168.0.127:50000/b1s/v1/Items?$select=ItemCode,ItemName
                    url = f"{sap.base_url}/b1s/v1/Items"
                    params = {
                        '$filter': f"ItemCode eq '{item_code}'",
                        '$select': 'ItemCode,ItemName'
                    }
                    response = sap.session.get(url, params=params, timeout=10)
                    
                    if response.status_code == 200:
                        data = response.json()
                        items = data.get('value', [])
                        
                        if items and len(items) > 0:
                            item = items[0]
                            item_name = item.get('ItemName') or f'Item {item_code}'
                            
                            logging.info(f"Retrieved item name for {item_code}: {item_name}")
                            return jsonify({
                                'success': True,
                                'item_code': item_code,
                                'item_name': item_name
                            })
                        else:
                            # Item not found in SAP
                            return jsonify({
                                'success': False,
                                'error': f'Item code {item_code} not found in SAP B1'
                            }), 404
                            
                except Exception as sap_error:
                    logging.error(f"Error getting item from SAP: {str(sap_error)}")
                    # Return fallback response
                    return jsonify({
                        'success': True,
                        'item_code': item_code,
                        'item_name': f'Item {item_code}',
                        'fallback': True
                    })
            
            # Return fallback if SAP not available
            return jsonify({
                'success': True,
                'item_code': item_code,
                'item_name': f'Item {item_code}',
                'fallback': True
            })
            
        except Exception as e:
            logging.error(f"Error in get_item_name API: {str(e)}")
            return jsonify({'success': False, 'error': str(e)}), 500