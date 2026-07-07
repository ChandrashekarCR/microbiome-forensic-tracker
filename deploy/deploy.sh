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
FILE_SHARE="microbiome-data"

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
cat > /tmp/api.yaml <<EOF
properties:
  configuration:
    ingress:
      external: true
      targetPort: 8000
      allowInsecure: false
    registries:
      - server: $REGISTRY
        username: microbiomeacr
        passwordSecretRef: acr-password
    secrets:
      - name: acr-password
        value: "$ACR_PASSWORD"
  template:
    containers:
      - image: $IMAGE
        name: microbiome-api
        resources:
          cpu: 0.5
          memory: 1.0Gi
        env:
          - name: PYTHONPATH
            value: "/app"
          - name: ENV_FILE
            value: ".env.azure"
          - name: PROJECT_ROOT
            value: "/app"
          - name: UPLOAD_DIR
            value: "/mnt/data/uploads"
          - name: RESULTS_DIR
            value: "/mnt/data/results"
          - name: LOGS_DIR
            value: "/mnt/data/logs"
          - name: RUNTIME_DIR
            value: "/mnt/data/runtime"
          - name: BACKEND_DB_URL
            value: "postgresql://${PG_USER}:${PG_PASSWORD}@${POSTGRES_HOST}:5432/malmo_db"
          - name: CELERY_BROKER_URL
            value: "redis://:${REDIS_PASSWORD}@${REDIS_IP}:6379/0"
          - name: CELERY_RESULT_BACKEND
            value: "redis://:${REDIS_PASSWORD}@${REDIS_IP}:6379/0"
          - name: SNAKEMAKE_PROFILE
            value: "profiles/azure_batch"
          - name: SNAKEMAKE_CONFIG
            value: "config/config_single_run.yaml"
          - name: SNAKEMAKE_BIN
            value: "snakemake"
        volumeMounts:
          - volumeName: microbiome-data
            mountPath: /mnt/data
    scale:
      minReplicas: 1
      maxReplicas: 2
    volumes:
      - name: microbiome-data
        storageName: microbiome-data
        storageType: AzureFile
EOF

# Generate Worker YAML (with all required env vars) 
cat > /tmp/worker.yaml <<EOF
properties:
  configuration:
    registries:
      - server: $REGISTRY
        username: microbiomeacr
        passwordSecretRef: acr-password
    secrets:
      - name: acr-password
        value: "$ACR_PASSWORD"
  template:
    containers:
      - image: $IMAGE
        name: microbiome-worker
        command:
          - celery
          - -A
          - src.backend.celery_app:celery_app
          - worker
          - --loglevel=info
          - --concurrency=2
        resources:
          cpu: 1.0
          memory: 2.0Gi
        env:
          - name: PYTHONPATH
            value: "/app"
          - name: ENV_FILE
            value: ".env.azure"
          - name: PROJECT_ROOT
            value: "/app"
          - name: UPLOAD_DIR
            value: "/mnt/data/uploads"
          - name: RESULTS_DIR
            value: "/mnt/data/results"
          - name: LOGS_DIR
            value: "/mnt/data/logs"
          - name: RUNTIME_DIR
            value: "/mnt/data/runtime"
          - name: BACKEND_DB_URL
            value: "postgresql://${PG_USER}:${PG_PASSWORD}@${POSTGRES_HOST}:5432/malmo_db"
          - name: CELERY_BROKER_URL
            value: "redis://:${REDIS_PASSWORD}@${REDIS_IP}:6379/0"
          - name: CELERY_RESULT_BACKEND
            value: "redis://:${REDIS_PASSWORD}@${REDIS_IP}:6379/0"
          - name: SNAKEMAKE_PROFILE
            value: "profiles/azure_batch"
          - name: SNAKEMAKE_CONFIG
            value: "config/config_single_run.yaml"
          - name: SNAKEMAKE_BIN
            value: "snakemake"

          # Required for Azure Batch executor plugin 
          - name: SNAKEMAKE_AZURE_BATCH_ACCOUNT_URL
            value: "https://microbiomebatch.swedencentral.batch.azure.com"
          - name: SNAKEMAKE_AZURE_BATCH_RESOURCE_GROUP_NAME
            value: "${RESOURCE_GROUP}"
          - name: SNAKEMAKE_AZURE_BATCH_SUBSCRIPTION_ID
            value: "${SUBSCRIPTION_ID}"

          # Additional Batch credentials 
          - name: AZ_BATCH_ACCOUNT_NAME
            value: "microbiomebatch"
          - name: AZ_BATCH_ACCOUNT_KEY
            value: "${BATCH_KEY}"
          - name: AZ_BATCH_ACCOUNT_URL
            value: "https://microbiomebatch.swedencentral.batch.azure.com"

          # Storage for staging (optional, but needed for Batch nodes) 
          - name: AZURE_STORAGE_ACCOUNT
            value: "${STORAGE_ACCOUNT}"
          - name: AZ_BLOB_SAS_TOKEN
            value: "${BLOB_SAS_TOKEN}"
          - name: AZ_BLOB_ACCOUNT_URL
            value: "https://${STORAGE_ACCOUNT}.blob.core.windows.net/?${BLOB_SAS_TOKEN}"

          # Paths for Batch nodes (mounted separately) 
          - name: SNAKEMAKE_TOOLS
            value: "/mnt/blob/tools"
          - name: KRAKEN2_DB
            value: "/mnt/blob/databases/core_nt_Database"
          - name: HUMAN_GENOME_DIR
            value: "/mnt/blob/databases/hg38_ref"
          - name: HUMAN_GENOME_INDEX
            value: "hg38_index"
          - name: APPTAINER_BINDS
            value: "--bind /mnt/blob:/mnt/blob --bind /mnt/data:/mnt/data"

          # For apptainer on Batch nodes 
          - name: APPTAINER_BINDS
            value: "--bind /mnt/blob:/mnt/blob --bind /mnt/data:/mnt/data"
        volumeMounts:
          - volumeName: microbiome-data
            mountPath: /mnt/data
    scale:
      minReplicas: 1
      maxReplicas: 1
    volumes:
      - name: microbiome-data
        storageName: microbiome-data
        storageType: AzureFile
EOF

# Deploy 
echo "Deploying API..."
az containerapp create \
  --name microbiome-api \
  --resource-group "$RESOURCE_GROUP" \
  --environment "$ENVIRONMENT" \
  --yaml /tmp/api.yaml

echo "Deploying Worker..."
az containerapp create \
  --name microbiome-worker \
  --resource-group "$RESOURCE_GROUP" \
  --environment "$ENVIRONMENT" \
  --yaml /tmp/worker.yaml

# Done 
API_URL=$(az containerapp show --name microbiome-api --resource-group "$RESOURCE_GROUP" --query "properties.configuration.ingress.fqdn" -o tsv)
echo ""
echo "Deployment complete"
echo "API live at: https://${API_URL}/docs"