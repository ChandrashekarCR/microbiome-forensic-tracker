# Azure Cloud Migration Guide
## Microbiome Forensic Tracker — Complete Step-by-Step

> **Read this before starting:**
> - Work through steps in order. Do not skip ahead.
> - After each step, run the verify command before moving on.
> - Every step has a delete command — use it if something goes wrong.
> - Your free tier covers most of this. Cost warnings are marked 💰.
> - **Never commit `.env.azure` to Git.**

---

## Prerequisites — Do This First

### Install Azure CLI on your laptop

```bash
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
az --version
# Should show: azure-cli 2.x.x
```

### Login to Azure

```bash
az login
# Opens browser — sign in with your student account

# Confirm correct subscription
az account show --output table
# Note the "Id" field — this is your subscription ID
```

### Save your subscription ID

```bash
SUBSCRIPTION_ID=$(az account show --query "id" --output tsv)
echo "Subscription: $SUBSCRIPTION_ID"
```

---

## Step 1 — Resource Group

**What it is:** A folder that holds all your Azure resources. Free. Deleting it deletes everything inside.

### Create

```bash
az group create \
  --name microbiome-rg \
  --location swedencentral
```

### Verify

```bash
az group show \
  --name microbiome-rg \
  --query "{name:name, location:location, state:properties.provisioningState}" \
  --output table
# Expected: name=microbiome-rg, state=Succeeded

# Show all available resource groups
az group list -o table
```

### Delete (if needed)

```bash
# WARNING: This deletes EVERYTHING inside it
az group delete --name microbiome-rg --yes --no-wait
```

### Register the subscription (optional)

```bash
# Perfrom a simple check if your scubscription is registered for using azure services
az provider show \
    --namespace Microsoft.Storage \
    --query registrationState \
    -o table

az provider show --namespace Microsoft.ContainerRegistry -o table

# If it says -:

Result
----------
Registered

# Then you are good to go. Else,

az provider register --namespace Microsoft.Storage

# Register for the azure continer serivice as well
az provider register --namespace Microsoft.ContainerRegistry

# Register for the azure postgres service as well
az provider register --namesapce Microsoft.DBPforPostgreSQL

# Register for the azure container hosting
az provier register --namespace Microsoft.OperationalInsights

# Then re-run the first command az provider show...
# It should show as registreed 

```
You may need to register for that service if needed and faced with the same issue.

---

# Step 2 — Azure Storage

Azure Storage is used for **two different purposes** in this project.

| Storage Type           | Purpose                                                                                                                    |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| **Azure Blob Storage** | Read-only assets such as bioinformatics tools, Kraken2 databases, Bracken databases, hg38 reference genome, taxonomy files |
| **Azure File Share**   | Shared runtime filesystem used by Snakemake. Stores uploads, intermediate files, logs and final results                    |

The overall architecture looks like this:

```text
Azure Storage
│
├── Blob Storage
│      ├── databases/
│      │      ├── kraken2/
│      │      ├── bracken/
│      │      └── hg38/
│      │
│      └── tools/
│             ├── kraken2.sif
│             ├── bracken.sif
│             └── fastqc.sif
│
└── Azure File Share
       ├── uploads/
       ├── runtime/
       ├── logs/
       └── results/
```

---

## 1. Create Storage Account

```bash
az storage account create \
  --name ednamicrobiomestorage \
  --resource-group microbiome-rg \
  --location swedencentral \
  --sku Standard_LRS \
  --kind StorageV2
```

### What is Standard_LRS?
- **Standard** performance tier.
- **LRS (Locally Redundant Storage)** replicates data three times within a single datacenter.

### What is StorageV2?
- General‑purpose v2 storage account supporting:
  - Blob Storage
  - Azure File Share
  - Queues
  - Tables

---

## 2. List Resources

```bash
# All resources in the resource group
az resource list --resource-group microbiome-rg --output table

# Storage accounts only
az storage account list --resource-group microbiome-rg --output table
```

---

## 3. Obtain Credentials

```bash
# Connection string
STORAGE_CONN=$(az storage account show-connection-string \
  --name ednamicrobiomestorage \
  --resource-group microbiome-rg \
  --output tsv)

# Storage account key
STORAGE_KEY=$(az storage account keys list \
  --resource-group microbiome-rg \
  --account-name ednamicrobiomestorage \
  --query "[0].value" -o tsv)

echo "STORAGE_CONN=$STORAGE_CONN"
echo "STORAGE_KEY=$STORAGE_KEY"
```

