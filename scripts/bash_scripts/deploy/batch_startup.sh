#!/bin/bash
set -e
LOG=/tmp/startup.log
exec > >(tee -a $LOG) 2>&1

echo "[startup] Enabling user namespaces for Apptainer..."
echo 1 > /proc/sys/kernel/unprivileged_userns_clone
sysctl -w kernel.unprivileged_userns_clone=1

echo "[startup] Mounting Azure File Share..."
mkdir -p /mnt/data
mount -t cifs \
  //ednamicrobiomestorage.file.core.windows.net/microbiome-data \
  /mnt/data \
  -o vers=3.0,username=ednamicrobiomestorage,password=${AZURE_STORAGE_KEY},dir_mode=0777,file_mode=0777,serverino

echo "[startup] Verifying Apptainer works..."
apptainer --version

echo "[startup] Done. Mounted: $(ls /mnt/data)"