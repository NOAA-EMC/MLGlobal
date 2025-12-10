import os
import socket
import datetime
#from datetime import datetime, timedelta
import argparse
import pathlib
from time import time
import subprocess
import json

import numpy as np

def get_closest_cycle(now=None, cycles=None): 
    if now is None:
        now = datetime.datetime.now(datetime.UTC)
        #now = datetime.utcnow()

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


def submit_slurm_run(member, param, model_id, curr_datetime, prev_datetime):

    #Step 1 - generate input file
    command1 = [
        'sbatch', '--nodes=1', '--ntasks=1', '--mem=10g', '--account=nems', '--partition=u1-service', \
        '--time=30:00', f'--job-name=getdata_{member}', f'--output=slurm/getdata_{member}.out', f'--error=slurm/getdata_{member}.err', \
        f'--export=gefs_member={member},config_path={param},model_id={model_id},curr_datetime={curr_datetime},prev_datetime={prev_datetime}', \
        'mlgefs_prepdata_ursa.sh'
    ]
    job_id1 = get_job_id(command1)

    #Step 2 - run graphcast
    command2 = ['sbatch', f'--dependency=afterok:{job_id1}', '--nodes=1', '--account=nems', '--partition=u1-h100', \
        '--qos=gpuwf', '--gres=gpu:h100:2', '--exclude=u22g[09-10]', '--time=30:00', f'--job-name=run_{member}', f'--output=slurm/gcgfs_{member}.out', \
        f'--error=slurm/gcgfs_{member}.err', f'--export=gefs_member={member},config_path={param},model_id={model_id},curr_datetime={curr_datetime}', \
        'mlgefs_runfcst_ursa.sh']
    job_id2 = get_job_id(command2)

    #Step 3 - run TC_tracker
    command3 = ['sbatch', f'--dependency=afterok:{job_id2}', '--nodes=1', '--ntasks=1', '--account=nems', \
        '--partition=u1-compute', '--time=30:00', '--mem=90g', f'--job-name=tctracker_{member}', f'--output=slurm/tctracker_{member}.out', \
        f'--error=slurm/tctracker_{member}.err', f'--export=gefs_member={member},PDY={curr_datetime[:8]},cyc={curr_datetime[8:]}', \
        'jAIGFS_cyclone_track_00.ecf_ursa']
    job_id3 = get_job_id(command3)

    #Step 4 - upload data to s3 bucket
    command4 = ['sbatch', f'--dependency=afterok:{job_id3}', '--nodes=1', '--ntasks=1', '--account=nems', \
        '--partition=u1-service', '--time=30:00', f'--job-name=datadissm_{member}', f'--output=slurm/datadissm_{member}.out', \
        f'--error=slurm/datadissm_{member}.err', f'--export=gefs_member={member},model_id={model_id},curr_datetime={curr_datetime}', \
        'mlgefs_datadissm_ursa.sh']
    job_id4 = get_job_id(command4)

if __name__ == '__main__':

    hostname = socket.gethostname()
    if hostname.startswith('ufe'):
        param_path = '/scratch3/NCEPDEV/nems/Linlin.Cui/Tests/MLGEFSv1.0/oper/graphcast_gefs_params'
    elif hostname.startswith('linlincui'):
        param_path = '/lustre2/Linlin.Cui/MLGEFSv1.0/weights'
    else:
        raise NotImplementedError(f'{hostname} is not supported yet!')

    with open('model_weights_ursa.json', 'r') as file:
        models = json.load(file)

    #Get current forecast cycle
    cycles = [0, 6, 12, 18]
    #now = datetime.datetime(2025, 7, 16, 4, 16)
    now = None
    curr_datetime = get_closest_cycle(now=now, cycles=cycles)
    prev_datetime = curr_datetime - datetime.timedelta(hours=6)
    print(f'curr_datetime: {curr_datetime}')
    print(f'prev_datetime: {prev_datetime}')

    for key, values in models.items():
        if key == '0':
            member = f'c{int(key):02d}'
        else:
            member = f'p{int(key):02d}'

        param = f'{param_path}/{values.get("params")}'
        submit_slurm_run(member, param, key, curr_datetime.strftime("%Y%m%d%H"), prev_datetime.strftime("%Y%m%d%H"))
