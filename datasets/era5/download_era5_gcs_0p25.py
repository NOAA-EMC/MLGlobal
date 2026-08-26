from time import time
import os
from datetime import datetime, timedelta

import xarray as xr

"""Download ERA5 data from GCS and save to zarr file.
   Each zarr file covers {year_start} to {year_end}.

"""

store = "gs://gcp-public-data-arco-era5/ar/full_37-1h-0p25deg-chunk-1.zarr-v3"

#2d varaibles (22 + 2 for precip)
vars_2d = [
    "10m_u_component_of_wind",
    "10m_v_component_of_wind",
    "2m_temperature",
    "mean_sea_level_pressure",
    "100m_u_component_of_wind",
    "100m_v_component_of_wind",
    "surface_pressure",
    "skin_temperature",
    "2m_dewpoint_temperature",
    "total_cloud_cover",
    "high_cloud_cover",
    "medium_cloud_cover",
    "low_cloud_cover",
    "total_column_water_vapour",
    "volumetric_soil_water_layer_1",
    "volumetric_soil_water_layer_2",
    "soil_temperature_level_1",
    "soil_temperature_level_2",
]

vars_accum_6h = [
    'total_precipitation', 
    'convective_precipitation', 
    'runoff', 
    'snowfall', 
    'surface_solar_radiation_downwards', 
    'surface_thermal_radiation_downwards'
]

# 3d variables (6)
vars_3d = [
    "temperature",
    "geopotential",
    "u_component_of_wind",
    "v_component_of_wind",
    "specific_humidity",
    "vertical_velocity",
]

#forcing variables (4)
vars_forcing = [
    "land_sea_mask",
    "geopotential_at_surface",
    "slope_of_sub_gridscale_orography",
    "standard_deviation_of_orography"
]

levels = [50, 100, 150, 200, 250, 300, 400, 500, 600, 700, 850, 925, 1000]

def main():

    ds = xr.open_zarr(
        store,
        storage_options={"token": "anon"},
        chunks={},
    )

    subset_vars = vars_forcing +vars_2d + vars_3d

    first = True
    dt_6h = timedelta(hours=6)
    dt_1h = timedelta(hours=1)

    #year_start = 2001
    #year_end = 2010
    year_start = 2011
    year_end = 2025
    out = f"./era5_subset_new/era5_0p25_6h_{year_start}_{year_end}.zarr"

    for year in range(year_start, year_end + 1):

        print(f"Processing {year}")
        date_start = datetime(year, 1, 1)
        date_end = datetime(year+1, 1, 1, 0) - dt_6h  # Last time step is 23:00:00 on Dec 31
        
        #out = f"./era5_subset/era5_0p25_6h_{year}.zarr"

        dsy = ds[subset_vars].sel(
            time=slice(f"{year}-01-01", f"{year}-12-31T23:00:00")
        ).isel(time=slice(None, None, 6))  # Select every 6th time step for 6-hourly data

        # add 6-hourly precip by summing the 1-hourly precip over 6 time steps.
        for var in vars_accum_6h:
            ds_precip = ds[var].sel(time=slice(date_start - 5*dt_1h, date_end))
            assert(ds_precip.time.size % 6 == 0)
            ds_precip_grouped = ds_precip.groupby_bins('time', ds_precip.time.size//6)
            ds_precip_sum = ds_precip_grouped.sum()
            
            ds_precip_sum = ds_precip_sum.rename({f"time_bins": "time"})
            ds_precip_sum['time'] = ds_precip['time'][5::6]
            dsy[f'{var}_6hr'] = ds_precip_sum

        # Subset pressure levels.
        # This only applies to variables that have the level dimension.
        dsy = dsy.sel(level=levels)
        
        dsy = dsy.rename({
            "surface_pressure": "sp",
            "2m_temperature": "2t",
            "10m_u_component_of_wind": "10u",
            "10m_v_component_of_wind": "10v",
            "mean_sea_level_pressure": "msl",
            "total_precipitation_6hr": "tp",        
            "convective_precipitation_6hr": "cp",
            "100m_u_component_of_wind": "100u",
            "100m_v_component_of_wind": "100v",
            "skin_temperature": "skt",
            "2m_dewpoint_temperature": "2d",
            "total_cloud_cover": "tcc",
            "high_cloud_cover": "hcc",
            "medium_cloud_cover": "mcc",
            "low_cloud_cover": "lcc",
            "total_column_water_vapour": "tcwv",
            "volumetric_soil_water_layer_1": "swvl1",
            "volumetric_soil_water_layer_2": "swvl2",
            "soil_temperature_level_1": "stl1",
            "soil_temperature_level_2": "stl2",
            "runoff_6hr": "ro",
            "snowfall_6hr": "sf",
            "surface_solar_radiation_downwards_6hr": "ssrd",
            "surface_thermal_radiation_downwards_6hr": "strd",
            "geopotential": "z",
            "specific_humidity": "q",
            "temperature": "t",
            "u_component_of_wind": "u",
            "v_component_of_wind": "v",
            "vertical_velocity": "w",
            "land_sea_mask": "lsm",
            "geopotential_at_surface": "orog",
            "slope_of_sub_gridscale_orography": "slor",
            "standard_deviation_of_orography": "sdor"
        })

        # Rechunk the output for local analysis.
        dsy = dsy.chunk({
            "time": 1,        
            "level": -1,
            "latitude": -1,
            "longitude": -1,
        })

        if not os.path.exists(out):
            dsy.to_zarr(out, mode='w', consolidated=True)
        else:
            dsy.to_zarr(out, mode='a', append_dim="time", consolidated=True)
        
if __name__ == "__main__":
    t0 = time()

    main()

    print(f"Finished in {time() - t0:.2f} seconds")