---

## 4. Create Blob Storage Containers

Blob Storage holds large, mostly read‑only assets.

### Create `databases` container

```bash
az storage container create \
  --name databases \
  --connection-string "$STORAGE_CONN"
```

### Create `tools` container

```bash
az storage container create \
  --name tools \
  --connection-string "$STORAGE_CONN"
```

### Create `startup` container

```bash
az storage container create \
  --name startup \
  --connection-string "$STORAGE_CONN"
```

---

## 5. Generate a SAS Token

A SAS token is useful when copying files from systems that cannot run Azure CLI (e.g., LUNARC).

```bash
az storage account generate-sas \
  --account-name ednamicrobiomestorage \
  --account-key "$STORAGE_KEY" \
  --expiry 2026-12-31 \
  --permissions acdlrw \
  --services bf \
  --resource-types sco \
  --https-only \
  --output tsv
```

---

## 6. Create Azure File Share

Azure File Share provides a persistent, mountable filesystem.

```bash
az storage share create \
  --name microbiome-data \
  --account-name ednamicrobiomestorage \
  --account-key "$STORAGE_KEY"
```

---

## 7. Create Runtime Directories

Inside the file share, create directories for the different data types.

```bash
# uploads – user FASTQ files
az storage directory create \
  --share-name microbiome-data \
  --name uploads \
  --account-name ednamicrobiomestorage \
  --account-key "$STORAGE_KEY"

# runtime – sample sheets, temporary files
az storage directory create \
  --share-name microbiome-data \
  --name runtime \
  --account-name ednamicrobiomestorage \
  --account-key "$STORAGE_KEY"

# logs – pipeline logs
az storage directory create \
  --share-name microbiome-data \
  --name logs \
  --account-name ednamicrobiomestorage \
  --account-key "$STORAGE_KEY"

# results – pipeline outputs
az storage directory create \
  --share-name microbiome-data \
  --name results \
  --account-name ednamicrobiomestorage \
  --account-key "$STORAGE_KEY"
```

---

## 8. Verify

```bash
# List blob containers
az storage container list \
  --connection-string "$STORAGE_CONN" \
  --output table

# View files inside your container

az storage blob list \
  --account-name ednamicrobiomestorage \
  --container-name tools \
  --account-key "$STORAGE_KEY" \
  --output table

# List file shares
az storage share list \
  --connection-string "$STORAGE_CONN" \
  --output table

# List directories inside the file share
az storage directory list \
  --share-name microbiome-data \
  --account-name ednamicrobiomestorage \
  --connection-string "$STORAGE_CONN" \
  --output table

# Inspect files inside a firectory
az storage file list \
    --share-name microbiome-data \
    --path uploads \
    --connection-string "$STORAGE_CONN" \
    --output table
```

---

## 9. Upload Bioinformatics Tools

**What it is:** Copy your `.sif` files from LUNARC to Blob Storage. One-time operation.

### Without azure on LUNARC.
Quite often you will not having sudo access on LUNARC and need to transfer files to cloud storage blobs.
This can be done as follows -:

I do this in dump folder in my preoject directory but this can be done anywhere as long as the paths are correct.

```bash
wget -q https://aka.ms/downloadazcopy-v10-linux
tar -xzf downloadazcopy-v10-linux
export PATH="$HOME/binp51/dump/azure_services/azcopy_linux_amd64_10.32.4:$PATH"

# Test it
echo $PATH # You should see your path for azcopy
azcopy --version
# azcopy version 10.32.4

```

Next on local you need to set this up so that you can transfer files without having to login
```bash
az storage account keys list -g microbiome-rg -n ednamicrobiomestorage --query "[0].value" -o tsv
```
Then we need to generate a SAS token which we can use to transfer files without having to login.
SAS tokens are like a temporary key you can use to transfer things by bypassing the login. Alwys set a short time for these SAS tokens and create when needed.

