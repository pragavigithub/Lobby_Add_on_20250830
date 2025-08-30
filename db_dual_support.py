"""
Dual Database Support Module
Handles both SQLite (for Replit) and MySQL (for local development) synchronization
"""

import os
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
import json
from datetime import datetime

class DualDatabaseManager:
    """Manages dual database support for SQLite and MySQL"""
    
    def __init__(self, app):
        self.app = app
        self.sqlite_engine = None
        self.mysql_engine = None
        self.setup_engines()
    
    def setup_engines(self):
        """Setup both SQLite and MySQL engines"""
        # SQLite engine (primary for Replit)
        sqlite_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'wms.db')
        self.sqlite_engine = create_engine(f"sqlite:///{sqlite_path}")
        
        # MySQL engine (for local development sync)
        mysql_config = {
            'host': os.environ.get('MYSQL_HOST', 'localhost'),
            'port': os.environ.get('MYSQL_PORT', '3306'),
            'user': os.environ.get('MYSQL_USER', 'root'),
            'password': os.environ.get('MYSQL_PASSWORD', 'root@123'),
            'database': os.environ.get('MYSQL_DATABASE', 'wms_db_dev')
        }
        
        try:
            mysql_url = f"mysql+pymysql://{mysql_config['user']}:{mysql_config['password']}@{mysql_config['host']}:{mysql_config['port']}/{mysql_config['database']}"
            self.mysql_engine = create_engine(mysql_url, connect_args={'connect_timeout': 5})
            
            # Test the connection
            with self.mysql_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                
            logging.info("✅ MySQL engine configured and connected successfully")
        except Exception as e:
            logging.warning(f"⚠️ MySQL engine connection failed: {e}. Operating in SQLite-only mode.")
            self.mysql_engine = None
    
    def sync_to_mysql(self, table_name, operation, data=None, where_clause=None):
        """Synchronize changes to MySQL database"""
        if not self.mysql_engine:
            logging.debug(f"MySQL not available, skipping sync for {table_name}")
            return
        
        if not data and operation in ['INSERT', 'UPDATE']:
            logging.warning(f"No data provided for {operation} operation on {table_name}")
            return
        
        try:
            with self.mysql_engine.connect() as conn:
                if operation == 'INSERT' and data:
                    # Build INSERT statement
                    columns = ', '.join(data.keys())
                    placeholders = ', '.join([f":{key}" for key in data.keys()])
                    sql = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"
                    conn.execute(text(sql), data)
                    
                elif operation == 'UPDATE' and data:
                    # Build UPDATE statement
                    set_clause = ', '.join([f"{key} = :{key}" for key in data.keys()])
                    sql = f"UPDATE {table_name} SET {set_clause} WHERE {where_clause}"
                    conn.execute(text(sql), data)
                    
                elif operation == 'DELETE':
                    # Build DELETE statement
                    sql = f"DELETE FROM {table_name} WHERE {where_clause}"
                    conn.execute(text(sql), data or {})
                
                conn.commit()
                logging.debug(f"✅ Synced {operation} to MySQL: {table_name}")
                
        except SQLAlchemyError as e:
            logging.error(f"❌ MySQL sync failed for {table_name}: {e}")
        except Exception as e:
            logging.error(f"❌ Unexpected error during MySQL sync: {e}")
    
    def execute_dual_query(self, sql, params=None):
        """Execute query on both databases"""
        results = {'sqlite': [], 'mysql': []}
        
        # Execute on SQLite
        if self.sqlite_engine:
            try:
                with self.sqlite_engine.connect() as conn:
                    result = conn.execute(text(sql), params or {})
                    if result.returns_rows:
                        results['sqlite'] = result.fetchall()
                    else:
                        results['sqlite'] = result.rowcount
            except Exception as e:
                logging.error(f"SQLite query failed: {e}")
        
        # Execute on MySQL if available
        if self.mysql_engine:
            try:
                with self.mysql_engine.connect() as conn:
                    result = conn.execute(text(sql), params or {})
                    if result.returns_rows:
                        results['mysql'] = result.fetchall()
                    else:
                        results['mysql'] = result.rowcount
                    conn.commit()
            except Exception as e:
                logging.error(f"MySQL query failed: {e}")
        
        return results

# Global instance
dual_db_manager = None

def init_dual_database(app):
    """Initialize dual database support"""
    global dual_db_manager
    dual_db_manager = DualDatabaseManager(app)
    return dual_db_manager

def sync_model_change(model_name, operation, data, where_clause=None):
    """Helper function to sync model changes"""
    if dual_db_manager:
        # Convert SQLAlchemy model name to table name
        table_name = model_name.lower() + 's' if not model_name.endswith('s') else model_name.lower()
        dual_db_manager.sync_to_mysql(table_name, operation, data, where_clause)