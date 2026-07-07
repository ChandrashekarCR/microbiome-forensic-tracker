# Azure Cloud Migration Guide
## Microbiome Forensic Tracker — Complete Step-by-Step

> **Read this before starting:**
> - Work through steps in order. Do not skip ahead.
> - After each step, run the verify command before moving on.
> - Every step has a delete command — use it if something goes wrong.
> - Your free tier covers most of this. Cost warnings are marked 💰.
> - **Never commit `.env.azure` to Git.**

---

## Your Budget Reality

| Service | Free Tier | After Free |
|---------|-----------|------------|
| Container Registry | ✅ 1 standard FREE | $5/month |
| PostgreSQL B1MS | ✅ 750 hrs/month FREE | $15/month |
| Linux VM B2pts | ✅ 750 hrs/month FREE | $8/month |
| Blob Storage | ✅ 5GB FREE | $0.02/GB/month |
| Redis Cache C0 | ❌ Not free | $15/month |
| Container Apps | ❌ Not free | ~$5/month |
| Azure Batch VMs | ❌ Pay per use | ~$0.10–4/hr |

**Strategy:** Use the free Linux VM to run Redis + Celery worker. This saves $15/month on Redis.

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

## Step 2 — Aure Storage

**What it is:** Azure's file storage. Holds your bioinformatics tools, databases as blob storage, uploads, logs, runtime and results are stored as Azure file servies which can be mounted to the contianer.

**Cost:** FREE up to 5GB. After that ~$0.02/GB/month. The Kraken2 database is 310GB — that costs ~$6/month once uploaded.

### Create storage account

```bash
az storage account create \
  --name ednamicrobiomestorage \
  --resource-group microbiome-rg \
  --location swedencentral \
  --sku Standard_LRS \
  --kind StorageV2

# What is Standard_LRS?
# Standard performace + Locally Redundant Storage (data is replicated 3 times with a single data center.)

# What is StorageV2?
# General-purpose v2 storage account - the latest version that support all features (Blobs, Files, Queues, Tables etc.)
```
| Data Type              | Estimated Size   | Storage Cost (per month) | Free Tier Coverage                         |
|------------------------|------------------|--------------------------|--------------------------------------------|
| FASTQ uploads          | ~10–50 GB (temp) | ~$0.20 – $1.00           | 5 GB free, rest ~$0.02/GB               |
| Pipeline results       | ~5–20 GB         | ~$0.10 – $0.40           | Covered by free 5 GB                    |
| Logs                   | ~1–5 GB          | ~$0.02 – $0.10           |  Covered                                 |
| SIF/container files    | ~5–10 GB         | ~$0.10 – $0.20           |  Mostly covered                          |
| Reference databases (Kraken2, hg38) | 50–300 GB | ~$1.00 – $6.00           |  Exceeds free tier                       |
| **Total (with databases)** | ~70–385 GB | ~$1.50 – $7.50/month     | —                                          |

### List everything in your Resource Group
```bash
az resource list \
    --resource-group microbiome-rg \
    --output table

# This shows every resource in the resource group, regardless of type.
```

### List only Storage Accounts
```bash
az storage account list \
    --resource-group microbiome-rg \
    --output table

### Get connection string — SAVE THIS

STORAGE_CONN=$(az storage account show-connection-string \
  --name ednamicrobiomestorage \
  --resource-group microbiome-rg \
  --output tsv)

STORAGE_KEY=$(az storage account keys list \
  --resource-group microbiome-rg \
  --account-name ednamicrobiomestorage \
  --query "[0].value" -o tsv)

echo "STORAGE_CONNECTION_STRING=$STORAGE_CONN"
# Copy this entire line into a safe place (password manager, notes)
```

### Create folders (containers) inside storage

```bash

# Bioinformatics databases (Kraken2, hg38)
az storage container create \
  --name databases \
  --connection-string "$STORAGE_CONN"

# Snakemake tools (Bioinformatics tools go here)
az storage container create \
  --name tools \
  --connection-string "$STORAGE_CONN"

# Generate a SAS token for the entire storage will help in file migrations and handling
az storage account generate-sas --account-name ednamicrobiomestorage --account-key "$STORAGE_ACCOUNT_KEY" --expiry 2026-07-07 --permissions acdlrw --services bf --resource-types sco --https-only --output tsv

# Creat azure storage for sharing between azure resources and that can be mounted to the container
az storage share create \
  --name microbiome-data \
  --account-name ednamicrobiomestorage \
  --account-key "$STORAGE_KEY"

# Create the directories for azure file servive - uploads, results, logs, runtime
  az storage directory create \
    --share-name microbiome-data \
    --name uploads \
    --account-name ednamicrobiomestorage \
    --account-key $STORAGE_KEY


```

