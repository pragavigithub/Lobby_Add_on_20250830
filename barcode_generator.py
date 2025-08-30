"""
QR Code and Barcode Generation Module
Equivalent to C# ZXing.QRCode functionality
"""

import qrcode
import io
import base64
from PIL import Image, ImageDraw, ImageFont
import logging
import os
from datetime import datetime

class BarcodeGenerator:
    def __init__(self):
        self.default_qr_size = 300
        self.default_margin = 1
        
    def generate_qr_code(self, data, size=None, margin=None, format='PNG'):
        """
        Generate QR code similar to C# ZXing.QRCode
        
        Args:
            data (str): Data to encode in QR code
            size (int): Size of QR code (default: 300x300)
            margin (int): Margin around QR code (default: 1)
            format (str): Output format ('PNG', 'JPEG', 'SVG')
            
        Returns:
            dict: {'success': bool, 'data': base64_string, 'filename': str}
        """
        try:
            if size is None:
                size = self.default_qr_size
            if margin is None:
                margin = self.default_margin
                
            # Create QR code instance
            qr = qrcode.QRCode(
                version=1,  # Controls size (1 = 21x21, up to 40)
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=margin,
            )
            
            # Add data
            qr.add_data(data)
            qr.make(fit=True)
            
            # Create image
            img = qr.make_image(fill_color="black", back_color="white")
            
            # Resize to requested size
            img = img.resize((size, size), Image.Resampling.LANCZOS)
            
            # Convert to base64 for web display
            buffer = io.BytesIO()
            img.save(buffer, format=format)
            img_base64 = base64.b64encode(buffer.getvalue()).decode()
            
            # Generate filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"qr_{timestamp}.{format.lower()}"
            
            logging.info(f"✅ QR code generated successfully: {len(data)} characters")
            
            return {
                'success': True,
                'data': img_base64,
                'filename': filename,
                'mime_type': f'image/{format.lower()}',
                'size': size
            }
            
        except Exception as e:
            logging.error(f"❌ Error generating QR code: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def generate_label_qr(self, label_data):
        """
        Generate QR code for warehouse labels
        
        Args:
            label_data (dict): Label information containing:
                - doc_entry: Document entry number
                - item_code: Item code
                - batch_number: Batch number
                - bin_location: Bin location
                - quantity: Quantity
                - warehouse: Warehouse code
                
        Returns:
            dict: QR code generation result
        """
        try:
            # Create QR text similar to your C# implementation
            qr_text = self._build_label_qr_text(label_data)
            
            # Generate QR code
            result = self.generate_qr_code(qr_text, size=300)
            
            if result['success']:
                result['label_data'] = label_data
                result['qr_text'] = qr_text
                
            return result
            
        except Exception as e:
            logging.error(f"❌ Error generating label QR code: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _build_label_qr_text(self, label_data):
        """Build QR text content for labels"""
        # Build QR text similar to your C# implementation
        # Customize this format based on your requirements
        qr_parts = []
        
        if label_data.get('doc_entry'):
            qr_parts.append(f"DOC:{label_data['doc_entry']}")
            
        if label_data.get('item_code'):
            qr_parts.append(f"ITEM:{label_data['item_code']}")
            
        if label_data.get('batch_number'):
            qr_parts.append(f"BATCH:{label_data['batch_number']}")
            
        if label_data.get('bin_location'):
            qr_parts.append(f"BIN:{label_data['bin_location']}")
            
        if label_data.get('quantity'):
            qr_parts.append(f"QTY:{label_data['quantity']}")
            
        if label_data.get('warehouse'):
            qr_parts.append(f"WH:{label_data['warehouse']}")
            
        # Add timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        qr_parts.append(f"TIME:{timestamp}")
        
        return "|".join(qr_parts)
    
    def parse_scanned_qr(self, qr_text):
        """
        Parse scanned QR code text back into label data
        
        Args:
            qr_text (str): Scanned QR code text
            
        Returns:
            dict: Parsed label data
        """
        try:
            parsed_data = {}
            
            if "|" in qr_text:
                # Parse structured QR code
                parts = qr_text.split("|")
                for part in parts:
                    if ":" in part:
                        key, value = part.split(":", 1)
                        if key == "DOC":
                            parsed_data['doc_entry'] = value
                        elif key == "ITEM":
                            parsed_data['item_code'] = value
                        elif key == "BATCH":
                            parsed_data['batch_number'] = value
                        elif key == "BIN":
                            parsed_data['bin_location'] = value
                        elif key == "QTY":
                            parsed_data['quantity'] = value
                        elif key == "WH":
                            parsed_data['warehouse'] = value
                        elif key == "TIME":
                            parsed_data['timestamp'] = value
            else:
                # Simple QR code - could be item code, bin code, etc.
                parsed_data['raw_data'] = qr_text
                
            parsed_data['success'] = True
            return parsed_data
            
        except Exception as e:
            logging.error(f"❌ Error parsing QR code: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'raw_data': qr_text
            }
    
    def save_qr_to_file(self, qr_data, filepath):
        """
        Save QR code to file system
        
        Args:
            qr_data (str): Base64 encoded QR code data
            filepath (str): Full path where to save the file
            
        Returns:
            dict: Save operation result
        """
        try:
            # Decode base64 data
            img_data = base64.b64decode(qr_data)
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            
            # Save file
            with open(filepath, 'wb') as f:
                f.write(img_data)
                
            logging.info(f"✅ QR code saved to: {filepath}")
            return {
                'success': True,
                'filepath': filepath
            }
            
        except Exception as e:
            logging.error(f"❌ Error saving QR code: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }