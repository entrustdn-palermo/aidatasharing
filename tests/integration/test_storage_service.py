#!/usr/bin/env python3
"""
Test Storage Service Multi-Backend Support
Verifies that the storage service can handle different backends properly
"""

import sys
import os
import asyncio
import tempfile
import shutil
from pathlib import Path

# Add the backend directory to the Python path
backend_dir = os.path.join(os.path.dirname(__file__), '..', 'backend')
sys.path.insert(0, backend_dir)

# Set up test environment
os.environ['STORAGE_TYPE'] = 'local'
os.environ['STORAGE_DIR'] = tempfile.mkdtemp()

from app.services.storage import StorageService, LocalStorageBackend, S3StorageBackend
from app.services.download_token import download_token_service

class TestStorageService:
    """Test storage service functionality"""
    
    def __init__(self):
        self.test_dir = tempfile.mkdtemp()
        self.storage_service = None
        
    async def setup(self):
        """Set up test environment"""
        print("Setting up test environment...")
        
        # Initialize storage service
        self.storage_service = StorageService()
        
        print(f"✓ Storage service initialized with backend: {type(self.storage_service.backend).__name__}")
        
    async def test_local_storage_backend(self):
        """Test local storage backend functionality"""
        print("\n--- Testing Local Storage Backend ---")
        
        try:
            # Test file content
            test_content = b"This is test file content for storage testing"
            test_filename = "test_file.txt"
            dataset_id = 1
            organization_id = 1
            
            # Store file
            print("Storing test file...")
            result = await self.storage_service.store_dataset_file(
                file_content=test_content,
                original_filename=test_filename,
                dataset_id=dataset_id,
                organization_id=organization_id
            )
            
            print(f"✓ File stored successfully: {result['filename']}")
            print(f"  Backend: {result.get('backend', 'unknown')}")
            print(f"  File size: {result['file_size']} bytes")
            print(f"  Relative path: {result['relative_path']}")
            
            # Retrieve file
            print("Retrieving test file...")
            retrieved_content = await self.storage_service.retrieve_dataset_file(result['relative_path'])
            
            if retrieved_content == test_content:
                print("✓ File retrieved successfully and content matches")
            else:
                print("✗ File content mismatch after retrieval")
                return False
            
            # Test file streaming
            print("Testing file streaming...")
            try:
                stream_response = await self.storage_service.get_file_stream(result['relative_path'])
                print(f"✓ File streaming response created: {type(stream_response).__name__}")
                print(f"  Content type: {stream_response.media_type}")
                print(f"  Headers: {dict(stream_response.headers)}")
            except Exception as e:
                print(f"✗ File streaming failed: {e}")
                return False
            
            # Test backend info
            backend_info = self.storage_service.get_backend_info()
            print(f"✓ Backend info: {backend_info}")
            
            # Delete file
            print("Deleting test file...")
            deleted = await self.storage_service.delete_dataset_file(result['relative_path'])
            
            if deleted:
                print("✓ File deleted successfully")
            else:
                print("✗ File deletion failed")
                return False
            
            # Verify file is gone
            retrieved_after_delete = await self.storage_service.retrieve_dataset_file(result['relative_path'])
            if retrieved_after_delete is None:
                print("✓ File confirmed deleted (retrieve returns None)")
            else:
                print("✗ File still exists after deletion")
                return False
            
            return True
            
        except Exception as e:
            print(f"✗ Local storage test failed: {e}")
            return False
    
    async def test_s3_backend_configuration(self):
        """Test S3 backend configuration without actual S3 connection"""
        print("\n--- Testing S3 Backend Configuration ---")
        
        try:
            # Test S3 backend availability
            try:
                import boto3
                print("✓ boto3 library is available")
                s3_available = True
            except ImportError:
                print("⚠ boto3 library not available - S3 functionality will be limited")
                s3_available = False
            
            # Test S3 configuration parsing
            original_storage_type = os.environ.get('STORAGE_TYPE', 'local')
            
            # Test AWS S3 configuration
            os.environ.update({
                'STORAGE_TYPE': 's3',
                'S3_BUCKET_NAME': 'test-bucket',
                'AWS_ACCESS_KEY_ID': 'test-access-key',
                'AWS_SECRET_ACCESS_KEY': 'test-secret-key',
                'AWS_DEFAULT_REGION': 'us-east-1'
            })
            
            if s3_available:
                try:
                    # This should fail gracefully due to invalid credentials
                    test_s3_service = StorageService()
                    backend_info = test_s3_service.get_backend_info()
                    print(f"✓ S3 configuration parsed: {backend_info}")
                except Exception as e:
                    print(f"✓ S3 backend failed as expected with invalid credentials: {type(e).__name__}")
            
            # Test S3-compatible configuration
            os.environ.update({
                'STORAGE_TYPE': 's3_compatible',
                'S3_COMPATIBLE_BUCKET_NAME': 'test-minio-bucket',
                'S3_COMPATIBLE_ACCESS_KEY': 'test-minio-key',
                'S3_COMPATIBLE_SECRET_KEY': 'test-minio-secret',
                'S3_COMPATIBLE_ENDPOINT': 'http://localhost:9000',
                'S3_COMPATIBLE_REGION': 'us-east-1'
            })
            
            if s3_available:
                try:
                    # This should fail gracefully due to invalid endpoint
                    test_s3_compat_service = StorageService()
                    backend_info = test_s3_compat_service.get_backend_info()
                    print(f"✓ S3-compatible configuration parsed: {backend_info}")
                except Exception as e:
                    print(f"✓ S3-compatible backend failed as expected with invalid endpoint: {type(e).__name__}")
            
            # Restore original configuration
            os.environ['STORAGE_TYPE'] = original_storage_type
            
            return True
            
        except Exception as e:
            print(f"✗ S3 configuration test failed: {e}")
            return False
    
    async def test_download_tokens(self):
        """Test download token generation and validation"""
        print("\n--- Testing Download Token System ---")
        
        try:
            # Test token generation
            dataset_id = 123
            user_id = 456
            
            token = download_token_service.generate(dataset_id, user_id)
            print(f"✓ Download token generated: {token[:20]}...")
            
            # Test token validation
            is_valid = download_token_service.validate(token)
            if is_valid:
                print("✓ Token validation passed")
            else:
                print("✗ Token validation failed")
                return False

            # Test invalid token validation
            invalid_tokens = [
                "",
                "invalid",
                "short_token",
                "invalid_format_with_no_underscore",
                "valid_length_but_wrong_format_12345678901234567890123456789012"
            ]

            for invalid_token in invalid_tokens:
                is_valid = download_token_service.validate(invalid_token)
                if not is_valid:
                    print(f"✓ Invalid token correctly rejected: {invalid_token[:20]}...")
                else:
                    print(f"✗ Invalid token incorrectly accepted: {invalid_token}")
                    return False
            
            return True
            
        except Exception as e:
            print(f"✗ Download token test failed: {e}")
            return False
    
    async def test_storage_service_info(self):
        """Test storage service information methods"""
        print("\n--- Testing Storage Service Information ---")
        
        try:
            # Test backend info
            backend_info = self.storage_service.get_backend_info()
            print(f"✓ Backend info retrieved: {backend_info}")
            
            # Verify required fields
            required_fields = ['backend_type', 'storage_type']
            for field in required_fields:
                if field not in backend_info:
                    print(f"✗ Missing required field in backend info: {field}")
                    return False
                print(f"  {field}: {backend_info[field]}")
            
            # Test presigned URL support detection
            supports_urls = backend_info.get('supports_presigned_urls', False)
            print(f"✓ Presigned URL support: {supports_urls}")
            
            # Test URL generation (should return None for local storage)
            test_url = self.storage_service.get_file_url("test/path.txt")
            if isinstance(self.storage_service.backend, LocalStorageBackend):
                if test_url is None:
                    print("✓ Local storage correctly returns None for presigned URLs")
                else:
                    print("✗ Local storage should not support presigned URLs")
                    return False
            
            return True
            
        except Exception as e:
            print(f"✗ Storage service info test failed: {e}")
            return False
    
    async def cleanup(self):
        """Clean up test environment"""
        print("\nCleaning up test environment...")
        
        try:
            # Clean up test directory
            if os.path.exists(self.test_dir):
                shutil.rmtree(self.test_dir)
                print("✓ Test directory cleaned up")
            
            # Clean up storage directory
            storage_dir = os.environ.get('STORAGE_DIR')
            if storage_dir and os.path.exists(storage_dir):
                shutil.rmtree(storage_dir)
                print("✓ Storage directory cleaned up")
                
        except Exception as e:
            print(f"⚠ Cleanup warning: {e}")
    
    async def run_all_tests(self):
        """Run all storage service tests"""
        print("=== Storage Service Multi-Backend Test Suite ===\n")
        
        await self.setup()
        
        tests = [
            ("Local Storage Backend", self.test_local_storage_backend),
            ("S3 Backend Configuration", self.test_s3_backend_configuration),
            ("Download Token System", self.test_download_tokens),
            ("Storage Service Information", self.test_storage_service_info)
        ]
        
        results = []
        
        for test_name, test_func in tests:
            try:
                result = await test_func()
                results.append((test_name, result))
                if result:
                    print(f"✓ {test_name}: PASSED")
                else:
                    print(f"✗ {test_name}: FAILED")
            except Exception as e:
                print(f"✗ {test_name}: ERROR - {e}")
                results.append((test_name, False))
        
        await self.cleanup()
        
        # Summary
        print(f"\n=== Test Results Summary ===")
        passed = sum(1 for _, result in results if result)
        total = len(results)
        
        for test_name, result in results:
            status = "PASSED" if result else "FAILED"
            print(f"{status}: {test_name}")
        
        print(f"\nOverall: {passed}/{total} tests passed")
        
        if passed == total:
            print("🎉 All storage service tests passed!")
            return True
        else:
            print("❌ Some storage service tests failed")
            return False

async def main():
    """Main test runner"""
    test_suite = TestStorageService()
    success = await test_suite.run_all_tests()
    return 0 if success else 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)