```bash
az storage container generate-sas --name tools --account-name ednamicrobiomestorage --account-key <paste it here> --permissions rwdl --expiry 2026-07-07 --https-only --output tsv
```
Then head bach to LUNRAC
```bash
# Bioinformatics tools upload
azcopy copy "/home/chandru/binp51/bin/*" "https://ednamicrobiomestorage.blob.core.windows.net/tools?<SAS_TOKEN>" --recursive --put-md5

# Copy to azure file share
azcopy copy "/home/chandru/binp51/bin/*"   "https://ednamicrobiomestorage.file.core.windows.net/microbiome-data/tools?<SAS_TOKEN>"   --recursive --put-md5

# Human genome index database upload
azcopy copy "/lunarc/nobackup/projects/snic2019-34-3/Daria/CAMP/ref_Human_hg38/ref_Human_hg38/hg38_ref/*" \
  "https://ednamicrobiomestorage.blob.core.windows.net/databases/hg38_ref?<SAS_TOKEN>" \
  --recursive --put-md5

# Copy human genome index databae upload to azure file
azcopy copy "/lunarc/nobackup/projects/snic2019-34-3/Daria/CAMP/ref_Human_hg38/ref_Human_hg38/hg38_ref/*" "https://ednamicrobiomestorage.file.core.windows.net/microbiome-data/databases/hg38_ref?<SAS_TOKEN>"   --recursive --put-md5

# Copy the entire karken2 database
azcopy copy "/lunarc/nobackup/projects/snic2019-34-3/Daria/core_nt_Database/*" \
  "https://ednamicrobiomestorage.blob.core.windows.net/databases/core_nt_Database?<SAS_TOKEN>" \
  --recursive --put-md5

azcopy copy "/lunarc/nobackup/projects/snic2019-34-3/Daria/core_nt_Database/**" "https://ednamicrobiomestorage.file.core.windows.net/microbiome-data/databases/core_nt_Database?<SAS_TOKEN>"   --recursive --put-md5

```
---

## 11. Mount Azure File Share (for local testing or Batch nodes)

### Install CIFS utilities

```bash
sudo apt update && sudo apt install -y cifs-utils
```

### Create mount point

```bash
sudo mkdir -p /mnt/microbiome-data
```

### Mount the share

```bash
sudo mount -t cifs \
  //ednamicrobiomestorage.file.core.windows.net/microbiome-data \
  /mnt/microbiome-data \
  -o vers=3.0,username=ednamicrobiomestorage,password=$STORAGE_KEY,dir_mode=0777,file_mode=0777,serverino
```



### Verify

```bash
ls /mnt/microbiome-data
```

You should see the directories:
```text
logs  results  runtime  uploads
```

### Unmount

```bash
sudo umount /mnt/microbiome-data
```

---

## 13. Delete Resources

### Delete a blob container

```bash
az storage container delete \
  --name tools \
  --connection-string "$STORAGE_CONN"
```

### Delete a File Share directory

```bash
az storage directory delete \
  --share-name microbiome-data \
  --name runtime \
  --account-name ednamicrobiomestorage \
  --account-key "$STORAGE_KEY"
```

### Delete blobs matching a pattern

```bash
az storage blob delete-batch \
  --source databases \
  --connection-string "$STORAGE_CONN" \
  --pattern "hg38/*"
```

### Delete the entire storage account

```bash
az storage account delete \
  --name ednamicrobiomestorage \
  --resource-group microbiome-rg \
  --yes
```

---

## How the Batch Node Sees Storage

```text
Azure Blob Storage (Read‑only)
    databases/   tools/
          │          │
          ▼          ▼
     /mnt/blob/ (mounted via BlobFuse2)

Azure File Share (Read/Write)
    uploads/  runtime/  logs/  results/
          │
          ▼
/mnt/microbiome-data/ (mounted via CIFS/SMB)

Docker Container (Snakemake)
    ├── /data -> /mnt/microbiome-data
    └── /db   -> /mnt/blob
```

This separation keeps your large, read‑only reference data in Blob Storage while your dynamic, write‑intensive runtime data lives in the File Share – exactly matching your architecture.

## Upload the startp script and get URL

