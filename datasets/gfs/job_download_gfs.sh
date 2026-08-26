#!/bin/bash

#SBATCH -J gfs-data-sf
#SBATCH -o slurm/getdata.sf.%j.out
#SBATCH -e slurm/getdata.sf.%j.err
#SBATCH --account=nems
#SBATCH --partition=u1-service
#SBATCH --mem=128g
#SBATCH -t 12:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=4
#SBATCH --cpus-per-task=1

unset SLURM_TRES_PER_TASK
source /scratch3/NCEPDEV/nems/Linlin.Cui/venvs/anemoi/bin/activate

srun ufs2arco gfs.0p25.instant.yaml --overwrite
#srun ufs2arco gfs.0p25.accum.yaml --overwrite
#srun ufs2arco gfs.0p25.sf.yaml --overwrite
#srun ufs2arco gfs.0p25.soil.yaml --overwrite
echo "dataset is complete"
