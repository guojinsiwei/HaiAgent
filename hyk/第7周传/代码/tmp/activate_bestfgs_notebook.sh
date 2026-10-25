# Source this file inside a Cube-Studio Notebook; no model calls or experiments start.
source /root/miniconda3/etc/profile.d/conda.sh
conda activate /mnt/lizh639/envs/bestfgs
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MPLBACKEND=Agg
cd /mnt/lizh639/BestFGS-compare-v3
