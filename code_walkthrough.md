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
from google.cloud import asset_v1
from google.protobuf.json_format import MessageToDict
from rich.console import Console
from rich.table import Table
```

### Terraform Analogy:
This is equivalent to your `terraform {}` and `provider "google" {}` blocks:
*   `from google.cloud import asset_v1` is like loading the GCP provider. It gives the script access to Google Cloud APIs.
*   `rich` is like a GUI provider; it handles color rendering and drawing tables.
*   `click` is like declaring input variables, but for arguments passed via the terminal CLI.

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
*   **What it does**: This ensures that if a user types `--scope <numeric-org-id>`, the script formats it as `organizations/<numeric-org-id>`. If they type `--scope proj-oka-demo`, it formats it as `projects/proj-oka-demo`.
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
    asset_type = inst.get("asset_type") or inst.get("assetType", "")
    add_attrs = inst.get("additional_attributes") or inst.get("additionalAttributes") or {}
    
    status = inst.get("state") or inst.get("status") or add_attrs.get("status") or "N/A"
    details = []
    
    # Extract short type name
    short_type = asset_type.split("/")[-1] if "/" in asset_type else asset_type
```
*   `inst.get("key")` is like using `lookup(local.map, "key", default)`. It looks up a value in a dictionary (map) safely without throwing an error if the key doesn't exist.
*   `asset_type.split("/")[-1]` splits a string by `/` and gets the last part. For example, `storage.googleapis.com/Bucket` becomes `Bucket`.

We then use `if / elif` (equivalent to HCL `cond ? true : false` nested expressions) to fetch type-specific metrics:

```python
    if asset_type == "compute.googleapis.com/Instance":
        mach = add_attrs.get("machineType") or ""
        details.append(f"Machine: {mach.split('/')[-1]}")
        
    elif asset_type == "storage.googleapis.com/Bucket":
        sc = add_attrs.get("storageClass") or ""
        details.append(f"Class: {sc}")
```
*   `details.append(...)` is like appending items to an HCL list.

---

## 3. Defining the CLI Interface vs. Variables
At the command-line interface level, we define option flags:

```python
@click.command()
@click.option('--scope', '-s', required=True, help="GCP Scope")
@click.option('--query', '-q', default="", help="Filter query")
@click.option('--asset-type', '-t', multiple=True, help="Asset type filter")
@click.option('--vms-only', is_flag=True, help="Display VM columns")
@click.option('--format', '-f', type=click.Choice(['table', 'json', 'csv']), default='table')
def main(scope, query, asset_type, vms_only, format):
```
*   **What it does**: Click turns command-line arguments (like `-s` or `-q`) into Python variables.
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
    
    response_iterator = client.search_all_resources(request=request)
```
*   **What it does**: This sends the query request to the GCP Cloud Asset Inventory API and starts downloading resources.
*   **Terraform Analogy**: This is like calling a GCP Data Source:
    ```hcl
    data "google_asset_resources" "all" {
      scope       = local.formatted_scope
      query       = var.query
      asset_types = var.asset_type
    }
    ```

---

## 5. Iteration & Rendering vs. `for_each` Output
Once we have our list of resources, we loop through them to display them:

```python
    for inst in resources:
        name = inst.get("display_name") or "N/A"
        project = clean_project(inst.get("project", ""))
        zone = clean_zone(inst.get("location", ""))
        
        short_type, status, details = extract_generic_details(inst)
        
        # Add a new row to the table
        table.add_row(name, short_type, project, zone, status, details)
```
*   **What it does**: `for inst in resources:` goes through the list of resources one by one. It extracts fields, converts the status string into a colored version, and appends it as a row in our Table block.
*   **Terraform Analogy**: This is similar to generating an output list using `for` expressions:
    ```hcl
    output "resource_inventory" {
      value = [
        for res in data.google_asset_resources.all.results : {
          name    = res.display_name
          project = replace(res.project, "projects/", "")
          type    = element(split("/", res.asset_type), length(split("/", res.asset_type)) - 1)
        }
      ]
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
