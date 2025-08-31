import requests
import json
import logging
import os
from datetime import datetime
import urllib.parse
import urllib3
from flask import jsonify

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class SAPIntegration:

    def __init__(self):
        # Use environment variables directly to avoid circular import
        self.base_url = os.environ.get('SAP_B1_SERVER', '')
        self.username = os.environ.get('SAP_B1_USERNAME', '')
        self.password = os.environ.get('SAP_B1_PASSWORD', '')
        self.company_db = os.environ.get('SAP_B1_COMPANY_DB', '')
        self.session_id = None
        self.session = requests.Session()
        self.session.verify = False  # For development, in production use proper SSL
        self.is_offline = False

        # Cache for frequently accessed data
        self._warehouse_cache = {}
        self._bin_cache = {}
        self._bin_location_cache = {}  # Cache for BinLocations API
        self._branch_cache = {}
        self._item_cache = {}
        self._batch_cache = {}

    def login(self):
        """Login to SAP B1 Service Layer"""
        # Check if SAP configuration exists
        if not self.base_url or not self.username or not self.password or not self.company_db:
            logging.warning(
                "SAP B1 configuration not complete. Running in offline mode.")
            return False

        login_url = f"{self.base_url}/b1s/v1/Login"
        login_data = {
            "UserName": self.username,
            "Password": self.password,
            "CompanyDB": self.company_db
        }

        try:
            response = self.session.post(login_url,
                                         json=login_data,
                                         timeout=30)
            if response.status_code == 200:
                self.session_id = response.json().get('SessionId')
                logging.info("Successfully logged in to SAP B1")
                return True
            else:
                logging.warning(
                    f"SAP B1 login failed: {response.text}. Running in offline mode."
                )
                return False
        except Exception as e:
            logging.warning(
                f"SAP B1 login error: {str(e)}. Running in offline mode.")
            self.is_offline = True
            return False

    def ensure_logged_in(self):
        """Ensure we have a valid session"""
        if not self.session_id:
            return self.login()
        return True

    def get_business_partners(self):
        """
        Get business partners from SAP B1 for invoice creation
        Returns list of business partners with CardCode and CardName
        """
        if not self.login():
            return None

        try:
            headers = {
                'Cookie': f'B1SESSION={self.session_id}',
                'Content-Type': 'application/json',
                'Prefer': 'odata.maxpagesize=0'
            }

            url = f"{self.base_url}/b1s/v1/BusinessPartners?$select=CardCode,CardName"

            response = requests.get(url, headers=headers, verify=False, timeout=30)
            response.raise_for_status()

            data = response.json()
            business_partners = data.get('value', [])

            logging.info(f"✅ Retrieved {len(business_partners)} business partners from SAP B1")
            return business_partners

        except Exception as e:
            logging.error(f"❌ Failed to get business partners: {e}")
            return None

    def get_inventory_transfer_request(self, doc_num):
        """Get specific inventory transfer request from SAP B1"""
        if not self.ensure_logged_in():
            logging.warning(
                "SAP B1 not available, returning mock transfer request for validation"
            )
            # Return mock data for offline mode to allow testing based on your real data
            return {

            }

        try:
            # Try multiple endpoints to find the transfer request
            endpoints_to_try = [
                f"InventoryTransferRequests?$filter=DocNum eq {doc_num}",
                f"InventoryTransferRequests?$filter=DocNum eq '{doc_num}'",
                f"StockTransfers?$filter=DocNum eq {doc_num}",
                f"StockTransfers?$filter=DocNum eq '{doc_num}'"
            ]

            for endpoint in endpoints_to_try:
                url = f"{self.base_url}/b1s/v1/{endpoint}"
                logging.info(f"🔍 Trying SAP B1 API: {url}")

                response = self.session.get(url)
                logging.info(f"📡 Response status: {response.status_code}")

                if response.status_code == 200:
                    data = response.json()
                    transfers = data.get('value', [])
                    logging.info(
                        f"📦 Found {len(transfers)} transfer requests for DocNum {doc_num}"
                    )

                    if transfers:
                        transfer_data = transfers[0]
                        doc_status = transfer_data.get(
                            'DocumentStatus',
                            transfer_data.get('DocStatus', ''))
                        logging.info(
                            f"✅ Transfer request found: {transfer_data.get('DocNum')} - Status: {doc_status}"
                        )

                        # Normalize the response structure for consistent access
                        if 'StockTransferLines' not in transfer_data and 'DocumentLines' in transfer_data:
                            transfer_data[
                                'StockTransferLines'] = transfer_data[
                                    'DocumentLines']

                        # Ensure consistent status field
                        if 'DocumentStatus' in transfer_data and 'DocStatus' not in transfer_data:
                            transfer_data['DocStatus'] = transfer_data[
                                'DocumentStatus']

                        # Log the full structure for debugging
                        logging.info(
                            f"📋 Transfer Data: DocNum={transfer_data.get('DocNum')}, FromWarehouse={transfer_data.get('FromWarehouse')}, ToWarehouse={transfer_data.get('ToWarehouse')}"
                        )

                        return transfer_data
                    else:
                        logging.info(f"No results from endpoint: {endpoint}")
                        continue
                else:
                    logging.warning(
                        f"API call failed for {endpoint}: {response.status_code}"
                    )
                    continue

            # If no endpoint worked, return None
            logging.warning(
                f"❌ No transfer request found for DocNum {doc_num} in any endpoint"
            )
            return None

        except Exception as e:
            logging.error(
                f"❌ Error getting inventory transfer request: {str(e)}")
            return None

    def get_bins(self, warehouse_code):
        """Get bins for a specific warehouse"""
        if not self.ensure_logged_in():
            return []

        try:
            url = f"{self.base_url}/b1s/v1/BinLocations?$filter=Warehouse eq '{warehouse_code}'"
            response = self.session.get(url)

            if response.status_code == 200:
                data = response.json()
                bins = data.get('value', [])

                # Transform the data to match our expected format
                formatted_bins = []
                for bin_data in bins:
                    formatted_bins.append({
                        'BinCode':
                        bin_data.get('BinCode'),
                        'Description':
                        bin_data.get('Description', ''),
                        'Warehouse':
                        bin_data.get('Warehouse'),
                        'Active':
                        bin_data.get('Active', 'Y')
                    })

                return formatted_bins
            else:
                logging.error(f"Failed to get bins: {response.status_code}")
                return []
        except Exception as e:
            logging.error(f"Error getting bins: {str(e)}")
            return []

    def get_purchase_order(self, po_number):
        """Get purchase order details from SAP B1"""
        if not self.ensure_logged_in():
            # Return mock data for offline mode
            return {

            }

        url = f"{self.base_url}/b1s/v1/PurchaseOrders?$filter=DocNum eq {po_number}"

        try:
            response = self.session.get(url, timeout=30)
            if response.status_code == 200:
                data = response.json()
                if data['value']:
                    return data['value'][0]
            return None
        except Exception as e:
            logging.warning(
                f"Error fetching PO {po_number}: {str(e)}. Using offline mode."
            )
            # Return mock data on error
            return {

            }

    def get_purchase_order_items(self, po_number):
        """Get purchase order line items"""
        try:
            po_data = self.get_purchase_order(po_number)
            if po_data:
                return po_data.get('DocumentLines', [])
        except Exception as e:
            logging.warning(
                f"Unable to fetch PO items for {po_number}: {str(e)}. Running in offline mode."
            )
        return []

    def get_item_master(self, item_code):
        """Get item master data from SAP B1"""
        if not self.ensure_logged_in():
            return None

        url = f"{self.base_url}/b1s/v1/Items('{item_code}')"

        try:
            response = self.session.get(url)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            logging.error(f"Error fetching item {item_code}: {str(e)}")
            return None

    def get_warehouse_bins(self, warehouse_code):
        """Get bins for a warehouse"""
        if not self.ensure_logged_in():
            return []

        url = f"{self.base_url}/b1s/v1/BinLocations?$filter=WhsCode eq '{warehouse_code}'"

        try:
            response = self.session.get(url)
            if response.status_code == 200:
                data = response.json()
                return data.get('value', [])
            return []
        except Exception as e:
            logging.error(
                f"Error fetching bins for warehouse {warehouse_code}: {str(e)}"
            )
            return []

    def get_bin_items(self, bin_code):
        """Enhanced bin scanning with detailed item information using your exact API patterns"""
        if not self.ensure_logged_in():
            logging.warning("SAP B1 not available, returning mock bin data")
            return self._get_mock_bin_items(bin_code)

        try:
            logging.info(f"🔍 Enhanced bin scanning for: {bin_code}")

            # Step 1: Get bin information using your exact API pattern
            bin_info_url = f"{self.base_url}/b1s/v1/BinLocations?$filter=BinCode eq '{bin_code}'"
            logging.debug(f"[DEBUG] Calling URL: {bin_info_url}")
            bin_response = self.session.get(bin_info_url)
            logging.debug(f"[DEBUG] Status code: {bin_response.status_code}")

            if bin_response.status_code != 200:
                logging.warning(f"❌ Bin {bin_code} not found: {bin_response.status_code}")
                return []

            bin_data = bin_response.json().get('value', [])
            if not bin_data:
                logging.warning(f"❌ Bin {bin_code} does not exist")
                return []

            bin_info = bin_data[0]
            warehouse_code = bin_info.get('Warehouse', '')
            abs_entry = bin_info.get('AbsEntry', 0)

            logging.info(f"✅ Found bin {bin_code} in warehouse {warehouse_code} (AbsEntry: {abs_entry})")

            # Step 2: Get warehouse business place info using your exact API pattern
            warehouse_info_url = (f"{self.base_url}/b1s/v1/Warehouses?"
                                f"$select=BusinessPlaceID,WarehouseCode,DefaultBin&"
                                f"$filter=WarehouseCode eq '{warehouse_code}'")
            logging.debug(f"[DEBUG] Calling URL: {warehouse_info_url}")
            warehouse_response = self.session.get(warehouse_info_url)
            logging.debug(f"[DEBUG] Status code: {warehouse_response.status_code}")

            business_place_id = 0
            if warehouse_response.status_code == 200:
                warehouse_data = warehouse_response.json().get('value', [])
                if warehouse_data:
                    business_place_id = warehouse_data[0].get('BusinessPlaceID', 0)
                    logging.info(f"✅ Warehouse {warehouse_code} BusinessPlaceID: {business_place_id}")

            # Step 3: Get warehouse items using your exact crossjoin API pattern
            crossjoin_url = (f"{self.base_url}/b1s/v1/$crossjoin(Items,Items/ItemWarehouseInfoCollection)?"
                           f"$expand=Items($select=ItemCode,ItemName,QuantityOnStock),"
                           f"Items/ItemWarehouseInfoCollection($select=InStock,Ordered,StandardAveragePrice)&"
                           f"$filter=Items/ItemCode eq Items/ItemWarehouseInfoCollection/ItemCode and "
                           f"Items/ItemWarehouseInfoCollection/WarehouseCode eq '{warehouse_code}'")

            logging.debug(f"[DEBUG] Calling URL: {crossjoin_url}")
            headers = {"Prefer": "odata.maxpagesize=300"}
            crossjoin_response = self.session.get(crossjoin_url,headers=headers)
            logging.debug(f"[DEBUG] Status code: {crossjoin_response.status_code}")
            logging.debug(f"[DEBUG] Response text: {crossjoin_response.text[:300]}")

            if crossjoin_response.status_code != 200:
                logging.error(f"❌ Failed to get warehouse items: {crossjoin_response.status_code}")
                return []

            # Step 4: Process crossjoin results and enhance with batch details
            formatted_items = []
            crossjoin_data = crossjoin_response.json().get('value', [])

            logging.info(f"📦 Found {len(crossjoin_data)} items in warehouse {warehouse_code}")

            for item_data in crossjoin_data:
                try:
                    item_info = item_data.get('Items', {})
                    warehouse_info = item_data.get('Items/ItemWarehouseInfoCollection', {})

                    item_code = item_info.get('ItemCode', '')
                    if not item_code:
                        continue

                    # Step 5: Get batch details for this item using your exact API pattern
                    batch_details = self._get_item_batch_details(item_code)

                    # Skip items with zero InStock quantity
                    in_stock_qty = float(warehouse_info.get('InStock', 0))
                    if in_stock_qty <= 0:
                        logging.debug(f"⏭️ Skipping item {item_code} - InStock quantity is {in_stock_qty}")
                        continue

                    # Create enhanced item record with all details
                    enhanced_item = {
                        'ItemCode': item_code,
                        'ItemName': item_info.get('ItemName', ''),
                        'UoM': item_info.get('InventoryUoM', ''),
                        'QuantityOnStock': float(item_info.get('QuantityOnStock', 0)),
                        'OnHand': in_stock_qty,
                        'OnStock': in_stock_qty,
                        'InStock': in_stock_qty,
                        'Ordered': float(warehouse_info.get('Ordered', 0)),
                        'StandardAveragePrice': float(warehouse_info.get('StandardAveragePrice', 0)),
                        'WarehouseCode': warehouse_code,
                        'Warehouse': warehouse_code,
                        'BinCode': bin_code,
                        'BinAbsEntry': abs_entry,
                        'BusinessPlaceID': business_place_id,
                        'BatchDetails': batch_details
                    }

                    # Add batch summary for display
                    if batch_details:
                        enhanced_item['BatchCount'] = len(batch_details)
                        enhanced_item['BatchNumbers'] = [b.get('Batch', '') for b in batch_details]
                        enhanced_item['ExpiryDates'] = [b.get('ExpirationDate') for b in batch_details if b.get('ExpirationDate')]
                        enhanced_item['AdmissionDates'] = [b.get('AdmissionDate') for b in batch_details if b.get('AdmissionDate')]
                        # Use first batch info for main display
                        if batch_details:
                            first_batch = batch_details[0]
                            enhanced_item['BatchNumber'] = first_batch.get('Batch', '')
                            enhanced_item['Batch'] = first_batch.get('Batch', '')
                            enhanced_item['Status'] = first_batch.get('Status', 'bdsStatus_Released')
                            enhanced_item['AdmissionDate'] = first_batch.get('AdmissionDate', '')
                            enhanced_item['ExpirationDate'] = first_batch.get('ExpirationDate', '')
                            enhanced_item['ExpiryDate'] = first_batch.get('ExpirationDate', '')
                    else:
                        enhanced_item['BatchCount'] = 0
                        enhanced_item['BatchNumbers'] = []
                        enhanced_item['ExpiryDates'] = []
                        enhanced_item['AdmissionDates'] = []
                        enhanced_item['BatchNumber'] = ''
                        enhanced_item['Batch'] = ''
                        enhanced_item['Status'] = 'No Batch'
                        enhanced_item['AdmissionDate'] = ''
                        enhanced_item['ExpirationDate'] = ''
                        enhanced_item['ExpiryDate'] = ''

                    # Add legacy fields for compatibility
                    enhanced_item['Quantity'] = enhanced_item['OnHand']
                    enhanced_item['ItemDescription'] = enhanced_item['ItemName']

                    formatted_items.append(enhanced_item)

                    logging.debug(f"✅ Enhanced item: {item_code} - OnHand: {enhanced_item['OnHand']}, Batches: {enhanced_item['BatchCount']}")

                except Exception as item_error:
                    logging.error(f"❌ Error processing item: {str(item_error)}")
                    continue

            logging.info(f"🎯 Successfully enhanced {len(formatted_items)} items for bin {bin_code}")
            return formatted_items

        except Exception as e:
            logging.error(f"❌ Error in enhanced bin scanning: {str(e)}")
            return []

    def _get_item_batch_details(self, item_code):
        """Get batch details for a specific item using your exact BatchNumberDetails API pattern"""
        try:
            batch_url = f"{self.base_url}/b1s/v1/BatchNumberDetails?$filter=ItemCode eq '{item_code}'"
            logging.debug(f"[DEBUG] Getting batch details for {item_code}")

            batch_response = self.session.get(batch_url)
            if batch_response.status_code == 200:
                batch_data = batch_response.json().get('value', [])
                logging.debug(f"✅ Found {len(batch_data)} batches for item {item_code}")
                return batch_data
            else:
                logging.debug(f"⚠️ No batch details found for item {item_code}")
                return []

        except Exception as e:
            logging.error(f"❌ Error getting batch details for {item_code}: {str(e)}")
            return []

    def _get_mock_bin_items(self, bin_code):
        """Mock data for offline mode with enhanced structure matching your API responses"""
        # Only return items with InStock > 0 to match the filtering logic
        return [
            {
            }
        ]

    def get_available_bins(self, warehouse_code):
        """Get available bins for a warehouse"""
        if not self.ensure_logged_in():
            # Return fallback bins if SAP is not available
            return []

        try:
            # Get bins from SAP B1
            url = f"{self.base_url}/b1s/v1/BinLocations"
            params = {
                '$filter': f"Warehouse eq '{warehouse_code}' and Active eq 'Y'"
            }

            response = self.session.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                bins = []
                for bin_data in data.get('value', []):
                    bins.append({
                        'BinCode': bin_data.get('BinCode'),
                        'Description': bin_data.get('Description', '')
                    })
                return bins
            else:
                logging.error(f"Failed to get bins from SAP: {response.text}")
                return []

        except Exception as e:
            logging.error(f"Error getting bins from SAP: {str(e)}")
            return []

    def create_goods_receipt_po(self, grpo_document):
        """Create Goods Receipt PO in SAP B1"""
        if not self.ensure_logged_in():
            # Return success for offline mode
            import random
            return {
                'success': True,
                'error': None,
                'document_number': f'GRPO-{random.randint(100000, 999999)}'
            }

        url = f"{self.base_url}/b1s/v1/PurchaseDeliveryNotes"

        # Get PO data to ensure we have correct supplier code
        po_data = self.get_purchase_order(grpo_document.po_number)
        if not po_data:
            return {
                'success': False,
                'error': f'Purchase Order {grpo_document.po_number} not found'
            }

        supplier_code = po_data.get('CardCode')
        if not supplier_code:
            return {'success': False, 'error': 'Supplier code not found in PO'}

        # Build document lines
        document_lines = []
        for item in grpo_document.items:
            line = {
                "ItemCode": item.item_code,
                "Quantity": item.received_quantity,
                "UnitOfMeasure": item.unit_of_measure,
                "WarehouseCode": "WH01",  # Default warehouse
                "BinCode": item.bin_location
            }

            # Add batch information if available
            if item.batch_number:
                line["BatchNumbers"] = [{
                    "BatchNumber":
                    item.batch_number,
                    "Quantity":
                    item.received_quantity,
                    "ExpiryDate":
                    item.expiration_date.strftime('%Y-%m-%d')
                    if item.expiration_date else None
                }]

            # Add serial numbers if needed
            if item.generated_barcode:
                line["SerialNumbers"] = [{
                    "SerialNumber": item.generated_barcode,
                    "Quantity": 1
                }]

            document_lines.append(line)

        grpo_data = {
            "CardCode": supplier_code,
            "DocDate": grpo_document.created_at.strftime('%Y-%m-%d'),
            "DocumentLines": document_lines,
            "Comments":
            f"Created from WMS GRPO {grpo_document.id} by {grpo_document.user.username}",
            "U_WMS_GRPO_ID":
            str(grpo_document.id)  # Custom field to track WMS document
        }

        try:
            response = self.session.post(url, json=grpo_data)
            if response.status_code == 201:
                result = response.json()
                return {
                    'success': True,
                    'document_number': result.get('DocNum')
                }
            else:
                return {
                    'success': False,
                    'error': f"SAP B1 error: {response.text}"
                }
        except Exception as e:
            logging.error(f"Error creating GRPO in SAP B1: {str(e)}")
            return {'success': False, 'error': str(e)}

    def get_bin_abs_entry(self, bin_code, warehouse_code):
        """Get bin AbsEntry from SAP B1 for bin allocation"""
        if not self.ensure_logged_in():
            return None

        try:
            url = f"{self.base_url}/b1s/v1/BinLocations?$filter=BinCode eq '{bin_code}' and Warehouse eq '{warehouse_code}'"
            response = self.session.get(url)

            if response.status_code == 200:
                bins = response.json().get('value', [])
                if bins:
                    return bins[0].get('AbsEntry')
            return None
        except Exception as e:
            logging.error(
                f"Error getting bin AbsEntry for {bin_code}: {str(e)}")
            return None

    def get_batch_number_details(self, item_code):
        """Get batch number details for a specific item using SAP B1 API - exact endpoint from user"""
        try:
            if not self.session_id:
                login_result = self.login()
                if not login_result:
                    return {'success': False, 'error': 'SAP B1 login failed'}

            # Use the exact API endpoint you provided
            url = f"{self.base_url}/BatchNumberDetails"
            params = {
                '$filter': f"ItemCode eq '{item_code}'"
            }

            headers = {
                'Content-Type': 'application/json',
                'Cookie': f'B1SESSION={self.session_id}'
            }

            logging.info(f"🔍 Fetching batch details for item {item_code} from SAP B1")
            response = requests.get(url, headers=headers, params=params, verify=False, timeout=30)

            if response.status_code == 200:
                data = response.json()
                batches = data.get('value', [])

                logging.info(f"✅ Found {len(batches)} batches for item {item_code}")
                return {
                    'success': True,
                    'batches': batches
                }
            else:
                logging.error(f"❌ Error fetching batch details: {response.status_code} - {response.text}")
                return {'success': False, 'error': f'HTTP {response.status_code}'}

        except Exception as e:
            logging.error(f"Error getting batch number details: {str(e)}")
            return {'success': False, 'error': str(e)}

    def get_batch_numbers(self, item_code):
        """Get batch numbers for specific item from SAP B1 BatchNumberDetails"""
        # Check cache first
        if item_code in self._batch_cache:
            return self._batch_cache[item_code]

        if not self.ensure_logged_in():
            logging.warning(
                f"SAP B1 not available, returning mock batch data for {item_code}"
            )
            # Return mock batch data for offline mode
            mock_batches = [{

            }, {

            }]
            self._batch_cache[item_code] = mock_batches
            return mock_batches

        try:
            url = f"{self.base_url}/b1s/v1/BatchNumberDetails?$filter=ItemCode eq '{item_code}' and Status eq 'bdsStatus_Released'"
            logging.info(f"🔍 Fetching batch numbers from SAP B1: {url}")

            response = self.session.get(url)
            if response.status_code == 200:
                data = response.json()
                batches = data.get('value', [])
                logging.info(
                    f"📦 Found {len(batches)} batch numbers for item {item_code}"
                )

                # Cache the results
                self._batch_cache[item_code] = batches
                return batches
            else:
                logging.warning(
                    f"Failed to fetch batch numbers: {response.status_code} - {response.text}"
                )
                return []
        except Exception as e:
            logging.error(
                f"Error fetching batch numbers for {item_code}: {str(e)}")
            return []

    def get_item_batches(self, item_code):
        """Get available batches for an item with stock information"""
        logging.info(
            f"🔍 Getting batches for item {item_code} in warehouse"
        )

        if not self.ensure_logged_in():
            logging.warning("⚠️ No SAP B1 session - returning mock batch data")
            return self._get_mock_batch_data(item_code)

        try:
            # SAP B1 API to get batch details
            filter_clause = f"ItemCode eq '{item_code}'"
            # if warehouse_code:
            #     filter_clause += f" and Warehouse eq '{warehouse_code}'"

            url = f"{self.base_url}/b1s/v1/BatchNumberDetails?$filter={filter_clause}&$select=Batch,ExpirationDate,ManufacturingDate"

            response = self.session.get(url)

            if response.status_code == 200:
                data = response.json()
                batches = data.get('value', [])
                logging.info(
                    f"✅ Found {len(batches)} batches for item {item_code}")
                return batches
            else:
                logging.error(
                    f"❌ SAP B1 API error getting batches: {response.status_code}"
                )
                return self._get_mock_batch_data(item_code)

        except Exception as e:
            logging.error(f"❌ Error getting batches from SAP B1: {str(e)}")
            return self._get_mock_batch_data(item_code)

    def get_batch_stock(self, item_code, batch_number, warehouse_code):
        """Get stock level for a specific batch"""
        logging.info(
            f"📊 Getting stock for batch {batch_number} of item {item_code}")

        if not self.ensure_logged_in():
            logging.warning("⚠️ No SAP B1 session - returning mock stock data")
            return {

            }

        try:
            filter_clause = f"ItemCode eq '{item_code}'"
            # if warehouse_code:
            #     filter_clause += f" and Warehouse eq '{warehouse_code}'"

            url = f"{self.base_url}/b1s/v1/BatchNumberDetails?$filter={filter_clause}"

            response = self.session.get(url)
            print(response)
            if response.status_code == 200:
                data = response.json()
                batches = data.get('value', [])
                if batches:
                    logging.info(
                        f"✅ Found stock for batch {batch_number}: {batches[0].get('Batch', 0)}"
                    )
                    return batches[0]
                else:
                    logging.warning(
                        f"⚠️ Batch {batch_number} not found for item {item_code}"
                    )
                    return None
            else:
                logging.error(
                    f"❌ SAP B1 API error getting batch stock: {response.status_code}"
                )
                return {
                    'OnHandQuantity': 100,
                    'Warehouse': warehouse_code,
                    'ExpiryDate': '2025-12-31',
                    'ManufacturingDate': '2025-01-01'
                }

        except Exception as e:
            logging.error(f"❌ Error getting batch stock from SAP B1: {str(e)}")
            return {
                'OnHandQuantity': 100,
                'Warehouse': warehouse_code,
                'ExpiryDate': '2025-12-31',
                'ManufacturingDate': '2025-01-01'
            }

    def get_bin_location_details(self, bin_abs_entry):
        """Get warehouse and bin code from BinLocations API by AbsEntry"""
        try:
            # Check cache first
            if bin_abs_entry in self._bin_location_cache:
                return self._bin_location_cache[bin_abs_entry]

            if not self.ensure_logged_in():
                logging.warning("⚠️ SAP B1 not available, returning mock bin location")
                mock_data = {

                }
                self._bin_location_cache[bin_abs_entry] = mock_data
                return mock_data

            # Use the exact API URL format from user's request
            url = f"{self.base_url}/b1s/v1/BinLocations?$select=BinCode,Warehouse&$filter=AbsEntry eq {bin_abs_entry}"

            response = self.session.get(url, timeout=30)

            if response.status_code == 200:
                data = response.json()
                bin_locations = data.get('value', [])

                if bin_locations:
                    bin_location = bin_locations[0]
                    result = {
                        'Warehouse': bin_location.get('Warehouse', ''),
                        'BinCode': bin_location.get('BinCode', ''),
                        'AbsEntry': bin_abs_entry
                    }

                    # Cache the result
                    self._bin_location_cache[bin_abs_entry] = result
                    logging.info(f"✅ Found bin location: {result['Warehouse']} - {result['BinCode']}")
                    return result
                else:
                    logging.warning(f"⚠️ Bin location not found for AbsEntry {bin_abs_entry}")
                    return {
                        'Warehouse': 'Unknown',
                        'BinCode': f'Bin-{bin_abs_entry}',
                        'AbsEntry': bin_abs_entry
                    }
            else:
                logging.error(f"❌ SAP B1 API error getting bin location: {response.status_code}")
                return {
                    'Warehouse': 'Error',
                    'BinCode': f'Bin-{bin_abs_entry}',
                    'AbsEntry': bin_abs_entry
                }

        except Exception as e:
            logging.error(f"❌ Error getting bin location details: {str(e)}")
            return {
                'Warehouse': 'Error',
                'BinCode': f'Bin-{bin_abs_entry}',
                'AbsEntry': bin_abs_entry
            }

    def enhance_pick_list_with_bin_details(self, pick_list_data):
        """Enhance pick list data with bin location details (Warehouse and BinCode)"""
        try:
            if not pick_list_data or 'PickListsLines' not in pick_list_data:
                return pick_list_data

            for line in pick_list_data['PickListsLines']:
                if 'DocumentLinesBinAllocations' in line and line['DocumentLinesBinAllocations']:
                    for bin_allocation in line['DocumentLinesBinAllocations']:
                        bin_abs_entry = bin_allocation.get('BinAbsEntry')
                        if bin_abs_entry:
                            bin_details = self.get_bin_location_details(bin_abs_entry)
                            # Add warehouse and bin code to the bin allocation
                            bin_allocation['Warehouse'] = bin_details.get('Warehouse', 'Unknown')
                            bin_allocation['BinCode'] = bin_details.get('BinCode', f'Bin-{bin_abs_entry}')

            return pick_list_data

        except Exception as e:
            logging.error(f"❌ Error enhancing pick list with bin details: {str(e)}")
            return pick_list_data

    def _get_mock_batch_data(self, item_code):
        """Return mock batch data for offline testing"""
        return []

    def create_inventory_transfer(self, transfer_document):
        """Create Stock Transfer in SAP B1 with correct JSON structure"""
        if not self.ensure_logged_in():
            logging.warning(
                "SAP B1 not available, simulating transfer creation for testing"
            )
            return {
                'success': True,
                'document_number': f'ST-{transfer_document.id}'
            }

        url = f"{self.base_url}/b1s/v1/StockTransfers"

        # Get transfer request data for BaseEntry reference
        transfer_request_data = self.get_inventory_transfer_request(
            transfer_document.transfer_request_number)
        base_entry = transfer_request_data.get(
            'DocEntry') if transfer_request_data else None

        # Build stock transfer lines with enhanced structure
        stock_transfer_lines = []
        for index, item in enumerate(transfer_document.items):
            # Get item details for accurate UoM and pricing
            item_details = self.get_item_details(item.item_code)

            # Use actual item UoM if available
            actual_uom = item_details.get(
                'InventoryUoM',
                item.unit_of_measure) if item_details else item.unit_of_measure

            # Find corresponding line in transfer request for price info
            price = 0
            unit_price = 0
            uom_entry = None
            base_line = index

            if transfer_request_data and 'StockTransferLines' in transfer_request_data:
                for req_line in transfer_request_data['StockTransferLines']:
                    if req_line.get('ItemCode') == item.item_code:
                        price = req_line.get('Price', 0)
                        unit_price = req_line.get('UnitPrice', price)
                        uom_entry = req_line.get('UoMEntry')
                        base_line = req_line.get('LineNum', index)
                        break

            line = {
                "LineNum": index,
                "ItemCode": item.item_code,
                "Quantity": float(item.quantity),
                "WarehouseCode": transfer_document.to_warehouse,
                "FromWarehouseCode": transfer_document.from_warehouse,
                "UoMCode": actual_uom
            }

            # Add BaseEntry and BaseLine if available (reference to transfer request)
            if base_entry:
                line["BaseEntry"] = base_entry
                line["BaseLine"] = base_line
                line["BaseType"] = "1250000001"  # oInventoryTransferRequest

            # Add pricing if available
            if price > 0:
                line["Price"] = price
                line["UnitPrice"] = unit_price

            # Add UoMEntry if available
            if uom_entry:
                line["UoMEntry"] = uom_entry

            # Add batch numbers if present
            if item.batch_number:
                line["BatchNumbers"] = [{
                    "BaseLineNumber": index,
                    "BatchNumberProperty": item.batch_number,
                    "Quantity": float(item.quantity)
                }]

            # Add bin allocation if bins are specified
            # if item.from_bin or item.to_bin:
            #     line["BinAllocation"] = []
            #
            #     if item.from_bin:
            #         line["BinAllocation"].append({
            #             "BinActionType": "batFromWarehouse",
            #             "BinAbsEntry": self.get_bin_abs_entry(item.from_bin, transfer_document.from_warehouse),
            #             "Quantity": float(item.quantity)
            #         })
            #
            #     if item.to_bin:
            #         line["BinAllocation"].append({
            #             "BinActionType": "batToWarehouse",
            #             "BinAbsEntry": self.get_bin_abs_entry(item.to_bin, transfer_document.to_warehouse),
            #             "Quantity": float(item.quantity)
            #         })

            stock_transfer_lines.append(line)

        transfer_data = {
            "DocDate": datetime.now().strftime('%Y-%m-%d'),
            "Comments":
            f"QC Approved WMS Transfer {transfer_document.id} by {transfer_document.qc_approver.username if transfer_document.qc_approver else 'System'}",
            "FromWarehouse": transfer_document.from_warehouse,
            "ToWarehouse": transfer_document.to_warehouse,
            "StockTransferLines": stock_transfer_lines
        }
        print(f"transfer_item (repr) --> {repr(transfer_data)}")
        # Log the JSON payload for debugging
        logging.info(f"📤 Sending stock transfer to SAP B1:")
        logging.info(f"JSON payload: {json.dumps(transfer_data, indent=2)}")

        try:
            response = self.session.post(url, json=transfer_data)
            logging.info(f"📡 SAP B1 response status: {response.status_code}")

            if response.status_code == 201:
                result = response.json()
                logging.info(
                    f"✅ Stock transfer created successfully: {result.get('DocNum')}"
                )
                return {
                    'success': True,
                    'document_number': result.get('DocNum')
                }
            else:
                error_msg = f"SAP B1 error: {response.text}"
                logging.error(
                    f"❌ Failed to create stock transfer: {error_msg}")
                return {'success': False, 'error': error_msg}
        except Exception as e:
            logging.error(
                f"❌ Error creating stock transfer in SAP B1: {str(e)}")
            return {'success': False, 'error': str(e)}

    def create_serial_item_stock_transfer(self, transfer_document):
        """Create Stock Transfer in SAP B1 for Serial Item Transfer"""
        if not self.ensure_logged_in():
            logging.warning(
                "SAP B1 not available, simulating serial item transfer creation for testing"
            )
            return {
                'success': True,
                'document_number': f'SIST-{transfer_document.id}',
                'doc_entry': f'{transfer_document.id}'
            }

        url = f"{self.base_url}/b1s/v1/StockTransfers"

        # Build stock transfer lines for serial items
        stock_transfer_lines = []
        for index, item in enumerate(transfer_document.items):
            line = {
                "LineNum": index,
                "ItemCode": item.item_code,
                "Quantity": 1,  # Serial items always have quantity 1
                "WarehouseCode": transfer_document.to_warehouse,
                "FromWarehouseCode": transfer_document.from_warehouse,
                "UoMCode": "Each"  # Default UoM for serial items
            }

            # Add serial numbers
            if item.serial_number:
                line["SerialNumbers"] = [{
                    "BaseLineNumber": index,
                    "InternalSerialNumber": item.serial_number,
                    "Quantity": 1,
                    "SystemSerialNumber": item.serial_number,
                    # Set date fields to null instead of "None" string
                    "ExpiryDate": None,
                    "ManufactureDate": None,
                    "ReceptionDate": None,
                    "WarrantyStart": None,
                    "WarrantyEnd": None
                }]

            stock_transfer_lines.append(line)

        transfer_data = {
            "DocDate": datetime.now().strftime('%Y-%m-%d'),
            "U_EA_CREATEDBy": transfer_document.user.username,
            "U_EA_Approved": transfer_document.qc_approver.username if transfer_document.qc_approver else transfer_document.user.username,
            "Comments": f"Serial Item Transfer {transfer_document.transfer_number} - Created by {transfer_document.user.username}, Approved by {transfer_document.qc_approver.username if transfer_document.qc_approver else 'System'}",
            "FromWarehouse": transfer_document.from_warehouse,
            "ToWarehouse": transfer_document.to_warehouse,
            "StockTransferLines": stock_transfer_lines
        }

        # Log the JSON payload for debugging
        logging.info(f"📤 Sending serial item stock transfer to SAP B1:")
        logging.info(f"JSON payload: {json.dumps(transfer_data, indent=2)}")

        try:
            response = self.session.post(url, json=transfer_data, timeout=30)
            logging.info(f"📡 SAP B1 response status: {response.status_code}")

            if response.status_code == 201:
                result = response.json()
                logging.info(
                    f"✅ Serial item stock transfer created successfully: {result.get('DocNum')}"
                )
                return {
                    'success': True,
                    'document_number': result.get('DocNum'),
                    'doc_entry': result.get('DocEntry')
                }
            else:
                error_msg = f"SAP B1 error: {response.text}"
                logging.error(
                    f"❌ Failed to create serial item stock transfer: {error_msg}")
                return {'success': False, 'error': error_msg}
        except Exception as e:
            logging.error(
                f"❌ Error creating serial item stock transfer in SAP B1: {str(e)}")
            return {'success': False, 'error': str(e)}

    def get_item_details(self, item_code):
        """Get detailed item information from SAP B1"""
        if not self.ensure_logged_in():
            return {

            }

        try:
            url = f"{self.base_url}/b1s/v1/Items('{item_code}')"
            response = self.session.get(url)

            if response.status_code == 200:
                item_data = response.json()

                # Get UoM details
                uom_group_entry = item_data.get('UoMGroupEntry')
                inventory_uom = item_data.get('InventoryUoM', '')

                return {
                    'ItemCode': item_data.get('ItemCode'),
                    'ItemName': item_data.get('ItemName'),
                    'UoMGroupEntry': uom_group_entry,
                    'UoMCode': inventory_uom,
                    'InventoryUoM': inventory_uom,
                    'DefaultWarehouse': item_data.get('DefaultWarehouse'),
                    'ItemType': item_data.get('ItemType'),
                    'ManageSerialNumbers':
                    item_data.get('ManageSerialNumbers'),
                    'ManageBatchNumbers': item_data.get('ManageBatchNumbers')
                }
            else:
                logging.error(
                    f"Failed to get item details for {item_code}: {response.text}"
                )
                return None
        except Exception as e:
            logging.error(
                f"Error getting item details for {item_code}: {str(e)}")
            return None

    def create_inventory_counting(self, count_document):
        """Create Inventory Counting Document in SAP B1"""
        if not self.ensure_logged_in():
            return {'success': False, 'error': 'Not logged in to SAP B1'}

        url = f"{self.base_url}/b1s/v1/InventoryCountings"

        # Build document lines
        document_lines = []
        for item in count_document.items:
            line = {
                "ItemCode": item.item_code,
                "CountedQuantity": item.counted_quantity,
                "BinCode": count_document.bin_location
            }
            if item.batch_number:
                line["BatchNumber"] = item.batch_number
            document_lines.append(line)

        count_data = {
            "CountDate": datetime.now().strftime('%Y-%m-%d'),
            "CountTime": datetime.now().strftime('%H:%M:%S'),
            "Remarks": f"Created from WMS Count {count_document.id}",
            "InventoryCountingLines": document_lines
        }

        try:
            response = self.session.post(url, json=count_data)
            if response.status_code == 201:
                result = response.json()
                return {
                    'success': True,
                    'document_number': result.get('DocNum')
                }
            else:
                return {
                    'success': False,
                    'error': f"SAP B1 error: {response.text}"
                }
        except Exception as e:
            logging.error(
                f"Error creating inventory counting in SAP B1: {str(e)}")
            return {'success': False, 'error': str(e)}

    def get_pick_lists(self, limit=100, offset=0, status_filter=None, date_filter=None):
        """Get pick lists from SAP B1 focusing on ps_released items, avoiding ps_closed"""
        if not self.ensure_logged_in():
            logging.warning("SAP B1 not available, returning mock pick list data")
            return self._get_mock_pick_lists()

        try:
            # Build filter parameters - focus on ps_released, avoid ps_closed
            filters = []

            # Default to filtering out ps_closed status unless specifically requested
            if status_filter:
                if status_filter != 'ps_Closed':
                    filters.append(f"Status eq '{status_filter}'")
            else:
                # Default: avoid ps_closed items, prefer ps_released
                filters.append(f"Status ne 'ps_Closed'")

            if date_filter:
                filters.append(f"PickDate ge '{date_filter}'")

            filter_clause = " and ".join(filters) if filters else ""

            # Construct URL with OData parameters
            url = f"{self.base_url}/b1s/v1/PickLists"
            if filter_clause:
                url += f"?$filter={filter_clause}"

            logging.info(f"🔍 Fetching pick lists from SAP B1 (avoiding ps_closed): {url}")
            response = self.session.get(url)

            if response.status_code == 200:
                data = response.json()
                pick_lists = data.get('value', [])

                # Additional filtering for ps_released line items
                filtered_pick_lists = []
                for pick_list in pick_lists:
                    # Check if pick list has ps_released line items
                    has_released_items = False
                    pick_list_lines = pick_list.get('PickListsLines', [])
                    for line in pick_list_lines:
                        if line.get('PickStatus') == 'ps_Released':
                            has_released_items = True
                            break

                    # Only include pick lists that have ps_released items
                    if has_released_items or not pick_list_lines:  # Include empty pick lists too
                        filtered_pick_lists.append(pick_list)

                logging.info(f"✅ Found {len(filtered_pick_lists)} pick lists with ps_released items (filtered from {len(pick_lists)} total)")
                return {
                    'success': True,
                    'pick_lists': filtered_pick_lists,
                    'total_count': len(filtered_pick_lists)
                }
            else:
                logging.error(f"❌ Error fetching pick lists: {response.status_code} - {response.text}")
                return {'success': False, 'error': f'HTTP {response.status_code}'}

        except Exception as e:
            logging.error(f"Error getting pick lists from SAP B1: {str(e)}")
            return {'success': False, 'error': str(e)}

    def get_pick_list_by_id(self, absolute_entry):
        """Get specific pick list from SAP B1 by AbsoluteEntry with full line items and bin allocations"""
        if not self.ensure_logged_in():
            logging.warning("SAP B1 not available, using actual SAP data structure for testing")
            # Use the real SAP structure from your attachment for pick list 613
            if absolute_entry == 613:
                # Enhanced mock data with warehouse and bin code details
                mock_pick_list = {

                    }

                # Return enhanced mock data
                return {
                    'success': True,
                    'pick_list': mock_pick_list
                }
            return self._get_mock_pick_list_detail(absolute_entry)

        try:
            url = f"{self.base_url}/b1s/v1/PickLists?$filter=Absoluteentry eq {absolute_entry}"
            logging.info(f"🔍 Fetching pick list {absolute_entry} from SAP B1: {url}")

            response = self.session.get(url)

            if response.status_code == 200:
                data = response.json()
                pick_lists = data.get('value', [])
                if pick_lists:
                    pick_list = pick_lists[0]
                    # Enhance pick list with bin location details (Warehouse and BinCode)
                    enhanced_pick_list = self.enhance_pick_list_with_bin_details(pick_list)
                    logging.info(f"✅ Found pick list {absolute_entry} with {len(enhanced_pick_list.get('PickListsLines', []))} line items (enhanced with bin details)")
                    return {
                        'success': True,
                        'pick_list': enhanced_pick_list
                    }
                else:
                    return {'success': False, 'error': 'Pick list not found'}
            else:
                logging.error(f"❌ Error fetching pick list: {response.status_code} - {response.text}")
                return {'success': False, 'error': f'HTTP {response.status_code}'}

        except Exception as e:
            logging.error(f"Error getting pick list {absolute_entry} from SAP B1: {str(e)}")
            return {'success': False, 'error': str(e)}

    def update_pick_list_status(self, absolute_entry, new_status, picked_quantities=None):
        """Update pick list status and quantities in SAP B1"""
        if not self.ensure_logged_in():
            logging.warning("SAP B1 not available - cannot update pick list")
            return {'success': False, 'error': 'SAP B1 not available'}

        try:
            # First get the current pick list
            pick_list_result = self.get_pick_list_by_id(absolute_entry)
            if not pick_list_result['success']:
                return pick_list_result

            pick_list = pick_list_result['pick_list']

            # Build update payload
            update_data = {
                'Status': new_status
            }

            # Update line quantities if provided
            if picked_quantities:
                lines = pick_list.get('PickListsLines', [])
                for line in lines:
                    line_number = line.get('LineNumber')
                    if line_number in picked_quantities:
                        line['PickedQuantity'] = picked_quantities[line_number]
                        line['PickStatus'] = new_status

                update_data['PickListsLines'] = lines

            url = f"{self.base_url}/b1s/v1/PickLists({absolute_entry})"
            response = self.session.patch(url, json=update_data)

            if response.status_code == 204:
                logging.info(f"✅ Pick list {absolute_entry} updated successfully")
                return {'success': True}
            else:
                logging.error(f"❌ Error updating pick list: {response.status_code} - {response.text}")
                return {'success': False, 'error': f'HTTP {response.status_code}'}

        except Exception as e:
            logging.error(f"Error updating pick list {absolute_entry}: {str(e)}")
            return {'success': False, 'error': str(e)}

    def _get_mock_pick_lists(self):
        """Return mock pick list data for offline/development mode"""
        return {
            'success': True,
            'pick_lists': [
                {
                }]
        }

    def sync_pick_list_to_local_db(self, sap_pick_list, local_pick_list):
        """Sync SAP B1 pick list line items and bin allocations to local database"""
        from app import db
        from models import PickListLine, PickListBinAllocation
        import json

        try:
            # Clear existing lines and bin allocations - Fix for SQLAlchemy join delete issue
            # First get the IDs of bin allocations to delete
            pick_list_line_ids = [line.id for line in PickListLine.query.filter_by(pick_list_id=local_pick_list.id).all()]

            if pick_list_line_ids:
                # Delete bin allocations first (foreign key dependency)
                PickListBinAllocation.query.filter(PickListBinAllocation.pick_list_line_id.in_(pick_list_line_ids)).delete(synchronize_session=False)

                # Then delete pick list lines
                PickListLine.query.filter_by(pick_list_id=local_pick_list.id).delete(synchronize_session=False)

            # Sync PickListsLines from SAP B1 - Focus on ps_released, avoid ps_closed
            sap_lines = sap_pick_list.get('PickListsLines', [])
            for sap_line in sap_lines:
                pick_status = sap_line.get('PickStatus', 'ps_Open')

                # Skip ps_closed items - only sync ps_released and other active statuses
                if pick_status == 'ps_Closed':
                    logging.info(f"⏭️ Skipping ps_Closed line item {sap_line.get('LineNumber', 0)}")
                    continue

                # Prefer ps_released items
                if pick_status == 'ps_Released':
                    logging.info(f"✅ Syncing ps_Released line item {sap_line.get('LineNumber', 0)}")

                # Create PickListLine
                pick_list_line = PickListLine()
                pick_list_line.pick_list_id = local_pick_list.id
                pick_list_line.absolute_entry = sap_line.get('AbsoluteEntry')
                pick_list_line.line_number = sap_line.get('LineNumber', 0)
                pick_list_line.order_entry = sap_line.get('OrderEntry')
                pick_list_line.order_row_id = sap_line.get('OrderRowID')
                pick_list_line.picked_quantity = float(sap_line.get('PickedQuantity', 0))
                pick_list_line.pick_status = pick_status
                pick_list_line.released_quantity = float(sap_line.get('ReleasedQuantity', 0))
                pick_list_line.previously_released_quantity = float(sap_line.get('PreviouslyReleasedQuantity', 0))
                pick_list_line.base_object_type = sap_line.get('BaseObjectType', 17)
                pick_list_line.serial_numbers = json.dumps(sap_line.get('SerialNumbers', []))
                pick_list_line.batch_numbers = json.dumps(sap_line.get('BatchNumbers', []))
                db.session.add(pick_list_line)
                db.session.flush()  # Get the ID

                # Sync DocumentLinesBinAllocations
                bin_allocations = sap_line.get('DocumentLinesBinAllocations', [])
                for bin_allocation in bin_allocations:
                    pick_list_bin_allocation = PickListBinAllocation()
                    pick_list_bin_allocation.pick_list_line_id = pick_list_line.id
                    pick_list_bin_allocation.bin_abs_entry = bin_allocation.get('BinAbsEntry')
                    pick_list_bin_allocation.quantity = float(bin_allocation.get('Quantity', 0))
                    pick_list_bin_allocation.allow_negative_quantity = bin_allocation.get('AllowNegativeQuantity', 'tNO')
                    pick_list_bin_allocation.serial_and_batch_numbers_base_line = bin_allocation.get('SerialAndBatchNumbersBaseLine', 0)
                    pick_list_bin_allocation.base_line_number = bin_allocation.get('BaseLineNumber')
                    db.session.add(pick_list_bin_allocation)

            # Update pick list totals
            total_lines = len(sap_lines)
            picked_lines = len([line for line in sap_lines if line.get('PickStatus') == 'ps_Closed'])

            local_pick_list.total_items = total_lines
            local_pick_list.picked_items = picked_lines

            db.session.commit()
            logging.info(f"✅ Synced {total_lines} lines and bin allocations for pick list {local_pick_list.absolute_entry}")
            return {'success': True, 'synced_lines': total_lines}

        except Exception as e:
            db.session.rollback()
            logging.error(f"❌ Error syncing pick list to local DB: {str(e)}")
            return {'success': False, 'error': str(e)}

    def _get_mock_pick_list_detail(self, absolute_entry):
        """Return mock pick list detail for development"""
        return {
            'success': True,
            'pick_list': {

            }
        }

    def sync_warehouses(self):
        """Sync warehouses from SAP B1 to local database"""
        if not self.ensure_logged_in():
            logging.warning("Cannot sync warehouses - SAP B1 not available")
            return False

        try:
            url = f"{self.base_url}/b1s/v1/Warehouses"
            response = self.session.get(url)

            if response.status_code == 200:
                warehouses = response.json().get('value', [])

                from app import db

                # Clear cache and update database
                self._warehouse_cache = {}

                for wh in warehouses:
                    # Check if warehouse exists in branches table
                    existing = db.session.execute(
                        db.text("SELECT id FROM branches WHERE id = :id"), {
                            "id": wh.get('WarehouseCode')
                        }).fetchone()

                    if not existing:
                        # Insert new warehouse as branch - use compatible SQL
                        import os
                        # Removed circular import
                        db_uri = os.environ.get('DATABASE_URL', '')

                        if 'postgresql' in db_uri.lower(
                        ) or 'mysql' in db_uri.lower():
                            insert_sql = """
                                INSERT INTO branches (id, name, address, is_active, created_at, updated_at)
                                VALUES (:id, :name, :address, :is_active, NOW(), NOW())
                            """
                        else:
                            insert_sql = """
                                INSERT INTO branches (id, name, address, is_active, created_at, updated_at)
                                VALUES (:id, :name, :address, :is_active, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                            """

                        db.session.execute(
                            db.text(insert_sql), {
                                "id": wh.get('WarehouseCode'),
                                "name": wh.get('WarehouseName', ''),
                                "address": wh.get('Street', ''),
                                "is_active": wh.get('Inactive') != 'Y'
                            })
                    else:
                        # Update existing warehouse - use compatible SQL
                        import os
                        # Removed circular import
                        db_uri = os.environ.get('DATABASE_URL', '')

                        if 'postgresql' in db_uri.lower(
                        ) or 'mysql' in db_uri.lower():
                            update_sql = """
                                UPDATE branches SET 
                                    name = :name, 
                                    address = :address, 
                                    is_active = :is_active,
                                    updated_at = NOW()
                                WHERE id = :id
                            """
                        else:
                            update_sql = """
                                UPDATE branches SET 
                                    name = :name, 
                                    address = :address, 
                                    is_active = :is_active,
                                    updated_at = CURRENT_TIMESTAMP
                                WHERE id = :id
                            """

                        db.session.execute(
                            db.text(update_sql), {
                                "id": wh.get('WarehouseCode'),
                                "name": wh.get('WarehouseName', ''),
                                "address": wh.get('Street', ''),
                                "is_active": wh.get('Inactive') != 'Y'
                            })

                    # Cache warehouse data
                    self._warehouse_cache[wh.get('WarehouseCode')] = {
                        'WarehouseCode': wh.get('WarehouseCode'),
                        'WarehouseName': wh.get('WarehouseName'),
                        'Address': wh.get('Street'),
                        'Active': wh.get('Inactive') != 'Y'
                    }

                db.session.commit()
                logging.info(
                    f"Synced {len(warehouses)} warehouses from SAP B1")
                return True

        except Exception as e:
            logging.error(f"Error syncing warehouses: {str(e)}")
            return False

    def sync_bins(self, warehouse_code=None):
        """Sync bin locations from SAP B1"""
        if not self.ensure_logged_in():
            logging.warning("Cannot sync bins - SAP B1 not available")
            return False

        try:
            # Get bins for specific warehouse or all warehouses
            if warehouse_code:
                url = f"{self.base_url}/b1s/v1/BinLocations?$filter=Warehouse eq '{warehouse_code}'"
            else:
                url = f"{self.base_url}/b1s/v1/BinLocations"

            response = self.session.get(url)

            if response.status_code == 200:
                bins = response.json().get('value', [])

                # Create bins table if not exists - use compatible SQL
                from app import db, app
                import os

                db_uri = os.environ.get('DATABASE_URL', '')

                if 'postgresql' in db_uri.lower():
                    create_table_sql = """
                        CREATE TABLE IF NOT EXISTS bin_locations (
                            id SERIAL PRIMARY KEY,
                            bin_code VARCHAR(50) NOT NULL,
                            warehouse_code VARCHAR(10) NOT NULL,
                            bin_name VARCHAR(100),
                            is_active BOOLEAN DEFAULT TRUE,
                            created_at TIMESTAMP DEFAULT NOW(),
                            updated_at TIMESTAMP DEFAULT NOW(),
                            UNIQUE(bin_code, warehouse_code)
                        )
                    """
                elif 'mysql' in db_uri.lower():
                    create_table_sql = """
                        CREATE TABLE IF NOT EXISTS bin_locations (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            bin_code VARCHAR(50) NOT NULL,
                            warehouse_code VARCHAR(10) NOT NULL,
                            bin_name VARCHAR(100),
                            is_active BOOLEAN DEFAULT TRUE,
                            created_at TIMESTAMP DEFAULT NOW(),
                            updated_at TIMESTAMP DEFAULT NOW() ON UPDATE NOW(),
                            UNIQUE KEY unique_bin_warehouse (bin_code, warehouse_code)
                        )
                    """
                else:
                    create_table_sql = """
                        CREATE TABLE IF NOT EXISTS bin_locations (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            bin_code VARCHAR(50) NOT NULL,
                            warehouse_code VARCHAR(10) NOT NULL,
                            bin_name VARCHAR(100),
                            is_active BOOLEAN DEFAULT 1,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            UNIQUE(bin_code, warehouse_code)
                        )
                    """

                db.session.execute(db.text(create_table_sql))

                # Clear cache
                self._bin_cache = {}

                for bin_data in bins:
                    bin_code = bin_data.get('BinCode')
                    wh_code = bin_data.get(
                        'Warehouse')  # Use 'Warehouse' not 'WarehouseCode'

                    if bin_code and wh_code:
                        # Upsert bin location - use database-specific syntax
                        if 'postgresql' in db_uri.lower():
                            upsert_sql = """
                                INSERT INTO bin_locations (bin_code, warehouse_code, bin_name, is_active, created_at, updated_at)
                                VALUES (:bin_code, :warehouse_code, :bin_name, :is_active, NOW(), NOW())
                                ON CONFLICT (bin_code, warehouse_code) 
                                DO UPDATE SET 
                                    bin_name = EXCLUDED.bin_name,
                                    is_active = EXCLUDED.is_active,
                                    updated_at = NOW()
                            """
                        elif 'mysql' in db_uri.lower():
                            upsert_sql = """
                                INSERT INTO bin_locations (bin_code, warehouse_code, bin_name, is_active, created_at, updated_at)
                                VALUES (:bin_code, :warehouse_code, :bin_name, :is_active, NOW(), NOW())
                                ON DUPLICATE KEY UPDATE 
                                    bin_name = VALUES(bin_name),
                                    is_active = VALUES(is_active),
                                    updated_at = NOW()
                            """
                        else:
                            # SQLite - use INSERT OR REPLACE
                            upsert_sql = """
                                INSERT OR REPLACE INTO bin_locations (bin_code, warehouse_code, bin_name, is_active, created_at, updated_at)
                                VALUES (:bin_code, :warehouse_code, :bin_name, :is_active, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                            """

                        db.session.execute(
                            db.text(upsert_sql), {
                                "bin_code": bin_code,
                                "warehouse_code": wh_code,
                                "bin_name": bin_data.get('Description', ''),
                                "is_active": bin_data.get('Inactive') != 'Y'
                            })

                        # Cache bin data
                        cache_key = f"{wh_code}:{bin_code}"
                        self._bin_cache[cache_key] = {
                            'BinCode': bin_code,
                            'WarehouseCode': wh_code,
                            'Description': bin_data.get('Description', ''),
                            'Active': bin_data.get('Inactive') != 'Y'
                        }

                db.session.commit()
                logging.info(f"Synced {len(bins)} bin locations from SAP B1")
                return True

        except Exception as e:
            logging.error(f"Error syncing bins: {str(e)}")
            return False

    def sync_business_partners(self):
        """Sync business partners (suppliers/customers) from SAP B1"""
        if not self.ensure_logged_in():
            logging.warning(
                "Cannot sync business partners - SAP B1 not available")
            return False

        try:
            # Get suppliers and customers
            url = f"{self.base_url}/b1s/v1/BusinessPartners?$filter=CardType eq 'cSupplier' or CardType eq 'cCustomer'"
            response = self.session.get(url)

            if response.status_code == 200:
                partners = response.json().get('value', [])

                from app import db, app

                # Create business_partners table if not exists - use database-specific syntax
                db_uri = os.environ.get('DATABASE_URL', '')

                if 'postgresql' in db_uri.lower():
                    create_table_sql = """
                        CREATE TABLE IF NOT EXISTS business_partners (
                            id SERIAL PRIMARY KEY,
                            card_code VARCHAR(50) UNIQUE NOT NULL,
                            card_name VARCHAR(200) NOT NULL,
                            card_type VARCHAR(20) NOT NULL,
                            phone VARCHAR(50),
                            email VARCHAR(100),
                            address TEXT,
                            is_active BOOLEAN DEFAULT TRUE,
                            created_at TIMESTAMP DEFAULT NOW(),
                            updated_at TIMESTAMP DEFAULT NOW()
                        )
                    """
                elif 'mysql' in db_uri.lower():
                    create_table_sql = """
                        CREATE TABLE IF NOT EXISTS business_partners (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            card_code VARCHAR(50) UNIQUE NOT NULL,
                            card_name VARCHAR(200) NOT NULL,
                            card_type VARCHAR(20) NOT NULL,
                            phone VARCHAR(50),
                            email VARCHAR(100),
                            address TEXT,
                            is_active BOOLEAN DEFAULT TRUE,
                            created_at TIMESTAMP DEFAULT NOW(),
                            updated_at TIMESTAMP DEFAULT NOW() ON UPDATE NOW()
                        )
                    """
                else:
                    create_table_sql = """
                        CREATE TABLE IF NOT EXISTS business_partners (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            card_code VARCHAR(50) UNIQUE NOT NULL,
                            card_name VARCHAR(200) NOT NULL,
                            card_type VARCHAR(20) NOT NULL,
                            phone VARCHAR(50),
                            email VARCHAR(100),
                            address TEXT,
                            is_active BOOLEAN DEFAULT 1,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """

                db.session.execute(db.text(create_table_sql))

                for partner in partners:
                    card_code = partner.get('CardCode')
                    if card_code:
                        # Use database-specific upsert syntax
                        if 'postgresql' in db_uri.lower():
                            upsert_sql = """
                                INSERT INTO business_partners (card_code, card_name, card_type, phone, email, address, is_active, created_at, updated_at)
                                VALUES (:card_code, :card_name, :card_type, :phone, :email, :address, :is_active, NOW(), NOW())
                                ON CONFLICT (card_code) 
                                DO UPDATE SET 
                                    card_name = EXCLUDED.card_name,
                                    card_type = EXCLUDED.card_type,
                                    phone = EXCLUDED.phone,
                                    email = EXCLUDED.email,
                                    address = EXCLUDED.address,
                                    is_active = EXCLUDED.is_active,
                                    updated_at = NOW()
                            """
                        elif 'mysql' in db_uri.lower():
                            upsert_sql = """
                                INSERT INTO business_partners (card_code, card_name, card_type, phone, email, address, is_active, created_at, updated_at)
                                VALUES (:card_code, :card_name, :card_type, :phone, :email, :address, :is_active, NOW(), NOW())
                                ON DUPLICATE KEY UPDATE 
                                    card_name = VALUES(card_name),
                                    card_type = VALUES(card_type),
                                    phone = VALUES(phone),
                                    email = VALUES(email),
                                    address = VALUES(address),
                                    is_active = VALUES(is_active),
                                    updated_at = NOW()
                            """
                        else:
                            # SQLite - use INSERT OR REPLACE
                            upsert_sql = """
                                INSERT OR REPLACE INTO business_partners (card_code, card_name, card_type, phone, email, address, is_active, created_at, updated_at)
                                VALUES (:card_code, :card_name, :card_type, :phone, :email, :address, :is_active, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                            """

                        db.session.execute(
                            db.text(upsert_sql), {
                                "card_code": card_code,
                                "card_name": partner.get('CardName', ''),
                                "card_type": partner.get('CardType', ''),
                                "phone": partner.get('Phone1', ''),
                                "email": partner.get('EmailAddress', ''),
                                "address": partner.get('Address', ''),
                                "is_active": partner.get('Valid') == 'Y'
                            })

                db.session.commit()
                logging.info(
                    f"Synced {len(partners)} business partners from SAP B1")
                return True

        except Exception as e:
            logging.error(f"Error syncing business partners: {str(e)}")
            return False

    def update_pick_list_status_to_picked(self, absolute_entry, pick_list_data):
        """Update pick list status to 'ps_Picked' in SAP B1 via PATCH API"""
        if not self.ensure_logged_in():
            # Return success for offline mode with mock response
            import random
            return {
                'success': True,
                'message': f'Pick list {absolute_entry} marked as picked (offline mode)',
                'sap_response': {'Absoluteentry': absolute_entry, 'Status': 'ps_Picked'}
            }

        try:
            # Build the PATCH URL with the absolute entry
            url = f"{self.base_url}/b1s/v1/PickLists({absolute_entry})"

            # Prepare the JSON payload with exact structure from user's example
            payload = {
                "Absoluteentry": absolute_entry,
                "Name": pick_list_data.get('name', 'manager'),
                "OwnerCode": pick_list_data.get('owner_code', 1),
                "OwnerName": pick_list_data.get('owner_name'),
                "PickDate": pick_list_data.get('pick_date', datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')),
                "Remarks": pick_list_data.get('remarks'),
                "Status": "ps_Picked",  # This is the key change
                "ObjectType": pick_list_data.get('object_type', '156'),
                "UseBaseUnits": pick_list_data.get('use_base_units', 'tNO'),
                "PickListsLines": []
            }

            # Add pick list lines with picked status
            if pick_list_data.get('lines'):
                for line in pick_list_data['lines']:
                    line_data = {
                        "AbsoluteEntry": absolute_entry,
                        "LineNumber": line.get('line_number', 0),
                        "OrderEntry": line.get('order_entry'),
                        "OrderRowID": line.get('order_row_id'),
                        "PickedQuantity": float(line.get('picked_quantity', 0)),
                        "PickStatus": "ps_Picked",  # Mark each line as picked
                        "ReleasedQuantity": float(line.get('released_quantity', 0)),
                        "PreviouslyReleasedQuantity": float(line.get('previously_released_quantity', 0)),
                        "BaseObjectType": line.get('base_object_type', 17),
                        "SerialNumbers": [],
                        "BatchNumbers": [],
                        "DocumentLinesBinAllocations": []
                    }
                    payload["PickListsLines"].append(line_data)

            # Execute PATCH request to SAP B1
            logging.info(f"Sending PATCH request to {url}")
            logging.info(f"Payload: {json.dumps(payload, indent=2)}")

            response = self.session.patch(url, json=payload, timeout=30)

            if response.status_code == 204:
                # SAP B1 returns 204 No Content for successful PATCH
                logging.info(f"Successfully marked pick list {absolute_entry} as picked in SAP B1")
                return {
                    'success': True,
                    'message': f'Pick list {absolute_entry} marked as picked successfully',
                    'sap_response': {'Absoluteentry': absolute_entry, 'Status': 'ps_Picked'}
                }
            else:
                error_msg = f"SAP B1 PATCH failed with status {response.status_code}: {response.text}"
                logging.error(error_msg)
                return {
                    'success': False,
                    'error': error_msg,
                    'sap_response': response.text
                }

        except Exception as e:
            error_msg = f"Error updating pick list status in SAP B1: {str(e)}"
            logging.error(error_msg)
            return {
                'success': False,
                'error': error_msg
            }

    def update_pick_list_line_to_picked(self, absolute_entry, line_pick_data):
        """Update specific pick list line to 'ps_Picked' in SAP B1 via PATCH API"""
        if not self.ensure_logged_in():
            # Return success for offline mode with mock response
            return {
                'success': True,
                'message': f'Pick list line {line_pick_data.get("line_number")} marked as picked (offline mode)',
                'sap_response': {'Absoluteentry': absolute_entry, 'LineStatus': 'ps_Picked'}
            }

        try:
            # Build the PATCH URL with the absolute entry
            url = f"{self.base_url}/b1s/v1/PickLists({absolute_entry})"

            # Get original pick list data
            sap_pick_list = line_pick_data.get('sap_pick_list', {})
            target_line_number = line_pick_data.get('line_number')
            picked_quantity = line_pick_data.get('picked_quantity', 0)

            # Prepare the JSON payload with exact structure, updating only the target line
            payload = {
                "Absoluteentry": absolute_entry,
                "Name": sap_pick_list.get('Name', 'manager'),
                "OwnerCode": sap_pick_list.get('OwnerCode', 1),
                "OwnerName": sap_pick_list.get('OwnerName'),
                "PickDate": sap_pick_list.get('PickDate', datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')),
                "Remarks": sap_pick_list.get('Remarks'),
                "ObjectType": sap_pick_list.get('ObjectType', '156'),
                "UseBaseUnits": sap_pick_list.get('UseBaseUnits', 'tNO'),
                "PickListsLines": []
            }

            # Calculate overall pick list status
            all_lines_picked = True
            any_line_picked = False

            # Add all pick list lines, updating the target line
            for line in sap_pick_list.get('PickListsLines', []):
                line_data = {
                    "AbsoluteEntry": absolute_entry,
                    "LineNumber": line.get('LineNumber', 0),
                    "OrderEntry": line.get('OrderEntry'),
                    "OrderRowID": line.get('OrderRowID'),
                    "BaseObjectType": line.get('BaseObjectType', 17),
                    "SerialNumbers": [],
                    "BatchNumbers": [],
                    "DocumentLinesBinAllocations": []
                }

                # Update the target line
                if line.get('LineNumber') == target_line_number:
                    line_data["PickedQuantity"] = float(picked_quantity)
                    line_data["PickStatus"] = "ps_Picked"
                    line_data["ReleasedQuantity"] = float(line.get('ReleasedQuantity', picked_quantity))
                    line_data["PreviouslyReleasedQuantity"] = float(line.get('PreviouslyReleasedQuantity', 0))
                    any_line_picked = True
                else:
                    # Keep original line data
                    line_data["PickedQuantity"] = float(line.get('PickedQuantity', 0))
                    line_data["PickStatus"] = line.get('PickStatus', 'ps_Released')
                    line_data["ReleasedQuantity"] = float(line.get('ReleasedQuantity', 0))
                    line_data["PreviouslyReleasedQuantity"] = float(line.get('PreviouslyReleasedQuantity', 0))

                    # Check if this line is picked
                    if line.get('PickStatus') == 'ps_Picked':
                        any_line_picked = True
                    elif line.get('PickStatus') != 'ps_Picked':
                        all_lines_picked = False

                payload["PickListsLines"].append(line_data)

            # Determine overall pick list status
            if all_lines_picked and any_line_picked:
                payload["Status"] = "ps_Picked"
            elif any_line_picked:
                payload["Status"] = "ps_PartiallyPicked"
            else:
                payload["Status"] = sap_pick_list.get('Status', 'ps_Open')

            # Execute PATCH request to SAP B1
            logging.info(f"Sending PATCH request to {url} for line {target_line_number}")
            logging.info(f"Payload: {json.dumps(payload, indent=2)}")

            response = self.session.patch(url, json=payload, timeout=30)

            if response.status_code == 204:
                # SAP B1 returns 204 No Content for successful PATCH
                logging.info(f"Successfully marked pick list line {target_line_number} as picked in SAP B1")
                return {
                    'success': True,
                    'message': f'Pick list line {target_line_number} marked as picked successfully',
                    'sap_response': {'Absoluteentry': absolute_entry, 'LineStatus': 'ps_Picked'},
                    'overall_status': payload["Status"]
                }
            else:
                error_msg = f"SAP B1 PATCH failed with status {response.status_code}: {response.text}"
                logging.error(error_msg)
                return {
                    'success': False,
                    'error': error_msg,
                    'sap_response': response.text
                }

        except Exception as e:
            error_msg = f"Error updating pick list line status in SAP B1: {str(e)}"
            logging.error(error_msg)
            return {
                'success': False,
                'error': error_msg
            }

    def get_warehouse_business_place_id(self, warehouse_code):
        """Get BusinessPlaceID for a warehouse from SAP B1"""
        if not self.ensure_logged_in():
            return 5  # Default fallback

        try:
            url = f"{self.base_url}/b1s/v1/Warehouses"
            params = {
                '$select': 'BusinessPlaceID',
                '$filter': f"WarehouseCode eq '{warehouse_code}'"
            }

            response = self.session.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                if data.get('value') and len(data['value']) > 0:
                    return data['value'][0].get('BusinessPlaceID', 5)
            return 5  # Default fallback

        except Exception as e:
            logging.error(
                f"Error getting BusinessPlaceID for warehouse {warehouse_code}: {str(e)}"
            )
            return 5  # Default fallback

    def generate_external_reference_number(self, grpo_document):
        """Generate unique external reference number for Purchase Delivery Note"""
        from datetime import datetime

        # Get current date in YYYYMMDD format
        date_str = datetime.now().strftime('%Y%m%d')

        # Get sequence number for today
        try:
            from app import db

            # Create sequence table if not exists
            create_sequence_table = """
                CREATE TABLE IF NOT EXISTS pdn_sequence (
                    date_key VARCHAR(8) PRIMARY KEY,
                    sequence_number INTEGER DEFAULT 0
                )
            """
            db.session.execute(db.text(create_sequence_table))

            # Get or create sequence for today
            result = db.session.execute(
                db.text(
                    "SELECT sequence_number FROM pdn_sequence WHERE date_key = :date_key"
                ), {
                    "date_key": date_str
                }).fetchone()

            if result:
                sequence_num = result[0] + 1
                db.session.execute(
                    db.text(
                        "UPDATE pdn_sequence SET sequence_number = :seq WHERE date_key = :date_key"
                    ), {
                        "seq": sequence_num,
                        "date_key": date_str
                    })
            else:
                sequence_num = 1
                db.session.execute(
                    db.text(
                        "INSERT INTO pdn_sequence (date_key, sequence_number) VALUES (:date_key, :seq)"
                    ), {
                        "date_key": date_str,
                        "seq": sequence_num
                    })

            db.session.commit()

            # Format: EXT-REF-YYYYMMDD-XXX
            return f"EXT-REF-{date_str}-{sequence_num:03d}"

        except Exception as e:
            logging.error(
                f"Error generating external reference number: {str(e)}")
            # Fallback to timestamp-based reference
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            return f"EXT-REF-{timestamp}"

    def create_purchase_delivery_note(self, grpo_document):
        """Create Purchase Delivery Note in SAP B1 with exact JSON structure specified"""
        if not self.ensure_logged_in():
            # Return success for offline mode
            import random
            return {
                'success': True,
                'error': None,
                'document_number': f'PDN-{random.randint(100000, 999999)}'
            }

        # Get PO data first to ensure proper field mapping
        po_data = self.get_purchase_order(grpo_document.po_number)
        if not po_data:
            return {
                'success':
                False,
                'error':
                f'Purchase Order {grpo_document.po_number} not found in SAP B1'
            }

        # Extract required fields from PO with correct date formatting
        card_code = po_data.get('CardCode')
        po_doc_entry = po_data.get('DocEntry')

        # Use PO dates in correct format (YYYY-MM-DD, not with time)
        doc_date = po_data.get('DocDate', datetime.now().strftime('%Y-%m-%d'))
        doc_due_date = po_data.get('DocDueDate', datetime.now().strftime('%Y-%m-%d'))

        # Ensure dates are in YYYY-MM-DD format (remove time if present)
        if 'T' in doc_date:
            doc_date = doc_date.split('T')[0]
        if 'T' in doc_due_date:
            doc_due_date = doc_due_date.split('T')[0]

        if not card_code or not po_doc_entry:
            return {
                'success': False,
                'error': 'Missing CardCode or PO DocEntry from SAP B1'
            }

        # Generate unique external reference number
        external_ref = self.generate_external_reference_number(grpo_document)

        # Get first warehouse code from PO DocumentLines to determine BusinessPlaceID
        first_warehouse_code = None
        if grpo_document.items:
            for item in grpo_document.items:
                if item.qc_status == 'approved':
                    # Find matching PO line to get proper warehouse code
                    for po_line in po_data.get('DocumentLines', []):
                        if po_line.get('ItemCode') == item.item_code:
                            first_warehouse_code = po_line.get(
                                'WarehouseCode') or po_line.get('WhsCode')
                            if first_warehouse_code:
                                break
                    if first_warehouse_code:
                        break

        # Get BusinessPlaceID for the warehouse
        business_place_id = self.get_warehouse_business_place_id(
            first_warehouse_code) if first_warehouse_code else 5

        # Build document lines with exact structure
        document_lines = []
        line_number = 0

        for item in grpo_document.items:
            # Only include QC approved items
            if item.qc_status != 'approved':
                continue

            # Find matching PO line for proper mapping
            po_line_num = None
            po_line_data = None
            for po_line in po_data.get('DocumentLines', []):
                if po_line.get('ItemCode') == item.item_code:
                    po_line_num = po_line.get('LineNum')
                    po_line_data = po_line
                    break

            if po_line_num is None:
                logging.warning(
                    f"PO line not found for item {item.item_code} in PO {grpo_document.po_number}"
                )
                continue  # Skip items not found in PO

            # Get exact warehouse code from PO line instead of bin location
            po_warehouse_code = None
            if po_line_data:
                po_warehouse_code = po_line_data.get(
                    'WarehouseCode') or po_line_data.get('WhsCode')

            # Use PO warehouse code, or fallback to extracted from bin location
            warehouse_code = po_warehouse_code or (item.bin_location.split(
                '-')[0] if '-' in item.bin_location else item.bin_location[:4])

            # Build line with exact SAP B1 structure
            line = {
                "BaseType": 22,  # Constant value for Purchase Order
                "BaseEntry": po_doc_entry,
                "BaseLine": po_line_num,
                "ItemCode": item.item_code,
                "Quantity": item.received_quantity,
                "WarehouseCode": warehouse_code
            }

            # Add batch information in EXACT format as user specified
            if item.batch_number:
                # Format expiry date properly
                expiry_date = doc_date + "T00:00:00Z"  # Default to PO date
                if item.expiration_date:
                    if hasattr(item.expiration_date, 'strftime'):
                        expiry_date = item.expiration_date.strftime(
                            '%Y-%m-%dT%H:%M:%SZ')
                    else:
                        # If it's a string, ensure proper format
                        expiry_date = str(item.expiration_date)
                        if 'T' not in expiry_date:
                            expiry_date += "T00:00:00Z"

                batch_info = {
                    "BatchNumber":
                    item.batch_number,
                    "Quantity":
                    item.received_quantity,
                    "BaseLineNumber":
                    line_number,
                    "ManufacturerSerialNumber":
                    getattr(item, 'manufacturer_serial', None) or "MFG-SN-001",
                    "InternalSerialNumber":
                    getattr(item, 'internal_serial', None) or "INT-SN-001",
                    "ExpiryDate":
                    expiry_date
                }

                line["BatchNumbers"] = [batch_info]

            document_lines.append(line)
            line_number += 1

        if not document_lines:
            return {
                'success':
                False,
                'error':
                'No approved items found for Purchase Delivery Note creation'
            }

        # Build Purchase Delivery Note with EXACT user-specified structure
        pdn_data = {
            "CardCode": card_code,
            "DocDate": doc_date,
            "DocDueDate": doc_due_date,
            "Comments": grpo_document.notes or "Auto-created from PO after QC",
            "NumAtCard": external_ref,
            "BPL_IDAssignedToInvoice": business_place_id,
            "DocumentLines": document_lines
        }

        # Submit to SAP B1
        url = f"{self.base_url}/b1s/v1/PurchaseDeliveryNotes"

        # Log the payload for debugging - Enhanced JSON logging
        import json
        logging.info("=" * 80)
        logging.info("PURCHASE DELIVERY NOTE - JSON PAYLOAD")
        logging.info("=" * 80)
        logging.info(json.dumps(pdn_data, indent=2, default=str))
        logging.info("=" * 80)
        print(pdn_data)
        try:
            response = self.session.post(url, json=pdn_data)
            if response.status_code == 201:
                result = response.json()
                logging.info(
                    f"Successfully created Purchase Delivery Note {result.get('DocNum')} for GRPO {grpo_document.id}"
                )
                return {
                    'success':
                    True,
                    'document_number':
                    result.get('DocNum'),
                    'doc_entry':
                    result.get('DocEntry'),
                    'external_reference':
                    external_ref,
                    'message':
                    f'Purchase Delivery Note {result.get("DocNum")} created successfully with reference {external_ref}'
                }
            else:
                error_msg = f"SAP B1 error creating Purchase Delivery Note: {response.text}"
                logging.error(error_msg)
                return {'success': False, 'error': error_msg}
        except Exception as e:
            error_msg = f"Error creating Purchase Delivery Note in SAP B1: {str(e)}"
            logging.error(error_msg)
            return {'success': False, 'error': error_msg}

    def post_grpo_to_sap(self, grpo_document):
        """Post approved GRPO to SAP B1 as Purchase Delivery Note"""
        if not self.ensure_logged_in():
            logging.warning("Cannot post GRPO - SAP B1 not available")
            return {'success': False, 'error': 'SAP B1 not available'}

        try:
            # Create Purchase Delivery Note to close PO
            result = self.create_purchase_delivery_note(grpo_document)

            if result.get('success'):
                # Update WMS record with SAP document number
                grpo_document.sap_document_number = str(
                    result.get('document_number'))
                grpo_document.status = 'posted'

                from app import db
                db.session.commit()

                logging.info(
                    f"GRPO posted to SAP B1 with Purchase Delivery Note: {result.get('document_number')}"
                )
                return {
                    'success':
                    True,
                    'sap_document_number':
                    result.get('document_number'),
                    'message':
                    f'GRPO posted to SAP B1 as Purchase Delivery Note {result.get("document_number")}'
                }
            else:
                return {
                    'success': False,
                    'error': result.get('error', 'Unknown error occurred')
                }
        except Exception as e:
            logging.error(f"Error posting GRPO to SAP: {str(e)}")
            return {'success': False, 'error': str(e)}

    def sync_all_master_data(self):
        """Sync all master data from SAP B1"""
        logging.info("Starting full SAP B1 master data synchronization...")

        results = {
            'warehouses': self.sync_warehouses(),
            'bins': self.sync_bins(),
            'business_partners': self.sync_business_partners()
        }

        success_count = sum(1 for result in results.values() if result)
        logging.info(
            f"Master data sync completed: {success_count}/{len(results)} successful"
        )

        return results

    def get_sales_order_by_doc_entry(self, doc_entry):
        """Get Sales Order by DocEntry for picklist integration"""
        if not self.ensure_logged_in():
            logging.warning("SAP B1 not available for Sales Order lookup")
            return self._get_mock_sales_order(doc_entry)

        try:
            url = f"{self.base_url}/b1s/v1/Orders?$filter=DocEntry eq {doc_entry}"
            logging.info(f"🔍 Fetching Sales Order DocEntry={doc_entry}: {url}")

            response = self.session.get(url)

            if response.status_code == 200:
                data = response.json()
                orders = data.get('value', [])

                if orders:
                    order = orders[0]
                    logging.info(f"✅ Found Sales Order DocEntry={doc_entry}: {order.get('CardCode')} - {order.get('CardName')}")
                    return {
                        'success': True,
                        'sales_order': order
                    }
                else:
                    logging.warning(f"⚠️ Sales Order DocEntry={doc_entry} not found")
                    return {'success': False, 'error': f'Sales Order {doc_entry} not found'}
            else:
                logging.error(f"❌ Error fetching Sales Order: {response.status_code} - {response.text}")
                return {'success': False, 'error': f'HTTP {response.status_code}'}

        except Exception as e:
            logging.error(f"Error getting Sales Order {doc_entry} from SAP B1: {str(e)}")
            return {'success': False, 'error': str(e)}

    def _get_mock_sales_order(self, doc_entry):
        """Mock Sales Order data for development/offline mode"""
        return {
            'success': True,
            'sales_order': {

            }
        }

    def sync_sales_order_to_local_db(self, order_data):
        """Sync Sales Order data to local database"""
        try:
            from app import db
            from models import SalesOrder, SalesOrderLine
            from datetime import datetime

            doc_entry = order_data.get('DocEntry')
            if not doc_entry:
                return {'success': False, 'error': 'Missing DocEntry'}

            # Check if Sales Order already exists
            sales_order = SalesOrder.query.filter_by(doc_entry=doc_entry).first()

            if not sales_order:
                sales_order = SalesOrder()
                db.session.add(sales_order)

            # Update Sales Order fields
            sales_order.doc_entry = doc_entry
            sales_order.doc_num = order_data.get('DocNum')
            sales_order.doc_type = order_data.get('DocType')

            # Parse dates
            doc_date = order_data.get('DocDate')
            if doc_date:
                if isinstance(doc_date, str):
                    sales_order.doc_date = datetime.fromisoformat(doc_date.replace('Z', '+00:00'))
                else:
                    sales_order.doc_date = doc_date

            doc_due_date = order_data.get('DocDueDate')
            if doc_due_date:
                if isinstance(doc_due_date, str):
                    sales_order.doc_due_date = datetime.fromisoformat(doc_due_date.replace('Z', '+00:00'))
                else:
                    sales_order.doc_due_date = doc_due_date

            sales_order.card_code = order_data.get('CardCode')
            sales_order.card_name = order_data.get('CardName')
            sales_order.address = order_data.get('Address')
            sales_order.doc_total = order_data.get('DocTotal')
            sales_order.doc_currency = order_data.get('DocCurrency')
            sales_order.comments = order_data.get('Comments')
            sales_order.document_status = order_data.get('DocumentStatus')
            sales_order.last_sap_sync = datetime.utcnow()

            db.session.flush()  # Get the ID

            # Sync Sales Order Lines
            lines_synced = 0
            document_lines = order_data.get('DocumentLines', [])

            for line_data in document_lines:
                line_num = line_data.get('LineNum')
                if line_num is None:
                    continue

                # Check if line already exists
                order_line = SalesOrderLine.query.filter_by(
                    sales_order_id=sales_order.id,
                    line_num=line_num
                ).first()

                if not order_line:
                    order_line = SalesOrderLine()
                    order_line.sales_order_id = sales_order.id
                    db.session.add(order_line)

                # Update line fields
                order_line.line_num = line_num
                order_line.item_code = line_data.get('ItemCode')
                order_line.item_description = line_data.get('ItemDescription') or line_data.get('Dscription')
                order_line.quantity = line_data.get('Quantity')
                order_line.open_quantity = line_data.get('OpenQuantity')
                order_line.delivered_quantity = line_data.get('DeliveredQuantity')
                order_line.unit_price = line_data.get('UnitPrice')
                order_line.line_total = line_data.get('LineTotal')
                order_line.warehouse_code = line_data.get('WarehouseCode')
                order_line.unit_of_measure = line_data.get('UoMCode')
                order_line.line_status = line_data.get('LineStatus')

                lines_synced += 1

            db.session.commit()

            logging.info(f"✅ Synced Sales Order {doc_entry} with {lines_synced} lines")
            return {
                'success': True,
                'sales_order_id': sales_order.id,
                'lines_synced': lines_synced
            }

        except Exception as e:
            db.session.rollback()
            logging.error(f"Error syncing Sales Order to local DB: {str(e)}")
            return {'success': False, 'error': str(e)}

    def enhance_picklist_with_sales_order_data(self, picklist_lines):
        """Enhance picklist lines with Sales Order item details"""
        enhanced_lines = []

        try:
            from app import db
            from models import SalesOrder, SalesOrderLine

            for line in picklist_lines:
                enhanced_line = line.copy()

                order_entry = line.get('OrderEntry')
                order_row_id = line.get('OrderRowID')

                if order_entry and order_row_id is not None:
                    # First try to get from local database
                    sales_order = SalesOrder.query.filter_by(doc_entry=order_entry).first()

                    if not sales_order:
                        # Fetch from SAP B1 and sync to local
                        sap_result = self.get_sales_order_by_doc_entry(order_entry)
                        if sap_result.get('success'):
                            sync_result = self.sync_sales_order_to_local_db(sap_result['sales_order'])
                            if sync_result.get('success'):
                                sales_order = SalesOrder.query.filter_by(doc_entry=order_entry).first()

                    if sales_order:
                        # Get the specific line based on OrderRowID (which corresponds to LineNum)
                        order_line = SalesOrderLine.query.filter_by(
                            sales_order_id=sales_order.id,
                            line_num=order_row_id
                        ).first()

                        if order_line:
                            # Enhance the picklist line with Sales Order data directly on the line object
                            enhanced_line.update({
                                'ItemCode': order_line.item_code,
                                'ItemDescription': order_line.item_description,
                                'SalesOrderDocNum': sales_order.doc_num,
                                'CustomerCode': sales_order.card_code,
                                'CustomerName': sales_order.card_name,
                                'OrderQuantity': order_line.quantity,
                                'OpenQuantity': order_line.open_quantity,
                                'UnitOfMeasure': order_line.unit_of_measure,
                                'WarehouseCode': order_line.warehouse_code,
                                'UnitPrice': order_line.unit_price,
                                'LineTotal': order_line.line_total
                            })

                            logging.info(f"✅ Enhanced picklist line {line.get('LineNumber')} with Sales Order data: {order_line.item_code}")
                        else:
                            logging.warning(f"⚠️ Sales Order line not found: OrderEntry={order_entry}, OrderRowID={order_row_id}")
                    else:
                        logging.warning(f"⚠️ Could not sync Sales Order: OrderEntry={order_entry}")
                else:
                    logging.debug(f"No OrderEntry or OrderRowID for picklist line {line.get('LineNumber')}")

                enhanced_lines.append(enhanced_line)

        except Exception as e:
            logging.error(f"Error enhancing picklist with Sales Order data: {str(e)}")
            return picklist_lines  # Return original lines if enhancement fails

        return enhanced_lines

    def validate_series_with_warehouse(self, serial_number, item_code, warehouse_code=None):
        """Validate series against SAP B1 API using SQL Queries for warehouse validation
        
        Args:
            serial_number: The series/serial number to validate
            item_code: The item code to check against
            warehouse_code: Optional warehouse code to check series availability in specific warehouse
        """
        if not self.ensure_logged_in():
            logging.warning("SAP B1 not available, cannot validate series")
            return {
                'valid': False,
                'error': 'SAP B1 not available'
            }

        try:
            # SAP B1 API endpoint for SQL Queries
            api_url = f"{self.base_url}/b1s/v1/SQLQueries('Series_Validation')/List"

            # Request body with ParamList - include warehouse code if provided
            if warehouse_code:
                payload = {
                    "ParamList": f"series='{serial_number}'&itemCode='{item_code}'&whsCode='{warehouse_code}'"
                }
            else:
                payload = {
                    "ParamList": f"series='{serial_number}'&itemCode='{item_code}'"
                }

            # Make API call with existing session
            response = self.session.post(api_url, json=payload, timeout=30)

            if response.status_code == 200:
                data = response.json()

                if data.get('value') and len(data['value']) > 0:
                    # Series found in the specified warehouse
                    series_data = data['value'][0]
                    return {
                        'valid': True,
                        'DistNumber': series_data.get('DistNumber'),
                        'ItemCode': series_data.get('ItemCode'),
                        'WhsCode': series_data.get('WhsCode'),
                        'available_in_warehouse': True,
                        'message': f'Series {serial_number} is available in warehouse {series_data.get("WhsCode")}'
                    }
                else:
                    # Series not found in the specified warehouse
                    if warehouse_code:
                        return {
                            'valid': True,  # Allow transfer to continue
                            'available_in_warehouse': False,
                            'warning': f'Series {serial_number} is not available in warehouse {warehouse_code}',
                            'message': 'Transfer can continue - series will be moved from another location'
                        }
                    else:
                        return {
                            'valid': True,  # Series exists but no stock in warehouse
                            'available_in_warehouse': False,
                            'warning': f'Series {serial_number} exists but has no stock in any warehouse'
                        }
            else:
                return {
                    'valid': False,
                    'error': f'SAP API error: {response.status_code} - {response.text}'
                }

        except Exception as e:
            logging.error(f"Error validating series with SAP: {str(e)}")
            return {
                'valid': False,
                'error': f'Validation error: {str(e)}'
            }

    def validate_batch_series_with_warehouse(self, serial_numbers, item_code, warehouse_code, batch_size=100):
        """Batch validate multiple series against SAP B1 API for improved performance
        
        Args:
            serial_numbers: List of serial numbers to validate
            item_code: The item code to check against
            warehouse_code: Warehouse code to check series availability
            batch_size: Number of serials to process in each batch (default 100)
            
        Returns:
            Dict with validation results for each serial number
        """
        if not self.ensure_logged_in():
            logging.warning("SAP B1 not available, cannot validate batch series")
            return {serial: {'valid': False, 'error': 'SAP B1 not available'} for serial in serial_numbers}

        if not serial_numbers:
            return {}

        results = {}
        total_serials = len(serial_numbers)

        try:
            # Process serials in batches to avoid API limits and improve performance
            for i in range(0, total_serials, batch_size):
                batch = serial_numbers[i:i+batch_size]
                batch_results = self._validate_batch_chunk(batch, item_code, warehouse_code)
                results.update(batch_results)

                # Log progress for large batches
                if total_serials > 100:
                    processed = min(i + batch_size, total_serials)
                    logging.info(f"📊 Batch validation progress: {processed}/{total_serials} serial numbers processed")

            logging.info(f"✅ Completed batch validation for {total_serials} serial numbers")
            return results

        except Exception as e:
            logging.error(f"❌ Error in batch series validation: {str(e)}")
            # Return error for all serials if batch fails
            return {serial: {'valid': False, 'error': f'Batch validation error: {str(e)}'} for serial in serial_numbers}

    def _validate_batch_chunk(self, serial_batch, item_code, warehouse_code):
        """Validate a chunk of serial numbers using SAP B1 bulk query
        
        Args:
            serial_batch: List of serial numbers in this chunk
            item_code: The item code to check against  
            warehouse_code: Warehouse code to check series availability
            
        Returns:
            Dict with validation results for each serial in the batch
        """
        results = {}

        try:
            # Create SQL query for batch validation
            serial_list = "','".join(serial_batch)
            sql_query = f"""
            SELECT 
                SN.DistNumber as SerialNumber,
                SN.ItemCode,
                SN.WhsCode,
                CASE WHEN SN.WhsCode = '{warehouse_code}' THEN 1 ELSE 0 END as AvailableInWarehouse
            FROM OSRN SN 
            WHERE SN.DistNumber IN ('{serial_list}')
            AND SN.ItemCode = '{item_code}'
            """

            # Use custom SQL query endpoint
            api_url = f"{self.base_url}/b1s/v1/SQLQueries('Batch_Series_Validation')/List"

            payload = {
                "ParamList": f"sqlQuery={sql_query}"
            }

            response = self.session.post(api_url, json=payload, timeout=60)

            if response.status_code == 200:
                data = response.json()
                found_serials = {item.get('SerialNumber'): item for item in data.get('value', [])}

                # Process each serial in the batch
                for serial in serial_batch:
                    if serial in found_serials:
                        series_data = found_serials[serial]
                        available_in_warehouse = bool(series_data.get('AvailableInWarehouse', 0))

                        results[serial] = {
                            'valid': True,
                            'DistNumber': series_data.get('SerialNumber'),
                            'ItemCode': series_data.get('ItemCode'),
                            'WhsCode': series_data.get('WhsCode'),
                            'available_in_warehouse': available_in_warehouse,
                            'validation_type': 'batch_warehouse_specific' if available_in_warehouse else 'batch_warehouse_unavailable',
                            'message': f'Series {serial} validated in batch'
                        }

                        if not available_in_warehouse:
                            results[serial]['warning'] = f'Series {serial} is not available in warehouse {warehouse_code}'
                    else:
                        # Serial not found in SAP
                        results[serial] = {
                            'valid': False,
                            'error': f'Series {serial} not found in SAP system',
                            'available_in_warehouse': False,
                            'validation_type': 'batch_not_found'
                        }
            else:
                # API error - mark all serials as failed
                error_msg = f'SAP API error: {response.status_code} - {response.text}'
                for serial in serial_batch:
                    results[serial] = {
                        'valid': False,
                        'error': error_msg,
                        'validation_type': 'batch_api_error'
                    }

        except Exception as e:
            logging.error(f"❌ Error in batch chunk validation: {str(e)}")
            # Mark all serials in chunk as failed
            error_msg = f'Batch chunk validation error: {str(e)}'
            for serial in serial_batch:
                results[serial] = {
                    'valid': False,
                    'error': error_msg,
                    'validation_type': 'batch_exception'
                }

        return results


    def create_serial_number_stock_transfer(self, serial_transfer_document):
        """Create Stock Transfer in SAP B1 for Serial Number Transfer"""
        if not self.ensure_logged_in():
            logging.warning("SAP B1 not available, simulating serial transfer creation")
            import random
            return {
                'success': True,
                'document_number': f'ST-{random.randint(100000, 999999)}',
                'error': None
            }

        try:
            url = f"{self.base_url}/b1s/v1/StockTransfers"

            # Build stock transfer document for serial numbers
            stock_transfer_lines = []

            for index, item in enumerate(serial_transfer_document.items):
                # Create transfer line with serial numbers
                line = {
                    "LineNum": index,
                    "ItemCode": item.item_code,
                    "Quantity": len(item.serial_numbers),  # Quantity based on serial count
                    "WarehouseCode": item.to_warehouse_code,
                    "FromWarehouseCode": item.from_warehouse_code,
                    "UoMCode": item.unit_of_measure or ""
                }

                # Add serial numbers to the line
                serial_numbers = []

                for serial in item.serial_numbers:
                    if serial.is_validated:  # Only include validated serials
                        system_number = self.get_system_number_from_sap_get(serial.serial_number)
                        serial_info = {
                            "SystemSerialNumber": system_number,
                            "InternalSerialNumber": serial.serial_number,
                            "ManufacturerSerialNumber": serial.serial_number,
                            "ExpiryDate": serial.expiry_date.isoformat() + "Z" if serial.expiry_date else None,
                            "ManufactureDate": serial.manufacturing_date.isoformat() + "Z" if serial.manufacturing_date else None,
                            "ReceptionDate": serial.admission_date.isoformat() + "Z" if serial.admission_date else None,
                            "WarrantyStart": None,
                            "WarrantyEnd": None,
                            "Location": None,
                            "Notes": None
                        }
                        serial_numbers.append(serial_info)

                if serial_numbers:
                    line["SerialNumbers"] = serial_numbers

                stock_transfer_lines.append(line)

            # Build the stock transfer document
            transfer_data = {
                "DocDate": serial_transfer_document.created_at.strftime('%Y-%m-%d'),
                "DueDate": serial_transfer_document.created_at.strftime('%Y-%m-%d'),
                "CardCode": "",
                "CardName": "",
                "Address": "",
                "U_EA_CREATEDBy": serial_transfer_document.user.username,
                "U_EA_Approved": serial_transfer_document.qc_approver.username if serial_transfer_document.qc_approver else serial_transfer_document.user.username,
                "Comments": f"Serial Number Transfer {serial_transfer_document.transfer_number} - {serial_transfer_document.user.username if serial_transfer_document.user else 'System'}",
                "JournalMemo": f"Serial Number Transfer - {serial_transfer_document.transfer_number}",
                "PriceList": -1,
                "SalesPersonCode": -1,
                "FromWarehouse": serial_transfer_document.from_warehouse,
                "ToWarehouse": serial_transfer_document.to_warehouse,
                "AuthorizationStatus": "sasWithout",
                "StockTransferLines": stock_transfer_lines
            }

            # Log the payload for debugging
            logging.info("=" * 80)
            logging.info("SERIAL NUMBER STOCK TRANSFER - JSON PAYLOAD")
            logging.info("=" * 80)
            import json
            logging.info(json.dumps(transfer_data, indent=2, default=str))
            logging.info("=" * 80)
            print(f"transfer_itemTSTAT (repr) --> {repr(transfer_data)}")
            # Submit to SAP B1
            response = self.session.post(url, json=transfer_data)

            if response.status_code == 201:
                result = response.json()
                doc_num = result.get('DocNum')
                logging.info(f"✅ Successfully created Serial Number Stock Transfer {doc_num}")

                return {
                    'success': True,
                    'document_number': doc_num,
                    'doc_entry': result.get('DocEntry'),
                    'message': f'Serial Number Stock Transfer {doc_num} created successfully'
                }
            else:
                error_msg = f"SAP B1 error creating Serial Number Stock Transfer: {response.text}"
                logging.error(error_msg)
                return {'success': False, 'error': error_msg}

        except Exception as e:
            error_msg = f"Error creating Serial Number Stock Transfer in SAP B1: {str(e)}"
            logging.error(error_msg)
            return {'success': False, 'error': error_msg}

    def get_system_number_from_sap_get(self, serial_number):
        try:
            if not self.ensure_logged_in():
                return jsonify({'success': False, 'error': 'SAP B1 connection failed'}), 500
            url = f"{self.base_url}/b1s/v1/SerialNumberDetails"
            params = {
                "$select": "SystemNumber",
                "$filter": f"SerialNumber eq '{serial_number}'"
            }
            response = self.session.get(url, params=params, timeout=15)
            print(response)
            if response.status_code == 200:
                data = response.json()
                print(data)
                logging.info(f"SAP response for {serial_number}: {data}")  # 👈 log full JSON
                if "value" in data and len(data["value"]) > 0:
                    return data["value"][0].get("SystemNumber", 0)  # 👈 safe get
            else:
                logging.error(f"SAP error {response.status_code}: {response.text}")
            return 0
        except Exception as e:
            logging.error(f"Error fetching SystemNumber for {serial_number}: {str(e)}")
            return 0

    def post_inventory_transfer_to_sap(self, transfer_document):
        """Post inventory transfer to SAP B1 as Stock Transfer"""
        try:
            logging.info(f"🚀 Posting Inventory Transfer {transfer_document.id} to SAP B1...")

            # Use the existing create_inventory_transfer function
            result = self.create_inventory_transfer(transfer_document)

            if result.get('success'):
                logging.info(f"✅ Inventory Transfer {transfer_document.id} posted successfully to SAP B1")
                return result
            else:
                logging.error(f"❌ Failed to post Inventory Transfer {transfer_document.id}: {result.get('error')}")
                return result

        except Exception as e:
            error_msg = f"Error posting inventory transfer to SAP B1: {str(e)}"
            logging.error(error_msg)
            return {'success': False, 'error': error_msg}

    def validate_serial_item_for_transfer(self, serial_number, warehouse_code):
        """
        Validate serial number and get item details using SAP B1 SQL Query for Serial Item Transfer
        Uses the specific API endpoint: SQLQueries('Item_Validation')/List
        """
        try:
            if not self.ensure_logged_in():
                logging.warning("SAP B1 not available, returning mock validation for Serial Item Transfer")
                return {

                }

            # SAP B1 SQL Query API endpoint as specified
            url = f"{self.base_url}/b1s/v1/SQLQueries('Item_Validation')/List"

            # Request body with parameters as specified
            request_body = {
                "ParamList": f"seriel_number='{serial_number}'&whcode='{warehouse_code}'"
            }

            logging.info(f"🔍 Validating serial {serial_number} in warehouse {warehouse_code} via SAP B1 SQL Query")
            logging.info(f"📡 Request URL: {url}")
            logging.info(f"📦 Request Body: {request_body}")

            response = self.session.post(url, json=request_body, timeout=30)
            logging.info(f"📡 Response Status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                logging.info(f"📦 SAP B1 Response: {data}")

                # Check if we have results
                values = data.get('value', [])
                if values and len(values) > 0:
                    # Get the first matching result
                    result = values[0]
                    item_code = result.get('ItemCode', '')
                    dist_number = result.get('DistNumber', '')
                    whs_code = result.get('WhsCode', '')

                    # For item description, we'll need to make another call to get item details
                    item_description = self._get_item_description(item_code)

                    logging.info(f"✅ Serial number {serial_number} validated successfully")
                    logging.info(f"📋 Item Code: {item_code}, Warehouse: {whs_code}")

                    return {
                        'valid': True,
                        'item_code': item_code,
                        'item_description': item_description,
                        'warehouse_code': whs_code,
                        'dist_number': dist_number,
                        'source': 'sap_b1',
                        'sql_text': data.get('SqlText', '')
                    }
                else:
                    # No results found
                    logging.warning(f"❌ Serial number {serial_number} not found in warehouse {warehouse_code}")
                    return {
                        'valid': False,
                        'error': f'Serial number {serial_number} not found in warehouse {warehouse_code} or quantity is 0',
                        'source': 'sap_b1'
                    }
            else:
                # API call failed
                logging.error(f"❌ SAP B1 API call failed: {response.status_code} - {response.text}")
                return {
                    'valid': False,
                    'error': f'SAP B1 API call failed: {response.status_code} - {response.text}',
                    'source': 'sap_b1_error'
                }

        except Exception as e:
            logging.error(f"❌ Error validating serial item: {str(e)}")
            return {
                'valid': False,
                'error': f'Error validating serial item: {str(e)}',
                'source': 'error'
            }

    def _get_item_description(self, item_code):
        """
        Get item description from SAP B1 Items master data
        """
        try:
            if not item_code:
                return "Unknown Item"

            # Try to get item description from Items master data
            url = f"{self.base_url}/b1s/v1/Items?$filter=ItemCode eq '{item_code}'&$select=ItemCode,ItemName"
            response = self.session.get(url, timeout=10)

            if response.status_code == 200:
                data = response.json()
                items = data.get('value', [])
                if items and len(items) > 0:
                    return items[0].get('ItemName', f'Item {item_code}')

        except Exception as e:
            logging.warning(f"⚠️ Could not fetch item description for {item_code}: {str(e)}")

        # Fallback to item code if description not found
        return f'Item {item_code}'

    def logout(self):
        """Logout from SAP B1"""
        if self.session_id:
            try:
                logout_url = f"{self.base_url}/b1s/v1/Logout"
                self.session.post(logout_url)
                self.session_id = None
                logging.info("Logged out from SAP B1")
            except Exception as e:
                logging.error(f"Error logging out from SAP B1: {str(e)}")


# Create global SAP integration instance for backward compatibility
sap_b1 = SAPIntegration()
