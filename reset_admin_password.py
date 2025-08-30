#!/usr/bin/env python3
"""
Simple script to reset admin password in MySQL database
"""

import os
import mysql.connector
from werkzeug.security import generate_password_hash

def reset_admin_password():
    """Reset admin password to 'admin123'"""
    
    # Database connection details
    host = os.environ.get('MYSQL_HOST', 'localhost')
    port = int(os.environ.get('MYSQL_PORT', '3306'))
    user = os.environ.get('MYSQL_USER', 'root')
    password = os.environ.get('MYSQL_PASSWORD', '')
    database = os.environ.get('MYSQL_DATABASE', 'wms_db')
    
    try:
        print("Connecting to MySQL database...")
        connection = mysql.connector.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database
        )
        
        cursor = connection.cursor()
        
        # Generate proper password hash
        password_hash = generate_password_hash('admin123')
        print(f"Generated password hash: {password_hash[:50]}...")
        
        # Update admin user password
        cursor.execute("""
            UPDATE users SET 
                password_hash = %s,
                role = 'admin',
                user_is_active = TRUE
            WHERE username = 'admin'
        """, (password_hash,))
        
        if cursor.rowcount > 0:
            print("✅ Admin password updated successfully!")
        else:
            print("❌ No admin user found to update")
            
            # Create admin user if doesn't exist
            cursor.execute("""
                INSERT INTO users (username, email, password_hash, role, user_is_active, first_name, last_name)
                VALUES ('admin', 'admin@wms.local', %s, 'admin', TRUE, 'Admin', 'User')
            """, (password_hash,))
            print("✅ Created new admin user")
        
        connection.commit()
        cursor.close()
        connection.close()
        
        print("\nLogin credentials:")
        print("Username: admin")
        print("Password: admin123")
        
        return True
        
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    reset_admin_password()