### Verify

```bash
az storage container list \
  --connection-string "$STORAGE_CONN" \
  --output table
# Expected: 2 containers listed

az storage share list \
  --connection-string "$STORAGE_CONN" \
  --output table

# Should see microbiome-data

```

### Delete (if needed)

```bash
# Delete one container
az storage container delete \
  --name tools \
  --connection-string "$STORAGE_CONN"

# Delete the whole storage account
az storage account delete \
  --name microdentifystorage \
  --resource-group microdentify-rg \
  --yes

# Delete only certain things inside a container
az storage blob delete-batch \
  --source databases \
  --connection-string "$STORAGE_CONN" \
  --pattern "hg38_ref/hg38_ref/*"

```

---

## Step 3 — Upload Tools to Blob Storage

**What it is:** Copy your `.sif` files from LUNARC to Blob Storage. One-time operation.

# Without azure on LUNARC.
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

# Human genome index database upload
azcopy copy "/lunarc/nobackup/projects/snic2019-34-3/Daria/CAMP/ref_Human_hg38/ref_Human_hg38/hg38_ref/*" \
  "https://ednamicrobiomestorage.blob.core.windows.net/databases/hg38_ref?<SAS_TOKEN>" \
  --recursive --put-md5

# Copy the entire karken2 database
azcopy copy "/lunarc/nobackup/projects/snic2019-34-3/Daria/core_nt_Database/*" \
  "https://ednamicrobiomestorage.blob.core.windows.net/databases/core_nt_Database?<SAS_TOKEN>" \
  --recursive --put-md5

```

### This section is for transferring files if you can use azure on LUNARC or general files transfers without azcopy.

### Upload tools (bionformatics)

```bash
# Set your connection string
STORAGE_CONN="<paste your connection string here>"

# Upload all .sif files from bin/
az storage blob upload-batch \
  --source /home/chandru/binp51/bin/ \
  --destination tools \
  --connection-string "$STORAGE_CONN" \
  --pattern "*.sif"


```

### Upload databases (WARNING: Kraken2 is 310GB — start this and leave it overnight)

```bash
# hg38 human genome index (for bowtie2 host removal)
az storage blob upload-batch \
  --source /lunarc/nobackup/projects/snic2019-34-3/Daria/CAMP/ref_Human_hg38/ref_Human_hg38/hg38_ref/ \
  --destination databases/hg38 \
  --connection-string "$STORAGE_CONN"

# Kraken2 database — this will take hours
# Run in a screen session so it doesn't stop if you disconnect
screen -S upload_kraken
az storage blob upload-batch \
  --source /lunarc/nobackup/projects/snic2019-34-3/Daria/core_nt_Database/ \
  --destination databases/kraken2 \
  --connection-string "$STORAGE_CONN"
# Ctrl+A, D to detach from screen
# screen -r upload_kraken to check progress
```

### Verify uploads

```bash
# Check tools uploaded
az storage blob list \
  --container-name tools \
  --connection-string "$STORAGE_CONN" \
  --output table

# Check the files created for azure file share
az storage directory list \
  --share-name microbiome-data \
  --account-name ednamicrobiomestorage \
  --account-key "<your_key>" \
  --output table

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
BACKEND_DB_URL="postgresql://<user>:<password>@microbiome-postgres.postgres.database.azure.com:5432/malmo_db"

# Redis — on your free VM
CELERY_BROKER_URL="redis://:<password>@<public ip>:6379/0"
CELERY_RESULT_BACKEND="redis://:<password>@<public ip>:6379/0"

# Pickle file for machine learning
# Need to update this
MODEL_PATH=/app/src/ml/mlruns/1/models/m-150112cb0dfd4175b98a23716a7f042b/artifacts/model.pkl

