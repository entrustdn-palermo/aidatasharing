"""
Universal File Processor Service for AI Share Platform
Handles processing of various file types with metadata extraction and preview generation
"""

import os
import json
import hashlib
import logging
import tempfile
from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime
from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.models.file_handler import FileUpload, FileType, UploadStatus
from app.models.dataset import Dataset
from app.models.user import User

logger = logging.getLogger(__name__)


class UniversalFileProcessor:
    """Service for processing various file types with enhanced metadata extraction"""
    
    def __init__(self, db: Session):
        """Initialize universal file processor"""
        self.db = db
        self.supported_formats = [
            '.txt', '.csv', '.json', '.xml', '.pdf', '.doc', '.docx',
            '.xls', '.xlsx', '.jpg', '.jpeg', '.png', '.gif', '.bmp',
            '.mp3', '.mp4', '.wav', '.avi', '.mov', '.zip', '.tar', '.gz'
        ]
        
        # File size limits by type (in MB)
        self.size_limits = {
            'image': 50,
            'document': 50,
            'spreadsheet': 100,
            'text': 10,
            'archive': 200,
            'audio': 100,
            'video': 500
        }
        
        logger.info("UniversalFileProcessor initialized")
    
    def is_supported_file(self, file_path: str) -> bool:
        """Check if file format is supported"""
        return Path(file_path).suffix.lower() in self.supported_formats
    
    def determine_file_type(self, filename: str) -> FileType:
        """Determine FileType enum from filename"""
        suffix = Path(filename).suffix.lower()
        
        if suffix in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', '.svg']:
            return FileType.IMAGE
        elif suffix in ['.pdf', '.doc', '.docx', '.txt', '.rtf', '.odt']:
            return FileType.DOCUMENT
        elif suffix in ['.csv', '.xlsx', '.xls', '.ods']:
            return FileType.SPREADSHEET
        elif suffix in ['.zip', '.tar', '.gz', '.rar', '.7z']:
            return FileType.ARCHIVE
        else:
            return FileType.OTHER

    def get_file_type_category(self, filename: str) -> str:
        """Get file type category as string"""
        suffix = Path(filename).suffix.lower()
        
        if suffix in ['.txt', '.csv', '.json', '.xml']:
            return 'text'
        elif suffix in ['.pdf', '.doc', '.docx']:
            return 'document'
        elif suffix in ['.xls', '.xlsx']:
            return 'spreadsheet'
        elif suffix in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']:
            return 'image'
        elif suffix in ['.mp3', '.wav']:
            return 'audio'
        elif suffix in ['.mp4', '.avi', '.mov']:
            return 'video'
        elif suffix in ['.zip', '.tar', '.gz']:
            return 'archive'
        else:
            return 'unknown'
    
    async def process_file(self, file: UploadFile, user: User, dataset: Dataset) -> FileUpload:
        """
        Process uploaded file and create FileUpload record with enhanced metadata
        
        Args:
            file: The uploaded file
            user: User uploading the file
            dataset: Dataset the file belongs to
            
        Returns:
            FileUpload record with comprehensive metadata
        """
        try:
            # Read file content
            file_content = await file.read()
            file_size = len(file_content)
            file_hash = hashlib.sha256(file_content).hexdigest()
            
            # Determine file type and validate
            file_type = self.determine_file_type(file.filename)
            file_category = self.get_file_type_category(file.filename)
            
            # Validate file size
            size_limit_mb = self.size_limits.get(file_category, 100)
            if file_size > size_limit_mb * 1024 * 1024:
                raise Exception(f"File size {file_size} bytes exceeds limit of {size_limit_mb}MB for {file_category} files")
            
            # Create temporary file for processing
            with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as temp_file:
                temp_file.write(file_content)
                temp_file_path = temp_file.name
            
            try:
                # Extract metadata based on file type
                metadata = await self._extract_metadata(temp_file_path, file.filename, file_type, file_content, file_hash)
                
                # Generate storage path
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_filename = f"{timestamp}_{user.id}_{file.filename}"
                upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
                os.makedirs(upload_dir, exist_ok=True)
                file_path = os.path.join(upload_dir, safe_filename)
                
                # Save file to storage
                with open(file_path, "wb") as f:
                    f.write(file_content)
                
                # Create FileUpload record
                file_upload = FileUpload(
                    dataset_id=dataset.id,
                    user_id=user.id,
                    organization_id=user.organization_id,
                    original_filename=file.filename,
                    file_path=file_path,
                    file_size=file_size,
                    file_hash=file_hash,
                    mime_type=metadata.get('mime_type'),
                    file_type=file_type.value,
                    upload_status=UploadStatus.UPLOADED,
                    file_metadata=metadata
                )
                
                # Add type-specific metadata to file_upload
                if file_type == FileType.IMAGE and 'image_info' in metadata:
                    img_info = metadata['image_info']
                    file_upload.image_width = img_info.get('width')
                    file_upload.image_height = img_info.get('height')
                    file_upload.image_format = img_info.get('format')
                    file_upload.color_mode = img_info.get('mode')
                
                self.db.add(file_upload)
                self.db.commit()
                self.db.refresh(file_upload)
                
                logger.info(f"✅ File processed successfully: {file.filename} -> {safe_filename}")
                return file_upload
                
            finally:
                # Cleanup temporary file
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
                    
        except Exception as e:
            logger.error(f"❌ Failed to process file {file.filename}: {str(e)}")
            raise

    async def _extract_metadata(self, file_path: str, filename: str, file_type: FileType, file_content: bytes, file_hash: str) -> Dict[str, Any]:
        """Extract comprehensive metadata from file"""
        import mimetypes
        
        metadata = {
            'filename': filename,
            'size_bytes': len(file_content),
            'mime_type': mimetypes.guess_type(filename)[0],
            'file_hash': file_hash,
            'processed_at': datetime.utcnow().isoformat(),
            'processor': 'UniversalFileProcessor',
            'type': file_type.value
        }
        
        try:
            if file_type == FileType.SPREADSHEET:
                metadata.update(await self._extract_spreadsheet_metadata(file_path, filename))
            elif file_type == FileType.IMAGE:
                metadata.update(await self._extract_image_metadata(file_path))
            elif file_type == FileType.DOCUMENT:
                metadata.update(await self._extract_document_metadata(file_path, filename))
            elif filename.lower().endswith('.json'):
                metadata.update(await self._extract_json_metadata(file_path))
                
        except Exception as e:
            logger.warning(f"Failed to extract specific metadata for {filename}: {e}")
            metadata['extraction_error'] = str(e)
            
        return metadata

    async def _extract_spreadsheet_metadata(self, file_path: str, filename: str) -> Dict[str, Any]:
        """Extract metadata from spreadsheet files"""
        import pandas as pd
        
        try:
            metadata = {'type': 'spreadsheet'}
            
            if filename.lower().endswith('.csv'):
                # CSV file
                df = pd.read_csv(file_path, nrows=1000)  # Read first 1000 rows for analysis
                metadata.update({
                    'format': 'csv',
                    'rows': len(df),
                    'columns': len(df.columns),
                    'headers': df.columns.tolist(),
                    'estimated_data_types': {col: str(df[col].dtype) for col in df.columns},
                    'sample_data': df.head(5).to_dict('records') if len(df) > 0 else [],
                    'has_header': True
                })
                
                # Try to detect delimiter
                with open(file_path, 'r') as f:
                    first_line = f.readline()
                    if ';' in first_line and first_line.count(';') > first_line.count(','):
                        metadata['delimiter'] = ';'
                    else:
                        metadata['delimiter'] = ','
                        
            else:
                # Excel file
                excel_file = pd.ExcelFile(file_path)
                metadata.update({
                    'format': 'excel',
                    'sheet_names': excel_file.sheet_names,
                    'sheet_count': len(excel_file.sheet_names)
                })
                
                # Analyze first sheet
                if excel_file.sheet_names:
                    df = pd.read_excel(file_path, sheet_name=excel_file.sheet_names[0], nrows=1000)
                    metadata.update({
                        'rows': len(df),
                        'columns': len(df.columns),
                        'headers': df.columns.tolist(),
                        'estimated_data_types': {col: str(df[col].dtype) for col in df.columns},
                        'sample_data': df.head(5).to_dict('records') if len(df) > 0 else [],
                        'primary_sheet': excel_file.sheet_names[0]
                    })
                    
        except Exception as e:
            logger.warning(f"Failed to extract spreadsheet metadata: {e}")
            metadata = {'type': 'spreadsheet', 'extraction_error': str(e)}
            
        return metadata

    async def _extract_image_metadata(self, file_path: str) -> Dict[str, Any]:
        """Extract metadata from image files"""
        try:
            from PIL import Image
            
            with Image.open(file_path) as img:
                metadata = {
                    'type': 'image',
                    'image_info': {
                        'width': img.width,
                        'height': img.height,
                        'format': img.format,
                        'mode': img.mode,
                        'has_transparency': img.mode in ('RGBA', 'LA') or 'transparency' in img.info
                    }
                }
                
                # Extract EXIF data if available
                if hasattr(img, '_getexif') and img._getexif():
                    try:
                        exif_data = img._getexif()
                        if exif_data:
                            metadata['exif'] = {str(k): str(v) for k, v in exif_data.items() if isinstance(v, (str, int, float))}
                    except Exception:
                        pass  # EXIF extraction can fail, continue without it
                        
                return metadata
                
        except Exception as e:
            logger.warning(f"Failed to extract image metadata: {e}")
            return {'type': 'image', 'extraction_error': str(e)}

    async def _extract_document_metadata(self, file_path: str, filename: str) -> Dict[str, Any]:
        """Extract metadata from document files"""
        metadata = {'type': 'document'}
        
        try:
            if filename.lower().endswith('.pdf'):
                try:
                    import fitz  # PyMuPDF
                    doc = fitz.open(file_path)
                    
                    metadata.update({
                        'format': 'pdf',
                        'pages': len(doc),
                        'title': doc.metadata.get('title', ''),
                        'author': doc.metadata.get('author', ''),
                        'subject': doc.metadata.get('subject', ''),
                        'creator': doc.metadata.get('creator', ''),
                        'producer': doc.metadata.get('producer', ''),
                        'creation_date': doc.metadata.get('creationDate', ''),
                        'modification_date': doc.metadata.get('modDate', '')
                    })
                    
                    # Extract some text from first few pages
                    preview_text = ""
                    for page_num in range(min(3, len(doc))):
                        page = doc.load_page(page_num)
                        text = page.get_text()
                        preview_text += text[:500] + "\n"
                        
                    metadata['preview'] = preview_text[:1000]
                    doc.close()
                    
                except ImportError:
                    metadata['note'] = 'PyMuPDF not available for PDF processing'
                    
            elif filename.lower().endswith('.txt'):
                # Plain text file
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    lines = content.split('\n')
                    
                metadata.update({
                    'format': 'text',
                    'lines': len(lines),
                    'characters': len(content),
                    'words': len(content.split()),
                    'preview': content[:1000],
                    'encoding': 'utf-8'
                })
                
        except Exception as e:
            logger.warning(f"Failed to extract document metadata: {e}")
            metadata['extraction_error'] = str(e)
            
        return metadata

    async def _extract_json_metadata(self, file_path: str) -> Dict[str, Any]:
        """Extract metadata from JSON files"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            metadata = {
                'type': 'json',
                'format': 'json',
                'structure_type': type(data).__name__,
                'valid_json': True
            }
            
            if isinstance(data, dict):
                metadata['top_level_keys'] = list(data.keys())
                metadata['key_count'] = len(data.keys())
            elif isinstance(data, list):
                metadata['items_count'] = len(data)
                if data and isinstance(data[0], dict):
                    metadata['common_fields'] = list(data[0].keys())
                    metadata['structure_analysis'] = 'array_of_objects'
                else:
                    metadata['structure_analysis'] = 'array_of_primitives'
            
            # Add preview of data structure
            metadata['preview'] = str(data)[:500] if len(str(data)) > 500 else data
            
            return metadata
            
        except json.JSONDecodeError as e:
            return {
                'type': 'json',
                'valid_json': False,
                'error': f'Invalid JSON: {str(e)}',
                'format': 'json'
            }
        except Exception as e:
            return {
                'type': 'json',
                'extraction_error': str(e),
                'format': 'json'
            }
    
    def get_supported_formats(self) -> List[str]:
        """Get list of supported file formats"""
        return self.supported_formats.copy()
    
    def generate_preview(self, file_upload: FileUpload, preview_type: str = "metadata") -> Dict[str, Any]:
        """Generate preview for uploaded file"""
        try:
            if preview_type == "metadata":
                return {
                    "success": True,
                    "file_upload_id": file_upload.id,
                    "filename": file_upload.original_filename,
                    "file_type": file_upload.file_type,
                    "file_size": file_upload.file_size,
                    "metadata": file_upload.file_metadata or {},
                    "preview_type": "metadata",
                    "generated_at": datetime.utcnow().isoformat()
                }
            elif preview_type == "content":
                # Generate content preview if file exists
                if file_upload.file_path and os.path.exists(file_upload.file_path):
                    content_preview = self._generate_content_preview(file_upload.file_path, file_upload.file_type)
                    return {
                        "success": True,
                        "file_upload_id": file_upload.id,
                        "filename": file_upload.original_filename,
                        "file_type": file_upload.file_type,
                        "content_preview": content_preview,
                        "preview_type": "content",
                        "generated_at": datetime.utcnow().isoformat()
                    }
                else:
                    return {
                        "success": False,
                        "error": "File not found for content preview",
                        "file_upload_id": file_upload.id
                    }
            else:
                return {
                    "success": False,
                    "error": f"Unsupported preview type: {preview_type}",
                    "file_upload_id": file_upload.id
                }
                
        except Exception as e:
            logger.error(f"Failed to generate preview for file {file_upload.id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "file_upload_id": file_upload.id
            }
    
    def _generate_content_preview(self, file_path: str, file_type: str) -> Dict[str, Any]:
        """Generate content preview for file"""
        try:
            if file_type == FileType.SPREADSHEET.value:
                return self._preview_spreadsheet_content(file_path)
            elif file_type == FileType.IMAGE.value:
                return self._preview_image_content(file_path)
            elif file_type == FileType.DOCUMENT.value:
                return self._preview_document_content(file_path)
            else:
                return {"type": "unsupported", "message": f"Content preview not supported for {file_type}"}
                
        except Exception as e:
            return {"type": "error", "message": str(e)}
    
    def _preview_spreadsheet_content(self, file_path: str) -> Dict[str, Any]:
        """Preview content of spreadsheet files"""
        import pandas as pd
        
        try:
            if file_path.lower().endswith('.csv'):
                df = pd.read_csv(file_path, nrows=20)
            else:
                df = pd.read_excel(file_path, nrows=20)
                
            return {
                "type": "tabular",
                "headers": df.columns.tolist(),
                "rows": df.to_dict('records'),
                "total_rows_shown": len(df),
                "column_count": len(df.columns)
            }
        except Exception as e:
            return {"type": "error", "message": f"Failed to preview spreadsheet: {e}"}
    
    def _preview_image_content(self, file_path: str) -> Dict[str, Any]:
        """Preview content of image files"""
        try:
            from PIL import Image
            
            with Image.open(file_path) as img:
                return {
                    "type": "image",
                    "width": img.width,
                    "height": img.height,
                    "format": img.format,
                    "mode": img.mode,
                    "file_path": file_path
                }
        except Exception as e:
            return {"type": "error", "message": f"Failed to preview image: {e}"}
    
    def _preview_document_content(self, file_path: str) -> Dict[str, Any]:
        """Preview content of document files"""
        try:
            if file_path.lower().endswith('.pdf'):
                try:
                    import fitz
                    doc = fitz.open(file_path)
                    
                    pages_preview = []
                    for page_num in range(min(3, len(doc))):
                        page = doc.load_page(page_num)
                        text = page.get_text()
                        pages_preview.append({
                            "page_number": page_num + 1,
                            "text_content": text[:500],
                            "has_text": bool(text.strip())
                        })
                    
                    doc.close()
                    
                    return {
                        "type": "pdf",
                        "total_pages": len(doc),
                        "pages_preview": pages_preview
                    }
                except ImportError:
                    return {"type": "error", "message": "PyMuPDF not available for PDF preview"}
                    
            elif file_path.lower().endswith('.txt'):
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read(2000)  # Read first 2000 chars
                    
                return {
                    "type": "text",
                    "content": content,
                    "truncated": len(content) >= 2000
                }
            else:
                return {"type": "unsupported", "message": "Document preview not supported for this format"}
                
        except Exception as e:
            return {"type": "error", "message": f"Failed to preview document: {e}"}
    
    def validate_file(self, file_path: str) -> Dict[str, Any]:
        """
        Validate file for processing
        
        Args:
            file_path: Path to the file
            
        Returns:
            Validation result dictionary
        """
        try:
            if not os.path.exists(file_path):
                return {
                    'valid': False,
                    'error': 'File does not exist'
                }
            
            if not self.is_supported_file(file_path):
                return {
                    'valid': False,
                    'error': f'Unsupported file format: {Path(file_path).suffix}'
                }
            
            file_size = os.path.getsize(file_path)
            file_category = self.get_file_type_category(file_path)
            max_size = self.size_limits.get(file_category, 100) * 1024 * 1024
            
            if file_size > max_size:
                return {
                    'valid': False,
                    'error': f'File too large: {file_size} bytes (max: {max_size//1024//1024}MB for {file_category})'
                }
            
            return {
                'valid': True,
                'file_size': file_size,
                'file_type': self.get_file_type_category(file_path),
                'file_category': file_category
            }
            
        except Exception as e:
            logger.error(f"Error validating file {file_path}: {e}")
            return {
                'valid': False,
                'error': str(e)
            }