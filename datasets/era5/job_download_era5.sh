#!/bin/bash

#SBATCH -J era5_data
#SBATCH -o slurm/era5.%j.out
#SBATCH -e slurm/era5.%j.err
#SBATCH --account=nems
#SBATCH --partition=u1-service
#SBATCH --mem=64g
#SBATCH -t 24:00:00
#SBATCH --ntasks=4

source /scratch3/NCEPDEV/nems/Linlin.Cui/venvs/anemoi/bin/activate

python download_era5_gcs_1p00.py
#python download_era5_gcs_0p25.py

echo "dataset is complete"
