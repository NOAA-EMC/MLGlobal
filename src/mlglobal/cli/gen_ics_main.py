import argparse
import logging
import os
from datetime import datetime

from mlglobal.ic_downloader import ICDownloader
from mlglobal.ic_processor import ICProcessor
from mlglobal.logger import setup_logging

logger = logging.getLogger(__name__)

_here = os.path.abspath(os.path.dirname(__file__))
_top = os.path.abspath(os.path.join(os.path.abspath(_here), "../../../"))

# Default bucket and root directory for each model  # TODO: store this in a yaml or some config file
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

# --- Helper strings for dynamic help text ---
BUCKET_HELP = (
    f"S3 bucket name. [default: {DEFAULTS['gfs']['bucket_name']} (for GFS), "
    f"{DEFAULTS['gefs']['bucket_name']} (for GEFS)]"
)

BUCKET_ROOT_DIR_HELP = (
    f"S3 bucket root directory. [default: {DEFAULTS['gfs']['bucket_root_directory']} (for GFS), "
    f"{DEFAULTS['gefs']['bucket_root_directory']} (for GEFS)]"
)

COMROOT_DIR_HELP = (
    f"Root directory. [default: {DEFAULTS['gfs']['comroot']} (for GFS), "
    f"{DEFAULTS['gefs']['comroot']} (for GEFS)]"
)


def main():

    parser = argparse.ArgumentParser(
        description="Download IC data for GFS or GEFS",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    subparsers = parser.add_subparsers(
        dest="model",
        help="Model to download and process initial conditions for [GFS | GEFS]",
        required=True,
    )

    def _common_args(inparser, model: str):
        dict_in = DEFAULTS[model]
        inparser.add_argument(
            "--current-cycle",
            help="Datetime to download and process initial conditions for in YYYYMMDDHH format",
            type=str,
            metavar="YYYYMMDDHH",
            required=True,
        )
        inparser.add_argument(
            "--source",
            help="Data source for getting model grib2 data",
            type=str,
            choices=["local", "s3"],
            default="local",
            required=False,
        )
        inparser.add_argument(
            "--target",
            help="Target directory to store grib2 model data into",
            type=str,
            default="./input_data",
            required=False,
        )
        inparser.add_argument(
            "--bucket-name",
            help=BUCKET_HELP,
            type=str,
            default=dict_in["bucket_name"],
            required=False,
        )
        inparser.add_argument(
            "--bucket-root-directory",
            help=BUCKET_ROOT_DIR_HELP,
            type=str,
            default=dict_in["bucket_root_directory"],
            required=False,
        )
        inparser.add_argument(
            "--comroot",
            help=COMROOT_DIR_HELP,
            type=str,
            default=dict_in["comroot"],
            required=False,
        )
        inparser.add_argument(
            "--num-levels",
            help="Number of vertical levels to download from the model data",
            type=int,
            default=13,
            required=False,
        )
        inparser.add_argument(
            "--varinfo-yaml",
            help="Path to the varinfo YAML file",
            type=str,
            default=os.path.join(_top, "config", f"{model}_varinfo.yaml"),
            required=False,
        )
        inparser.add_argument(
            "--output",
            help="Name of the output NetCDF file",
            type=str,
            default="graphcast_ic.nc",
            required=False,
        )
        inparser.add_argument(
            "--debug",
            help="Set logging level to DEBUG",
            action="store_true",
            required=False,
        )
        inparser.add_argument(
            "--download-only",
            help="Only download the data, do not process",
            action="store_true",
            required=False,
        )

        return inparser

    # GFS subparser
    gfs_parser = subparsers.add_parser("gfs", help="Download GFS data")
    gfs_parser = _common_args(gfs_parser, "gfs")

    # GEFS subparser
    gefs_parser = subparsers.add_parser("gefs", help="Download GEFS ensemble data")
    gefs_parser = _common_args(gefs_parser, "gefs")
    gefs_members = ["c00"] + [f"p{str(i).zfill(2)}" for i in range(1, 31)]
    gefs_parser.add_argument(
        "--member",
        help="Ensemble member",
        type=str,
        choices=gefs_members,
        default="c00",
    )

    args = parser.parse_args()

    setup_logging(debug=args.debug)

    current_cycle = datetime.strptime(args.current_cycle, "%Y%m%d%H")

    logger.info(f"Downloading {args.model.upper()} data for cycle {args.current_cycle}")
    downloader = ICDownloader(
        current_cycle=current_cycle,
        num_levels=args.num_levels,
        member=None if args.model == "gfs" else args.member,
        download_source=args.source,
        local_directory=args.target,
        bucket_name=args.bucket_name,
        bucket_root_directory=args.bucket_root_directory,
        root_directory=args.comroot,
    )
    downloader.get_data()

    # TODO: validate the downloaded files before processing

    if args.download_only:
        logger.info("Download-only flag set, skipping processing step.")
        return

    logger.info(f"Processing {args.model.upper()} data for cycle {args.current_cycle}")
    processor = ICProcessor(
        current_cycle=current_cycle,
        num_levels=args.num_levels,
        member=None if args.model == "gfs" else args.member,
        varinfo_file=args.varinfo_yaml,
        data_dir=args.target,
        output_netcdf=args.output,
    )
    processor.process_files()


if __name__ == "__main__":
    main()
