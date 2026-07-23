---
name: gcp-asset-inventory
description: Use this skill whenever the user asks to inspect, query, filter, audit, or inventory GCP resources (Compute VMs, Cloud Storage buckets, Cloud SQL instances, GKE clusters, VPC networks, Cloud Run, IAM service accounts, etc.) using the local GCP Asset Inventory CLI script.
---

# GCP Asset Inventory Skill

Use this skill when the user asks to inspect, query, list, or inventory GCP resources across an Organization, Folder, or Project scope using the local Cloud Asset Inventory CLI tool.

## 1. Primary Entrypoint & Execution

Always execute the tool using `run_command` via the helper wrapper script `./run.sh` (or `python3 asset_inventory.py`):

```bash
./run.sh --scope <SCOPE> [OPTIONS]
```

### Scope Parameter (`-s, --scope`)
* **Organization**: `organizations/<NUMERIC_ID>` or `<NUMERIC_ID>`
* **Folder**: `folders/<NUMERIC_ID>`
* **Project**: `projects/<PROJECT_ID>` or `<PROJECT_ID>`

---

## 2. Command Options & Guidelines

* **Output Formats (`-f, --format`)**:
  * Use `--format json` when Jetski needs to parse resource details, audit security/configuration state, or evaluate properties programmatically.
  * Use `--format table` (default) for rendering styled CLI tables.
  * Use `--format csv` if generating CSV outputs.

* **Filtering Asset Types (`-t, --asset-type`)**:
  * Pass one or multiple `-t` flags to filter by specific resource types:
    * `compute.googleapis.com/Instance`
    * `storage.googleapis.com/Bucket`
    * `sqladmin.googleapis.com/Instance`
    * `container.googleapis.com/Cluster`
    * `compute.googleapis.com/Network`
    * `run.googleapis.com/Service`
    * `iam.googleapis.com/ServiceAccount`

* **VM Quick View (`--vms-only`)**:
  * Use `--vms-only` to display a detailed Compute Engine VM instance layout (including machine type, internal/external IPs, and status).

* **Grouping (`-g, --group-by`)**:
  * Use `--group-by project` or `--group-by type` to group output tables dynamically.

* **Search Query (`-q, --query`)**:
  * Filter results with query expressions (e.g. `--query "state: RUNNING"` or `--query "name: prod-*"`).
  * **Tag Filtering**:
    * Query Resource Manager tag values: `-q "tagValues: *tag-value-name*"`
    * Combine tag value & display name: `-q "tagValues: *iap-ssh* OR displayName: iap-ssh"`
    * Query Resource Manager tag keys: `-q "tagKeys: *tag-key-name*"`
    * Query Network Tags (VMs): `-q "networkTags: iap-ssh"`
    * Query Labels: `-q "labels.env: prod"`

---

## 3. Common Usage Examples

### List all resources in a project
```bash
./run.sh --scope "my-project-id"
```

### List resources with a specific tag value in an organization
```bash
./run.sh --scope "organizations/1234567890" -q "tagValues: *iap-ssh* OR displayName: iap-ssh"
```

### List running VMs in an organization
```bash
./run.sh --scope "1234567890" --vms-only -q "state: RUNNING"
```

### Audit Storage Buckets & SQL instances in JSON format
```bash
./run.sh --scope "projects/my-project-id" -t "storage.googleapis.com/Bucket" -t "sqladmin.googleapis.com/Instance" -f json
```

### Group folder resources by asset type
```bash
./run.sh --scope "folders/1234567890" --group-by type
```

