#!/bin/bash --login

##SBATCH --nodes=1
#SBATCH --account=gpu-ai4wp
#SBATCH --partition=u1-h100
#SBATCH --gres=gpu:h100:1
###SBATCH --ntasks-per-node=1
##SBATCH --mem=500G
#SBATCH --cpus-per-task=16
##SBATCH --exclusive
#SBATCH --time=32:00:00
#SBATCH --job-name=create
#SBATCH --output=slurm/create.%j.out
#SBATCH --error=slurm/create.%j.err

anemoi-datasets create \
  --overwrite \
  --processes 8 \
  recipe_era5_local_0p25.yaml era5-0p25-13pl-1979-2025-6h-v3.zarr 
