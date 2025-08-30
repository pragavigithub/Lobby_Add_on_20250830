#!/usr/bin/env python3
"""
SAP B1 Connection Test Script
Run this to verify your SAP B1 configuration and connection
"""

import os
import sys
import requests
import urllib3
from datetime import datetime

# Disable SSL warnings for development
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def test_sap_connection():
    """Test SAP B1 connection with current configuration"""
    
    # Load configuration from environment
    sap_server = os.getenv('SAP_B1_SERVER', 'https://192.168.1.5:50000')
    sap_username = os.getenv('SAP_B1_USERNAME', 'manager')
    sap_password = os.getenv('SAP_B1_PASSWORD', 'Ea@12345')
    sap_company_db = os.getenv('SAP_B1_COMPANY_DB', 'Test_Hutchinson')
    
    print("🔍 SAP B1 Connection Test")
    print("=" * 50)
    print(f"Server: {sap_server}")
    print(f"Username: {sap_username}")
    print(f"Company DB: {sap_company_db}")
    print(f"Password: {'*' * len(sap_password)}")
    print()
    
    # Test 1: Server Reachability
    print("📡 Testing server reachability...")
    try:
        test_url = f"{sap_server}/b1s/v1/"
        response = requests.get(test_url, timeout=10, verify=False)
        print(f"✅ Server is reachable (Status: {response.status_code})")
    except requests.exceptions.ConnectTimeout:
        print("❌ Connection timeout - server may be unreachable")
        return False
    except requests.exceptions.ConnectionError:
        print("❌ Connection failed - check server address and network")
        return False
    except Exception as e:
        print(f"❌ Server test failed: {str(e)}")
        return False
    
    # Test 2: Login Authentication
    print("\n🔐 Testing SAP B1 login...")
    login_url = f"{sap_server}/b1s/v1/Login"
    login_data = {
        "UserName": sap_username,
        "Password": sap_password,
        "CompanyDB": sap_company_db
    }
    
    try:
        session = requests.Session()
        session.verify = False
        
        response = session.post(login_url, json=login_data, timeout=30)
        
        if response.status_code == 200:
            session_data = response.json()
            session_id = session_data.get('SessionId')
            print(f"✅ Login successful! Session ID: {session_id[:20]}...")
            
            # Test 3: API Access
            print("\n📋 Testing API access...")
            test_api_url = f"{sap_server}/b1s/v1/CompanyService"
            api_response = session.get(test_api_url, timeout=10)
            
            if api_response.status_code == 200:
                print("✅ API access working correctly")
                company_info = api_response.json()
                print(f"Company Name: {company_info.get('CompanyName', 'N/A')}")
                print(f"DB Name: {company_info.get('CompanyDB', 'N/A')}")
                
                # Test 4: Purchase Orders Access
                print("\n📦 Testing Purchase Orders access...")
                po_url = f"{sap_server}/b1s/v1/PurchaseOrders?$top=1"
                po_response = session.get(po_url, timeout=10)
                
                if po_response.status_code == 200:
                    po_data = po_response.json()
                    po_count = len(po_data.get('value', []))
                    print(f"✅ Purchase Orders accessible ({po_count} found)")
                else:
                    print(f"⚠️ Purchase Orders access limited (Status: {po_response.status_code})")
                
                print("\n🎉 SAP B1 connection test PASSED!")
                print("Your GRPO posting should work correctly now.")
                return True
                
            else:
                print(f"❌ API access failed (Status: {api_response.status_code})")
                return False
                
        else:
            print(f"❌ Login failed (Status: {response.status_code})")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Login test failed: {str(e)}")
        return False

def main():
    """Main function"""
    print(f"Starting SAP B1 connection test at {datetime.now()}")
    
    success = test_sap_connection()
    
    print("\n" + "=" * 50)
    if success:
        print("✅ ALL TESTS PASSED - SAP B1 is ready for GRPO posting!")
    else:
        print("❌ TESTS FAILED - Please check your SAP B1 configuration")
        print("\nTroubleshooting:")
        print("1. Verify SAP B1 server is running and accessible")
        print("2. Check username, password, and company database name")
        print("3. Ensure network connectivity to SAP B1 server")
        print("4. Verify SAP B1 Service Layer is enabled")
    
    return success

if __name__ == "__main__":
    main()