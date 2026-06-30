# Python Code Walkthrough (For Terraform Developers)

This guide walks you through the Python script `asset_inventory.py` line-by-line, comparing it to concepts you know from Terraform and HashiCorp Configuration Language (HCL).

---

## 1. Imports vs. Providers
At the very top of `asset_inventory.py`, we import libraries:

```python
import click
import json
import csv
import sys
from collections import defaultdict
from google.cloud import asset_v1
from google.protobuf.json_format import MessageToDict
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
```

### Terraform Analogy:
This is equivalent to your `terraform {}` and `provider "google" {}` blocks:
*   `from google.cloud import asset_v1` is like loading the GCP provider. It gives the script access to Google Cloud APIs.
*   `rich` (including `Console`, `Table`, and `Progress`) is like a GUI provider; it handles rendering colors, tables, and execution progress spinners.
*   `click` is like declaring input variables, but for arguments passed via the terminal CLI.
*   `collections.defaultdict` is a helper for grouping lists/maps of resources (used to implement output grouping).

---

## 2. Helper Functions vs. Locals / Expressions
In Python, a block starting with `def` is a **function** (a reusable sub-routine).

### A. Formatting Scope
```python
def format_scope(scope):
    scope = scope.strip()
    if not (scope.startswith("organizations/") or scope.startswith("folders/") or scope.startswith("projects/")):
        if scope.isdigit():
            return f"organizations/{scope}"
        else:
            return f"projects/{scope}"
    return scope
```
*   **What it does**: This ensures that if a user types `--scope <numeric-org-id>`, the script formats it as `organizations/<numeric-org-id>`. If they type `--scope <project-id>`, it formats it as `projects/<project-id>`.
*   **Terraform Analogy**: This is like using local variables with conditional logic:
    ```hcl
    locals {
      formatted_scope = (
        can(regex("^organizations/|^folders/|^projects/", var.scope)) ? var.scope :
        can(regex("^[0-9]+$", var.scope)) ? "organizations/${var.scope}" : "projects/${var.scope}"
      )
    }
    ```

---

### B. Extracting Generic Details (The Magic Column)
Because a database, bucket, and VM instance have completely different fields, we write a parser that checks the type of asset and retrieves custom info:

```python
def extract_generic_details(inst):
    asset_type = inst.get("asset_type") or inst.get("assetType", "Unknown Type")
    add_attrs = inst.get("additional_attributes") or inst.get("additionalAttributes") or {}
    
    # Try to find a state/status
    status = inst.get("state") or inst.get("status") or add_attrs.get("status") or add_attrs.get("state") or "N/A"
    
    details = []
    # Make type readable
    short_type = asset_type.split("/")[-1] if "/" in asset_type else asset_type
```
*   `inst.get("key")` is like using `lookup(local.map, "key", default)`. It looks up a value in a dictionary (map) safely without throwing an error if the key doesn't exist.
*   `asset_type.split("/")[-1]` splits a string by `/` and gets the last part. For example, `storage.googleapis.com/Bucket` becomes `Bucket`.

We then use `if / elif` (equivalent to HCL `cond ? true : false` nested expressions) to fetch type-specific metrics:

```python
    if asset_type == "compute.googleapis.com/Instance":
        mach = add_attrs.get("machineType") or add_attrs.get("machine_type") or ""
        if "/" in mach:
            mach = mach.split("/")[-1]
        if mach:
            details.append(f"Machine: {mach}")
        ips = add_attrs.get("internalIPs") or add_attrs.get("internal_ips") or []
        if ips:
            details.append(f"IntIP: {ips[0] if isinstance(ips, list) else ips}")
            
    elif asset_type == "storage.googleapis.com/Bucket":
        sc = add_attrs.get("storageClass") or add_attrs.get("storage_class") or ""
        if sc:
            details.append(f"Class: {sc}")

    # Similar handlers parse GKE, Cloud Run Services, Cloud Run Jobs, Cloud SQL, DNS, etc.
```
*   `details.append(...)` is like appending items to an HCL list.

We also have a dynamic fallback parser for unhandled resource types that scans `additionalAttributes` for any non-system properties, and automatically appends resource labels (e.g. `labels:{env=prod}`) to the details list.

---

### C. Smart Name Extraction Fallback
Some GCP resource types do not expose a standard `displayName` or `display_name` property in the Asset Inventory response (for example, Memorystore Redis instances). To handle this gracefully:

