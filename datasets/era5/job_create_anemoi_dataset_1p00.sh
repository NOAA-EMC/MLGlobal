#!/bin/bash --login

#SBATCH --nodes=1
#SBATCH --account=nems
#SBATCH --partition=u1-compute
##SBATCH --qos=long
#SBATCH --ntasks-per-node=1
##SBATCH --mem=500G
#SBATCH --cpus-per-task=16
###SBATCH --exclusive
#SBATCH --time=4:00:00
#SBATCH --job-name=create
#SBATCH --output=slurm/create.%j.out
#SBATCH --error=slurm/create.%j.err

source /scratch3/NCEPDEV/nems/Linlin.Cui/venvs/anemoi/bin/activate

anemoi-datasets create \
  --overwrite \
  --processes 8 \
  recipe_era5_local_1p00.yaml era5-1p00-13pl-2020-2025-6h-v3.zarr 

