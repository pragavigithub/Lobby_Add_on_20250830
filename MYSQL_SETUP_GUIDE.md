# MySQL Integration Setup Guide

Your WMS application is now configured to **prioritize MySQL** for local development while maintaining PostgreSQL support for Replit cloud environment.

## Current Status
✅ **Application Running**: Server is active on port 5000
✅ **MySQL Priority**: Database connection logic updated to check MySQL first
✅ **Dual Database**: Maintains sync between local MySQL and cloud PostgreSQL
✅ **Auto-Fallback**: Gracefully falls back to PostgreSQL/SQLite if MySQL unavailable

## Setting Up MySQL on Your Local Machine

### Option 1: Quick Setup (Recommended)
Run the setup script to configure your environment:
```bash
python setup_mysql_env.py
```

This will:
- Create a `.env` file with MySQL configuration
- Set up default connection parameters
- Test your MySQL connection

### Option 2: Manual Setup
Create a `.env` file in your project root:
```env
# MySQL Configuration (Primary Database)
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_mysql_password
MYSQL_DATABASE=wms_db_dev

# Alternative: Direct DATABASE_URL
DATABASE_URL=mysql+pymysql://root:your_password@localhost:3306/wms_db_dev

# Other settings...
SESSION_SECRET=your-secret-key
```

### Option 3: Using Docker MySQL (Easiest)
```bash
# Run MySQL in Docker
docker run --name mysql-wms \
  -e MYSQL_ROOT_PASSWORD=root@123 \
  -e MYSQL_DATABASE=wms_db_dev \
  -p 3306:3306 \
  -d mysql:8.0

# Then use these settings in .env:
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=root@123
MYSQL_DATABASE=wms_db_dev
```

## Database Priority Order

The application now connects in this order:

1. **MySQL (Local Development)** - Checks for:
   - `MYSQL_HOST`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE` environment variables
   - OR `DATABASE_URL` starting with `mysql+pymysql://`

2. **PostgreSQL (Replit Cloud)** - Uses:
   - `DATABASE_URL` environment variable (automatically set by Replit)

3. **SQLite (Fallback)** - Creates:
   - Local SQLite file in `instance/wms.db`

## Testing Your MySQL Connection

```bash
# Test connection with current settings
python setup_mysql_env.py test

# Or check application logs when it starts
# Look for: "✅ MySQL database connection successful"
```

## Verifying Integration

1. **Check Logs**: When you restart the application, you should see:
   ```
   ✅ Using MySQL from individual environment variables
   ✅ MySQL database connection successful
   ✅ Dual database support initialized for MySQL sync
   ```

2. **Database Tables**: MySQL tables will be automatically created when the app starts

3. **Data Sync**: Any changes made in the application will sync to both databases

## Troubleshooting

### MySQL Connection Failed
- Ensure MySQL server is running
- Check credentials in `.env` file
- Verify database exists: `CREATE DATABASE wms_db_dev;`
- Check firewall/port 3306 access

### No MySQL Environment Variables
- Run `python setup_mysql_env.py` to create `.env` file
- Restart the application after creating `.env`

### Still Using PostgreSQL/SQLite
- Ensure `.env` file exists in project root
- Check that environment variables are loaded
- Verify MySQL server is accessible

## Next Steps

1. Set up your local MySQL server
2. Run the setup script: `python setup_mysql_env.py`
3. Restart the application to use MySQL
4. Test the inventory transfer functionality with "Add Remaining" buttons
5. Verify SAP B1 integration and batch selection works

Your application will now prioritize your local MySQL database while maintaining full compatibility with the Replit cloud environment!