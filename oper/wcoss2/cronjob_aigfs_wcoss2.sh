#!/bin/bash --login

module load PrgEnv-intel intel python
module load wgrib2
module use /lfs/h2/emc/eib/noscrub/rahul.mahajan/eibWork/eagleWork/pyvenv/modulefiles
module load aigfs/1.0

HOMEDIR=${1:-/lfs/h2/emc/nems/noscrub/$USER/MLGlobal}

JOBDIR=${HOMEDIR}/oper/wcoss2
cd $JOBDIR

#link required scripts to run dir
ln -sf ../gen_aigfs_ics.py .
ln -sf ../run_graphcast.py .
ln -sf ../utils .

# Get the UTC hour and calculate the time in the format yyyymmddhh
current_hour=$(date -u +%H)
current_hour=$((10#$current_hour))

if (( $current_hour >= 0 && $current_hour < 6 )); then
    datetime=$(date -u -d 'today 00:00')
elif (( $current_hour >= 6 && $current_hour < 12 )); then
    datetime=$(date -u -d 'today 06:00')
elif (( $current_hour >= 12 && $current_hour < 18 )); then
    datetime=$(date -u -d 'today 12:00')
else
    datetime=$(date -u -d 'today 18:00')
fi

# Calculate time 6 hours before
#curr_datetime=$(date -u -d "$time" +'%Y%m%d%H')
curr_datetime=$( date -d "$datetime 6 hour ago" "+%Y%m%d%H" )
prev_datetime=$( date -d "$datetime 12 hour ago" "+%Y%m%d%H" )

PDY=$(echo $curr_datetime | cut -c1-8)
cyc=$(echo $curr_datetime | cut -c9-10)

echo "Current state: $curr_datetime"
echo "6 hours earlier state: $prev_datetime"

echo "Job 1 is running"
./jaigfs_prep.ecf $curr_datetime $prev_datetime $HOMEDIR
sleep 60  # Simulating some work
echo "Job 1 completed"

echo "Job 2 is running"
job2_id=$(qsub -v PDY=$PDY,cyc=$cyc jaigfs_forecast.ecf | awk '{print $1}')

#sed "s/jobid/${job2_id}/g" jAIGFS_cyclone_track_00.ecf_tmpl > jAIGFS_cyclone_track_00.ecf
#echo "Job 3: running TC tracker"
#qsub -v PDY=$PDY,cyc=$cyc,pert="" jAIGFS_cyclone_track_00.ecf
