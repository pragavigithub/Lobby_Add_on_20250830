from app import db
from datetime import datetime

class Branch(db.Model):
    """Branch/Location model for multi-branch support"""
    __tablename__ = 'branches'
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.String(10), primary_key=True)  # Branch code like 'BR001'
    name = db.Column(db.String(100), nullable=True)  # For backward compatibility
    description = db.Column(db.String(255), nullable=True)
    branch_code = db.Column(db.String(10), unique=True, nullable=False)  # 01, 02, etc.
    branch_name = db.Column(db.String(100), nullable=False)  # Main Branch, etc.
    address = db.Column(db.String(255), nullable=True)
    city = db.Column(db.String(50), nullable=True)
    state = db.Column(db.String(50), nullable=True)
    postal_code = db.Column(db.String(20), nullable=True)
    country = db.Column(db.String(50), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    manager_name = db.Column(db.String(100), nullable=True)
    warehouse_codes = db.Column(db.Text, nullable=True)  # JSON array of warehouse codes
    active = db.Column(db.Boolean, default=True)
    is_default = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<Branch {self.branch_code}: {self.branch_name}>'

    def get_warehouses(self):
        """Get list of warehouse codes for this branch"""
        if self.warehouse_codes:
            import json
            try:
                return json.loads(self.warehouse_codes)
            except:
                return self.warehouse_codes.split(',') if ',' in self.warehouse_codes else [self.warehouse_codes]
        return []

class UserSession(db.Model):
    """Track user login sessions"""
    __tablename__ = 'user_sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    session_token = db.Column(db.String(256), nullable=False)
    branch_id = db.Column(db.String(10), nullable=True)
    login_time = db.Column(db.DateTime, default=datetime.utcnow)
    logout_time = db.Column(db.DateTime, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.Text, nullable=True)
    active = db.Column(db.Boolean, default=True)

class PasswordResetToken(db.Model):
    """Password reset tokens for users"""
    __tablename__ = 'password_reset_tokens'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    token = db.Column(db.String(256), nullable=False, unique=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # Admin who created token
    created_at = db.Column(db.DateTime, default=datetime.utcnow)