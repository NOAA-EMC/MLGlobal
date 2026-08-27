#!/bin/bash --login

#SBATCH --nodes=1
#SBATCH --account=nems
#SBATCH --partition=u1-compute
#SBATCH --ntasks-per-node=1
###SBATCH --cpus-per-task=16
#SBATCH --time=8:00:00
#SBATCH --job-name=add-stats
#SBATCH --output=slurm/add-stats.%j.out
#SBATCH --error=slurm/add-stats.%j.err

source /scratch3/NCEPDEV/nems/Linlin.Cui/venvs/anemoi/bin/activate

# Add statistics for 6h increments
anemoi-datasets init-additions era5-1p00-13pl-1979-2025-6h-v3.zarr --delta 6h
anemoi-datasets load-additions era5-1p00-13pl-1979-2025-6h-v3.zarr --parts 1/2 --delta 6h
anemoi-datasets load-additions era5-1p00-13pl-1979-2025-6h-v3.zarr --parts 2/2 --delta 6h
anemoi-datasets finalise-additions era5-1p00-13pl-1979-2025-6h-v3.zarr --delta 6h
anemoi-datasets cleanup era5-1p00-13pl-1979-2025-6h-v3.zarr
