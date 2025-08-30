#!/usr/bin/env python3
"""
Quick fix for existing MySQL branches table schema
This script adds missing columns to the branches table without recreating it
"""

import os
import logging
import pymysql
from pymysql.cursors import DictCursor

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def fix_branches_schema():
    """Fix branches table schema by adding missing columns"""
    config = {
        'host': os.getenv('MYSQL_HOST', 'localhost'),
        'port': int(os.getenv('MYSQL_PORT', 3306)),
        'user': os.getenv('MYSQL_USER', 'root'),
        'password': os.getenv('MYSQL_PASSWORD', ''),
        'database': os.getenv('MYSQL_DATABASE', 'wms_db_dev'),
        'charset': 'utf8mb4',
        'autocommit': False
    }
    
    try:
        connection = pymysql.connect(**config)
        logger.info(f"✅ Connected to MySQL: {config['database']}")
        
        with connection.cursor() as cursor:
            # Check which columns are missing
            cursor.execute("""
                SELECT COLUMN_NAME 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'branches'
            """, [config['database']])
            
            existing_columns = [row[0] for row in cursor.fetchall()]
            logger.info(f"Existing columns: {existing_columns}")
            
            # Add missing columns
            required_columns = {
                'name': 'VARCHAR(100)',
                'description': 'VARCHAR(255)', 
                'branch_code': 'VARCHAR(10) UNIQUE',
                'branch_name': 'VARCHAR(100)',
                'city': 'VARCHAR(50)',
                'state': 'VARCHAR(50)',
                'postal_code': 'VARCHAR(20)',
                'country': 'VARCHAR(50)',
                'warehouse_codes': 'TEXT',
                'is_default': 'BOOLEAN DEFAULT FALSE'
            }
            
            for col_name, col_def in required_columns.items():
                if col_name not in existing_columns:
                    try:
                        cursor.execute(f"ALTER TABLE branches ADD COLUMN {col_name} {col_def}")
                        logger.info(f"✅ Added column: {col_name}")
                    except Exception as e:
                        logger.warning(f"⚠️ Could not add column {col_name}: {e}")
            
            # Ensure there's at least one branch record
            cursor.execute("SELECT COUNT(*) as count FROM branches")
            count = cursor.fetchone()[0]
            
            if count == 0:
                logger.info("Inserting default branch record...")
                cursor.execute("""
                    INSERT INTO branches (
                        id, name, description, branch_code, branch_name, 
                        address, phone, email, manager_name, is_active, is_default
                    ) VALUES (
                        'BR001', 'Main Branch', 'Primary warehouse branch', 
                        '01', 'Main Branch', '123 Warehouse St', 
                        '+1-555-0123', 'main@company.com', 'Warehouse Manager', 
                        TRUE, TRUE
                    )
                """)
                logger.info("✅ Default branch record created")
            
        connection.commit()
        logger.info("✅ Branches schema fix completed successfully!")
        
    except Exception as e:
        logger.error(f"❌ Fix failed: {e}")
        return False
    finally:
        if 'connection' in locals():
            connection.close()
    
    return True

if __name__ == "__main__":
    success = fix_branches_schema()
    if success:
        print("\n🎉 Branches schema fixed! You can now run your application.")
    else:
        print("\n❌ Fix failed. Please check the error messages above.")