#!/bin/bash
set -e
LOG=/tmp/container_entrypoint.log
exec > >(tee -a $LOG) 2>&1

echo "[entrypoint] Starting container entrypoint..."

# Source .env.azure if present (export variables)
if [ -f /app/.env.azure ]; then
  set -a
  . /app/.env.azure
  set +a
  echo "[entrypoint] Sourced /app/.env.azure"
fi

# Reuse an existing Azure CLI session if one is already available
if az account show >/dev/null 2>&1; then
  echo "[entrypoint] Azure CLI session already available."
elif [ "${AZURE_USE_MANAGED_IDENTITY:-0}" = "1" ] || [ "${AZURE_AUTH_MODE:-}" = "managed-identity" ]; then
  echo "[entrypoint] Attempting az login with managed identity..."
  az login --identity || true
  echo "[entrypoint] Managed identity login finished (status ignored)."
elif [ -n "${AZURE_CLIENT_ID:-}" ] && [ -n "${AZURE_CLIENT_SECRET:-}" ] && [ -n "${AZURE_TENANT_ID:-}" ]; then
  echo "[entrypoint] Attempting az login with service principal..."
  az login --service-principal --username "$AZURE_CLIENT_ID" --password "$AZURE_CLIENT_SECRET" --tenant "$AZURE_TENANT_ID" || true
  echo "[entrypoint] Service principal login finished (status ignored)."
else
  echo "[entrypoint] AZURE service principal creds not provided; skipping az login."
fi

# Note about apptainer availability
if command -v apptainer >/dev/null 2>&1; then
  echo "[entrypoint] apptainer available: $(apptainer --version 2>/dev/null || echo 'unknown')"
else
  echo "[entrypoint] apptainer not present inside container. On Azure Batch VMs apptainer is installed by the VM start task."
fi

echo "[entrypoint] Ready. Executing command: ${@:-bash}"

if [ $# -eq 0 ]; then
  exec bash
else
  exec "$@"
fi
