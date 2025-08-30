#!/usr/bin/env python3
"""
Check and Fix Admin User Script
Verifies and resets admin user credentials in MySQL database
"""

import os
import sys
import mysql.connector
from mysql.connector import Error
from werkzeug.security import generate_password_hash

def check_and_fix_admin():
    """Check admin user and fix credentials"""
    
    # Get database connection details from environment
    host = os.environ.get('MYSQL_HOST', 'localhost')
    port = int(os.environ.get('MYSQL_PORT', '3306'))
    user = os.environ.get('MYSQL_USER', 'root')
    password = os.environ.get('MYSQL_PASSWORD', '')
    database = os.environ.get('MYSQL_DATABASE', 'wms_db')
    
    try:
        print("🔧 Connecting to MySQL database...")
        connection = mysql.connector.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database
        )
        
        if connection.is_connected():
            cursor = connection.cursor()
            
            print("📝 Checking current admin user...")
            
            # Check if admin user exists and show current data
            cursor.execute("SELECT id, username, email, password_hash, role FROM users WHERE username = 'admin'")
            admin_user = cursor.fetchone()
            
            if admin_user:
                print(f"✓ Admin user found:")
                print(f"  ID: {admin_user[0]}")
                print(f"  Username: {admin_user[1]}")
                print(f"  Email: {admin_user[2]}")
                print(f"  Password Hash: {admin_user[3][:50]}...")
                print(f"  Role: {admin_user[4]}")
                
                # Generate new password hash for 'admin123'
                new_password_hash = generate_password_hash('admin123')
                print(f"\n📝 Updating admin password...")
                
                cursor.execute("""
                    UPDATE users SET 
                        password_hash = %s,
                        role = 'admin',
                        user_is_active = 1,
                        first_name = 'Admin',
                        last_name = 'User',
                        branch_name = 'Head Office'
                    WHERE username = 'admin'
                """, (new_password_hash,))
                
                print("✅ Admin user updated with new password")
                
            else:
                print("❌ Admin user not found. Creating new admin user...")
                
                # Create new admin user
                password_hash = generate_password_hash('admin123')
                cursor.execute("""
                    INSERT INTO users (username, email, password_hash, role, user_is_active, first_name, last_name, branch_name)
                    VALUES ('admin', 'admin@wms.local', %s, 'admin', 1, 'Admin', 'User', 'Head Office')
                """, (password_hash,))
                
                print("✅ New admin user created")
            
            # Show all users for verification
            print("\n📋 All users in database:")
            cursor.execute("SELECT id, username, email, role, user_is_active FROM users")
            users = cursor.fetchall()
            
            for user_data in users:
                status = "Active" if user_data[4] else "Inactive"
                print(f"  {user_data[0]}: {user_data[1]} ({user_data[2]}) - Role: {user_data[3]} - {status}")
            
            connection.commit()
            cursor.close()
            connection.close()
            
            print("\n🎉 Admin user verification and fix completed!")
            print("📌 Login credentials:")
            print("   Username: admin")
            print("   Password: admin123")
            print("\nYou can now login to your application!")
            
            return True
            
    except Error as e:
        print(f"❌ Database connection error: {e}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("   WMS Admin User Check & Fix Script")
    print("=" * 60)
    print()
    
    success = check_and_fix_admin()
    
    if success:
        print("\n🚀 Admin user is ready! Try logging in now.")
    else:
        print("\n❌ Fix failed. Please check your database connection.")
        sys.exit(1)