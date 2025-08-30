#!/usr/bin/env python3
"""
Test script for SAP B1 bin scanning functionality
Tests the enhanced get_bin_items method with real SAP B1 API calls
"""

import os
import sys
import logging
from sap_integration import SAPIntegration

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def test_bin_scanning():
    """Test the enhanced bin scanning functionality"""
    print("🔬 Testing SAP B1 Bin Scanning Integration")
    print("=" * 50)
    
    # Initialize SAP integration
    sap = SAPIntegration()
    
    # Test bin code from your example
    test_bin_code = "7000-FG-SYSTEM-BIN-LOCATION"
    
    print(f"🔍 Testing bin code: {test_bin_code}")
    print("-" * 30)
    
    try:
        # Test the get_bin_items method
        items = sap.get_bin_items(test_bin_code)
        
        print(f"✅ Successfully retrieved {len(items)} items from bin {test_bin_code}")
        
        if items:
            print("\n📦 First few items found:")
            for i, item in enumerate(items[:3], 1):
                print(f"{i}. Item: {item.get('ItemCode', 'N/A')}")
                print(f"   Name: {item.get('ItemName', 'N/A')}")
                print(f"   Batch: {item.get('BatchNumber', 'N/A')}")
                print(f"   Stock: {item.get('OnStock', 0)}")
                print(f"   Warehouse: {item.get('WarehouseCode', 'N/A')}")
                print(f"   BusinessPlaceID: {item.get('BusinessPlaceID', 0)}")
                print()
        else:
            print("⚠️ No items found in this bin")
            
    except Exception as e:
        print(f"❌ Test failed: {str(e)}")
        logging.error(f"Bin scanning test failed: {e}")
        return False
    
    print("🎯 Bin scanning test completed")
    return True

def test_warehouse_info():
    """Test warehouse information retrieval"""
    print("\n🏭 Testing Warehouse Info Retrieval")
    print("-" * 30)
    
    sap = SAPIntegration()
    test_warehouse = "7000-FG"
    
    try:
        # Test warehouse lookup (this would be part of the bin scanning process)
        print(f"Testing warehouse: {test_warehouse}")
        
        # This would be called internally by get_bin_items
        warehouse_url = f"{sap.base_url}/b1s/v1/Warehouses?$select=BusinessPlaceID,WarehouseCode,DefaultBin&$filter=WarehouseCode eq '{test_warehouse}'"
        
        if sap.ensure_logged_in():
            response = sap.session.get(warehouse_url)
            if response.status_code == 200:
                data = response.json().get('value', [])
                if data:
                    warehouse_info = data[0]
                    print(f"✅ Warehouse found:")
                    print(f"   Code: {warehouse_info.get('WarehouseCode')}")
                    print(f"   BusinessPlaceID: {warehouse_info.get('BusinessPlaceID')}")
                    print(f"   DefaultBin: {warehouse_info.get('DefaultBin')}")
                else:
                    print("⚠️ Warehouse not found")
            else:
                print(f"❌ API call failed: {response.status_code}")
        else:
            print("❌ SAP login failed")
            
    except Exception as e:
        print(f"❌ Warehouse test failed: {str(e)}")

if __name__ == "__main__":
    print("🚀 Starting SAP B1 Integration Tests")
    print("=" * 50)
    
    # Run tests
    success = test_bin_scanning()
    test_warehouse_info()
    
    if success:
        print("\n✅ All tests completed successfully!")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed!")
        sys.exit(1)