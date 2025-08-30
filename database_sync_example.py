"""
Example usage of dual database synchronization
This shows how to sync changes to both SQLite and MySQL databases
"""

from db_dual_support import sync_model_change
from flask import current_app
import logging

# Example: Sync a new GRPO document to both databases
def create_grpo_with_sync(grpo_data):
    """Create GRPO document and sync to both databases"""
    try:
        # Create in SQLite (primary database)
        from models import GRPODocument
        from app import db
        
        grpo = GRPODocument(**grpo_data)
        db.session.add(grpo)
        db.session.commit()
        
        # Sync to MySQL
        sync_model_change('grpo_document', 'INSERT', grpo_data)
        
        logging.info(f"✅ GRPO {grpo.po_number} created and synced to both databases")
        return grpo
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"❌ Failed to create GRPO: {e}")
        raise

# Example: Update user and sync to MySQL
def update_user_with_sync(user_id, update_data):
    """Update user and sync changes to MySQL"""
    try:
        from models import User
        from app import db
        
        user = User.query.get(user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")
        
        # Update fields
        for key, value in update_data.items():
            setattr(user, key, value)
        
        db.session.commit()
        
        # Sync to MySQL
        sync_model_change('user', 'UPDATE', update_data, f"id = {user_id}")
        
        logging.info(f"✅ User {user.username} updated and synced to both databases")
        return user
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"❌ Failed to update user: {e}")
        raise