import yaml
import os
import logging
import grib2io
import xarray as xr
import numpy as np
from datetime import datetime
from pprint import pprint
import fnmatch

logger = logging.getLogger(__name__)

class PrepareIC:
    """Class to prepare initial conditions."""

    def __init__(self,
                 current_cycle: datetime,
                 varinfo_file: str,
                 filelist: list = [],
                 data_dir: str = "./data",
                 output_netcdf: str = "ic.nc") -> None:

        self.current_cycle = current_cycle
        self.varinfo = self.get_var_info(varinfo_file)
        self.input_file_list = filelist
        self.data_dir = data_dir
        self.output_netcdf = output_netcdf

    def get_var_info(self, yaml_file) -> dict:

        with open(yaml_file, "r") as fh:
            variables_to_extract = yaml.safe_load(fh)

        return variables_to_extract

    def process_files(self):

        file_patterns = list(self.varinfo.keys())

        mergeDSs = []
        mergeDAs = []

        # Files are all valid at the same time, so we can merge them along the time dimension
        for file in self.input_file_list:
            matched = False
            for pattern in file_patterns:
                if fnmatch.fnmatch(file, os.path.join(self.data_dir, '*' + pattern)):
                    logger.debug(f"Matched pattern: {pattern} in file: {file}")
                    matched = True
                    break

            if not matched:
                logger.warning(f"No pattern matched for file: {file}")  # TODO: should this raise an error?

            logger.info(f"Processing file: {os.path.basename(file)}")

            gribfh = grib2io.open(file)

            #for var_pattern, details in self.varinfo[pattern].items():
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

        ds = xr.concat(mergeDSs, dim="time")

        # Get 2D static data from the f000 file
        # From the file list find the first file that ends with .f000
        f000_file = next((f for f in self.input_file_list if f.endswith(".f000")), None)
        if f000_file is None:
            logger.warning("No 00Z f000 file found.")  # TODO: should this raise an error?
            return

        gribfh = grib2io.open(os.path.join(self.data_dir, f000_file))
        static_vars = ["LAND", "HGT"]
        for var_name in static_vars:
            da = self.get_dataarray_2d(gribfh, var_name, "surface")
            ds = xr.merge([ds, da], compat="no_conflicts")
        gribfh.close()

        ds = ds.rename({
            "LAND_surface": "land_sea_mask",
            "HGT_surface": "geopotential_at_surface",
            "PRMSL_meansealevel": "mean_sea_level_pressure",
            "TMP_2maboveground": "2m_temperature",
            "UGRD_10maboveground": "10m_u_component_of_wind",
            "VGRD_10maboveground": "10m_v_component_of_wind",
            "APCP_surface": "total_precipitation_6hr",
            "HGT": "geopotential",
            "TMP": "temperature",
            "SPFH": "specific_humidity",
            "VVEL": "vertical_velocity",
            "UGRD": "u_component_of_wind",
            "VGRD": "v_component_of_wind",
        })

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

        # Update total_precipitation_6hr unit to (m) from (kg/m^2) by dividing it by 1000kg/m³
        ds["total_precipitation_6hr"] = ds["total_precipitation_6hr"] / 1000.0

        ds.to_netcdf(self.output_netcdf)
        ds.close()

        return

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
            print("3D data found in 2D function")
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

    input_file_list = [os.path.join(args.data_dir, "gfs.t00z.pgrb2.0p25.f000"),
                       os.path.join(args.data_dir, "gfs.t18z.pgrb2.0p25.f006")]
    #input_file_list = glob.glob(os.path.join(args.data_dir, "*"))

    prep = PrepareIC(
        current_cycle=datetime.strptime(args.current_cycle, "%Y%m%d%H"),
        varinfo_file=args.yaml,
        filelist=input_file_list,
        output_netcdf=args.output,
        data_dir=args.data_dir
    )

    logger.info("Starting IC preparation...")
    prep.process_files()