# Snakemake
SNAKEMAKE_PROFILE=profiles/azure_batch
SNAKEMAKE_CONFIG=config/config_single_run.yaml
SNAKEMAKE_BIN=snakemake
SNAKEMAKE_TOOLS=/mnt/blob/tools

# Reference databases — on Blob Storage
KRAKEN2_DB=/mnt/blob/databases/core_nt_Database
HUMAN_GENOME_DIR=/mnt/blob/databases/hg38_ref
HUMAN_GENOME_INDEX=hg38_index


# Azure batch configurations
# These are the credentials Snakemake needs to submit jobs to Azure Batch
AZ_BATCH_ACCOUNT_URL="https://microbiomebatch.swedencentral.batch.azure.com"
AZ_BATCH_ACCOUNT_KEY=""

# Azure Blob - Snakemake uses this to stage data to batch vms
AZ_BLOB_ACCOUNT_URL="https://ednamicrobiomestorage.blob.core.windows.net/?<SAS Token>"
AZ_BLOB_PREFIX=uploads


# Apptainer bind mounts on Batch VMs
APPTAINER_BINDS="--bind /mnt/blob:/mnt/blob --bind /mnt/data:/mnt/data"

```

Replace `<REDIS_VM_IP>`, `<BATCH_KEY>`, and `<STORAGE_CONN>` with your actual values.

### Add to .gitignore

```bash
echo ".env.azure" >> .gitignore
echo ".env.lunarc" >> .gitignore
echo ".env.local" >> .gitignore
```

---

## Step 9 — Write `profiles/azure_batch/config.yaml`

**What it is:** Tells Snakemake to use Azure Batch as the job executor instead of SLURM.

```bash
mkdir -p profiles/azure_batch
```

```yaml
# profiles/azure_batch/config.yaml

executor: azure-batch

# Azure Batch connection (read from environment)
az-batch-account-name: "${AZURE_BATCH_ACCOUNT_NAME}"
az-batch-account-key: "${AZURE_BATCH_ACCOUNT_KEY}"
az-batch-account-url: "${AZURE_BATCH_ACCOUNT_URL}"

# Blob Storage for input/output
az-storage-account-name: "${AZURE_STORAGE_ACCOUNT}"
az-storage-account-key: ""

# Pool settings
az-batch-pool-id: "snakemake-pool"

# Job limits
cores: 50
jobs: 15
latency-wait: 60
keep-going: true
printshellcmds: false

# Container support
software-deployment-method:
  - apptainer

apptainer-args: "${APPTAINER_BINDS}"

# Default resources for all rules
default-resources:
  az_batch_node_size: "Standard_D4s_v3"
  runtime: "1h"
  mem_mb: 8000

# Per-rule overrides
set-resources:
  fastqc_raw:
    az_batch_node_size: "Standard_D2s_v3"
    runtime: "30m"
    mem_mb: 2000

  fastp:
    az_batch_node_size: "Standard_D2s_v3"
    runtime: "30m"
    mem_mb: 2000

  adapter_removal:
    az_batch_node_size: "Standard_D2s_v3"
    runtime: "30m"
    mem_mb: 2000

  remove_human_reads:
    az_batch_node_size: "Standard_D4s_v3"
    runtime: "1h"
    mem_mb: 8000

  error_correction:
    az_batch_node_size: "Standard_D4s_v3"
    runtime: "1h"
    mem_mb: 16000

  multiqc:
    az_batch_node_size: "Standard_D2s_v3"
    runtime: "15m"
    mem_mb: 2000

  kraken:
    az_batch_node_size: "Standard_E96bds_v5"
    runtime: "2h"
    mem_mb: 460000

  bracken:
    az_batch_node_size: "Standard_D2s_v3"
    runtime: "15m"
    mem_mb: 2000

  standardize_bracken:
    az_batch_node_size: "Standard_D2s_v3"
    runtime: "15m"
    mem_mb: 500

  merge_bracken:
    az_batch_node_size: "Standard_D2s_v3"
    runtime: "15m"
    mem_mb: 500
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
az containerapp env storage set --name microbiome-env --resource-group microbiome-rg --storage-name microbiome-data --azure-file-account-name ednamicrobiomestorage --azure-file-account-key "<storage key>" --azure-file-share-name microbiome-data --access-mode ReadWrite

# CHeck if it is attached
az containerapp env storage show \
  --name microbiome-env \
  --resource-group microbiome-rg \
  --storage-name microbiome-data \
  -o table

