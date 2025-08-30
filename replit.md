# Warehouse Management System (WMS)

## Overview
A Flask-based Warehouse Management System (WMS) designed to streamline warehouse operations. It integrates with SAP for critical functions like barcode scanning, inventory management, goods receipt processing, pick list generation, and inventory transfers. The system aims to enhance efficiency and accuracy in warehouse logistics.

## User Preferences
None specified yet

## System Architecture
The WMS is built using a Flask web application backend with server-side rendering through Jinja2 templates for the frontend. It supports a SQLite database by default, with robust configurations for PostgreSQL and MySQL, including automatic fallback mechanisms.

Key architectural decisions and features include:
- **Core Modules**: Goods Receipt Purchase Order (GRPO) management, Inventory Transfer Requests, Pick List management, Barcode scanning, Branch management, and a Quality Control (QC) Dashboard.
- **User Management**: Implemented with Flask-Login, featuring user authentication, role-based access control, and comprehensive user/branch management functionalities. Permissions are integrated throughout templates for navigation filtering.
- **SAP Integration**: Extensive integration with SAP B1 APIs for various operations including:
    - Sales Order fetching for enhanced picklist functionality.
    - Serial number validation and auto-population for item details.
    - Direct posting of approved inventory transfers and invoices.
    - Handling of specific SAP B1 API endpoints for serial number validation and document creation.
- **Data Management**: Robust database migration capabilities ensure schema consistency across different environments (SQLite, MySQL, PostgreSQL), including handling missing columns and legacy data.
- **UI/UX Enhancements**:
    - Status-based UI controls for modules like GRPO and Inventory Transfers, disabling actions based on document status.
    - Visual highlighting and user-managed duplicate detection for serial numbers.
    - Tab key navigation and auto-fetch for serial number entry.
    - Display of relevant item and customer details in picklists.
- **Performance**: Optimized batch processing for serial number validation (e.g., 1000+ serials in chunks of 100) to improve efficiency and avoid API timeouts.
- **Workflow Automation**:
    - **QC Workflow**: Integrated QC approval/rejection processes for GRPO, Serial Item Transfers, and Invoices, with direct SAP B1 posting upon approval.
    - **Draft Mode**: Invoice creation supports a draft mode workflow, allowing full editing until QC approval, at which point it becomes read-only and posts to SAP.
- **Security**: Adheres to best practices with client/server separation, environment variable-based configuration for sensitive data (no hardcoded secrets), and proper password hashing.

## External Dependencies
The system relies on the following key external services and integrations:
- **SAP B1**: Primary integration for warehouse operations, including:
    - Goods Receipt Purchase Orders
    - Inventory Transfers
    - Sales Orders (for picklist enhancement)
    - Serial Number validation and lookup
    - Invoice creation and posting
- **PostgreSQL**: Preferred database for cloud compatibility.
- **SQLite**: Default fallback database.
- **MySQL**: Supported database, primarily for local development and specific migration paths.
- **Jinja2**: Templating engine for server-side rendering.
- **Flask-Login**: For user authentication and session management.
- **jQuery**: For frontend interactivity and dynamic content.