from time import time

import dask
import dask.distributed
import dask.config
import xarray as xr
import numpy as np

def fill_missing(ds: xr.Dataset):
    target_dims = {"time", "latitude", "longitude"}
    vars_to_fill = []

    for var_name, var_data in ds.variables.items():
        # Check if the variable's dimensions exactly match your 2D target set
        if set(var_data.dims) == target_dims:
            # Check if there are any NaNs in this variable
            if var_data.isnull().any():
                vars_to_fill.append(var_name)
    
    print(f"Variables to fill: {vars_to_fill}")
    
    # Fill NaNs with a fixed value (e.g., -999.0) only in those variables
    fixed_value = 0
    for var in vars_to_fill:
        ds[var] = ds[var].fillna(fixed_value)

    return ds

def prepare_dataset(ds: xr.Dataset):
    ds_clean = ds.squeeze('fhr')
    ds_clean = ds_clean.swap_dims({'t0': 'valid_time'})
    ds_clean = ds_clean.rename({'valid_time': 'time'})
    ds_clean = ds_clean.drop_vars({'fhr', 't0', 'lead_time'})

    #if np.diff(ds_clean.lat)[0] < 0:
    #    ds_clean = ds_clean.reindex(lat=ds_clean.lat[::-1])

    return ds_clean

out_path = "gfs-1p00-13pl-20210401-20260331-6h-combined-v4.zarr"

ds1 = xr.open_zarr("gfs-1p00-13pl-20210401-20260331-6h-instant.zarr")
ds1_clean = prepare_dataset(ds1)

#Get 6-h accumulated sf
ds_sf = xr.open_zarr("gfs-1p00-13pl-20210401-20260331-6h-snowfall.zarr")
sf_diff = ds_sf.sf.sel(fhr=6) - ds_sf.sf.sel(fhr=0) 
breakpoint()
ds1_clean['sf'][:] = sf_diff.values

ds2 = xr.open_zarr("gfs-1p00-13pl-20210401-20260331-6h-accum.zarr")
ds2_clean = prepare_dataset(ds2)

ds3 = xr.open_zarr("gfs-1p00-13pl-20210401-20260331-6h-soil.zarr")
ds3_clean = prepare_dataset(ds3)

ds2_clean = ds2_clean.sel(time=ds1_clean.time)
ds = xr.merge([ds1_clean, ds2_clean])

print('Merged ds1 and ds2!')

#add soil water
ds['swvl1'] = prepare_dataset(ds3.isel(depthBelowLandLayer=0)).swvl1
ds['swvl2'] = prepare_dataset(ds3.isel(depthBelowLandLayer=1)).swvl1

#add soil temp 
ds['stl1'] = prepare_dataset(ds3.isel(depthBelowLandLayer=0)).stl1
ds['stl2'] = prepare_dataset(ds3.isel(depthBelowLandLayer=1)).stl1
print('added soil components to ds!')

ds = ds.drop('depthBelowLandLayer')
#add slor and sdor from era5
ds4 = xr.open_dataset("../era5/era5_subset_1deg/era5_1deg_6h_2021.nc")

chunks = {'time': 1, 'latitude': 181, 'longitude': 360}
ds['slor'] = ds4.slor.isel(time=0).expand_dims({'time': ds.time}).chunk(chunks)
ds['sdor'] = ds4.sdor.isel(time=0).expand_dims({'time': ds.time}).chunk(chunks)


#ds = fill_missing(ds)

if 'units' in ds.time.attrs:
    del ds.time.attrs['units']
if 'calendar' in ds.time.attrs:
    del ds.time.attrs['calendar']

ds.time.encoding = {}

# Create a dask client
dask.config.set({
    'distributed.worker.memory.target': False,
    'distributed.worker.memory.spill': False,
})

Client = dask.distributed.Client(processes=False, threads_per_worker=20)

t0 = time()
#delayed = ds.to_zarr(out_path, mode='w', encoding=encoding, compute=False)
delayed = ds.to_zarr(out_path, mode='w', compute=False)

delayed = dask.optimize(delayed)

try:
    Client.compute(delayed, sync=True)
except Exception as e:
    import sys
    print(f"Error combining training dataset, exception {e=}", file=sys.stderr)
    sys.exit(1)

t1 = time()
print(f'Finished, time is {(t1-t0)/60} mins')
