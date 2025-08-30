# Warehouse Management System (WMS) - Complete Setup Guide

## Overview

This is a comprehensive Warehouse Management System (WMS) built with Flask that integrates with SAP Business One (B1) for enterprise-level warehouse operations. The system supports both PostgreSQL (for Replit deployment) and MySQL (for local development).

## Quick Setup

### For Local MySQL Development

Run the single migration script:

```bash
python mysql_complete_migration.py
```

This script will:
1. Create a `.env` file with MySQL configuration
2. Create the MySQL database
3. Create all required tables with complete schema
4. Set up default admin user and branch

### For Replit PostgreSQL Deployment

The application is already configured for PostgreSQL on Replit and will work automatically.

## System Requirements

- Python 3.8+
- Flask with dependencies (already installed)
- For local development: MySQL Server
- For production: PostgreSQL (provided by Replit)

## Default Login Credentials

After setup, login with:
- **Username:** admin
- **Password:** admin123

## Core Features

### 1. Authentication & User Management
- Role-based access control (admin, manager, user, qc)
- Branch-specific permissions
- Session management with Flask-Login

### 2. Warehouse Operations
- **GRPO (Goods Receipt PO)**: Scan PO numbers, validate items, record receipts
- **Inventory Transfer**: Inter-warehouse and bin-to-bin transfers with QC approval
- **Pick Lists**: Sales order-based picking operations
- **Inventory Counting**: Cycle counting and physical inventory tasks
- **Bin Scanning**: Real-time SAP B1 integration for OnStock/OnHand quantities

### 3. SAP B1 Integration
- Service Layer REST API communication
- Real-time data synchronization
- Enhanced bin scanning with proper API patterns:
  - BinLocations API: `?$filter=BinCode eq 'BIN_CODE'`
  - Warehouses API: `?$select=BusinessPlaceID,WarehouseCode,DefaultBin&$filter=WarehouseCode eq 'WAREHOUSE'`
  - BatchNumberDetails API: `?$filter=SystemNumber eq SYSTEM_NUMBER`
  - ItemWhsStock API: `?$filter=ItemCode eq 'ITEM' and WarehouseCode eq 'WAREHOUSE'`

### 4. Barcode Management
- Multiple label formats (standard, large, small, custom)
- QR code generation for items without supplier barcodes
- Camera-based scanning through device camera
- Label reprinting functionality

### 5. Progressive Web App (PWA)
- Offline capability with service worker
- Mobile-optimized responsive design
- App-like experience for handheld devices

## Database Schema

The system creates these tables:

### Core Tables
- `users` - User accounts and permissions
- `branches` - Branch/location information

### GRPO Module
- `grpo_documents` - Goods Receipt PO documents
- `grpo_items` - Individual items in GRPO

### Inventory Transfer Module
- `inventory_transfers` - Transfer requests with QC workflow
- `inventory_transfer_items` - Items in transfers with batch tracking

### Pick List Module
- `pick_lists` - Pick list documents
- `pick_list_items` - Items to pick

### Inventory Management
- `inventory_counts` - Counting tasks
- `inventory_count_items` - Counted items
- `bin_locations` - Warehouse bin locations
- `bin_items` - Items stored in bins
- `bin_scanning_logs` - Bin scanning activity logs

### Barcode System
- `barcode_labels` - Generated barcode labels

## Environment Configuration

The `.env` file includes:

```env
# Database Configuration - MySQL Primary
DATABASE_URL=mysql+pymysql://user:password@host:port/database

# MySQL Configuration
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=wms_db

# Session Configuration
SESSION_SECRET=your-secret-key-here

# SAP B1 Integration
SAP_B1_SERVER=https://your-sap-server:50000
SAP_B1_USERNAME=your_sap_user
SAP_B1_PASSWORD=your_sap_password
SAP_B1_COMPANY_DB=your_company_db

# Application Configuration
FLASK_ENV=development
FLASK_DEBUG=True
```

## Running the Application

### Local Development (MySQL)
1. Run the migration: `python mysql_complete_migration.py`
2. Start the application: `python main.py`
3. Open http://localhost:5000
4. Login with admin/admin123

### Replit Deployment (PostgreSQL)
The application runs automatically on Replit with PostgreSQL. Access it through your Replit URL.

## Troubleshooting

### MySQL Connection Issues
1. Ensure MySQL server is running
2. Verify credentials in `.env` file
3. Check database user permissions
4. Install required package: `pip install mysql-connector-python`

### SAP B1 Integration Issues
1. Verify SAP B1 Service Layer is accessible
2. Check credentials in `.env` file
3. Ensure SSL certificates are valid
4. Test connection from SAP admin dashboard

### Bin Scanning Issues
The bin scanning has been enhanced with proper SAP API integration. If issues persist:
1. Check SAP B1 connectivity
2. Verify warehouse and bin codes exist in SAP
3. Check user permissions for inventory queries

## Mobile Application

A complete React Native mobile application is available with:
- Offline-first architecture with SQLite
- Barcode scanning with camera integration
- All core WMS modules (GRPO, Transfers, Pick Lists)
- JWT authentication and role-based access
- Background synchronization with backend

## Architecture

### Backend
- **Framework:** Flask with SQLAlchemy ORM
- **Database:** PostgreSQL (production) / MySQL (development)
- **Authentication:** Flask-Login with role-based permissions
- **SAP Integration:** REST API with Service Layer

### Frontend
- **UI:** Bootstrap 5 responsive design
- **PWA:** Service worker for offline capability
- **Barcode:** QuaggaJS and QR Scanner libraries
- **Icons:** Feather Icons

### Security
- Password hashing with Werkzeug
- Session management with Flask-Login
- Role-based access control
- Environment-based configuration

## API Endpoints

Key API endpoints for mobile/external integration:
- `/api/scan_bin` - Bin scanning with real-time SAP data
- `/api/validate_transfer_request` - Transfer request validation
- `/api/generate-qr-label` - QR code generation
- `/api/sync_bin_data` - SAP data synchronization

## Next Steps

1. Start with `python mysql_complete_migration.py` for local setup
2. Configure SAP B1 connection in `.env`
3. Test bin scanning functionality
4. Set up mobile application if needed
5. Configure barcode printers for label generation

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Verify environment configuration
3. Test SAP B1 connectivity
4. Review application logs for specific errors

---

*This guide covers the complete setup and operation of the WMS system. All features are production-ready with dual database support for flexible deployment.*