```bash
STORAGE_KEY=$(az storage account keys list \
  -g microbiome-rg \
  -n ednamicrobiomestorage \
  --query "[0].value" -o tsv)

# Upload startup script
az storage blob upload \
  --account-name ednamicrobiomestorage \
  --account-key "$STORAGE_KEY" \
  --container-name startup \
  --name batch_startup.sh \
  --file deploy/batch_startup.sh

# Generate SAS URL (Batch VMs download this to run it)
EXPIRY=$(date -u -d "+90 days" '+%Y-%m-%dT%H:%MZ')
STARTUP_URL=$(az storage blob generate-sas \
  --account-name ednamicrobiomestorage \
  --account-key "$STORAGE_KEY" \
  --container-name startup \
  --name batch_startup.sh \
  --permissions r \
  --expiry "$EXPIRY" \
  --https-only \
  --full-uri \
  --output tsv)

echo "BATCH_NODE_START_TASK_URL=$STARTUP_URL"
```

---

## Step 4 — Container Registry

**What it is:** Stores your Docker image. FREE (1 standard registry in student offer).

### Create

```bash
az acr create \
  --resource-group microbiome-rg \
  --name microbiomeacr \
  --sku Standard \
  --admin-enabled true
```

### Get credentials — SAVE THESE

```bash
ACR_SERVER=$(az acr show \
  --name microbiomeacr \
  --query "loginServer" \
  --output tsv)

ACR_USERNAME=$(az acr credential show \
  --name microbiomeacr \
  --query "username" \
  --output tsv)

ACR_PASSWORD=$(az acr credential show \
  --name microbiomeacr \
  --query "passwords[0].value" \
  --output tsv)

echo "ACR_SERVER=$ACR_SERVER"
echo "ACR_USERNAME=$ACR_USERNAME"
echo "ACR_PASSWORD=$ACR_PASSWORD"
```

### Push your Docker image — run on your laptop

```bash
# Login to registry
az acr login --name microbiomeacr

# If the above step fails this is because you need docker to be able to talk to the container service and currently you as a user have not given that permission
# Do the following and then try the above command
sudo usermode -aG docker <your user name>
sudo su -
sudo su <your user name>

# To log out of your container registry
# docker logout microbiomeacr.azurecr.io

# Tag your image
docker tag microbiome:latest microbiomeacr.azurecr.io/microbiome:latest

# Push
docker push microbiomeacr.azurecr.io/microbiome:latest
```

### Verify

```bash
# List all the repositores
az acr repository list --name microbiomeacr -o table

# List all the tags in the repository
az acr repository show-tags \
  --name microbiomeacr \
  --repository microbiome \
  --output table
# Expected: latest
```

### Delete image (if needed)

```bash
# Delete a specific tag
az acr repository delete \
  --name microbiomeacr \
  --image microbiome:latest \
  --yes

# Delete a repository
az acr repository delete --name microbiomeacr --repository microbiome --yes

# Delete the whole registry
az acr delete \
  --name microbiomeacr \
  --resource-group microbiome-rg \
  --yes
```

---

## Step 5 — PostgreSQL Database

**What it is:** Managed Postgres. FREE (750 hrs/month B1MS = runs all month for free).

### Create

```bash
az postgres flexible-server create \
  --resource-group microbiome-rg \
  --name microbiome-postgres \
  --location swedencentral \
  --admin-user <username> \
  --admin-password "<password>" \
  --sku-name Standard_B1ms \ # Defines compute Burstable VM with 1vCPU and 2GB RAM
  --tier Burstable \ # cheaper aimer for low traffic workloads
  --storage-size 32 \
  --version 15 \
  --yes

# Takes 3-5 minutes. Wait for it.
```

### List all PostgreSQL servers in your resource group
```bash
az postgres flexible-server list --resource-group microbiome-rg --query "[].{Name:name, State:state, Location:location}" --output table
```

### Create your database

```bash
az postgres flexible-server db create \
  --resource-group microbiome-rg \
  --server-name microbiome-postgres \
  --name malmo_db
```

### Allow connections from Azure services

Practical takeaway

You are not “creating a database table” here. You are opening the network gate so something can connect to PostgreSQL. After the rule exists, your FastAPI app, local machine, or Azure service can reach the database on port 5432 if the credentials are also correct.

Think of the firewall rule as saying:

  - “Allow connections from this IP range.”
  - If you set both start and end IP to 0.0.0.0, Azure interprets that as allowing access from Azure services broadly.

```bash
az postgres flexible-server firewall-rule create \
  --resource-group microbiome-rg \
  --server-name microbiome-postgres \
  --name AllowAzureServices \
  --start-ip-address 0.0.0.0 \
  --end-ip-address 0.0.0.0
```

