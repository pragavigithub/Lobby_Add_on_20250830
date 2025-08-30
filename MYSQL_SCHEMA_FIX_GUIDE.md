# MySQL Schema Fix Guide

## Problem
Your local MySQL database is missing columns that the updated WMS application requires:
- `users.first_name`, `users.last_name`, `users.branch_name`, etc.
- `branches.description`, `branches.address`, `branches.phone`, etc.
- Missing `document_number_series` table for GRPO numbering

## Quick Fix Solution

### Method 1: Run the Schema Fix Script (Recommended)

1. **Run the fix script:**
   ```bash
   python fix_mysql_schema.py
   ```

2. **Restart your Flask application:**
   ```bash
   python main.py
   ```

### Method 2: Manual MySQL Commands

If the script doesn't work, run these SQL commands manually in MySQL:

```sql
-- Add missing columns to users table
ALTER TABLE users ADD COLUMN first_name VARCHAR(80);
ALTER TABLE users ADD COLUMN last_name VARCHAR(80);
ALTER TABLE users ADD COLUMN branch_name VARCHAR(100);
ALTER TABLE users ADD COLUMN must_change_password BOOLEAN DEFAULT FALSE;
ALTER TABLE users ADD COLUMN last_login TIMESTAMP NULL;
ALTER TABLE users ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP;

-- Fix the role column naming issue (rename user_role to role)
ALTER TABLE users CHANGE COLUMN user_role role VARCHAR(20) DEFAULT 'user';

-- Add missing columns to branches table  
ALTER TABLE branches ADD COLUMN description TEXT;
ALTER TABLE branches ADD COLUMN address TEXT;
ALTER TABLE branches ADD COLUMN phone VARCHAR(20);
ALTER TABLE branches ADD COLUMN email VARCHAR(100);
ALTER TABLE branches ADD COLUMN manager_name VARCHAR(100);
ALTER TABLE branches ADD COLUMN is_default BOOLEAN DEFAULT FALSE;
ALTER TABLE branches ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP;

-- Create document number series table
CREATE TABLE IF NOT EXISTS document_number_series (
    id INT AUTO_INCREMENT PRIMARY KEY,
    document_type VARCHAR(20) NOT NULL UNIQUE,
    prefix VARCHAR(10) NOT NULL, 
    current_number INT DEFAULT 1,
    year_suffix BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_document_type (document_type)
);

-- Insert default document series
INSERT IGNORE INTO document_number_series (document_type, prefix, current_number, year_suffix)
VALUES 
('GRPO', 'GRPO-', 1, TRUE),
('TRANSFER', 'TR-', 1, TRUE), 
('PICKLIST', 'PL-', 1, TRUE);

-- Update existing admin user
UPDATE users SET 
    first_name = COALESCE(first_name, 'Admin'),
    last_name = COALESCE(last_name, 'User'),
    branch_name = COALESCE(branch_name, 'Head Office'),
    role = COALESCE(role, 'admin')
WHERE username = 'admin';

-- Ensure default branch exists
INSERT IGNORE INTO branches (id, name, description, is_active)
VALUES ('HQ001', 'Head Office', 'Main headquarters branch', TRUE);

-- Add missing columns to grpo_documents table
ALTER TABLE grpo_documents ADD COLUMN sap_document_number VARCHAR(50);
ALTER TABLE grpo_documents ADD COLUMN qc_user_id INT;
ALTER TABLE grpo_documents ADD COLUMN qc_notes TEXT;
ALTER TABLE grpo_documents ADD COLUMN draft_or_post VARCHAR(20) DEFAULT 'draft';
```

### Method 3: Complete Database Rebuild

If you want to start fresh with a complete schema:

1. **Run the complete migration:**
   ```bash
   python mysql_complete_migration.py
   ```

This will create a completely new database with all the latest schema updates.

## Verification

After running the fix, you should see:
- ✅ No more "Unknown column" errors
- ✅ Successful login with admin/admin123
- ✅ GRPO creation with auto-generated numbers (GRPO-0001-2025)
- ✅ Quantity validation working properly

## Features Added

1. **GRPO Validation:** Prevents receiving more than PO order quantity
2. **Document Numbering:** Auto-generates GRPO numbers like GRPO-0001-2025
3. **Enhanced Schema:** All missing columns added for proper functionality

## Support

If you continue to have issues:
1. Check your .env file has correct MySQL credentials
2. Ensure MySQL service is running
3. Verify you have proper permissions to alter tables
4. Run the fix script with administrator privileges if needed