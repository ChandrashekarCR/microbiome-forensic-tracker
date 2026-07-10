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

# Deploy 
echo "Deploying API..."
az containerapp create \
  --name microbiome-api \
  --resource-group "$RESOURCE_GROUP" \
  --environment "$ENVIRONMENT" \
  --yaml api.yaml

echo "Deploying Worker..."
az containerapp create \
  --name microbiome-worker \
  --resource-group "$RESOURCE_GROUP" \
  --environment "$ENVIRONMENT" \
  --yaml worker.yaml

# Done 
API_URL=$(az containerapp show --name microbiome-api --resource-group "$RESOURCE_GROUP" --query "properties.configuration.ingress.fqdn" -o tsv)
echo ""
echo "Deployment complete"
echo "API live at: https://${API_URL}/docs"