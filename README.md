# Global EAGLE ensemble
This project is part of Experimental AI Global and Limited-area Ensemble project (EAGLE), which is an ensemble GraphCast tuned on GDAS, ERA5 and HRES with GDAS as input. Thirty-one [model weights](https://noaa-nws-graphcastgfs-pds.s3.amazonaws.com/index.html#EAGLE_ensemble/model_weights/) were saved during training process. This repo contains scripts to run an ensemble-based cascaded version of the GraphCast weather model initialized with GEFSv12.   

## Table of Contents
- [Overview](#overview)
- [Prerequisites and Installation](#prerequisites-and-installation)
- [Usage](#usage)
- [Output](#output)
- [Contact](#contact)

## Overview

The National Centers for Environmental Prediction (NCEP) provides GEFS data that can be used for ensemble weather prediction and analysis. Currently, this dataset is not publicly avaiable. If you are interested in getting the data, please contact Jun Wang[Jun.Wang@noaa.gov](mailto:Jun.Wang@noaa.gov).

## Installation

Creating an environment from an environment.yml file:

```bash
conda env create -f environment.yml
```

To activate the env:
```bash
conda activate graphcast
```

If you would like to run on GPU, you'll need to update cuda-enabled jax:
```bash
pip install -U "jax[cuda12]"
```

## Usage
### Download model weights and statistics files:
```bash
aws s3 cp --recursive s3://noaa-nws-graphcastgfs-pds/EAGLE_ensemble/model_weights model_weights --no-sign-request
```
There are three subdirectories:  
`ens_weights/`: contains 31 model weights.
`params/`: contains original graphcast model weight from Google DeepMind, which is used for initializing model.
`stats/`: contains statistic files.

### Generate IC from an individual ensemble member:
```bash
python gen_gefs_ics.py prev_datetime curr_datetime "gefs_member" -l 13 -o /path/to/output -d /path/to/download -k no
```
where "gefs_member" is from the list of ["c00", "p01", "p02", ..., "p30"].

### Run the model for an individual ensemble member:
```bash
python run_graphcast_ens.py -i /path/to/inputfile -o /path/to/output -w /path/to/stats -m "gefs_member" -c /path/to/"model_id".pkl  -l forecast_length(steps) -p num_pressure_levels -u no -k yes
```
where "model_id" is from the list of [0, 1, 2, ..., 30].

Slurm jobs for 31 members can be submitted with `oper/submit_jobs.py`. Change the env path in `oper/gcjob_cloud_ens.sh` accordingly, then run the script:
```bash
python submit_jobs.py -w /path/to/ens_weights
```

## Output
The model is running 4 times a day at 00Z, 06Z, 12Z and 18Z. The model outputs are avaible on [AWS s3 bucket](https://noaa-nws-graphcastgfs-pds.s3.amazonaws.com/index.html#EAGLE_ensemble/).

## Contact

For questions or issues, please contact:\
    Linlin Cui [Linlin.Cui@noaa.gov](mailto:Linlin.Cui@noaa.gov)\
    Jun Wang [Jun.Wang@noaa.gov](mailto:Jun.Wang@noaa.gov)
