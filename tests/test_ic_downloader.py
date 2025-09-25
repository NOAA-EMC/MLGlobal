import pytest
import os
import tempfile
import shutil
from datetime import datetime
from botocore.exceptions import ClientError

from mlglobal.ic_downloader import ICDownloader


class TestICDownloader:
    """Test cases for the ICDownloader class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.test_dir = tempfile.mkdtemp()
        self.current_cycle = datetime(2023, 1, 1, 12, 0, 0)

    def teardown_method(self):
        """Clean up test fixtures."""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_init_gfs(self):
        """Test ICDownloader initialization for GFS mode."""
        downloader = ICDownloader(
            current_cycle=self.current_cycle,
            num_levels=13,
            member=None,
            download_source="local",
            local_directory=self.test_dir,
            root_directory="/test/root"
        )

        assert downloader.current_cycle == self.current_cycle
        assert downloader.num_levels == 13
        assert downloader.member is None
        assert downloader.download_source == "local"
        assert downloader.local_directory == self.test_dir
        assert downloader.root_directory == "/test/root"
        assert len(downloader.file_list) > 0
        assert os.path.exists(self.test_dir)

    def test_init_gefs(self):
        """Test ICDownloader initialization for GEFS mode."""
        downloader = ICDownloader(
            current_cycle=self.current_cycle,
            num_levels=13,
            member="c00",
            download_source="local",
            local_directory=self.test_dir
        )

        assert downloader.member == "c00"
        assert len(downloader.file_list) > 0

    def test_init_s3(self, mocker):
        """Test ICDownloader initialization for S3 source."""
        mock_s3_client = mocker.MagicMock()

        # Mock the get_s3_client_by_bucket_type method since boto3 is imported inside it
        mock_get_s3_client = mocker.patch.object(
            ICDownloader, 'get_s3_client_by_bucket_type',
            return_value=mock_s3_client
        )

        # Mock the environment variable
        mocker.patch.dict(os.environ, {'AWS_PROFILE': 'test-profile'})

        downloader = ICDownloader(
            current_cycle=self.current_cycle,
            download_source="s3",
            bucket_name="test-bucket"
        )

        assert downloader.s3 == mock_s3_client
        mock_get_s3_client.assert_called_once_with("test-bucket", profile_name="test-profile")

    def test_get_s3_client_by_bucket_type_public(self, mocker):
        """Test S3 client creation for public bucket."""
        mock_client = mocker.MagicMock()
        mock_boto3_client = mocker.patch('boto3.client')
        mock_boto3_client.return_value = mock_client
        mock_client.head_bucket.return_value = None  # Success

        result = ICDownloader.get_s3_client_by_bucket_type("public-bucket")

        assert result == mock_client
        mock_client.head_bucket.assert_called_once_with(Bucket="public-bucket")

    def test_get_s3_client_by_bucket_type_private(self, mocker):
        """Test S3 client creation for private bucket."""
        # Mock public client failing
        mock_public_client = mocker.MagicMock()
        mock_boto3_client = mocker.patch('boto3.client')
        mock_boto3_client.return_value = mock_public_client
        mock_public_client.head_bucket.side_effect = ClientError(
            {"Error": {"Code": "403"}}, "head_bucket"
        )

        # Mock private client
        mock_private_client = mocker.MagicMock()
        mock_session_instance = mocker.MagicMock()
        mock_session = mocker.patch('boto3.Session')
        mock_session.return_value = mock_session_instance
        mock_session_instance.client.return_value = mock_private_client
        mock_session_instance.get_credentials.return_value.get_frozen_credentials.return_value = mocker.MagicMock(
            access_key="test-key", secret_key="test-secret"
        )

        result = ICDownloader.get_s3_client_by_bucket_type("private-bucket", "test-profile")

        assert result == mock_private_client
        mock_session.assert_called_once_with(profile_name="test-profile")

    def test_get_s3_client_by_bucket_type_error(self, mocker):
        """Test S3 client creation with error."""
        mock_client = mocker.MagicMock()
        mock_boto3_client = mocker.patch('boto3.client')
        mock_boto3_client.return_value = mock_client
        mock_client.head_bucket.side_effect = ClientError(
            {"Error": {"Code": "NoSuchBucket"}}, "head_bucket"
        )

        result = ICDownloader.get_s3_client_by_bucket_type("nonexistent-bucket")

        assert result is None

    def test_get_s3_objects(self, mocker):
        """Test S3 objects retrieval with pagination."""
        mock_s3 = mocker.MagicMock()

        # Mock paginated response
        mock_s3.list_objects_v2.side_effect = [
            {
                "Contents": [{"Key": "file1"}, {"Key": "file2"}],
                "IsTruncated": True,
                "NextContinuationToken": "token123"
            },
            {
                "Contents": [{"Key": "file3"}],
                "IsTruncated": False
            }
        ]

        result = ICDownloader.get_s3_objects(mock_s3, "test-bucket", "prefix/")

        assert len(result) == 3
        assert result[0]["Key"] == "file1"
        assert result[1]["Key"] == "file2"
        assert result[2]["Key"] == "file3"

        # Verify pagination calls
        assert mock_s3.list_objects_v2.call_count == 2

    def test_get_s3_objects_no_contents(self, mocker):
        """Test S3 objects retrieval with no contents."""
        mock_s3 = mocker.MagicMock()
        mock_s3.list_objects_v2.return_value = {"IsTruncated": False}

        result = ICDownloader.get_s3_objects(mock_s3, "test-bucket", "prefix/")

        assert len(result) == 0

    def test_get_data_from_s3(self, mocker):
        """Test downloading data from S3."""
        mock_s3 = mocker.MagicMock()
        downloader = ICDownloader(
            current_cycle=self.current_cycle,
            download_source="s3",
            local_directory=self.test_dir,
            bucket_name="test-bucket"
        )
        downloader.s3 = mock_s3

        file_list = ["path/to/file1.grib2", "path/to/file2.grib2"]

        downloader.get_data_from_s3(file_list, self.test_dir)

        # Verify download calls
        assert mock_s3.download_file.call_count == 2
        mock_s3.download_file.assert_any_call(
            "test-bucket", "path/to/file1.grib2",
            os.path.join(self.test_dir, "file1.grib2")
        )
        mock_s3.download_file.assert_any_call(
            "test-bucket", "path/to/file2.grib2",
            os.path.join(self.test_dir, "file2.grib2")
        )

    def test_get_data_from_s3_with_bucket_root(self, mocker):
        """Test downloading data from S3 with bucket root directory."""
        mock_s3 = mocker.MagicMock()
        downloader = ICDownloader(
            current_cycle=self.current_cycle,
            download_source="s3",
            local_directory=self.test_dir,
            bucket_name="test-bucket",
            bucket_root_directory="root/dir"
        )
        downloader.s3 = mock_s3

        file_list = ["file1.grib2"]

        downloader.get_data_from_s3(file_list, self.test_dir)

        mock_s3.download_file.assert_called_once_with(
            "test-bucket", "root/dir/file1.grib2",
            os.path.join(self.test_dir, "file1.grib2")
        )

    def test_get_data_from_s3_file_exists(self, mocker):
        """Test S3 download when local file already exists."""
        mock_s3 = mocker.MagicMock()
        downloader = ICDownloader(
            current_cycle=self.current_cycle,
            download_source="s3",
            local_directory=self.test_dir,
            bucket_name="test-bucket"
        )
        downloader.s3 = mock_s3

        # Create existing file
        existing_file = os.path.join(self.test_dir, "file1.grib2")
        with open(existing_file, 'w') as f:
            f.write("test")

        file_list = ["path/to/file1.grib2"]

        downloader.get_data_from_s3(file_list, self.test_dir)

        # Should not attempt download
        mock_s3.download_file.assert_not_called()

    def test_get_data_from_s3_download_error(self, mocker):
        """Test S3 download with error."""
        mock_s3 = mocker.MagicMock()
        mock_s3.download_file.side_effect = Exception("Download failed")

        downloader = ICDownloader(
            current_cycle=self.current_cycle,
            download_source="s3",
            local_directory=self.test_dir,
            bucket_name="test-bucket"
        )
        downloader.s3 = mock_s3

        file_list = ["path/to/file1.grib2"]

        # Should not raise exception, just log error
        downloader.get_data_from_s3(file_list, self.test_dir)

        mock_s3.download_file.assert_called_once()

    def test_get_data_from_local(self):
        """Test copying data from local directory."""
        # Create source directory and files
        source_dir = tempfile.mkdtemp()
        try:
            source_file1 = os.path.join(source_dir, "file1.grib2")
            source_file2 = os.path.join(source_dir, "file2.grib2")

            with open(source_file1, 'w') as f:
                f.write("test data 1")
            with open(source_file2, 'w') as f:
                f.write("test data 2")

            downloader = ICDownloader(
                current_cycle=self.current_cycle,
                download_source="local",
                local_directory=self.test_dir,
                root_directory=source_dir
            )

            file_list = ["file1.grib2", "file2.grib2"]

            downloader.get_data_from_local(file_list, self.test_dir)

            # Verify files were copied
            assert os.path.exists(os.path.join(self.test_dir, "file1.grib2"))
            assert os.path.exists(os.path.join(self.test_dir, "file2.grib2"))

            # Verify content
            with open(os.path.join(self.test_dir, "file1.grib2"), 'r') as f:
                assert f.read() == "test data 1"

        finally:
            shutil.rmtree(source_dir)

    def test_get_data_from_local_file_exists(self):
        """Test local copy when destination file already exists."""
        source_dir = tempfile.mkdtemp()
        try:
            source_file = os.path.join(source_dir, "file1.grib2")
            with open(source_file, 'w') as f:
                f.write("source data")

            # Create existing destination file
            dest_file = os.path.join(self.test_dir, "file1.grib2")
            with open(dest_file, 'w') as f:
                f.write("existing data")

            downloader = ICDownloader(
                current_cycle=self.current_cycle,
                download_source="local",
                local_directory=self.test_dir,
                root_directory=source_dir
            )

            file_list = ["file1.grib2"]

            downloader.get_data_from_local(file_list, self.test_dir)

            # File should not be overwritten
            with open(dest_file, 'r') as f:
                assert f.read() == "existing data"

        finally:
            shutil.rmtree(source_dir)

    def test_get_data_from_local_copy_error(self):
        """Test local copy with error."""
        downloader = ICDownloader(
            current_cycle=self.current_cycle,
            download_source="local",
            local_directory=self.test_dir,
            root_directory="/nonexistent/path"
        )

        file_list = ["file1.grib2"]

        with pytest.raises(OSError, match="Unable to copy"):
            downloader.get_data_from_local(file_list, self.test_dir)

    def test_get_data_s3(self, mocker):
        """Test get_data method with S3 source."""
        mock_s3 = mocker.MagicMock()
        downloader = ICDownloader(
            current_cycle=self.current_cycle,
            download_source="s3",
            local_directory=self.test_dir,
            bucket_name="test-bucket"
        )
        downloader.s3 = mock_s3

        mock_get_s3 = mocker.patch.object(downloader, 'get_data_from_s3')
        downloader.get_data()
        mock_get_s3.assert_called_once_with(downloader.file_list, self.test_dir)

    def test_get_data_local(self, mocker):
        """Test get_data method with local source."""
        downloader = ICDownloader(
            current_cycle=self.current_cycle,
            download_source="local",
            local_directory=self.test_dir,
            root_directory="/test/root"
        )

        mock_get_local = mocker.patch.object(downloader, 'get_data_from_local')
        downloader.get_data()
        mock_get_local.assert_called_once_with(downloader.file_list, self.test_dir)

    def test_get_data_invalid_source(self):
        """Test get_data method with invalid source."""
        downloader = ICDownloader(
            current_cycle=self.current_cycle,
            download_source="invalid",
            local_directory=self.test_dir
        )

        with pytest.raises(KeyError):
            downloader.get_data()


@pytest.fixture
def sample_datetime():
    """Fixture providing a sample datetime for testing."""
    return datetime(2023, 1, 1, 12, 0, 0)


@pytest.fixture
def temp_directory():
    """Fixture providing a temporary directory for testing."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


class TestIntegration:
    """Integration tests for ICDownloader."""

    def test_full_workflow_local(self, sample_datetime, temp_directory, mocker):
        """Test full workflow with local data source."""
        # Create mock source data
        source_dir = os.path.join(temp_directory, "source")
        os.makedirs(source_dir, exist_ok=True)

        # Create some mock files that match the expected patterns
        test_files = [
            "gfs.20230101/12/atmos/gfs.t12z.pgrb2.0p25.f000",
            "gfs.20230101/12/atmos/gfs.t12z.pgrb2.0p25.f006",
        ]

        for file_path in test_files:
            full_path = os.path.join(source_dir, file_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, 'w') as f:
                f.write(f"mock data for {file_path}")

        dest_dir = os.path.join(temp_directory, "dest")

        downloader = ICDownloader(
            current_cycle=sample_datetime,
            num_levels=13,
            member=None,
            download_source="local",
            local_directory=dest_dir,
            root_directory=source_dir
        )

        # Mock the file lookup to return our test files
        downloader.file_list = test_files

        # This should work without errors
        downloader.get_data()

        # Verify destination directory was created
        assert os.path.exists(dest_dir)