### Get hostname 

```bash
POSTGRES_HOST=$(az postgres flexible-server show \
  --resource-group microbiome-rg \
  --name microbiome-postgres \
  --query "fullyQualifiedDomainName" \
  --output tsv)

echo "POSTGRES_HOST=$POSTGRES_HOST"
# Looks like: microbiome-postgres.postgres.database.azure.com
```

```bash
# List all resources in your resource group
az resource list --resource-group microbiome-rg --output table

# Or list just PostgreSQL servers
az postgres flexible-server list --resource-group microbiome-rg --output table

# Get details of your specific server
az postgres flexible-server show --resource-group microbiome-rg --name microbiome-postgres
```

### Verify connection

```bash

az postgres flexible-server show \
  --resource-group microbiome-rg \
  --name microbiome-postgres \
  --query state \
  -o tsv

# Install psql locally if needed: sudo apt install postgresql-client
psql "host=$POSTGRES_HOST port=5432 dbname=malmo_db user=<username> password=<password> sslmode=require"
# Should open a postgres prompt. Type \q to exit.
```

### Stop (to save credits when not in use)

```bash
az postgres flexible-server stop \
  --resource-group microbiome-rg \
  --name microbiome-postgres

# Start again when needed
az postgres flexible-server start \
  --resource-group microbiome-rg \
  --name microbiome-postgres
```

### Delete (if needed)

```bash
az postgres flexible-server delete \
  --resource-group microbiome-rg \
  --name microbiome-postgres \
  --yes
```

---

## Step 6 — Redis (FREE using the free Linux VM)

**What it is:** Message broker for Celery. Instead of paying $15/month for managed Redis, we run it on the free B2pts Linux VM.

### Create the VM

```bash
az vm create \
  --resource-group microbiome-rg \
  --name microbiome-redis-vm \
  --image Ubuntu2204 \
  --size Standard_B2ats_v2 \
  --admin-username azureuser \
  --generate-ssh-keys \
  --public-ip-sku Standard

# Get the public IP — SAVE THIS
REDIS_VM_IP=$(az vm show \
  --resource-group microbiome-rg \
  --name microbiome-redis-vm \
  --show-details \
  --query "publicIps" \
  --output tsv)

echo "REDIS_VM_IP=$REDIS_VM_IP"
```

### Install Redis on the VM

```bash
ssh azureuser@$REDIS_VM_IP

# Once inside the VM:
sudo apt-get update
sudo apt-get install -y redis-server

# Configure Redis to accept connections from Azure services
sudo sed -i 's/bind 127.0.0.1/bind 0.0.0.0/' /etc/redis/redis.conf
sudo sed -i 's/# requirepass foobared/requirepass <password>/' /etc/redis/redis.conf

# Start and enable
sudo systemctl restart redis-server
sudo systemctl enable redis-server

# Verify
redis-cli -a <password> ping
# Expected: PONG

exit
```

### Open Redis port in Azure firewall

```bash
az vm open-port \
  --resource-group microbiome-rg \
  --name microbiome-redis-vm \
  --port 6379 \
  --priority 100
```

### Verify from your laptop

```bash
redis-cli -h $REDIS_VM_IP -p 6379 -a <password> ping
# Expected: PONG
```

### Stop VM (to save credits when not running pipeline)

```bash
# Stop (deallocate = no charges)
az vm deallocate \
  --resource-group microbiome-rg \
  --name microbiome-redis-vm

# Start again
az vm start \
  --resource-group microbiome-rg \
  --name microbiome-redis-vm
```

### Delete (if needed)

```bash
az vm delete \
  --resource-group microbiome-rg \
  --name microbiome-redis-vm \
  --yes
```

---

## Step 7 — Azure Batch Account

**What it is:** Runs your Snakemake pipeline on demand. Account is FREE. You pay only when a VM is running (~$0.10–4/hour, then $0 when done).

### Create batch account

```bash
az batch account create \
  --name microbiomebatch \
  --resource-group microbiome-rg \
  --location swedencentral \
  --storage-account ednamicrobiomestorage
```

### Get credentials — SAVE THESE

