#!/bin/bash
#SBATCH --job-name=hangtian-report-probe
#SBATCH --partition=compute
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:nvidia_a100_80gb_pcie:1
#SBATCH --mem=110G
#SBATCH --time=01:00:00
#SBATCH --output=/home/xjshang/hangtian_material_pipeline/runs/pi_qwen35_reporting_001/slurm-%j.log
#SBATCH --error=/home/xjshang/hangtian_material_pipeline/runs/pi_qwen35_reporting_001/slurm-%j.log
set -euo pipefail
cd /home/xjshang/hangtian_material_pipeline
unset DEEPSEEK_API_KEY OPENAI_API_KEY ANTHROPIC_API_KEY
export PYTHONUNBUFFERED=1
exec /home/xjshang/anaconda3/bin/python scripts/run_qwen_pi_job.py --reporting-baseline "$1"
