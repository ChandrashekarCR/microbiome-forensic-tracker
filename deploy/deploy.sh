#!/bin/bash

set -e

echo "Microbiome Forensic Tracker - Azure Deploy"

# Prerequisites 
# Before running, export these variables in your shell:
#   export PG_USER="malmo"
#   export PG_PASSWORD="YourPostgresPassword"
#   export REDIS_PASSWORD="YourRedisPassword"
#   export BATCH_KEY="YourBatchKey"
#   export BLOB_SAS_TOKEN="se=2026-...&sig=..."   # full SAS token WITHOUT leading '?'
#   export REDIS_IP="20.91.202.193"              # or your Redis VM IP
#   export POSTGRES_SERVER="microbiome-postgres"  # your server name

# Fixed names 
RESOURCE_GROUP="microbiome-rg"
ENVIRONMENT="microbiome-env"
REGISTRY="microbiomeacr.azurecr.io"
IMAGE="$REGISTRY/microbiome:latest"
STORAGE_ACCOUNT="ednamicrobiomestorage"
FILE_SHARE="appdata"

# Dynamic lookups
echo "Fetching Azure credentials..."

# ACR password
ACR_PASSWORD=$(az acr credential show \
  --name microbiomeacr \
  --query "passwords[0].value" \
  --output tsv)

# Storage account key
STORAGE_KEY=$(az storage account keys list \
  -g "$RESOURCE_GROUP" \
  -n "$STORAGE_ACCOUNT" \
  --query "[0].value" \
  -o tsv)

# PostgreSQL hostname (fully qualified domain name)
if [ -z "$POSTGRES_SERVER" ]; then
  echo "ERROR: POSTGRES_SERVER environment variable not set."
  echo "Please set it to your PostgreSQL server name (e.g., microdentify-postgres)."
  exit 1
fi
POSTGRES_HOST=$(az postgres flexible-server show \
  --resource-group "$RESOURCE_GROUP" \
  --name "$POSTGRES_SERVER" \
  --query "fullyQualifiedDomainName" \
  --output tsv)

if [ -z "$POSTGRES_HOST" ]; then
  echo "ERROR: Could not retrieve PostgreSQL host for server '$POSTGRES_SERVER'."
  exit 1
fi

# Subscription ID (used for logging, optional)
SUBSCRIPTION_ID=$(az account show --query "id" --output tsv)

echo "Subscription  : $SUBSCRIPTION_ID"
echo "PostgreSQL    : $POSTGRES_HOST"
echo "Storage key   : obtained"
echo "ACR password  : obtained"

# Register Azure File Share with environment 
echo "Registering File Share '$FILE_SHARE' as 'microbiome-data'..."
az containerapp env storage set \
  --name "$ENVIRONMENT" --resource-group "$RESOURCE_GROUP" \
  --storage-name microbiome-data \
  --azure-file-account-name "$STORAGE_ACCOUNT" \
  --azure-file-account-key "$STORAGE_KEY" \
  --azure-file-share-name "$FILE_SHARE" \
  --access-mode ReadWrite

# Common environment variables (API & Worker) 
# These point to the mounted File Share (/mnt/data)
COMMON_ENV_VARS=(
  PYTHONPATH=/app
  ENV_FILE=.env.azure
  PROJECT_ROOT=/app
  UPLOAD_DIR=/mnt/data/uploads
  RESULTS_DIR=/mnt/data/results
  LOGS_DIR=/mnt/data/logs
  RUNTIME_DIR=/mnt/data/runtime
  "BACKEND_DB_URL=postgresql://${PG_USER}:${PG_PASSWORD}@${POSTGRES_HOST}:5432/malmo_db"
  "CELERY_BROKER_URL=redis://:${REDIS_PASSWORD}@${REDIS_IP}:6379/0"
  "CELERY_RESULT_BACKEND=redis://:${REDIS_PASSWORD}@${REDIS_IP}:6379/0"
  SNAKEMAKE_PROFILE=profiles/azure_batch
  SNAKEMAKE_CONFIG=config/config_single_run.yaml
  SNAKEMAKE_BIN=snakemake
)

# Worker extra variables (for Batch submission) 
# These point to paths that will be mounted on Batch nodes (/mnt/blob)
WORKER_ENV_VARS=(
  "${COMMON_ENV_VARS[@]}"
  SNAKEMAKE_TOOLS=/mnt/blob/tools
  KRAKEN2_DB=/mnt/blob/databases/core_nt_Database
  HUMAN_GENOME_DIR=/mnt/blob/databases/hg38_ref
  HUMAN_GENOME_INDEX=hg38_index
  AZ_BATCH_ACCOUNT_URL=https://microbiomebatch.swedencentral.batch.azure.com
  "AZ_BATCH_ACCOUNT_KEY=${BATCH_KEY}"
  # Blob storage URL with SAS token for Snakemake staging (temporary transfers)
  "AZ_BLOB_ACCOUNT_URL=https://ednamicrobiomestorage.blob.core.windows.net/?${BLOB_SAS_TOKEN}"
  # Staging prefix – NEVER point to uploads or results; use a dedicated staging path
  AZ_BLOB_PREFIX=az://staging/snakemake/
  "APPTAINER_BINDS=--bind /mnt/blob:/mnt/blob --bind /mnt/data:/mnt/data"
)

# Deploy API (mounts only File Share) 
echo "Deploying API container..."
az containerapp create \
  --name microbiome-api \
  --resource-group "$RESOURCE_GROUP" \
  --environment "$ENVIRONMENT" \
  --image "$IMAGE" \
  --registry-server "$REGISTRY" \
  --registry-username microbiomeacr \
  --registry-password "$ACR_PASSWORD" \
  --target-port 8000 \
  --ingress external \
  --min-replicas 1 --max-replicas 2 \
  --cpu 0.5 --memory 1.0Gi \
  --mount-path /mnt/data \
  --storage-type azurefile \
  --storage-account "$STORAGE_ACCOUNT" \
  --storage-account-key "$STORAGE_KEY" \
  --storage-share-name "$FILE_SHARE" \
  --env-vars "${COMMON_ENV_VARS[@]}"

# Deploy Worker (mounts same File Share)
echo "Deploying Worker container..."
az containerapp create \
  --name microbiome-worker \
  --resource-group "$RESOURCE_GROUP" \
  --environment "$ENVIRONMENT" \
  --image "$IMAGE" \
  --registry-server "$REGISTRY" \
  --registry-username microbiomeacr \
  --registry-password "$ACR_PASSWORD" \
  --min-replicas 1 --max-replicas 1 \
  --cpu 1.0 --memory 2.0Gi \
  --mount-path /mnt/data \
  --storage-type azurefile \
  --storage-account "$STORAGE_ACCOUNT" \
  --storage-account-key "$STORAGE_KEY" \
  --storage-share-name "$FILE_SHARE" \
  --env-vars "${WORKER_ENV_VARS[@]}" \
  --command "celery" \
  --args "-A" "src.backend.celery_app:celery_app" "worker" "--loglevel=info" "--concurrency=2"

# Done 
API_URL=$(az containerapp show --name microbiome-api --resource-group "$RESOURCE_GROUP" --query "properties.configuration.ingress.fqdn" -o tsv)
echo ""
echo "Deployment complete"
echo "API live at: https://${API_URL}/docs"