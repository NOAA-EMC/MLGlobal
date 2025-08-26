import argparse
import os
from datetime import datetime

from mlglobal.ic_downloader import ICDownloader

# Default bucket and root directory for each mode  # TODO: store this in a yaml or some config file
DEFAULTS = {
    "gfs": {
        "bucket_name": "noaa-gfs-bdp-pds",
        "root_directory": "gdas",
    },
    "gefs": {
        "bucket_name": "noaa-ncepdev-none-ca-ufs-cpldcld",
        "root_directory": "gefs",
    },
}


def main():
    parser = argparse.ArgumentParser(description="Download IC data for GFS or GEFS")

    subparsers = parser.add_subparsers(
        dest="mode", help="System to download IC data for GFS or GEFS", required=True
    )

    def _common_args(inparser, dict_in):
        inparser.add_argument(
            "--start_date",
            help="Start datetime",
            type=str,
            metavar="YYYYMMDDHH",
            required=True,
        )
        inparser.add_argument(
            "--end_date",
            help="End datetime",
            type=str,
            metavar="YYYYMMDDHH",
            required=True,
        )
        inparser.add_argument(
            "--levels",
            help="number of pressure levels",
            type=int,
            choices=[13, 37],
            default=13,
            required=False,
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
            default=dict_in["root_directory"],
            required=False,
        )
        return inparser

    # GFS subparser
    gfs_parser = subparsers.add_parser("gfs", help="Download GFS ensemble data")
    gfs_parser = _common_args(gfs_parser, DEFAULTS["gfs"])

    # GEFS subparser
    gefs_parser = subparsers.add_parser("gefs", help="Download GEFS ensemble data")
    gefs_parser = _common_args(gefs_parser, DEFAULTS["gefs"])
    gefs_parser.add_argument(
        "--member",
        help="Ensemble member",
        type=int,
        choices=list(range(0, 31)),
        default=0,
    )

    args = parser.parse_args()

    downloader = ICDownloader(
        mode=args.mode,
        start_datetime=datetime.strptime(args.start_date, "%Y%m%d%H"),
        end_datetime=datetime.strptime(args.end_date, "%Y%m%d%H"),
        member=None if args.mode == "gfs" else args.member,
        download_source=args.source,
        download_directory=args.target,
        bucket_name=args.bucket_name,
        root_directory=args.root_directory,
    )
    downloader.download()


if __name__ == "__main__":
    main()
