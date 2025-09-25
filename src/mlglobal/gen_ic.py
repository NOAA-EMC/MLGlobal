import yaml
import os
import logging
import grib2io
import xarray as xr
import numpy as np
from datetime import datetime
from pprint import pprint
import fnmatch
from mlglobal.ic_downloader import FileLookup


logger = logging.getLogger(__name__)

class PrepareIC:
    """Class to prepare initial conditions."""

    def __init__(self,
                 current_cycle: datetime,
                 varinfo_file: str,
                 member: str | None = None,
                 num_levels: int = 13,
                 data_dir: str = "./data",
                 output_netcdf: str = "ic.nc") -> None:

        self.current_cycle = current_cycle
        self.varinfo = self.get_var_info(varinfo_file)
        self.member = member
        self.num_levels = num_levels
        self.data_dir = data_dir
        self.output_netcdf = output_netcdf

        # Generate the lookup dictionary
        lookup = FileLookup(self.current_cycle, member=self.member, num_levels=self.num_levels)
        self.file_dict = lookup.get_file_info()

    def get_var_info(self, yaml_file) -> dict:

        with open(yaml_file, "r") as fh:
            variables_to_extract = yaml.safe_load(fh)

        return variables_to_extract


    def get_matching_pattern(self, file, patterns, fatal=True):

        matched = False
        for pattern in file_patterns:
            if fnmatch.fnmatch(file, os.path.join(self.data_dir, '*' + pattern)):
                logger.debug(f"Matched pattern: {pattern} in file: {filename}")
                matched = True
                break

        if not matched:
            logger.error(f"No pattern matched for file: {filename}")
            pattern = None
            if fatal:
                raise FileNotFoundError(f"No pattern matched for file: {filename}")

        return pattern

    def process_files(self):

        file_patterns = list(self.varinfo['time_variant'].keys())

        mergeDSs = []
        for cycle in self.file_dict.keys():

            mergeDAs = []

            # Files valid at the same time, so we can merge them along the time dimension
            for file in self.file_dict[cycle]:

                filename = os.path.basename(file)
                file = os.path.join(self.data_dir, filename)

                pattern = get_pattern(file, file_patterns)

                logger.info(f"Processing {filename=}")

                gribfh = grib2io.open(file, "r")

                for var_dict in self.varinfo[pattern]:

                    variable_names = var_dict["variables"]
                    levels = var_dict["levels"]

                    for var_name in variable_names:
                        logger.info(f"Extracting variable: {var_name} at levels: {levels}")
                        if len(levels) > 1:
                            da = self.get_dataarray_3d(gribfh, var_name, levels)
                        else:
                            da = self.get_dataarray_2d(gribfh, var_name, levels[0])
                        mergeDAs.append(da)

                gribfh.close()

            ds = xr.merge(mergeDAs, compat="no_conflicts")
            mergeDSs.append(ds)
            ds.close()

        # Concatenate along the time dimension
        ds = xr.concat(mergeDSs, dim="time")

        # Get 2D static data from the f000 file
        # From the file list find the first file that ends with .f000
        f000_file = next((f for f in self.file_dict[self.current_cycle] if f.endswith(".f000")), None)
        if f000_file is None:
            logger.error("No 00Z f000 file found.")  # TODO: should this raise an error?
            raise FileNotFoundError("No f000 file found.")

        f000_file = os.path.join(self.data_dir, os.path.basename(f000_file))
        gribfh = grib2io.open(f000_file, "r")
        static_vars = ["LAND", "HGT"]
        for var_name in static_vars:
            da = self.get_dataarray_2d(gribfh, var_name, "surface")
            ds = xr.merge([ds, da], compat="no_conflicts")
        gribfh.close()

        # Rename variables to match graphcast naming conventions
        ds = self.rename_dsvars(ds)

        # Add datetime coordinate
        ds = ds.assign_coords(datetime=ds.time)

        # Adjust time values relative to the first time step
        ds["time"] = ds["time"] - ds["time"][0]

        # Expand dimensions
        ds = ds.expand_dims(dim="batch")
        ds["datetime"] = ds["datetime"].expand_dims(dim="batch")

        # Squeeze dimensions
        ds["geopotential_at_surface"] = ds["geopotential_at_surface"].squeeze("batch")
        ds["land_sea_mask"] = ds["land_sea_mask"].squeeze("batch")

        # Update geopotential unit to m2/s2 by multiplying 9.80665
        ds["geopotential_at_surface"] = ds["geopotential_at_surface"] * 9.80665
        ds["geopotential"] = ds["geopotential"] * 9.80665

        # For GEFS, if total_precipitation_6hr is missing, create it with zeros
        if "total_precipitation_6hr" not in ds:
            logger.warning("total_precipitation_6hr variable not found. Creating it with zeros.")
            ds["total_precipitation_6hr"] = xr.zeros_like(ds["2m_temperature"])
        else:
            # Update total_precipitation_6hr unit to (m) from (kg/m^2) by dividing it by 1000kg/m³
            ds["total_precipitation_6hr"] = ds["total_precipitation_6hr"] / 1000.0

        ds.to_netcdf(self.output_netcdf)
        ds.close()

        return

    @staticmethod
    def rename_dsvars(ds: xr.Dataset, rename_dict: dict = None) -> xr.Dataset:
        """Rename dataset variables to match graphcast naming conventions."""
        logger.info("Renaming dataset variables to match graphcast naming conventions.")

        # Default rename dictionary  #TODO: move to yaml?
        if rename_dict is None:
            rename_dict = {
                "LAND_surface": "land_sea_mask",
                "HGT_surface": "geopotential_at_surface",
                "PRMSL_meansealevel": "mean_sea_level_pressure",
                "TMP_2maboveground": "2m_temperature",
                "UGRD_10maboveground": "10m_u_component_of_wind",
                "VGRD_10maboveground": "10m_v_component_of_wind",
                "HGT": "geopotential",
                "TMP": "temperature",
                "SPFH": "specific_humidity",
                "VVEL": "vertical_velocity",
                "UGRD": "u_component_of_wind",
                "VGRD": "v_component_of_wind",
            }
            if "APCP_surface" in ds:
                rename_dict["APCP_surface"] = "total_precipitation_6hr"
            logger.debug(f"Using rename_dict: {rename_dict}")

        ds = ds.rename(rename_dict)

        return ds

    @staticmethod
    def get_dataarray_2d(grbfile, var_name, desired_level):

        logger.info(f"Getting 2D data for variable: {var_name} at level: {desired_level}")

        msg = grbfile.select(shortName=var_name, level=desired_level)[0]

        # create a netcdf dataset using the matching grib message
        lats, lons = msg.latlons()
        lats = lats[:,0]
        lons = lons[0,:]

        #check latitude range
        reverse_lat = False
        if lats[0] > 0:
            reverse_lat = True

        steps = msg.validDate
        data = msg.data
        if reverse_lat:
            data = data[::-1, :]
            lats = lats[::-1]

        var_name2 = f'{var_name}_{"".join(desired_level.split())}'
        if len(data.shape) == 2:
            da = xr.Dataset(
                data_vars={
                    var_name2: (["lat", "lon"], data.astype("float32"))
                },
                coords={
                    "lon": lons.astype("float32"),
                    "lat": lats.astype("float32"),
                    "time": steps,
                }
            )
        elif len(data.shape) == 3:
            logger.warning("3D data found in 2D function")
            da = xr.Dataset(
                data_vars={
                    var_name: (["level", "lat", "lon"], data.astype("float32"))
                },
                coords={
                    "lon": lons.astype("float32"),
                    "lat": lats.astype("float32"),
                    "level": np.array(desired_level).astype("int32"),
                    "time": steps,
                }
            )

        return da

    @staticmethod
    def get_dataarray_3d(grbfile, var_name, desired_level):

        logger.info(f"Getting 3D data for variable: {var_name} at levels: {desired_level}")
        data, levels = [], []
        for ii, level in enumerate(desired_level):
            msg = grbfile.select(shortName=var_name, level=level)[0]

            if ii == 0:
                lats, lons = msg.latlons()
                lats = lats[:,0]
                lons = lons[0,:]

                #check latitude range, graphcast needs [-90, 90]
                reverse_lat = False
                if lats[0] > 0:
                    reverse_lat = True
                steps = msg.validDate
            data.append(msg.data)
            levels.append(int(level.split(' ')[0]))

        data = np.array(data)
        if reverse_lat:
            data = data[:, ::-1, :]
            lats = lats[::-1]

        da = xr.Dataset(
            data_vars={
                var_name: (["level", "lat", "lon"], data.astype("float32"))
            },
            coords={
                "lon": lons.astype("float32"),
                "lat": lats.astype("float32"),
                "level": np.array(levels).astype("int32"),
                "time": steps,
            }
        )

        return da

if __name__ == "__main__":

    import argparse
    from datetime import datetime
    from mlglobal.logger import setup_logging

    setup_logging()

    parser = argparse.ArgumentParser(
        description="Process data to generate initial conditions for graphcast"
        )

    parser.add_argument(
            "--current-cycle",
            help="Current cycle in YYYYMMDDHH format",
            type=str,
            metavar="YYYYMMDDHH",
            required=True
            )
    parser.add_argument(
            "--yaml",
            help="YAML file containing variable information",
            type=str,
            required=True
            )
    parser.add_argument(
            "--data-dir",
            help="Directory containing input GRIB2 files",
            type=str,
            default="./data",
            required=False
            )
    parser.add_argument(
            "--output",
            help="Output NetCDF file",
            type=str,
            default="ic.nc",
            required=False
            )

    args = parser.parse_args()

    prep = PrepareIC(
        current_cycle=datetime.strptime(args.current_cycle, "%Y%m%d%H"),
        varinfo_file=args.yaml,
        member=None,
        num_levels=13,
        output_netcdf=args.output,
        data_dir=args.data_dir
    )

    logger.info("Starting IC preparation...")
    prep.process_files()