```python
def get_resource_name(inst):
    name = inst.get("display_name") or inst.get("displayName")
    if not name:
        full_name = inst.get("name") or ""
        if "/" in full_name:
            name = full_name.split("/")[-1]
        else:
            name = "N/A"
    return name
```
*   **What it does**: It checks if a display name is available. If not, it parses the resource's full API name (URI path) and extracts the last segment (leaf name), ensuring the output table always has a friendly identifier.

---

## 3. Defining the CLI Interface vs. Variables
At the command-line interface level, we define option flags:

```python
@click.command()
@click.option('--scope', '-s', required=True, help="GCP Scope (e.g., 'organizations/123456789', 'folders/456789', 'projects/my-project')")
@click.option('--query', '-q', default="", help="Query string for filtering assets (e.g. 'state: RUNNING')")
@click.option('--asset-type', '-t', multiple=True, help="Asset type(s) to filter by (e.g. 'compute.googleapis.com/Instance'). Can be specified multiple times. If omitted, lists all resource types.")
@click.option('--vms-only', is_flag=True, help="Shortcut to list only compute VM instances and show detailed columns.")
@click.option('--group-by', '-g', type=click.Choice(['project', 'type']), default=None, help="Group resources in the output by project or resource type.")
@click.option('--format', '-f', type=click.Choice(['table', 'json', 'csv']), default='table', help="Output format")
def main(scope, query, asset_type, vms_only, group_by, format):
```
*   **What it does**: Click turns command-line arguments (like `-s`, `-q`, or `--group-by`) into Python variables.
*   **Terraform Analogy**: This is identical to defining variables in your `variables.tf`:
    ```hcl
    variable "scope" {
      type     = string
      nullable = false
    }
    variable "query" {
      type    = string
      default = ""
    }
    variable "group_by" {
      type    = string
      default = null
    }
    ```

---

## 4. Querying the API vs. Data Sources
Inside the `main` function, we instantiate the API client and build our query request:

```python
    client = asset_v1.AssetServiceClient()
    
    request = asset_v1.SearchAllResourcesRequest(
        scope=formatted_scope,
        query=query,
        asset_types=actual_asset_types if actual_asset_types else None,
    )
    
    # We display an interactive CLI spinner while querying the API:
    if format == 'table':
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True
        ) as progress:
            task = progress.add_task(description="Querying Google Cloud Asset Inventory...", total=None)
            response_iterator = client.search_all_resources(request=request)
            for resource in response_iterator:
                raw_resources.append(resource)
```
*   **What it does**: This sends the query request to the GCP Cloud Asset Inventory API and downloads the resources in an iterator while showing a spinner to the user.
*   **Terraform Analogy**: This is like calling a GCP Data Source:
    ```hcl
    data "google_asset_resources" "all" {
      scope       = local.formatted_scope
      query       = var.query
      asset_types = var.asset_type
    }
    ```

Once downloaded, the raw protobuf response objects are converted to standard python dictionaries preserving field names:
```python
    resources = [MessageToDict(res._pb, preserving_proto_field_name=True) for res in raw_resources]
```

---

## 5. Iteration & Rendering vs. `for_each` Output
Once we have our list of resources, we loop through them to display them. Depending on the grouping option requested, the resources are either rendered in a flat table, or partitioned into sub-groups:

```python
    if group_by == 'project':
        # Group items by project name dynamically
        project_groups = defaultdict(list)
        for inst in resources:
            proj = clean_project(inst.get("project", ""))
            project_groups[proj].append(inst)
            
        for proj_name, items in sorted(project_groups.items()):
            # Create a separate Table for each project group
            ...
            for inst in items:
                name = get_resource_name(inst)
                ...
```
*   **What it does**: The tool iterates over the resources, extracts fields (such as using `get_resource_name` to handle missing display names), styles the statuses with appropriate colors, and formats them into one or more `rich` tables. If the output format is `json` or `csv`, it serializes the structured list directly.
*   **Terraform Analogy**: This is similar to filtering and generating an output list or Map grouping using `for` expressions:
    ```hcl
    output "resource_inventory_grouped" {
      value = {
        for res in data.google_asset_resources.all.results : 
        replace(res.project, "projects/", "") => res...
      }
    }
    ```

---

## 6. Execution entrypoint
At the bottom of the script, you see:
```python
if __name__ == '__main__':
    main()
```
*   **What it does**: In Python, when a file is executed directly (rather than being imported as a helper library inside another script), Python assigns it the name `"__main__"`. This block says: "If this script is run directly, call the `main()` function to start everything."
