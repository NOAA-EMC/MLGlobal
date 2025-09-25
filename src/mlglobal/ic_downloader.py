import os
import shutil
from datetime import timedelta
from logging import getLogger

logger = getLogger(__name__)


class FileLookup:
    def __init__(self, current_cycle, num_levels=13, member=None):

        self.current_cycle = current_cycle
        self.num_levels = num_levels
        self.member = member  # GEFS member values are c00, p01, p02, ..., p30

        # Look back 6 hours for precip and 2 time-level data
        self.current_cycle_m6h = self.current_cycle - timedelta(hours=6)

        if self.member is not None:
            self.get_file_info = self._gefs_file_info
        else:
            self.get_file_info = self._gfs_file_info

    def _gfs_file_info(self):

        # Template for GFS files
        template = f"gfs.{{cycle:%Y%m%d}}/{{cycle:%H}}/atmos/gfs.t{{cycle:%H}}z.{{fspec}}.f{{fhour:03d}}"  # noqa: F541

        # From current cycle
        pgrb2_0p25_f000 = template.format(
            cycle=self.current_cycle, fspec="pgrb2.0p25", fhour=0
        )
        if self.num_levels == 37:  # Need additional pgrb2b file for 37 level data
            pgrb2b_0p25_f000 = template.format(
                cycle=self.current_cycle, fspec="pgrb2b.0p25", fhour=0
            )

        # From current cycle - 6 hours
        pgrb2_0p25_f000_m6 = template.format(
            cycle=self.current_cycle_m6h, fspec="pgrb2.0p25", fhour=0
        )
        pgrb2_0p25_f006_m6 = template.format(
            cycle=self.current_cycle_m6h, fspec="pgrb2.0p25", fhour=6
        )

        # Create a flat list of files valid at current and current-6h cycles
        file_dict = {}
        file_dict[self.current_cycle] = [pgrb2_0p25_f000, pgrb2_0p25_f006_m6]
        if self.num_levels == 37:
            file_dict[self.current_cycle].append(pgrb2b_0p25_f000)
        file_dict[self.current_cycle_m6h] = [pgrb2_0p25_f000_m6]

        return file_dict

    def _gefs_file_info(self):

        # Template for GEFS files
        template = f"gefs.{{cycle:%Y%m%d}}/{{cycle:%H}}/atmos/{{fspec_dir}}/ge{{member}}.t{{cycle:%H}}z.{{fspec}}.f{{fhour:03d}}"  # noqa: F541

        # From current cycle
        pgrb2_0p25_f000 = template.format(
            cycle=self.current_cycle,
            fspec_dir="pgrb2p25",
            fspec="pgrb2.0p25",
            fhour=0,
            member=self.member,
        )
        pgrb2s_0p25_f000 = template.format(
            cycle=self.current_cycle,
            fspec_dir="pgrb2sp25",
            fspec="pgrb2s.0p25",
            fhour=0,
            member=self.member,
        )

        # From current cycle - 6 hours
        pgrb2_0p25_f000_m6 = template.format(
            cycle=self.current_cycle_m6h,
            fspec_dir="pgrb2p25",
            fspec="pgrb2.0p25",
            fhour=0,
            member=self.member,
        )
        pgrb2s_0p25_f000_m6 = template.format(
            cycle=self.current_cycle_m6h,
            fspec_dir="pgrb2sp25",
            fspec="pgrb2s.0p25",
            fhour=0,
            member=self.member,
        )

        file_dict = {}
        file_dict[self.current_cycle] = [pgrb2_0p25_f000, pgrb2s_0p25_f000]
        file_dict[self.current_cycle_m6h] = [pgrb2_0p25_f000_m6, pgrb2s_0p25_f000_m6]

        return file_dict