```bash
BATCH_URL=$(az batch account show \
  --name microbiomebatch \
  --resource-group microbiome-rg \
  --query "accountEndpoint" \
  --output tsv)

BATCH_KEY=$(az batch account keys list \
  --name microbiomebatch \
  --resource-group microbiome-rg \
  --query "primary" \
  --output tsv)

echo "BATCH_ACCOUNT_NAME=microbiomebatch"
echo "BATCH_ACCOUNT_URL=https://$BATCH_URL"
echo "BATCH_ACCOUNT_KEY=$BATCH_KEY"
```

### Verify

```bash
az batch account show \
  --name microbiomebatch \
  --resource-group microbiome-rg \
  --query "{name:name, state:provisioningState}" \
  --output table
# Expected: state=Succeeded
```

### Delete (if needed)

```bash
az batch account delete \
  --name microbiomebatch \
  --resource-group microbiome-rg \
  --yes
```

---

## Step 8 — Write `.env.azure`

**What it is:** Environment file for Azure. Lives in your repo root. Never committed to Git.

Fill in all the values you saved in the steps above:

```bash
# Azure cloud environment
# NEVER commit this file to Git
 
PROJECT_ROOT=/app
 
 
# Azure File Share mounted at /mnt/data 
# Nothing stored in the container — all goes to Azure storage
UPLOAD_DIR=/mnt/data/uploads
RESULTS_DIR=/mnt/data/results
LOGS_DIR=/mnt/data/logs
RUNTIME_DIR=/mnt/data/runtime
 
 
# PostgreSQL
BACKEND_DB_URL="postgresql://<USER_NAME>:<POSTGRES_PASSWORD>@microbiome-postgres.postgres.database.azure.com:5432/malmo_db"
 
# Redis — on your free VM
CELERY_BROKER_URL="redis://:<REDIS_PASSWORD>@<REDIS_IP>/0"
CELERY_RESULT_BACKEND="redis://:<REDIS_PASSWORD>@<REDIS_IP>/0"
 
# Pickle file for machine learning
# Need to update this
MODEL_PATH=/app/src/ml/mlruns/1/models/m-150112cb0dfd4175b98a23716a7f042b/artifacts/model.pkl
 
# Snakemake
SNAKEMAKE_PROFILE=profiles/azure_batch
SNAKEMAKE_CONFIG=config/config_single_run.yaml
SNAKEMAKE_BIN=snakemake
SNAKEMAKE_TOOLS=/mnt/data/tools
SNAKEMAKE_STORAGE_PREFIX=az://results/snakemake/
 
# Reference databases — on Blob Storage
KRAKEN2_DB=/mnt/data/databases/core_nt_Database
HUMAN_GENOME_DIR=/mnt/data/databases/hg38_ref
HUMAN_GENOME_INDEX=hg38_index
 
 
# Azure batch configurations
# These are the credentials Snakemake needs to submit jobs to Azure Batch
AZ_BATCH_ACCOUNT_URL="https://microbiomebatch.swedencentral.batch.azure.com"
AZ_BATCH_RESOURCE_GROUP_NAME="microbiome-rg"
AZ_BATCH_SUBSCRIPTION_ID=""
AZ_BLOB_PREFIX="uploads"
 
AZ_BATCH_ACCOUNT_NAME="microbiomebatch"
AZ_BATCH_ACCOUNT_KEY=""
 
# Azure Blob - Snakemake uses this to stage data to batch vms
AZURE_STORAGE_ACCOUNT="ednamicrobiomestorage"
AZ_BLOB_SAS_TOKEN=""
AZ_BLOB_ACCOUNT_URL="https://ednamicrobiomestorage.blob.core.windows.net/?<SAS_TOKEN>"


# Apptainer bind mounts on Batch VMs
APPTAINER_BINDS="--bind /mnt/blob:/mnt/blob --bind /mnt/data:/mnt/data"

AZURE_CLIENT_ID=""
AZURE_CLIENT_SECRET=""
AZURE_TENANT_ID=""

# Optional auth mode for the container entrypoint:
#   AZURE_AUTH_MODE=managed-identity
#   AZURE_USE_MANAGED_IDENTITY=1
# If neither is set, the entrypoint falls back to the service principal above.

# Azure Storage key
BATCH_NODE_START_TASK_URL="https://ednamicrobiomestorage.blob.core.windows.net/startup/batch_startup.sh?<SAS_TOKEN>"
AZURE_STORAGE_KEY="<Azure storage key>"

# Apptainer configurations
APPTAINER_NO_USERNS=1

```

