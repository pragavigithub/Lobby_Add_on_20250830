"""
Enhanced SAP B1 Bin Scanning Integration
Fix for get_bin_items function with proper OnStock/OnHand API calls
"""
import logging

def get_bin_items_enhanced(self, bin_code):
    """Get items in a specific bin location with OnStock/OnHand details
    
    Uses the exact API pattern provided by user:
    1. BinLocations API to get bin info
    2. Warehouses API to get warehouse details
    3. BatchNumberDetails API to get batch items
    4. ItemWhsStock API to get OnHand/OnStock quantities
    """
    if not self.ensure_logged_in():
        # Return mock data for offline mode
        logging.warning(f"SAP B1 not available, returning mock bin data for {bin_code}")
        return []

    try:
        # Step 1: Get bin information using provided API pattern
        bin_info_url = f"{self.base_url}/b1s/v1/BinLocations?$filter=BinCode eq '{bin_code}'"
        logging.info(f"🔍 Getting bin info: {bin_info_url}")
        
        bin_response = self.session.get(bin_info_url)
        if bin_response.status_code != 200:
            logging.warning(f"Bin {bin_code} not found in SAP B1")
            return []

        bin_data = bin_response.json().get('value', [])
        if not bin_data:
            logging.warning(f"Bin {bin_code} does not exist")
            return []

        bin_info = bin_data[0]
        warehouse_code = bin_info.get('Warehouse', '')
        abs_entry = bin_info.get('AbsEntry', 0)
        
        logging.info(f"✅ Found bin {bin_code} in warehouse {warehouse_code} (AbsEntry: {abs_entry})")

        # Step 2: Get warehouse details using provided API pattern
        warehouse_url = f"{self.base_url}/b1s/v1/Warehouses?$select=BusinessPlaceID,WarehouseCode,DefaultBin&$filter=WarehouseCode eq '{warehouse_code}'"
        logging.info(f"🔍 Getting warehouse info: {warehouse_url}")
        
        warehouse_response = self.session.get(warehouse_url)
        if warehouse_response.status_code != 200:
            logging.error(f"Failed to get warehouse info: {warehouse_response.status_code}")
            return []

        warehouse_data = warehouse_response.json().get('value', [])
        if not warehouse_data:
            logging.warning(f"Warehouse {warehouse_code} not found")
            return []
            
        warehouse_info = warehouse_data[0]
        business_place_id = warehouse_info.get('BusinessPlaceID', 0)
        default_bin = warehouse_info.get('DefaultBin', 0)
        
        logging.info(f"✅ Warehouse {warehouse_code} - BusinessPlaceID: {business_place_id}, DefaultBin: {default_bin}")

        # Step 3: Get batch details using provided API pattern
        # Use the AbsEntry from bin info as SystemNumber
        batch_url = f"{self.base_url}/b1s/v1/BatchNumberDetails?$filter=SystemNumber eq {abs_entry}"
        logging.info(f"🔍 Getting batch details: {batch_url}")
        
        batch_response = self.session.get(batch_url)
        if batch_response.status_code != 200:
            logging.warning(f"No batch data found for SystemNumber {abs_entry}")
            # Try alternative approach with DefaultBin
            batch_url = f"{self.base_url}/b1s/v1/BatchNumberDetails?$filter=SystemNumber eq {default_bin}"
            logging.info(f"🔍 Trying alternative batch lookup: {batch_url}")
            batch_response = self.session.get(batch_url)

        formatted_items = []
        
        if batch_response.status_code == 200:
            batch_data = batch_response.json().get('value', [])
            logging.info(f"📦 Found {len(batch_data)} batch items")
            
            for batch_item in batch_data:
                item_code = batch_item.get('ItemCode', '')
                if not item_code:
                    continue
                    
                # Step 4: Get OnHand/OnStock quantities for each item
                # Using ItemWhsStock API to get warehouse-specific stock levels
                stock_url = f"{self.base_url}/b1s/v1/ItemWhsStock?$filter=ItemCode eq '{item_code}' and WarehouseCode eq '{warehouse_code}'"
                try:
                    stock_response = self.session.get(stock_url)
                    on_hand = 0.0
                    on_stock = 0.0
                    uom = 'EA'
                    
                    if stock_response.status_code == 200:
                        stock_data = stock_response.json().get('value', [])
                        if stock_data:
                            stock_info = stock_data[0]
                            on_hand = float(stock_info.get('OnHand', 0.0))
                            on_stock = float(stock_info.get('OnStock', 0.0))
                            
                    # Get item master data for UoM and updated name
                    item_url = f"{self.base_url}/b1s/v1/Items('{item_code}')?$select=ItemCode,ItemName,InventoryUOM"
                    item_response = self.session.get(item_url)
                    item_name = batch_item.get('ItemDescription', '')
                    
                    if item_response.status_code == 200:
                        item_data = item_response.json()
                        item_name = item_data.get('ItemName', item_name)
                        uom = item_data.get('InventoryUOM', 'EA')
                    
                    formatted_items.append({
                        'ItemCode': item_code,
                        'ItemName': item_name,
                        'OnHand': on_hand,
                        'OnStock': on_stock,
                        'UoM': uom,
                        'BatchNumber': batch_item.get('Batch', ''),
                        'ExpiryDate': batch_item.get('ExpirationDate', ''),
                        'AdmissionDate': batch_item.get('AdmissionDate', ''),
                        'ManufacturingDate': batch_item.get('ManufacturingDate', ''),
                        'Status': batch_item.get('Status', ''),
                        'Warehouse': warehouse_code,
                        'BinCode': bin_code,
                        'BinAbsEntry': abs_entry,
                        'BusinessPlaceID': business_place_id
                    })
                    
                except Exception as e:
                    logging.error(f"Error getting stock data for item {item_code}: {e}")
                    continue
        else:
            logging.warning(f"No batch data found for bin {bin_code}")

        logging.info(f"✅ Found {len(formatted_items)} items in bin {bin_code}")
        return formatted_items

    except Exception as e:
        logging.error(f"❌ Error getting bin items: {str(e)}")
        return []


# Apply this fix to the existing SAPIntegration class
def apply_bin_scanning_fix():
    """Apply the enhanced bin scanning fix to existing SAP integration"""
    try:
        # Import sap_integration dynamically to avoid circular imports
        import sys
        if 'sap_integration' in sys.modules:
            sap_integration = sys.modules['sap_integration']
        else:
            import sap_integration
        
        # Replace the get_bin_items method with the enhanced version
        sap_integration.SAPIntegration.get_bin_items = get_bin_items_enhanced
        print("✅ Applied enhanced bin scanning fix to SAP integration")
    except Exception as e:
        print(f"⚠️ Could not apply bin scanning fix: {e}")


if __name__ == "__main__":
    apply_bin_scanning_fix()