class ICDownloader:

    def __init__(
        self,
        current_cycle,
        num_levels=13,
        member=None,
        download_source="local",
        local_directory="./data",
        bucket_name=None,
        bucket_root_directory=None,
        root_directory=None,
    ):
        self.current_cycle = current_cycle
        self.num_levels = num_levels
        self.member = member
        self.download_source = download_source
        self.local_directory = local_directory
        self.bucket_name = bucket_name
        self.bucket_root_directory = bucket_root_directory
        self.root_directory = root_directory

        # Generate the lookup dictionary
        lookup = FileLookup(
            self.current_cycle, member=self.member, num_levels=self.num_levels
        )
        self.file_dict = lookup.get_file_info()

        # Flatten the file_dict to a simple list of files
        file_list = []
        for files in self.file_dict.values():
            file_list.extend(files)
        self.file_list = file_list

        if self.download_source in ["s3"]:
            aws_profile = os.environ.get("AWS_PROFILE", "default")
            self.s3 = self.get_s3_client_by_bucket_type(
                self.bucket_name, profile_name=aws_profile
            )

        os.makedirs(self.local_directory, exist_ok=True)

    @staticmethod
    def get_s3_client_by_bucket_type(bucket_name, profile_name="default"):
        """
        Initializes and returns a boto3 S3 client for a given bucket.

        The function first attempts to get a public client. If that fails, it
        assumes the bucket is private and creates a client using the specified
        AWS profile.

        Args:
            bucket_name (str): The name of the S3 bucket.
            profile_name (str): The AWS profile to use for private buckets.
                                Defaults to 'default'.

        Returns:
            boto3.client: A configured S3 client.
        """

        try:
            import boto3
            from botocore import UNSIGNED
            from botocore.config import Config
            from botocore.exceptions import ClientError
        except ImportError as ee:
            raise ImportError(
                "boto3 and botocore are required for S3 operations."
            ) from ee

        # 1. Try to get a client configured for a public (unsigned) bucket
        s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))
        try:
            # Check if the bucket can be accessed publicly without authentication
            s3.head_bucket(Bucket=bucket_name)
            logger.info(
                f"Bucket '{bucket_name}' is public. Returning an unsigned client."
            )
            return s3
        except ClientError as ee:
            error_code = ee.response["Error"]["Code"]
            # 2. If it's a 403 Forbidden, the bucket is likely private.
            if error_code in ("403", "404"):
                logger.warning(
                    f"Bucket '{bucket_name}' is not public. Returning client with profile '{profile_name}'."
                )

                # Create a session with the specified profile
                session = boto3.Session(profile_name=profile_name)
                current_credentials = session.get_credentials().get_frozen_credentials()
                s3 = session.client(
                    "s3",
                    aws_access_key_id=current_credentials.access_key,
                    aws_secret_access_key=current_credentials.secret_key,
                )
                return s3
            else:
                # Handle other errors, such as a non-existent bucket
                logger.error(f"Error accessing bucket '{bucket_name}': {ee}")
                return None

    @staticmethod
    def get_s3_objects(s3, bucket_name: str, prefix: str) -> list:
        """Retrieve a list of objects from an S3 bucket with a specific prefix.
        This method handles pagination to ensure all objects are retrieved.
        By default, S3 returns up to 1000 objects per request.

        Parameters
        ----------
        s3 : boto3.client
            The S3 client to use for the operation.
        bucket_name : str
            The name of the S3 bucket.
        prefix : str
            The prefix to filter the objects.

        Returns
        -------
        list
            A list of S3 objects that match the prefix.
        """

        objects = []
        continuation_token = None

        while True:
            list_kwargs = {
                "Bucket": bucket_name,
                "Prefix": prefix,
                "MaxKeys": 1000,  # Explicitly set MaxKeys, though it's default
            }
            if continuation_token:
                list_kwargs["ContinuationToken"] = continuation_token

            response = s3.list_objects_v2(**list_kwargs)

            if "Contents" in response:
                objects.extend(response["Contents"])

            if not response.get("IsTruncated"):
                # No more objects to retrieve, or less than 1000 objects in total
                break

            continuation_token = response.get("NextContinuationToken")
            if not continuation_token:
                # Should not happen if 'IsTruncated' is True, but as a safeguard
                break

        return objects

    def get_data_from_s3(self, file_list: list, local_directory: str) -> None:
        """
        Download files from S3 bucket to a local directory.
        Parameters
        ----------
        file_list : list
            A list of files that need to be downloaded
        local_directory : str
            The local directory path where the downloaded files will be saved.

        Returns
        -------
        None
            This function does not return anything. Files are downloaded as a side effect.

        Raises
        ------
        Exception
            If the file download operation fails.
        """

        logger.info(f"Downloading files from S3 bucket: {self.bucket_name}")
        logger.info(f"Downloading files to {local_directory}")

        for file_name in file_list:
            local_file_path = os.path.join(local_directory, os.path.basename(file_name))
            if os.path.exists(local_file_path):
                logger.warning(f"File already exists, skipping: {file_name}")
                continue
            file_name_in_bucket = (
                self.bucket_root_directory + "/" + file_name
                if self.bucket_root_directory
                else file_name
            )
            print(f"Downloading {file_name_in_bucket} to {local_file_path}")
            try:
                self.s3.download_file(
                    self.bucket_name, file_name_in_bucket, local_file_path
                )
                logger.info(f"Downloaded:  {file_name} -> {local_directory}")
            except Exception as ee:
                logger.error(f"Error downloading {file_name}: {ee}")

    def get_data_from_local(self, file_list: list, local_directory: str) -> None:
        """Copy files from a local directory to another local directory.

        Parameters
        ----------
        file_list : list
            A list of files that need to be copied.
        local_directory : str
            The local directory path where the copied files will be saved.

        Returns
        -------
        None
            This function does not return anything. Files are copied as a side effect.

        Raises
        ------
        OSError
            If the file copy operation fails.
        """

        logger.info(f"Copying files from directory: {self.root_directory}")
        logger.info(f"Copying files to {local_directory}")

        for file_name in file_list:
            local_file_path = os.path.join(local_directory, os.path.basename(file_name))
            if os.path.exists(local_file_path):
                logger.warning(f"File already exists, skipping: {file_name}")
                continue
            file_name_in_remote = (
                self.root_directory + "/" + file_name
                if self.root_directory
                else file_name
            )
            try:
                shutil.copy2(file_name_in_remote, local_file_path)
                logger.info(f"Copied:  {file_name} -> {local_directory}")
            except OSError:
                logger.error(f"Unable to copy {file_name} to {local_directory}")
                raise OSError(f"Unable to copy {file_name} to {local_directory}")

        return

    def get_data(self) -> None:

        GET_DATA_MAP = {"s3": self.get_data_from_s3, "local": self.get_data_from_local}

        logger.info("Starting download...")
        GET_DATA_MAP[self.download_source](self.file_list, self.local_directory)
        logger.info("Download completed.")
