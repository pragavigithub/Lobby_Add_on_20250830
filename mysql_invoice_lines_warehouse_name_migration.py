"""
MySQL Migration: Add warehouse_name column to invoice_lines table
This migration adds the missing warehouse_name column to the invoice_lines table
for compatibility with the Invoice Creation module.

Run this script against your local MySQL database to fix the schema mismatch.
"""

import pymysql
import logging

# Database configuration - update these with your local MySQL settings
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',  # Change to your MySQL username
    'password': 'root123',  # Change to your MySQL password
    'database': 'wms_test',  # Change to your database name
    'port': 3306
}

def run_migration():
    """Add warehouse_name column to invoice_lines table"""
    try:
        # Connect to MySQL database
        connection = pymysql.connect(**DB_CONFIG)
        cursor = connection.cursor()
        
        print("✅ Connected to MySQL database")
        
        # Check if warehouse_name column already exists
        cursor.execute("""
            SELECT COLUMN_NAME 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_NAME = 'invoice_lines' 
            AND COLUMN_NAME = 'warehouse_name'
            AND TABLE_SCHEMA = %s
        """, (DB_CONFIG['database'],))
        
        if cursor.fetchone():
            print("⚠️ Column 'warehouse_name' already exists in invoice_lines table")
            return
        
        # Add warehouse_name column
        print("🔄 Adding warehouse_name column to invoice_lines table...")
        cursor.execute("""
            ALTER TABLE invoice_lines 
            ADD COLUMN warehouse_name VARCHAR(100) NULL
            AFTER warehouse_code
        """)
        
        # Commit the changes
        connection.commit()
        print("✅ Successfully added warehouse_name column to invoice_lines table")
        
        # Verify the column was added
        cursor.execute("""
            SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_NAME = 'invoice_lines' 
            AND TABLE_SCHEMA = %s
            ORDER BY ORDINAL_POSITION
        """, (DB_CONFIG['database'],))
        
        print("\n📋 Current invoice_lines table schema:")
        for column in cursor.fetchall():
            print(f"  - {column[0]} ({column[1]}) - Nullable: {column[2]}")
        
    except pymysql.Error as e:
        print(f"❌ MySQL Error: {e}")
        if connection:
            connection.rollback()
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        if 'connection' in locals():
            connection.close()
            print("🔐 Database connection closed")

if __name__ == "__main__":
    print("🚀 Starting MySQL Migration: Add warehouse_name to invoice_lines")
    print("=" * 60)
    print(f"Target Database: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")
    print("=" * 60)
    
    # Confirm before running
    confirm = input("Do you want to run this migration? (y/N): ")
    if confirm.lower() in ['y', 'yes']:
        run_migration()
    else:
        print("❌ Migration cancelled")