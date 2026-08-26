#!/bin/bash --login

#SBATCH --nodes=1
#SBATCH --account=nems #gpu-ai4wp
#SBATCH --partition=u1-compute
##SBATCH --qos=long
#SBATCH --ntasks-per-node=1
##SBATCH --mem=500G
#SBATCH --cpus-per-task=16
##SBATCH --exclusive
#SBATCH --time=2:00:00
#SBATCH --job-name=create
#SBATCH --output=slurm/create.%j.out
#SBATCH --error=slurm/create.%j.err

#  --processes $SLURM_CPUS_PER_TASK \
anemoi-datasets create \
  --overwrite \
  --processes 8 \
  recipe_gfs_local_1p.yaml anemoi-gfs-1p00-13pl-20210401-20260331-6h-v4.zarr
