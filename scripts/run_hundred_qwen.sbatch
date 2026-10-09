#!/bin/bash
#SBATCH --job-name=hangtian-author100
#SBATCH --partition=compute
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:nvidia_a100_80gb_pcie:1
#SBATCH --mem=110G
#SBATCH --time=02:00:00
#SBATCH --output=/home/xjshang/hangtian_material_pipeline/runs/autonomous_tasks_100_001/slurm-%j.log
#SBATCH --error=/home/xjshang/hangtian_material_pipeline/runs/autonomous_tasks_100_001/slurm-%j.log
set -euo pipefail
cd /home/xjshang/hangtian_material_pipeline
unset DEEPSEEK_API_KEY OPENAI_API_KEY ANTHROPIC_API_KEY
export PYTHONUNBUFFERED=1 PYTHONPATH=src
exec /home/xjshang/anaconda3/bin/python scripts/generate_hundred_qwen.py --out /home/xjshang/hangtian_material_pipeline/runs/autonomous_tasks_100_001 "$@"