### Add to .gitignore

```bash
echo ".env.azure" >> .gitignore
echo ".env.lunarc" >> .gitignore
echo ".env.local" >> .gitignore
```

---

## Step 10 — Deploy API to Azure Container Apps

**What it is:** Runs your FastAPI container publicly on the internet. Scales to zero when idle.

### Install extension

```bash
az extension add --name containerapp --upgrade
```

### Create Container Apps environment

```bash
# Create the container app environment
az containerapp env create \
  --name microbiome-env \
  --resource-group microbiome-rg \
  --location swedencentral


# To check if it has been created
az containerapp env show \
  --name microbiome-env \
  --resource-group microbiome-rg \
  --output table

# Register the file share with the container app environment
az containerapp env storage set --name microbiome-env --resource-group microbiome-rg --storage-name microbiome-data --azure-file-account-name ednamicrobiomestorage --azure-file-account-key "$STORAGE_KEY" --azure-file-share-name microbiome-data --access-mode ReadWrite

# Check if it is attached
az containerapp env storage show \
  --name microbiome-env \
  --resource-group microbiome-rg \
  --storage-name microbiome-data \
  -o table

```

### Deploy FastAPI

```bash
# This ensures that your yaml file has the correct env varibales
envsubst < scripts/bash_scripts/deploy/api.yaml > /tmp/api_final.yaml

az containerapp create \
  --name microbiome-api \
  --resource-group "$RESOURCE_GROUP" \
  --environment "$ENVIRONMENT" \
  --yaml /tmp/api_final.yaml
```

### Deploy Celery worker

```bash
envsubst < scripts/bash_scripts/deploy/worker.yaml > /tmp/worker_final.yaml

az containerapp create \
  --name microbiome-worker \
  --resource-group "$RESOURCE_GROUP" \
  --environment "$ENVIRONMENT" \
  --yaml /tmp/worker_final.yaml
```

### Get your live API URL

```bash
API_URL=$(az containerapp show \
  --name microbiome-api \
  --resource-group microbiome-rg \
  --query "properties.configuration.ingress.fqdn" \
  --output tsv)

echo "Your API is live at: https://$API_URL/docs"
```

### Verify

Open `https://<your-url>/docs` in your browser. You should see the Swagger UI.

### Update when you push new code

```bash
az containerapp update \
  --name microbiome-api \
  --resource-group microbiome-rg \
  --image microbiomeacr.azurecr.io/microbiome:latest

az containerapp update \
  --name microbiome-worker \
  --resource-group microbiome-rg \
  --image microbiomeacr.azurecr.io/microbiome:latest

# For verificaiton
az containerapp env show --name microbiome-env --resource-group microbiome-rg -o table
az containerapp list --resource-group microbiome-rg -o table
az resource list --resource-group microbiome-rg -o table

```

### Delete (if needed)

```bash
az containerapp delete \
  --name microbiome-api \
  --resource-group microbiome-rg \
  --yes

az containerapp delete \
  --name microbiome-worker \
  --resource-group microbiome-rg \
  --yes
```

---

## Step 11 — CI/CD with GitHub Actions

**What it is:** Every time you push to main branch, GitHub automatically builds and deploys your new code.

### Create the workflow file

```bash
mkdir -p .github/workflows
```

```yaml
# .github/workflows/deploy.yml
name: Build and Deploy to Azure

on:
  push:
    branches: [main]

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Login to Azure
        uses: azure/login@v1
        with:
          creds: ${{ secrets.AZURE_CREDENTIALS }}

      - name: Login to Container Registry
        uses: azure/docker-login@v1
        with:
          login-server: microbiomeacr.azurecr.io
          username: ${{ secrets.ACR_USERNAME }}
          password: ${{ secrets.ACR_PASSWORD }}

      - name: Build and push Docker image
        run: |
          docker build -t microbiomeacr.azurecr.io/microbiome:latest .
          docker push microbiomeacr.azurecr.io/microbiome:latest

      - name: Deploy API
        run: |
          az containerapp update \
            --name microbiome-api \
            --resource-group microbiome-rg \
            --image microbiomeacr.azurecr.io/microbiome:latest

      - name: Deploy Worker
        run: |
          az containerapp update \
            --name microbiome-worker \
            --resource-group microbiome-rg \
            --image microbiomeacr.azurecr.io/microbiome:latest
```

