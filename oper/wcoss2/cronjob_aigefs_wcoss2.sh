#!/bin/bash --login

module load PrgEnv-intel intel python
module load wgrib2
module use /lfs/h2/emc/eib/noscrub/rahul.mahajan/eibWork/eagleWork/pyvenv/modulefiles
module load aigfs/1.0

HOMEDIR=${1:-/lfs/h2/emc/nems/noscrub/$USER/MLGlobal}

JOBDIR=${HOMEDIR}/oper/wcoss2
cd $JOBDIR

#link required scripts to run dir
ln -sf ../gen_aigefs_ics.py .
ln -sf ../run_graphcast.py .
ln -sf ../utils .

# delete previous files
rm *.out *.err *.pbs

python submit_aigefs_job_wcoss2.py -w $HOMEDIR
