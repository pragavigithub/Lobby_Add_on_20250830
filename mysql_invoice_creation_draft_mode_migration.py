"""
MySQL Migration for Invoice Creation Draft Mode Enhancement
Date: 2025-08-30
Description: Enhanced Invoice Creation module with draft mode workflow and QC approval process

This migration adds support for:
1. Document status tracking (draft, pending_qc, posted, rejected)
2. QC approval workflow with SAP integration
3. Edit controls based on document status
"""

import mysql.connector
import os
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_migration():
    """Run the MySQL migration for Invoice Creation draft mode enhancement"""
    
    # MySQL connection configuration
    mysql_config = {
        'host': os.environ.get('MYSQL_HOST', 'localhost'),
        'port': int(os.environ.get('MYSQL_PORT', '3306')),
        'user': os.environ.get('MYSQL_USER', 'root'),
        'password': os.environ.get('MYSQL_PASSWORD', 'root@123'),
        'database': os.environ.get('MYSQL_DATABASE', 'wms_db_dev')
    }
    
    try:
        # Connect to MySQL
        connection = mysql.connector.connect(**mysql_config)
        cursor = connection.cursor()
        
        logger.info("🔄 Starting Invoice Creation Draft Mode migration...")
        
        # Check if invoice_documents table exists, create if not
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS invoice_documents (
                id INT AUTO_INCREMENT PRIMARY KEY,
                invoice_number VARCHAR(50),
                customer_code VARCHAR(20),
                customer_name VARCHAR(100),
                branch_id INT,
                branch_name VARCHAR(100),
                user_id INT NOT NULL,
                status VARCHAR(20) DEFAULT 'draft',
                bpl_id INT DEFAULT 5,
                bpl_name VARCHAR(100) DEFAULT 'ORD-CHENNAI',
                doc_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                due_date DATETIME,
                total_amount DECIMAL(15,2),
                sap_doc_entry INT,
                sap_doc_num VARCHAR(50),
                notes TEXT,
                json_payload TEXT,
                sap_response TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_user_status (user_id, status),
                INDEX idx_status (status),
                INDEX idx_customer (customer_code),
                INDEX idx_sap_doc (sap_doc_entry),
                FOREIGN KEY (user_id) REFERENCES users(id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        logger.info("✅ invoice_documents table created/verified")
        
        # Check if invoice_lines table exists, create if not
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS invoice_lines (
                id INT AUTO_INCREMENT PRIMARY KEY,
                invoice_id INT NOT NULL,
                line_number INT NOT NULL,
                item_code VARCHAR(50) NOT NULL,
                item_description VARCHAR(200),
                quantity DECIMAL(15,3) NOT NULL DEFAULT 1.0,
                unit_price DECIMAL(15,4),
                line_total DECIMAL(15,2),
                warehouse_code VARCHAR(10),
                warehouse_name VARCHAR(100),
                tax_code VARCHAR(20) DEFAULT 'CSGST@18',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_invoice (invoice_id),
                INDEX idx_item (item_code),
                INDEX idx_warehouse (warehouse_code),
                FOREIGN KEY (invoice_id) REFERENCES invoice_documents(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        logger.info("✅ invoice_lines table created/verified")
        
        # Check if invoice_serial_numbers table exists, create if not
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS invoice_serial_numbers (
                id INT AUTO_INCREMENT PRIMARY KEY,
                invoice_line_id INT NOT NULL,
                serial_number VARCHAR(100) NOT NULL,
                item_code VARCHAR(50) NOT NULL,
                item_description VARCHAR(200),
                warehouse_code VARCHAR(10),
                customer_code VARCHAR(20),
                customer_name VARCHAR(100),
                bpl_id INT DEFAULT 5,
                bpl_name VARCHAR(100),
                base_line_number INT DEFAULT 0,
                quantity DECIMAL(15,3) DEFAULT 1.0,
                validation_status VARCHAR(20) DEFAULT 'pending',
                validation_error TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_invoice_line (invoice_line_id),
                INDEX idx_serial (serial_number),
                INDEX idx_item (item_code),
                INDEX idx_validation_status (validation_status),
                FOREIGN KEY (invoice_line_id) REFERENCES invoice_lines(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        logger.info("✅ invoice_serial_numbers table created/verified")
        
        # Check if serial_number_lookups table exists, create if not
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS serial_number_lookups (
                id INT AUTO_INCREMENT PRIMARY KEY,
                serial_number VARCHAR(100) NOT NULL UNIQUE,
                item_code VARCHAR(50),
                item_name VARCHAR(200),
                warehouse_code VARCHAR(10),
                warehouse_name VARCHAR(100),
                branch_id INT,
                branch_name VARCHAR(100),
                lookup_status VARCHAR(20) DEFAULT 'pending',
                sap_response TEXT,
                last_updated DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_serial_unique (serial_number),
                INDEX idx_item (item_code),
                INDEX idx_warehouse (warehouse_code),
                INDEX idx_status (lookup_status)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        logger.info("✅ serial_number_lookups table created/verified")
        
        # Update status field to support the new workflow if it exists
        try:
            cursor.execute("""
                ALTER TABLE invoice_documents 
                MODIFY COLUMN status VARCHAR(20) DEFAULT 'draft'
                COMMENT 'Status: draft, pending_qc, posted, rejected, failed'
            """)
            logger.info("✅ invoice_documents.status field updated for draft mode workflow")
        except mysql.connector.Error as e:
            if "Duplicate column name" not in str(e):
                logger.warning(f"⚠️ Could not update status field: {e}")
        
        # Add indexes for performance if they don't exist
        try:
            cursor.execute("ALTER TABLE invoice_documents ADD INDEX idx_status_date (status, created_at)")
            logger.info("✅ Added status+date index for performance")
        except mysql.connector.Error:
            logger.info("ℹ️ Status+date index already exists")
        
        try:
            cursor.execute("ALTER TABLE invoice_lines ADD INDEX idx_invoice_line (invoice_id, line_number)")
            logger.info("✅ Added invoice+line number index for performance")
        except mysql.connector.Error:
            logger.info("ℹ️ Invoice+line number index already exists")
        
        # Commit all changes
        connection.commit()
        logger.info("✅ Invoice Creation Draft Mode migration completed successfully!")
        
        # Show current table status
        cursor.execute("SELECT COUNT(*) FROM invoice_documents")
        invoice_count = cursor.fetchone()[0]
        logger.info(f"📊 Current invoice documents: {invoice_count}")
        
        cursor.execute("SELECT status, COUNT(*) FROM invoice_documents GROUP BY status")
        status_counts = cursor.fetchall()
        for status, count in status_counts:
            logger.info(f"📊 Status '{status}': {count} documents")
        
    except mysql.connector.Error as error:
        logger.error(f"❌ MySQL migration error: {error}")
        if 'connection' in locals():
            connection.rollback()
        raise
    
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'connection' in locals():
            connection.close()
        logger.info("🔚 MySQL connection closed")

if __name__ == "__main__":
    run_migration()