```

### Deploy FastAPI

```bash
az containerapp create \
  --resource-group microbiome-rg \
  --yaml deploy/api.yaml
```

### Deploy Celery worker

```bash
az containerapp create \
  --resource-group microbiome-rg \
  --yaml deploy/worker.yaml
```

### Get your live API URL

```bash
API_URL=$(az containerapp show \
  --name microdentify-api \
  --resource-group microdentify-rg \
  --query "properties.configuration.ingress.fqdn" \
  --output tsv)

echo "Your API is live at: https://$API_URL/docs"
```

### Verify

Open `https://<your-url>/docs` in your browser. You should see the Swagger UI.

### Update when you push new code

```bash
az containerapp update \
  --name microdentify-api \
  --resource-group microdentify-rg \
  --image microdentifyacr.azurecr.io/microdentify:latest

az containerapp update \
  --name microdentify-worker \
  --resource-group microdentify-rg \
  --image microdentifyacr.azurecr.io/microdentify:latest

# For verificaiton
az containerapp env show --name microbiome-env --resource-group microbiome-rg -o table
az containerapp list --resource-group microbiome-rg -o table
az resource list --resource-group microbiome-rg -o table

```

### Delete (if needed)

```bash
az containerapp delete \
  --name microdentify-api \
  --resource-group microdentify-rg \
  --yes

az containerapp delete \
  --name microdentify-worker \
  --resource-group microdentify-rg \
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
          login-server: microdentifyacr.azurecr.io
          username: ${{ secrets.ACR_USERNAME }}
          password: ${{ secrets.ACR_PASSWORD }}

      - name: Build and push Docker image
        run: |
          docker build -t microdentifyacr.azurecr.io/microdentify:latest .
          docker push microdentifyacr.azurecr.io/microdentify:latest

      - name: Deploy API
        run: |
          az containerapp update \
            --name microdentify-api \
            --resource-group microdentify-rg \
            --image microdentifyacr.azurecr.io/microdentify:latest

      - name: Deploy Worker
        run: |
          az containerapp update \
            --name microdentify-worker \
            --resource-group microdentify-rg \
            --image microdentifyacr.azurecr.io/microdentify:latest
```

### Add secrets to GitHub

Go to: `GitHub repo → Settings → Secrets and variables → Actions → New repository secret`

Add these three secrets:

**Secret 1: `AZURE_CREDENTIALS`**
```bash
# Run this command and copy the entire JSON output
az ad sp create-for-rbac \
  --name "microdentify-github-actions" \
  --role contributor \
  --scopes /subscriptions/$SUBSCRIPTION_ID/resourceGroups/microdentify-rg \
  --sdk-auth
```

**Secret 2: `ACR_USERNAME`**
```
microdentifyacr
```

**Secret 3: `ACR_PASSWORD`**
```bash
# Run this and copy the output
az acr credential show \
  --name microdentifyacr \
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
psql "host=$POSTGRES_HOST port=5432 dbname=malmo_db user=malmo password=MalmoSecure2026! sslmode=require" \
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
  --resource-group microdentify-rg \
  --name microdentify-postgres

# Stop Redis VM
az vm deallocate \
  --resource-group microdentify-rg \
  --name microdentify-redis-vm

# Scale API to zero
az containerapp update \
  --name microdentify-api \
  --resource-group microdentify-rg \
  --min-replicas 0

az containerapp update \
  --name microdentify-worker \
  --resource-group microdentify-rg \
  --min-replicas 0

# Nuclear option — delete everything
az group delete --name microdentify-rg --yes
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

| Resource | Monthly Cost |
|----------|-------------|
| Container Registry Standard | ✅ FREE |
| PostgreSQL B1MS | ✅ FREE (750 hrs) |
| Linux VM B2pts (Redis) | ✅ FREE (750 hrs) |
| Blob Storage up to 5GB | ✅ FREE |
| Blob Storage for databases (~350GB) | 💰 ~$7/month |
| Container Apps (2 containers) | 💰 ~$10/month |
| Azure Batch per sample (~30 min) | 💰 ~$2–4/sample |
| **Total fixed** | **~$17/month** |
| **Per sample run** | **~$2–4** |

With $200: fixed costs for 11+ months, plus ~50 sample runs.

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