import glob
import os
import shutil
from datetime import datetime, timedelta


class FileFormats:
    def __init__(self, mode, num_levels=13):

        FILE_FORMATS = {"gfs": self.gfs_file_formats, "gefs": self.gefs_file_formats}
        self.num_levels = num_levels
        self.file_formats = FILE_FORMATS[mode]()

    def gfs_file_formats(self):
        # List of file formats to download
        if self.num_levels == 13:
            file_formats = ["pgrb2.0p25.f000", "pgrb2.0p25.f006"]  # , '0p25.f001'
        else:
            file_formats = [
                "pgrb2.0p25.f000",
                "pgrb2b.0p25.f000",
                "pgrb2.0p25.f006",
            ]  # , '0p25.f001'

        return file_formats

    def gefs_file_formats(self):

        # List of file formats to download
        if self.num_levels == 13:
            file_formats = ["pgrb2.0p25.f000", "pgrb2s.0p25.f000"]  # , '0p25.f001'
        else:
            file_formats = [
                "pgrb2.0p25.f000",
                "pgrb2b.0p25.f000",
                "pgrb2.0p25.f006",
            ]  # , '0p25.f001'

        return file_formats


class ICDownloader:

    def __init__(
        self,
        mode,
        start_datetime,
        end_datetime,
        member=None,
        num_pressure_levels=13,
        download_source="s3",
        download_directory=None,
        bucket_name=None,
        root_directory=None,
    ):
        self.mode = mode
        self.start_datetime = start_datetime
        self.end_datetime = end_datetime
        self.member = member
        self.num_pressure_levels = num_pressure_levels
        self.download_source = download_source
        self.download_directory = download_directory
        self.bucket_name = bucket_name
        self.root_directory = root_directory

        ff = FileFormats(mode, num_levels=self.num_pressure_levels)
        self.file_formats = ff.file_formats

        self.s3 = self.init_s3_client() if self.download_source == "s3" else None

    @staticmethod
    def init_s3_client():

        try:
            import boto3
            from botocore import UNSIGNED
            from botocore.config import Config
        except ImportError as ee:
            raise ImportError(
                "boto3 and botocore are required for S3 operations."
            ) from ee

        try:
            # Try to create S3 client using profile method
            profile_name = os.environ.get("AWS_PROFILE", "default")
            session = boto3.Session(profile_name=profile_name)
            current_credentials = session.get_credentials().get_frozen_credentials()
            s3 = session.client(
                "s3",
                aws_access_key_id=current_credentials.access_key,
                aws_secret_access_key=current_credentials.secret_key,
            )
        except Exception as e1:
            print(f"Failed to create S3 client with profile method: {e1}")
            try:
                # Try to create S3 client using unsigned method
                s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))
            except Exception as e2:
                print(f"Failed to create S3 client with unsigned method: {e2}")
                raise RuntimeError(
                    "Failed to create S3 client with unsigned method."
                ) from e2

        return s3

    def get_s3_specs(self, ymd, hh, file_format):

        if self.mode == "gefs":

            s3_prefix = (
                f"Linlin.Cui/gefs_wcoss2/{self.root_directory}.{ymd}/{hh}/atmos/"
            )
            s3_file_format = f"{self.member:02d}.t{hh}z.{file_format}"

        elif self.mode == "gfs":

            if file_format == "pgrb2.0p25.f006":
                # get prefix for precip from the previous cycle
                # Convert ymd and hh to datetime object
                datetime_obj = datetime.strptime(ymd + hh, "%Y%m%d%H")

                # Get the datetime 6 hours before
                datetime_before = datetime_obj - timedelta(hours=6)

                # Get the date string and time string from datetime objects
                ymd_precip = datetime_before.strftime("%Y%m%d")
                hh_precip = datetime_before.strftime("%H")

                # Construct the S3 prefix for the directory
                s3_prefix = f"{self.root_directory}.{ymd_precip}/{hh_precip}/"

            else:

                s3_prefix = f"{self.root_directory}.{ymd}/{hh}/"

            s3_file_format = file_format

        return s3_prefix, s3_file_format

    def get_data_from_s3(
        self, path_prefix: str, file_format: str, local_directory: str
    ) -> None:
        """
        Downloads files with a specific format from an S3 bucket to a local directory.

        Parameters
        ----------
        prefix : str
            The prefix (folder path) in the S3 bucket to filter objects.
        file_format : str
            The file extension or format to filter files (e.g., '.csv', '.json').
        local_directory : str
            The local directory path where the downloaded files will be saved.

        Returns
        -------
        None
            This function does not return anything. Files are downloaded as a side effect.

        Notes
        -----
        Only files ending with the specified `file_format` will be downloaded.
        """

        objects = self.s3.list_objects_v2(Bucket=self.bucket_name, Prefix=path_prefix)
        for obj in objects.get("Contents", []):
            obj_key = obj["Key"]
            if obj_key.endswith(f"{file_format}"):
                local_file_path = os.path.join(
                    local_directory, os.path.basename(obj_key)
                )
                if not os.path.exists(local_file_path):
                    self.s3.download_file(self.bucket_name, obj_key, local_file_path)
                    print(f"Downloaded {obj_key} to {local_file_path}")
                else:
                    print(f"File {local_file_path} already exists, skipping download.")

    def get_local_specs(self, ymd: str, hh: str, file_format: str) -> tuple[str, str]:
        """
        Get the local specifications for a given date, time, and file format.

        Parameters
        ----------
        ymd : str
            The date string in the format 'YYYYMMDD'.
        hh : str
            The time string in the format 'HH'.
        file_format : str
            The file format string (e.g., 'pgrb2.0p25.f006').

        Returns
        -------
        tuple[str, str]
            A tuple containing the local path prefix and the local file format.
        """
        # TODO: elevate the hard-coded paths to class constructor (or above)
        if self.mode == "gefs":
            gefs_com_dir = "/lfs/h2/emc/da/noscrub/rahul.mahajan/mldata"  # For testing on Acorn
            gefs_com_dir = "/lfs/h2/emc/ptmp/jun.wang"  # NCO does not mirror all of GEFS data to dev in RT
            gefs_com_dir = "/lfs/h1/ops/prod/com/gefs/v12.3"
            fprefix = file_format.split('.')[0]
            local_prefix = f"{gefs_com_dir}/gefs.{ymd}/{hh}/atmos/{fprefix}p25"
            local_file_format = f"{self.member:02d}.t{hh}z.{file_format}"

        elif self.mode == "gfs":

            # TODO: elevate the hard-coded paths to constructor
            gfs_com_dir = "/lfs/h2/emc/da/noscrub/rahul.mahajan/mldata"  # For testing on Acorn
            gfs_com_dir = "/lfs/h1/ops/prod/com/gfs/v16.3"
            if file_format == "pgrb2.0p25.f006":
                # get prefix for precip from the previous cycle
                # Convert ymd and hh to datetime object
                datetime_obj = datetime.strptime(ymd + hh, "%Y%m%d%H")

                # Get the datetime 6 hours before
                datetime_before = datetime_obj - timedelta(hours=6)

                # Get the date string and time string from datetime objects
                ymd_precip = datetime_before.strftime("%Y%m%d")
                hh_precip = datetime_before.strftime("%H")

                # Construct the S3 prefix for the directory
                local_prefix = f"{gfs_com_dir}/gfs.{ymd_precip}/{hh_precip}/atmos"
                local_file_format = f"gfs.t{hh_precip}z.{file_format}"

            else:

                local_prefix = f"{gfs_com_dir}/gfs.{ymd}/{hh}/atmos"
                local_file_format = f"gfs.t{hh}z.{file_format}"

        return local_prefix, local_file_format

    def get_data_from_local(
        self, path_prefix: str, file_format: str, local_directory: str
    ) -> None:

        file_objects = glob.glob(f"{path_prefix}/*")
        for obj_key in file_objects:
            if obj_key.endswith(f"{file_format}"):

                # Define the local file path
                local_file_path = os.path.join(
                    local_directory, os.path.basename(obj_key)
                )

                # Copy data to the local path
                try:
                    shutil.copy2(obj_key, local_file_path)
                    print(f"Copied:  {obj_key} -> {local_directory}")
                except OSError:
                    raise OSError(f"Unable to copy {obj_key} to {local_directory}")

        return

    def download(self, loop_interval=6):

        _SPECS_MAP = {"s3": self.get_s3_specs, "local": self.get_local_specs}
        _GET_DATA_MAP = {"s3": self.get_data_from_s3, "local": self.get_data_from_local}

        interval_dt = timedelta(hours=loop_interval)

        # Loop through the intervals
        current_datetime = self.start_datetime
        while current_datetime <= self.end_datetime:
            ymd = current_datetime.strftime("%Y%m%d")
            hh = current_datetime.strftime("%H")

            # Define the local directory path where the file will be saved
            local_directory = os.path.join(self.download_directory, ymd, hh)

            # Create the local directory if it doesn't exist
            os.makedirs(local_directory, exist_ok=True)

            # Loop over file formats and download data
            for file_format in self.file_formats:
                prefix, fformat = _SPECS_MAP[self.download_source](ymd, hh, file_format)
                _GET_DATA_MAP[self.download_source](prefix, fformat, local_directory)

            # Move to the next interval
            current_datetime += interval_dt

        print("Download completed.")
