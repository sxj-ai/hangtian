#!/bin/bash
#SBATCH --job-name=hangtian-pi-flash15
#SBATCH --partition=compute
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=12G
#SBATCH --time=10:00:00
#SBATCH --output=/home/xjshang/hangtian_material_pipeline/runs/pi_deepseek_flash_budget80_001/slurm-%j.log
#SBATCH --error=/home/xjshang/hangtian_material_pipeline/runs/pi_deepseek_flash_budget80_001/slurm-%j.log
set -euo pipefail
cd /home/xjshang/hangtian_material_pipeline
unset DEEPSEEK_API_KEY OPENAI_API_KEY ANTHROPIC_API_KEY NODE_OPTIONS
export PYTHONUNBUFFERED=1
exec /home/xjshang/anaconda3/bin/python scripts/run_deepseek_pi_job.py
