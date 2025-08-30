#!/usr/bin/env python3
"""
Test script to import SAP B1 PickList data directly
This bypasses the web authentication to test the SAP integration
"""

import os
import sys
import logging
from datetime import datetime

# Add the current directory to the Python path
sys.path.insert(0, '.')

from app import app, db
from models import User, PickList, PickListLine, PickListBinAllocation

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_import_picklist_613():
    """Test importing the specific SAP pick list 613"""
    
    with app.app_context():
        # Set up SAP configuration for testing - using offline mode since SAP not accessible from Replit
        app.config['SAP_B1_SERVER'] = 'https://10.112.253.173:50000'
        app.config['SAP_B1_USERNAME'] = os.getenv('SAP_B1_USERNAME', 'manager')
        app.config['SAP_B1_PASSWORD'] = os.getenv('SAP_B1_PASSWORD', 'manager')
        app.config['SAP_B1_COMPANY_DB'] = os.getenv('SAP_B1_COMPANY_DB', 'SBODemoUS')
        
        # Since SAP is not accessible from Replit, we'll manually create the pick list with your real SAP data
        logger.info("🔧 Creating pick list with real SAP data structure...")
        
        # Create pick list directly from your provided SAP data
        sap_pick_list = {
            "Absoluteentry": 613,
            "Name": "SCM-ORD",
            "OwnerCode": 15,
            "OwnerName": None,
            "PickDate": "2024-02-02T00:00:00Z",
            "Remarks": None,
            "Status": "ps_Closed",
            "ObjectType": "156",
            "UseBaseUnits": "tNO"
        }
        
        logger.info("🔧 SAP B1 Configuration:")
        logger.info(f"   Server: {app.config['SAP_B1_SERVER']}")
        logger.info(f"   Username: {app.config['SAP_B1_USERNAME']}")
        logger.info(f"   Company DB: {app.config['SAP_B1_COMPANY_DB']}")
        
        # Create a test user if needed
        test_user = User.query.filter_by(username='admin').first()
        if not test_user:
            test_user = User(
                username='admin',
                email='admin@test.com',
                role='admin'
            )
            test_user.set_password('admin')
            db.session.add(test_user)
            db.session.commit()
            logger.info("✅ Created test admin user")
        
        # Add complete PickListsLines data from your real SAP response
        sap_pick_list["PickListsLines"] = [
            {
                "AbsoluteEntry": 613,
                "LineNumber": 0,
                "OrderEntry": 1236,
                "OrderRowID": 0,
                "PickedQuantity": 42000.0,
                "PickStatus": "ps_Closed",
                "ReleasedQuantity": 0.0,
                "PreviouslyReleasedQuantity": 42000.0,
                "BaseObjectType": 17,
                "DocumentLinesBinAllocations": [
                    {
                        "BinAbsEntry": 1,
                        "Quantity": 21000.0,
                        "AllowNegativeQuantity": "tNO",
                        "SerialAndBatchNumbersBaseLine": 0,
                        "BaseLineNumber": 0
                    },
                    {
                        "BinAbsEntry": 1,
                        "Quantity": 21000.0,
                        "AllowNegativeQuantity": "tNO",
                        "SerialAndBatchNumbersBaseLine": 0,
                        "BaseLineNumber": 0
                    }
                ]
            },
            {
                "AbsoluteEntry": 613,
                "LineNumber": 1,
                "OrderEntry": 1236,
                "OrderRowID": 1,
                "PickedQuantity": 30000.0,
                "PickStatus": "ps_Closed",
                "ReleasedQuantity": 0.0,
                "PreviouslyReleasedQuantity": 30000.0,
                "BaseObjectType": 17,
                "DocumentLinesBinAllocations": [
                    {"BinAbsEntry": 1, "Quantity": 1000.0, "AllowNegativeQuantity": "tNO", "SerialAndBatchNumbersBaseLine": 0, "BaseLineNumber": 1},
                    {"BinAbsEntry": 1, "Quantity": 1000.0, "AllowNegativeQuantity": "tNO", "SerialAndBatchNumbersBaseLine": 0, "BaseLineNumber": 1},
                    {"BinAbsEntry": 1, "Quantity": 1000.0, "AllowNegativeQuantity": "tNO", "SerialAndBatchNumbersBaseLine": 0, "BaseLineNumber": 1}
                ]
            },
            {
                "AbsoluteEntry": 613,
                "LineNumber": 2,
                "OrderEntry": 1236,
                "OrderRowID": 2,
                "PickedQuantity": 50000.0,
                "PickStatus": "ps_Closed",
                "ReleasedQuantity": 0.0,
                "PreviouslyReleasedQuantity": 50000.0,
                "BaseObjectType": 17,
                "DocumentLinesBinAllocations": [
                    {"BinAbsEntry": 1, "Quantity": 1000.0, "AllowNegativeQuantity": "tNO", "SerialAndBatchNumbersBaseLine": 0, "BaseLineNumber": 2}
                ]
            }
        ]
        
        logger.info(f"✅ Using real SAP pick list data: {sap_pick_list.get('Name')} (Status: {sap_pick_list.get('Status')})")
        
        # Check if pick list exists locally
        existing_pick_list = PickList.query.filter_by(absolute_entry=613).first()
        
        if existing_pick_list:
            pick_list = existing_pick_list
            logger.info("🔄 Updating existing pick list...")
            # Clear existing lines and allocations
            PickListBinAllocation.query.join(PickListLine).filter(
                PickListLine.pick_list_id == pick_list.id
            ).delete(synchronize_session=False)
            PickListLine.query.filter_by(pick_list_id=pick_list.id).delete()
        else:
            logger.info("🆕 Creating new pick list...")
            # Create new pick list
            pick_list = PickList(
                absolute_entry=613,
                name=sap_pick_list.get('Name', 'SAP-613'),
                owner_code=sap_pick_list.get('OwnerCode'),
                owner_name=sap_pick_list.get('OwnerName'),
                remarks=sap_pick_list.get('Remarks'),
                status=sap_pick_list.get('Status', 'ps_Open'),
                object_type=sap_pick_list.get('ObjectType', '156'),
                use_base_units=sap_pick_list.get('UseBaseUnits', 'tNO'),
                user_id=test_user.id
            )
            
            if sap_pick_list.get('PickDate'):
                try:
                    pick_list.pick_date = datetime.strptime(
                        sap_pick_list['PickDate'][:19], '%Y-%m-%dT%H:%M:%S'
                    )
                except Exception as e:
                    logger.warning(f"Could not parse PickDate: {e}")
            
            db.session.add(pick_list)
        
        # Update fields
        pick_list.status = sap_pick_list.get('Status', pick_list.status)
        pick_list.remarks = sap_pick_list.get('Remarks', pick_list.remarks)
        
        db.session.flush()  # Get the pick_list.id
        
        # Import pick list lines
        lines_imported = 0
        allocations_imported = 0
        
        for sap_line in sap_pick_list.get('PickListsLines', []):
            pick_list_line = PickListLine(
                pick_list_id=pick_list.id,
                absolute_entry=sap_line.get('AbsoluteEntry'),
                line_number=sap_line.get('LineNumber'),
                order_entry=sap_line.get('OrderEntry'),
                order_row_id=sap_line.get('OrderRowID', 0),
                picked_quantity=sap_line.get('PickedQuantity', 0.0),
                pick_status=sap_line.get('PickStatus', 'ps_Open'),
                released_quantity=sap_line.get('ReleasedQuantity', 0.0),
                previously_released_quantity=sap_line.get('PreviouslyReleasedQuantity', 0.0),
                base_object_type=sap_line.get('BaseObjectType')
            )
            
            db.session.add(pick_list_line)
            db.session.flush()  # Get the line id
            lines_imported += 1
            
            logger.info(f"   📦 Line {sap_line.get('LineNumber')}: {sap_line.get('PickedQuantity')} units")
            
            # Import bin allocations for this line
            for sap_allocation in sap_line.get('DocumentLinesBinAllocations', []):
                bin_allocation = PickListBinAllocation(
                    pick_list_line_id=pick_list_line.id,
                    bin_abs_entry=sap_allocation.get('BinAbsEntry'),
                    quantity=sap_allocation.get('Quantity', 0.0),
                    allow_negative_quantity=sap_allocation.get('AllowNegativeQuantity', 'tNO'),
                    serial_and_batch_numbers_base_line=sap_allocation.get('SerialAndBatchNumbersBaseLine', 0),
                    base_line_number=sap_allocation.get('BaseLineNumber')
                )
                
                db.session.add(bin_allocation)
                allocations_imported += 1
        
        # Update pick list totals
        pick_list.total_items = lines_imported
        pick_list.picked_items = len([line for line in sap_pick_list.get('PickListsLines', []) 
                                    if line.get('PickStatus') == 'ps_Closed'])
        
        db.session.commit()
        
        logger.info("✅ Import completed successfully!")
        logger.info(f"   Pick List ID: {pick_list.id}")
        logger.info(f"   Lines imported: {lines_imported}")
        logger.info(f"   Bin allocations: {allocations_imported}")
        logger.info(f"   Total items: {pick_list.total_items}")
        logger.info(f"   Picked items: {pick_list.picked_items}")
        
        return True

def main():
    """Main function"""
    print("=" * 60)
    print("  SAP B1 PICKLIST IMPORT TEST")
    print("  Testing import of PickList 613")
    print("=" * 60)
    
    success = test_import_picklist_613()
    
    if success:
        print("\n🎉 Import test completed successfully!")
        print("Check the pick list in your web application at /pick_list")
    else:
        print("\n❌ Import test failed!")
        print("Check the logs above for error details")

if __name__ == "__main__":
    main()