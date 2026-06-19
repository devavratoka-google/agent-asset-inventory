# GCP Cloud Asset Inventory Resource Agent

This directory contains a Python-based command-line agent that queries Google Cloud Asset Inventory to list and display GCP resources in a specified scope (Organization, Folder, or Project).

It can retrieve a complete inventory of all resources (e.g., Disks, Buckets, Networks, SQL Instances) or render a specialized, detailed table for Compute VM Instances.

It supports rendering outputs in a premium, beautifully-styled CLI table, JSON format, or CSV format.

## Setup & Prerequisites

### 1. Authenticate with Google Cloud

The agent uses **Application Default Credentials (ADC)** to connect to Google Cloud. If your active credentials have expired, run:

```bash
gcloud auth application-default login
```

If you are querying resources across an organization, ensure your authenticated account is the correct one. Set it via:

```bash
gcloud config set account YOUR_ACCOUNT_EMAIL
gcloud auth login
```

### 2. IAM Permissions Required

To query Cloud Asset Inventory, your user account or service account needs the **Cloud Asset Viewer** role (`roles/cloudasset.viewer`) on the target scope (e.g., Organization, Folder, or Project).

---

## How to Run the Agent

We have provided a helper script `./run.sh` that automatically activates the Python virtual environment and executes the agent.

### Usage

```bash
./run.sh --scope SCOPE [OPTIONS]
```

### Options

*   `-s, --scope TEXT`: **(Required)** The GCP scope to search. E.g.
    *   Organization ID: `1234567890` or `organizations/1234567890`
    *   Folder ID: `folders/1234567890`
    *   Project ID: `my-project-id` or `projects/my-project-id`
*   `-t, --asset-type TEXT`: Filter by specific asset type(s) (e.g. `compute.googleapis.com/Instance`, `storage.googleapis.com/Bucket`). Can be specified multiple times. If omitted, queries all resource types.
*   `--vms-only`: Shortcut to query only compute VM instances and show a detailed VM-specific columns layout.
*   `-q, --query TEXT`: Filter query (e.g., `state: RUNNING` to only list active resources, or `name: prod-*`).
*   `-f, --format [table|json|csv]`: Output format (default: `table`).

---

## Examples

### 1. View all GCP Resources in your Organization
```bash
./run.sh --scope "organizations/340934488751"
```

### 2. View all Buckets and SQL Instances in your Organization
```bash
./run.sh --scope "organizations/340934488751" -t "storage.googleapis.com/Bucket" -t "sqladmin.googleapis.com/Instance"
```

### 3. View only Compute VM Instances (Detailed layout)
```bash
./run.sh --scope "organizations/340934488751" --vms-only
```

### 4. View only RUNNING VMs in a project
```bash
./run.sh --scope "projects/proj-oka-int-demo" --vms-only --query "state: RUNNING"
```

### 5. Output all resources as JSON
```bash
./run.sh --scope "projects/proj-oka-int-demo" --format json
```

### 6. Save resources list to a CSV file
```bash
./run.sh --scope "projects/proj-oka-int-demo" --format csv > resources.csv
```

---

## Directory Structure

*   [agent.py](file:///Users/devavratoka/Documents/agent-asset-inventory/agent.py) - The core Python script using GCP libraries.
*   [run.sh](file:///Users/devavratoka/Documents/agent-asset-inventory/run.sh) - Simple bash entrypoint that handles python virtual environment activation.
*   [requirements.txt](file:///Users/devavratoka/Documents/agent-asset-inventory/requirements.txt) - Dependency file.
