#!/usr/bin/env python

import os
import subprocess
from time import time
import json
import multiprocessing as mp

import xarray as xr
import datetime
import grib2io
import numpy as np
import pandas as pd


SECTION3 = np.array([0, 1038240, 0, 0, 0, 6, 0, 0, 0, 0, 0, 0, 1440, 721, 0, -1, 90000000, 0, 48, -90000000, 359750000,250000, 250000, 0])


class Netcdf2Grib:
    def __init__(self, start_date, case_name="mlgfs"):
        self.case_name = case_name

        if self.case_name == "mlgfs":
            table_file = "utils/tables_mlgfs.json"
        elif self.case_name.startswith("mlge"):
            table_file = "utils/tables_mlgefs.json"
        else:
            raise ValueError(f"name {self.case_name} is not supported!")

        with open(table_file, "r") as f:
            self.attrs = json.load(f)
        self.start_date = start_date

    def create_grib2_message(self, var, da, lead, level=None):

        # Set duration. NOTE: the duration attr exists for all Grib2Message objects.
        # For Grib2Messages that are instantaneous, the duration is just 0.
        duration = datetime.timedelta(hours=0)
        if var == "total_precipitation_6hr":
            duration = datetime.timedelta(hours=6)
        elif var == "total_precipitation_cumsum":
            duration = datetime.timedelta(hours=lead)

        # Create GRIB2 message.
        msg = grib2io.Grib2Message(
            section3=SECTION3,
            pdtn=self.attrs[var]["templates"]["pdtn"],
            drtn=self.attrs[var]["templates"]["drtn"],
        )

        # Set GRIB2 attributes from json table.
        for k,v in self.attrs[var]["attrs"].items():
            setattr(msg, k, v)

        # Set GRIB2 attributes for ensemble members
        if self.case_name.startswith("mlge"):
            number = int(self.case_name[-2:])
            msg.perturbationNumber = number
            if "c00" in self.case_name:
                msg.typeOfEnsembleForecast = 1
                msg.typeOfData = 3
            else:
                msg.typeOfEnsembleForecast = 3
                msg.typeOfData = 4

        # Set GRIB2 attributes unique to each iteration.
        msg.refDate = self.start_date
        msg.duration = duration
        msg.unitOfForecastTime = 1 # Hour
        msg.leadTime = datetime.timedelta(hours=lead)
        if level is not None:
            msg.scaledValueOfFirstFixedSurface = level

        return msg

    def save_grib2(self, xarray_ds, outdir):

        # Convert geopotential to geopotential height.
        xarray_ds["geopotential"] = xarray_ds["geopotential"] / 9.80665

        # Successively accumulate 6-hr precip.
        if "total_precipitation_6hr" in xarray_ds:
            xarray_ds["total_precipitation_6hr"] = xarray_ds["total_precipitation_6hr"].clip(min=0) * 1000
            xarray_ds["total_precipitation_cumsum"] = xarray_ds["total_precipitation_6hr"].cumsum(axis=0)

        # Convert levels values from mb to Pa.
        xarray_ds["level"] = xarray_ds["level"] * 100 # Convert mb to Pa
        xarray_ds = xarray_ds.squeeze(dim="batch")

        # Reverse lat
        xarray_ds = xarray_ds.reindex(lat = xarray_ds.lat[::-1])

        for time in xarray_ds.coords["time"]:

            # Select single lead time.
            ds_singletime = xarray_ds.sel(time=time)

            # Set output GRIB2 file.
            cycle = self.start_date.hour
            lead = int(time.dt.total_seconds()//3600)
            outfile = os.path.join(outdir, f"{self.case_name}.t{cycle:02d}z.pgrb2.0p25.f{lead:03d}")

            # Delete the old file.
            if os.path.isfile(outfile):
                os.remove(outfile)

            # Open GRIB2 file.
            grib2_out = grib2io.open(outfile, mode="w")
            print(f" Opening GRIB2 File: {outfile}")

            # Iterate over the variable name keys in JSON file.
            for var in sorted(xarray_ds.data_vars):

                # Get variable as DataArray.
                da = ds_singletime[var]

                # Iterate over level...
                if "level" in da.coords.keys():
                    for level in da.coords["level"]:
                        msg = self.create_grib2_message(var, da, lead, level=level)
                        msg.data = da.sel(level=level).values
                        msg.pack()
                        print(f"\t{msg}")
                        grib2_out.write(msg)
                else:
                    msg = self.create_grib2_message(var, da, lead)
                    msg.data = da.values
                    msg.pack()
                    print(f"\t{msg}")
                    grib2_out.write(msg)

            # Close GRIB2 file
            grib2_out.close()

            # Use wgrib2 to generate index files
            output_idx_file = f"{outfile}.idx"
            
            # Construct the wgrib2 command
            wgrib2_command = ['wgrib2', '-s', outfile]
            
            try:
                # Open the output file for writing
                with open(output_idx_file, "w") as f_out:
                    # Execute the wgrib2 command and redirect stdout to the output file
                    subprocess.run(wgrib2_command, stdout=f_out, check=True)
            
                print(f"Index file created successfully: {output_idx_file}")
            
            except subprocess.CalledProcessError as e:
                print(f"Error running wgrib2 command: {e}")

        ##Temporary save netCDF files for UPP
        #output_netcdf = os.path.join(outdir, f"{self.case_name}.t{cycle:02d}z.pgrb2.0p25.nc")
        #xarray_ds.to_netcdf(output_netcdf)

if __name__ == "__main__":
    
    table_file = "tables.json"
    
    start_date = pd.to_datetime("2025-07-30 06:00:00")
    ds = xr.open_dataset("forecasts_levels-13_steps-64.nc")
    g2prefix = "mlgec00"

    t0 = time()
    outdir = "./"
    os.makedirs(outdir, exist_ok=True)
    converter = Netcdf2Grib(start_date)
    converter.save_grib2(ds, g2prefix, outdir)

    print(f"It took {(time()-t0)/60} mins")
