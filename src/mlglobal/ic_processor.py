import fnmatch
import logging
import os
from datetime import datetime

import grib2io
import numpy as np
import xarray as xr
import yaml

from mlglobal.ic_downloader import FileLookup

logger = logging.getLogger(__name__)


class ICProcessor:
    """Class to prepare initial conditions for graphcast from downloaded data files."""

    def __init__(
        self,
        current_cycle: datetime,
        varinfo_file: str,
        member: str | None = None,
        num_levels: int = 13,
        data_dir: str = "./data",
        output_netcdf: str = "./ic.nc",
    ) -> None:

        self.current_cycle = current_cycle
        self.varinfo = self.load_yaml(varinfo_file)
        self.member = member
        self.num_levels = num_levels
        self.data_dir = data_dir
        self.output_netcdf = output_netcdf

        # Generate the lookup dictionary
        lookup = FileLookup(
            self.current_cycle, member=self.member, num_levels=self.num_levels
        )
        self.file_dict = lookup.get_file_info()

    @staticmethod
    def load_yaml(yaml_file: str) -> dict:
        """Load a YAML file and return the contents as a dictionary.
        Parameters
        ----------
        yaml_file : str
            Path to the YAML file.
        Returns
        -------
        dict
            Dictionary containing the contents of the YAML file.
        Raises
        ------
        FileNotFoundError
            If the YAML file does not exist.
        yaml.YAMLError
            If there is an error parsing the YAML file.
        """

        try:
            with open(yaml_file, "r") as fh:
                yaml_dict = yaml.safe_load(fh)
        except FileNotFoundError:
            logger.error(f"YAML file {yaml_file} not found.")
            raise FileNotFoundError(f"YAML file {yaml_file} not found.")
        except yaml.YAMLError as e:
            logger.error(f"Error parsing YAML file {yaml_file}: {e}")
            raise yaml.YAMLError(f"Error parsing YAML file {yaml_file}: {e}")

        return yaml_dict

    def get_matching_pattern(self, file, patterns, fatal=True):

        filename = os.path.basename(file)

        matched = False
        pattern = None
        # Check each pattern to see if it matches the filename
        for pp in patterns:
            if fnmatch.fnmatch(file, os.path.join(self.data_dir, "*" + pp)):
                pattern = pp
                logger.debug(f"Matched pattern: {pattern} in file: {filename}")
                matched = True
                break

        if not matched and fatal:
            logger.error(f"No pattern matched for file: {filename}")
            raise FileNotFoundError(f"No pattern matched for file: {filename}")

        return pattern

    def process_files(self):
        """
        Process input files and extract relevant variables.
        This function reads GRIB2 files, extracts specified variables,
        and saves them into a NetCDF file.
        Returns
        -------
        None

        Raises
        ------
        FileNotFoundError
            If any of the input files do not exist.
        ValueError
            If there is an error processing the files.
        IOError
            If there is an error saving the NetCDF file.
        """

        logger.info("Starting to process files...")

        file_patterns = list(self.varinfo["time_variant"].keys())
        mergeDSs = []
        for cycle in self.file_dict.keys():

            mergeDAs = []

            # Files valid at the same time, so we can merge them along the time dimension
            for file in self.file_dict[cycle]:

                logger.info(f"Processing {file=}")

                file = os.path.join(self.data_dir, os.path.basename(file))

                pattern = self.get_matching_pattern(file, file_patterns)

                gribfh = grib2io.open(file, "r")
                for var_dict in self.varinfo["time_variant"][pattern]:
                    for var_name in var_dict["variables"]:
                        logger.info(
                            f"Extracting variable: {var_name} at levels: {var_dict['levels']}"
                        )
                        da = self.get_dataarray(gribfh, var_name, var_dict["levels"])
                        mergeDAs.append(da)
                gribfh.close()

            ds = xr.merge(mergeDAs, compat="no_conflicts")
            mergeDSs.append(ds)
            ds.close()

        # Concatenate along the time dimension
        ds = xr.concat(mergeDSs, dim="time")

        logger.info("Processing static variables...")

        # Now handle the static variables
        file_patterns = list(self.varinfo["time_invariant"].keys())
        mergeDAs = []
        for file in self.file_dict[self.current_cycle]:

            logger.info(f"Processing {file=}")

            file = os.path.join(self.data_dir, os.path.basename(file))

            pattern = self.get_matching_pattern(file, file_patterns, fatal=False)
            if pattern is None:  # No pattern matched, so skip this file
                continue

            gribfh = grib2io.open(file, "r")
            for var_dict in self.varinfo["time_invariant"][pattern]:
                for var_name in var_dict["variables"]:
                    logger.info(
                        f"Extracting variable: {var_name} at levels: {var_dict['levels']}"
                    )
                    da = self.get_dataarray(gribfh, var_name, var_dict["levels"])
                    mergeDAs.append(da)
            gribfh.close()

        ds_static = xr.merge(mergeDAs, compat="no_conflicts")
        ds = xr.merge([ds, ds_static], compat="no_conflicts")
        ds_static.close()

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
            logger.warning(
                "total_precipitation_6hr variable not found. Creating it with zeros."
            )
            ds["total_precipitation_6hr"] = xr.zeros_like(ds["2m_temperature"])
        else:
            # Update total_precipitation_6hr unit to (m) from (kg/m^2) by dividing it by 1000kg/m³
            ds["total_precipitation_6hr"] = ds["total_precipitation_6hr"] / 1000.0

        # Save to NetCDF
        logger.info(f"Saving processed data to {self.output_netcdf}")
        os.makedirs(os.path.dirname(self.output_netcdf), exist_ok=True)
        ds.to_netcdf(self.output_netcdf)
        ds.close()

        return

    @staticmethod
    def rename_dsvars(ds: xr.Dataset, rename_dict: dict = None) -> xr.Dataset:
        """Rename dataset variables to match graphcast naming conventions."""
        logger.info("Renaming dataset variables to match graphcast naming conventions.")

        # Default rename dictionary  # TODO: move to yaml?
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
    def get_dataarray(gh, var_name: str, levels: list | int | str) -> xr.Dataset:
        """Get a data array from the GRIB file.

        Parameters
        ----------
        gh : Handle of opened grib2io file
        var_name : str
            Name of the variable to extract
        levels : list | int | str
            Levels to extract (can be a single level or a list of levels)

        Returns
        -------
        xr.Dataset
            A dataset containing the extracted data
        """

        if isinstance(levels, list) and len(levels) > 1:
            return ICProcessor._get_dataarray_3d(gh, var_name, levels)
        else:
            return ICProcessor._get_dataarray_2d(
                gh, var_name, levels[0] if isinstance(levels, list) else levels
            )

    @staticmethod
    def _get_dataarray_2d(gh, var_name, level):

        logger.info(f"Getting 2D data for variable: {var_name} at level: {level}")

        msg = gh.select(shortName=var_name, level=level)[0]

        # create a netcdf dataset using the matching grib message
        lats, lons = msg.latlons()
        lats = lats[:, 0]
        lons = lons[0, :]

        # check latitude range, graphcast needs [-90, 90]
        reverse_lat = False
        if lats[0] > 0:
            reverse_lat = True

        steps = msg.validDate
        data = msg.data
        if reverse_lat:
            data = data[::-1, :]
            lats = lats[::-1]

        if len(data.shape) == 2:
            var_name2 = f'{var_name}_{"".join(level.split())}'
            da = xr.Dataset(
                data_vars={var_name2: (["lat", "lon"], data.astype("float32"))},
                coords={
                    "lon": lons.astype("float32"),
                    "lat": lats.astype("float32"),
                    "time": steps,
                },
            )
        elif len(data.shape) == 3:
            logger.warning("3D data found in 2D function")
            da = xr.Dataset(
                data_vars={var_name: (["level", "lat", "lon"], data.astype("float32"))},
                coords={
                    "lon": lons.astype("float32"),
                    "lat": lats.astype("float32"),
                    "level": np.array(level).astype("int32"),
                    "time": steps,
                },
            )

        return da

    @staticmethod
    def _get_dataarray_3d(gh, var_name, levels):

        logger.info(f"Getting 3D data for variable: {var_name} at levels: {levels}")
        data, vlevs = [], []
        for ii, level in enumerate(levels):
            msg = gh.select(shortName=var_name, level=level)[0]

            if ii == 0:
                lats, lons = msg.latlons()
                lats = lats[:, 0]
                lons = lons[0, :]

                # check latitude range, graphcast needs [-90, 90]
                reverse_lat = False
                if lats[0] > 0:
                    reverse_lat = True
                steps = msg.validDate
            data.append(msg.data)
            vlevs.append(int(level.split(" ")[0]))

        data = np.array(data)
        if reverse_lat:
            data = data[:, ::-1, :]
            lats = lats[::-1]

        da = xr.Dataset(
            data_vars={var_name: (["level", "lat", "lon"], data.astype("float32"))},
            coords={
                "lon": lons.astype("float32"),
                "lat": lats.astype("float32"),
                "level": np.array(vlevs).astype("int32"),
                "time": steps,
            },
        )

        return da
