import os
import datetime
import argparse
import pathlib
from time import time
import subprocess
import json
import tempfile

import numpy as np

def get_closest_cycle(now=None, cycles=[0, 6, 12, 18]): 

    if now is None:
        #now = datetime.datetime.now(datetime.UTC)
        now = datetime.datetime.utcnow()

    current_hour = now.hour

    recent_cycle = max([c for c in cycles if c <= current_hour], default=18)
    if current_hour < min(cycles):
        # If current time is before 00z, subtract a day
        cycle_time = datetime.datetime(now.year, now.month, now.day, recent_cycle) - datetime.timedelta(days=1)
    else:
        cycle_time = datetime.datetime(now.year, now.month, now.day, recent_cycle)

    #return cycle_time - datetime.timedelta(hours=6)
    return cycle_time

def get_job_id(command):
    result = subprocess.run(
        command, 
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    if result.returncode != 0:
        print("Job submission failed:", result.stderr)
        exit(1)

    job_id = result.stdout.strip().split()[-1]

    return job_id

def submit_job_wcoss2(member, param, curr_datetime, prev_datetime, package):
    ymd=curr_datetime[:8]
    cyc=curr_datetime[8:]

    pbs_content = f"""#!/bin/bash
    #PBS -o {member}.out
    #PBS -e {member}.err
    #PBS -N fcst_{member}
    #PBS -A GFS-DEV
    #PBS -q dev 
    #PBS -l place=vscatter,select=1:ncpus=80:mpiprocs=80:mem=500G
    #PBS -l place=excl
    #PBS -l walltime=02:00:00
    
    # load necessary modules
    module load PrgEnv-intel/8.3.3 intel/19.1.3.304 python/3.12
    module load libjpeg-turbo/2.1.0
    module use /lfs/h2/emc/eib/noscrub/rahul.mahajan/eibWork/eagleWork/pyvenv/modulefiles
    module load wgrib2
    module load mlgfs/1.0
    module list
    
    model_weights=/lfs/h2/emc/nems/noscrub/jun.wang/mlwp/aiml/gc_weights
    DATAROOT=/lfs/h2/emc/ptmp/$USER
    PACKAGEROOT={package}

    cd $PACKAGEROOT/oper/wcoss2

    # get input data
    python3 gen_mlgefs_ics.py {prev_datetime} {curr_datetime} {member} -l 13 -s wcoss2 -o $DATAROOT/mlgefs.{ymd}/{cyc} -d $DATAROOT/mlgefs.{ymd}/{cyc}
    
    #get forecasts
    python3 run_graphcast.py -i $DATAROOT/mlgefs.{ymd}/{cyc}/ml{member}_t{cyc}z_ic.nc -w $model_weights -n ml"{member}" -c {param} -l 64 -p 13 -m grib2io -o $DATAROOT/mlgefs.{ymd}/{cyc} -u no -k yes 
    """

    with tempfile.NamedTemporaryFile(mode="w+", suffix=".pbs", delete=False) as tmpfile:
        tmpfile.write(pbs_content)
        tmpfile.flush()

    # the GEFS ICs are available on WCOSS2, so step 1 and step 2 are combined.
    command1 = ['qsub', tmpfile.name]
    job_id1 = get_job_id(command1)

    #Step 2 - run TC_tracker
    tpl = pathlib.Path("jMLGEFS_cyclone_track_00.ecf_tmpl").read_text()

    #tracker verification code only accepts 4 letters, remove "ge" from the member -> member[2:]
    rendered = tpl.format(
        out=f'tracker_{member}.out',
        err=f'tracker_{member}.err',
        job_name=f'tc_{member}', 
        jobid=job_id1, 
        ymd=curr_datetime[:8],
        cyc=curr_datetime[8:],
        ensemble_member=f"{member[2:]}"
    )
    jobcard = f"job{member}.pbs"
    pathlib.Path(jobcard).write_text(rendered)
    command2 = ['qsub', jobcard]
    job_id2 = get_job_id(command2)

    return job_id1

def compute_avgspr(ids, curr_datetime):
    PDY = curr_datetime[:8]
    cyc = curr_datetime[8:]
    dep_str = ":".join(ids)
    tpl = pathlib.Path("jMLGEFS_ens_debias.ecf_tmpl").read_text()
    rendered = tpl.format(
        jobid = dep_str, 
        PDY = PDY, 
        cyc = cyc,
    )
    jobcard = f"job.pbs"
    pathlib.Path(jobcard).write_text(rendered)
    command = ['qsub', jobcard]
    job_id = get_job_id(command)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Submit jobs on WCOSS2")
    parser.add_argument("-w", "--workdir", help="The directory where this script locates")

    args = parser.parse_args()

    param_path = '/lfs/h2/emc/nems/noscrub/linlin.cui/Tests/eagle_ensemble/model_weights'

    with open('../model_weights.json', 'r') as file:
        models = json.load(file)

    #Get current forecast cycle
    #If run a hindcast, specify a datetime here, otherwise use now = None
    #now = datetime.datetime(2025, 8, 21, 6)
    now = None
    curr_datetime = get_closest_cycle(now=now)
    prev_datetime = curr_datetime - datetime.timedelta(hours=6)
    print(f'curr_datetime: {curr_datetime}')
    print(f'prev_datetime: {prev_datetime}')

    job_ids = []
    for key, values in models.items():
        if key == '0':
            member = f'gec{int(key):02d}'
        else:
            member = f'gep{int(key):02d}'

        param = f'{param_path}/{values.get("params")}'
        job_id = submit_job_wcoss2(
            member, 
            param, 
            curr_datetime.strftime("%Y%m%d%H"), 
            prev_datetime.strftime("%Y%m%d%H"),
            args.workdir
        )
        job_ids.append(job_id)

    # compute ensemble mean and spread
    compute_avgspr(job_ids, curr_datetime.strftime("%Y%m%d%H"))
