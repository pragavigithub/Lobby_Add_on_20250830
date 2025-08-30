# MySQL PickList Migration Guide - August 2025 Update

This guide helps you migrate your MySQL database to support the complete SAP B1 compatible PickList structure with all recent enhancements.

## What This Migration Does (August 2025 Update)

### Updates to `pick_lists` Table
- Adds complete SAP B1 compatible columns:
  - `absolute_entry` - SAP B1 unique identifier
  - `name` - Pick list name from SAP B1
  - `owner_code` - SAP B1 owner code
  - `owner_name` - SAP B1 owner name
  - `pick_date` - Pick date from SAP B1
  - `remarks` - SAP B1 remarks
  - `object_type` - SAP B1 object type
  - `use_base_units` - SAP B1 base units flag
  - `priority` - Pick list priority (normal, high, urgent)
  - `warehouse_code` - Warehouse code
  - `customer_code` - Customer code
  - `customer_name` - Customer name
  - `total_items` - Total items count
  - `picked_items` - Picked items count
  - `notes` - Additional notes

### Schema Fixes (August 2025)
- Makes `sales_order_number` and `pick_list_number` nullable for SAP B1 compatibility
- Adds performance indexes on SAP B1 fields
- Adds unique constraint on `absolute_entry` for data integrity

### Creates New Tables
1. **`pick_list_lines`** - Individual line items in pick lists
   - Maps exactly to SAP B1 PickListsLines structure
   - Includes item details, quantities, status, and tracking
   - Enhanced with item_code, item_name, and warehouse fields

2. **`pick_list_bin_allocations`** - Bin allocation details
   - Maps exactly to SAP B1 DocumentLinesBinAllocations structure
   - Manages bin locations and quantities with full tracking
   - Includes picked_quantity tracking for real-time updates

### Creates Integration Views
1. **`vw_sap_pick_lists`** - Complete pick list view with aggregated line data
2. **`vw_pick_list_metrics`** - Performance metrics and completion tracking

## Prerequisites

1. **Python Environment**
   ```bash
   pip install pymysql
   ```

2. **MySQL Database Access**
   - MySQL server running
   - Database credentials
   - CREATE, ALTER, INDEX privileges

3. **Environment Variables** (Optional)
   ```bash
   export MYSQL_HOST=localhost
   export MYSQL_PORT=3306
   export MYSQL_USER=root
   export MYSQL_PASSWORD=your_password
   export MYSQL_DATABASE=warehouse_db
   ```

## How to Run the Migration

### Option 1: Complete Migration (Recommended - August 2025)
```bash
python mysql_complete_migration.py
```

### Option 2: Quick Run (Legacy)
```bash
python run_mysql_picklist_migration.py
```

### Option 3: Direct Migration (Legacy)
```bash
python mysql_picklist_migration.py
```

### Option 4: Manual Environment Setup
```python
import os
os.environ['MYSQL_HOST'] = 'your_host'
os.environ['MYSQL_PASSWORD'] = 'your_password'
os.environ['MYSQL_DATABASE'] = 'your_database'

from mysql_picklist_migration import main
main()
```

## Migration Process

1. **Connects to MySQL** - Establishes database connection
2. **Checks Existing Structure** - Verifies current table state
3. **Adds New Columns** - Safely adds missing columns to pick_lists
4. **Creates New Tables** - Creates pick_list_lines and bin_allocations tables
5. **Updates Existing Data** - Sets default values for existing records
6. **Creates Indexes** - Adds performance indexes
7. **Shows Summary** - Reports migration results

## Safety Features

- **Transaction-based** - All changes in a single transaction
- **Rollback on Error** - Automatic rollback if anything fails
- **Non-destructive** - Only adds columns/tables, never removes data
- **Idempotent** - Safe to run multiple times

## What Happens to Existing Data

- **Existing pick lists preserved** - No data loss
- **Default values applied** - New columns get sensible defaults
- **Relationships maintained** - Foreign keys preserved

## After Migration

### New Capabilities
1. **SAP B1 Sync** - Real-time synchronization with SAP B1 PickLists
2. **Enhanced Search** - Search by customer, warehouse, priority
3. **Line Item Details** - Detailed pick list line management
4. **Bin Management** - Precise bin location tracking

### Updated Models
Your Flask models now support:
- SAP B1 absolute entry mapping
- Pick list line items with bin allocations
- Enhanced filtering and search capabilities
- Real-time status synchronization

### API Endpoints
New endpoints available:
- `/api/sync-sap-pick-lists` - Sync with SAP B1
- Enhanced pick list search and pagination

## Verification

After migration, verify:

1. **Table Structure**
   ```sql
   DESCRIBE pick_lists;
   DESCRIBE pick_list_lines;
   DESCRIBE pick_list_bin_allocations;
   ```

2. **Data Integrity**
   ```sql
   SELECT COUNT(*) FROM pick_lists;
   SELECT * FROM pick_lists LIMIT 5;
   ```

3. **Application Test**
   - Visit `/pick_list` in your web application
   - Test search and pagination
   - Try creating a new pick list

## Troubleshooting

### Common Issues

1. **Connection Failed**
   - Check MySQL server is running
   - Verify credentials
   - Ensure database exists

2. **Permission Denied**
   - Ensure user has CREATE, ALTER privileges
   - Check database permissions

3. **Column Already Exists**
   - Migration is idempotent - this is normal
   - Script will skip existing columns

### Getting Help

Check the migration logs for detailed error messages. The script provides comprehensive logging to help diagnose issues.

## Rollback (If Needed)

If you need to rollback (not recommended as it will lose data):

```sql
-- Backup first!
-- DROP TABLE pick_list_bin_allocations;
-- DROP TABLE pick_list_lines;
-- ALTER TABLE pick_lists DROP COLUMN absolute_entry;
-- ... (drop other new columns)
```

**Note**: Only rollback if absolutely necessary and after backing up your data.