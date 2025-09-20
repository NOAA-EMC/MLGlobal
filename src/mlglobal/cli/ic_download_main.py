import argparse
import logging
import os
from datetime import datetime

from mlglobal.ic_downloader import ICDownloader
from mlglobal.logger import setup_logging


# Default bucket and root directory for each mode  # TODO: store this in a yaml or some config file
DEFAULTS = {
    "gfs": {
        "bucket_name": "noaa-gfs-bdp-pds",
        "bucket_root_directory": "",
        "comroot": "/lfs/h1/ops/prod/com/gfs/v16.3",
    },
    "gefs": {
        "bucket_name": "noaa-ncepdev-none-ca-ufs-cpldcld",
        "bucket_root_directory": "Linlin.Cui/gefs_wcoss2",
        "comroot": "/lfs/h1/ops/prod/com/gefs/v12.3",
    },
}


def main():

    setup_logging()

    parser = argparse.ArgumentParser(description="Download IC data for GFS or GEFS")

    subparsers = parser.add_subparsers(
        dest="mode", help="System to download IC data for GFS or GEFS", required=True
    )

    def _common_args(inparser, dict_in):
        inparser.add_argument(
            "--current_cycle",
            help="Datetime to download data for in YYYYMMDDHH format",
            type=str,
            metavar="YYYYMMDDHH",
            required=True,
        )
        inparser.add_argument(
            "--source",
            help="Data source",
            type=str,
            choices=["s3", "local"],
            default="s3",
            required=False,
        )
        inparser.add_argument(
            "--target",
            help="Target directory to store raw data into",
            type=str,
            default=os.getcwd(),
            required=False,
        )
        inparser.add_argument(
            "--bucket-name",
            help="S3 bucket name",
            type=str,
            default=dict_in["bucket_name"],
            required=False,
        )
        inparser.add_argument(
            "--root-directory",
            help="Root directory",
            type=str,
            default=dict_in["bucket_root_directory"],
            required=False,
        )
        return inparser

    # GFS subparser
    gfs_parser = subparsers.add_parser("gfs", help="Download GFS ensemble data")
    gfs_parser = _common_args(gfs_parser, DEFAULTS["gfs"])

    # GEFS subparser
    gefs_parser = subparsers.add_parser("gefs", help="Download GEFS ensemble data")
    gefs_parser = _common_args(gefs_parser, DEFAULTS["gefs"])
    gefs_members = ["c00"] + [f"p{str(i).zfill(2)}" for i in range(1, 31)]
    gefs_parser.add_argument(
        "--member",
        help="Ensemble member",
        type=str,
        choices=gefs_members,
        default=0,
    )

    args = parser.parse_args()

    downloader = ICDownloader(
        current_cycle=datetime.strptime(args.current_cycle, "%Y%m%d%H"),
        member=None if args.mode == "gfs" else args.member,
        download_source=args.source,
        local_directory=args.target,
        bucket_name=args.bucket_name,
        root_directory=args.root_directory,
    )
    downloader.get_data()


if __name__ == "__main__":
    main()
