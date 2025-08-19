import os
import socket
import datetime
#from datetime import datetime, timedelta
import argparse
import pathlib
from time import time
import subprocess
import json
import tempfile

import numpy as np

def get_closest_cycle(now=None, cycles=None): 
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


def submit_job_wcoss2(member, param, model_id, curr_datetime, prev_datetime, packagedir):
    ymd=curr_datetime[:8]
    cyc=curr_datetime[8:]

    pbs_content = f"""#!/bin/bash
    #PBS -o {member}.out
    #PBS -e {member}.err
    #PBS -N mlgefs{member}
    #PBS -A GFS-DEV
    #PBS -q dev 
    #PBS -l place=vscatter,select=1:ncpus=80:mpiprocs=80:mem=500G
    #PBS -l place=excl
    #PBS -l walltime=02:00:00
    
    # load necessary modules
    module load intel/19.1.3.304 
    module load wgrib2 
    module use /apps/dev/lmodules/intel/19.1.3.304
    module load libjpeg/9c
    module load ve/eagle/1.0
    module list
    
    #curr_datetime={curr_datetime}
    #num_pressure_levels=13
    #forecast_length=64
    model_weights=/lfs/h2/emc/nems/noscrub/jun.wang/mlwp/aiml/gc_weights
    DATAROOT=/lfs/h2/emc/ptmp/$USER
    PACKAGEDIR=(packagedir} #/lfs/h2/emc/nems/noscrub/linlin.cui/Tests/eagle_ensemble

    cd {PACKAGEDIR}

    # get input data
    python3 gen_gefs_ics.py {prev_datetime} {curr_datetime} {member} -l 13 -s wcoss2 -o $DATAROOT/mlgefs.{ymd}/{cyc} -d $DATAROOT/mlgefs.{ymd}/{cyc}
    
    #get forecasts
    python3 run_graphcast_ens.py -i $DATAROOT/mlgefs.{ymd}/{cyc}/source-ge{member}_date-{curr_datetime}_res-0.25_levels-13_steps-2.nc -w $model_weights -m "{member}" -g "{g2prefix} -c {param} -l 64 -p 13 -o $DATAROOT/mlgefs.{ymd}/{cyc} -u no -k yes 
    """

    with tempfile.NamedTemporaryFile(mode="w+", suffix=".pbs", delete=False) as tmpfile:
        tmpfile.write(pbs_content)
        tmpfile.flush()

    # the GEFS ICs are available on WCOSS2, so step 1 and step 2 are combined.
    command1 = ['qsub', tmpfile.name]
    job_id1 = get_job_id(command1)

    #Step 2 - run TC_tracker
    tpl = pathlib.Path("jAIGFS_cyclone_track_00.ecf_tmpl").read_text()
    rendered = tpl.format(
        out=f'tracker_{member}.out',
        err=f'tracker_{member}.err',
        job_name=f'tc_{member}', 
        jobid=job_id1, 
        ymd=curr_datetime[:8],
        cyc=curr_datetime[8:],
        ensemble_member=member
    )
    jobcard = f"job{member}.pbs"
    pathlib.Path(jobcard).write_text(rendered)
    command2 = ['qsub', jobcard]
    job_id2 = get_job_id(command2)


if __name__ == '__main__':

    #Get current forecast cycle
    cycles = [0, 6, 12, 18]
    #now = datetime.datetime(2025, 8, 15, 19, 16)
    now = None
    curr_datetime = get_closest_cycle(now=now, cycles=cycles)
    prev_datetime = curr_datetime - datetime.timedelta(hours=6)
    print(f'curr_datetime: {curr_datetime}')
    print(f'prev_datetime: {prev_datetime}')

    #for MLGEFS
    #hostname = socket.gethostname()
    #if hostname.startswith('ufe'):
    #    param_path = '/scratch3/NCEPDEV/nems/Linlin.Cui/Tests/MLGEFSv1.0/oper/graphcast_gefs_params'
    #elif hostname.startswith('linlincui'):
    #    param_path = '/lustre2/Linlin.Cui/MLGEFSv1.0/weights'
    #else:
    #    raise NotImplementedError(f'{hostname} is not supported yet!')
    param_path = '/lfs/h2/emc/nems/noscrub/linlin.cui/Tests/eagle_ensemble/model_weights'

    with open('model_weights.json', 'r') as file:
        models = json.load(file)

    for key, values in models.items():
        if key == '0':
            member = f'c{int(key):02d}'
        else:
            member = f'p{int(key):02d}'

        g2prefix = "mlge"+{member}

        param = f'{param_path}/{values.get("params")}'
        submit_job_wcoss2(member, g2prefix, param, key, curr_datetime.strftime("%Y%m%d%H"), prev_datetime.strftime("%Y%m%d%H"))

    #for MLGFS
    #param_path='/lfs/h2/emc/nems/noscrub/jun.wang/mlwp/aiml/gc_weights'
    #param = f'{param_path}/{values.get("params")}'
    #case_name = "mlgfs"
    #g2prefix = "mlgfs"
    #submit_job_wcoss2(case_name, g2prefix, param, key, curr_datetime.strftime("%Y%m%d%H"), prev_datetime.strftime("%Y%m%d%H"))



