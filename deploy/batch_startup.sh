#!/bin/bash
# Runs on every Azure Batch VM before any Snakemake job starts
set -e
LOG=/tmp/startup.log
exec > >(tee -a $LOG) 2>&1

echo "[startup] Starting VM setup..."

# Install dependencies
apt-get update -qq
apt-get install -y cifs-utils wget fuse

# Install Apptainer (for running .sif containers)
wget -q https://github.com/apptainer/apptainer/releases/download/v1.3.4/apptainer_1.3.4_amd64.deb
dpkg -i apptainer_1.3.4_amd64.deb
rm apptainer_1.3.4_amd64.deb
echo "[startup] Apptainer: $(apptainer --version)"

# Mount Azure File Share at /mnt/data
# This gives VMs access to: uploads, results, logs, runtime, tools, databases
mkdir -p /mnt/data
mount -t cifs \
  //ednamicrobiomestorage.file.core.windows.net/microbiome-data \
  /mnt/data \
  -o vers=3.0,username=ednamicrobiomestorage,password=${AZURE_STORAGE_KEY},dir_mode=0777,file_mode=0777,serverino

echo "[startup] File share mounted: $(ls /mnt/data)"
echo "[startup] Done."