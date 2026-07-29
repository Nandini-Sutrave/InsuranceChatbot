import os
import shutil
import uuid
from typing import Optional
from fastapi import UploadFile
from app.core.config import settings

class StorageService:
    def __init__(self, upload_dir: str = settings.UPLOAD_DIR):
        self.upload_dir = upload_dir
        # Ensure target upload directory path exists
        os.makedirs(self.upload_dir, exist_ok=True)

    def save_file(self, file: UploadFile, custom_filename: Optional[str] = None) -> str:
        """
        Saves an uploaded file to the local directory.
        Generates a unique prefix to avoid filename collisions and folder traversal attacks.
        Returns the resolved file path.
        """
        original_name = file.filename or "unnamed_file"
        file_extension = os.path.splitext(original_name)[1]
        
        if custom_filename:
            safe_filename = f"{custom_filename}{file_extension}"
        else:
            safe_filename = f"{uuid.uuid4()}_{original_name}"
            
        # Clean the filename from path injection vectors
        safe_filename = os.path.basename(safe_filename)
        dest_path = os.path.join(self.upload_dir, safe_filename)

        with open(dest_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        return dest_path

    def delete_file(self, file_path: str) -> None:
        """Removes a file from the disk storage if it exists."""
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError as e:
                print(f"Error deleting file from storage: {file_path} - {e}")