### Add secrets to GitHub

Go to: `GitHub repo → Settings → Secrets and variables → Actions → New repository secret`

Add these three secrets:

**Secret 1: `AZURE_CREDENTIALS`**
```bash
# Run this command and copy the entire JSON output
az ad sp create-for-rbac \
  --name "microbiome-github-actions" \
  --role contributor \
  --scopes /subscriptions/$SUBSCRIPTION_ID/resourceGroups/microbiome-rg \
  --sdk-auth
```

**Secret 2: `ACR_USERNAME`**
```
microbiomeacr
```

**Secret 3: `ACR_PASSWORD`**
```bash
# Run this and copy the output
az acr credential show \
  --name microbiomeacr \
  --query "passwords[0].value" \
  --output tsv
```

### Test it

```bash
git add .
git commit -m "feat: add Azure deployment"
git push

# Watch at: github.com/your-repo/actions
# Should complete in ~3-5 minutes
```

---

## Step 12 — Test End to End

### 1. Check all services are running

```bash
# API is live
curl https://$API_URL/
# Expected: {"status":"running","message":"Microdentify"}

# Database tables exist
psql "host=$POSTGRES_HOST port=5432 dbname=malmo_db user=malmo password=<passwordhere> sslmode=require" \
  -c "\dt"
# Expected: samples, abundance tables

# Redis is responding
redis-cli -h $REDIS_VM_IP -p 6379 -a RedisSecure2026! ping
# Expected: PONG
```

### 2. Upload a test sample

```bash
curl -X POST "https://$API_URL/samples" \
  -F "username=test_user" \
  -F "email=test@example.com" \
  -F "sample_name=test_sample" \
  -F "r1=@/path/to/test_R1.fastq.gz" \
  -F "r2=@/path/to/test_R2.fastq.gz"
# Expected: 201 Created with sample details
```

### 3. Check sample status

```bash
curl "https://$API_URL/samples/test_sample"
# Watch status change: pending → processing → completed
```

### 4. Get prediction

```bash
curl "https://$API_URL/samples/test_sample/predict?rank=genus"
# Expected: {"latitude": ..., "longitude": ...}
```

---

## Emergency: Shut Everything Down

If you need to stop all spending immediately:

```bash
# Stop Postgres (biggest ongoing cost)
az postgres flexible-server stop \
  --resource-group microbiome-rg \
  --name microbiome-postgres

# Stop Redis VM
az vm deallocate \
  --resource-group microbiome-rg \
  --name microbiome-redis-vm

# Scale API to zero
az containerapp update \
  --name microbiome-api \
  --resource-group microbiome-rg \
  --min-replicas 0

az containerapp update \
  --name microbiome-worker \
  --resource-group microbiome-rg \
  --min-replicas 0

# Nuclear option — delete everything
az group delete --name microbiome-rg --yes
```

---

## What Does NOT Go in Docker

```
Docker image contains:          Blob Storage contains:
────────────────────            ──────────────────────
src/backend/                    bin/fastqc.sif
src/ml/                         bin/fastp.sif
workflow/                       bin/kraken2.sif
profiles/                       bin/bbmap.sif
config/                         bin/bowtie2.sif
All Python packages             bin/common_adapters.txt
snakemake                       databases/kraken2/
                                databases/hg38/
                                uploads/ (user files)
                                results/ (pipeline output)
```

---

## Cost Summary with Free Tier


# Cloud Migration

In order to migrate to cloud, we first need to containerize the repository into docker images.
First we need to install docker.

## Docker Installation

On Ubuntu version 16 and later this can be done.
```bash
# Check the version you are on currently
lsb_release -a
#No LSB modules are available.
#Distributor ID:	Ubuntu
#Description:	Ubuntu 22.04.5 LTS
#Release:	22.04
#Codename:	jammy

# Next update your pacakges
sudo apt-get update

# Install docker
sudo apt install docker.io

# Enable docker to be running when the system is booted
sudo systemctl enable docker

# Finally check the status of docker
sudo systemctl status docker

# Need docker-compose as well to have different services run in the same container and talk to one another
sudo apt install docker-compose
```