#!/usr/bin/env python3
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

# Helper to format scope input
def format_scope(scope):
    scope = scope.strip()
    if not (scope.startswith("organizations/") or scope.startswith("folders/") or scope.startswith("projects/")):
        # If numeric, assume organization, otherwise project
        if scope.isdigit():
            return f"organizations/{scope}"
        else:
            return f"projects/{scope}"
    return scope

# Parse project name from projects/PROJECT_ID or projects/PROJECT_NUMBER
def clean_project(project_field):
    if not project_field:
        return "N/A"
    return project_field.replace("projects/", "")

def clean_zone(location):
    if not location:
        return "N/A"
    return location

# Extract attributes from VM instances Struct safely
def extract_vm_attrs(inst):
    status = inst.get("state") or inst.get("status")
    
    add_attrs = inst.get("additional_attributes") or inst.get("additionalAttributes") or {}
    
    if not status:
        status = add_attrs.get("status") or add_attrs.get("state") or "UNKNOWN"
        
    machine_type = add_attrs.get("machineType") or add_attrs.get("machine_type") or "N/A"
    if "/" in machine_type:
        machine_type = machine_type.split("/")[-1]
        
    internal_ips = add_attrs.get("internalIPs") or add_attrs.get("internal_ips") or []
    external_ips = add_attrs.get("externalIPs") or add_attrs.get("external_ips") or []
    
    # Fallback to networkInterfaces parsing
    if not internal_ips and not external_ips:
        network_interfaces = add_attrs.get("networkInterfaces") or add_attrs.get("network_interfaces") or []
        for net_inf in network_interfaces:
            ip = net_inf.get("networkIP") or net_inf.get("network_ip")
            if ip:
                internal_ips.append(ip)
            access_configs = net_inf.get("accessConfigs") or net_inf.get("access_configs") or []
            for acc in access_configs:
                nat_ip = acc.get("natIP") or acc.get("nat_ip")
                if nat_ip:
                    external_ips.append(nat_ip)
                    
    if isinstance(internal_ips, str):
        internal_ips = [internal_ips]
    if isinstance(external_ips, str):
        external_ips = [external_ips]
        
    return status, machine_type, internal_ips, external_ips

# Helper to extract a friendly type and details from any resource type
def extract_generic_details(inst):
    asset_type = inst.get("asset_type") or inst.get("assetType", "Unknown Type")
    add_attrs = inst.get("additional_attributes") or inst.get("additionalAttributes") or {}
    
    # Try to find a state/status
    status = inst.get("state") or inst.get("status") or add_attrs.get("status") or add_attrs.get("state") or "N/A"
    
    details = []
    # Make type readable
    short_type = asset_type.split("/")[-1] if "/" in asset_type else asset_type
    
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
            
    elif asset_type == "compute.googleapis.com/Disk":
        size = add_attrs.get("sizeGb") or add_attrs.get("size_gb") or ""
        if size:
            details.append(f"Size: {size}GB")
        dtype = add_attrs.get("type") or ""
        if "/" in dtype:
            dtype = dtype.split("/")[-1]
        if dtype:
            details.append(f"Type: {dtype}")
            
    elif asset_type == "dns.googleapis.com/ManagedZone":
        dns = add_attrs.get("dnsName") or add_attrs.get("dns_name") or ""
        if dns:
            details.append(f"DNS: {dns}")
            
    elif asset_type == "sqladmin.googleapis.com/Instance":
        ver = add_attrs.get("databaseVersion") or add_attrs.get("database_version") or ""
        if ver:
            details.append(f"DbVersion: {ver}")
            
    elif asset_type == "compute.googleapis.com/Network":
        rt = add_attrs.get("routingConfig", {}).get("routingMode") or ""
        if rt:
            details.append(f"Routing: {rt}")
            
    elif asset_type == "iam.googleapis.com/ServiceAccount":
        email = add_attrs.get("email") or ""
        if email:
            details.append(f"Email: {email}")

    elif asset_type == "container.googleapis.com/Cluster":
        node_count = add_attrs.get("currentNodeCount") or add_attrs.get("current_node_count") or ""
        endpoint = add_attrs.get("endpoint") or ""
        if node_count:
            details.append(f"Nodes: {node_count}")
        if endpoint:
            details.append(f"Endpoint: {endpoint}")
            
    elif asset_type == "dataproc.googleapis.com/Cluster":
        config = add_attrs.get("config") or add_attrs.get("clusterConfig") or {}
        worker_config = config.get("workerConfig") or {}
        num_instances = worker_config.get("numInstances") or worker_config.get("num_instances") or ""
        if num_instances:
            details.append(f"Workers: {num_instances}")
            
    elif asset_type == "compute.googleapis.com/Interconnect":
        link_type = add_attrs.get("linkType") or ""
        if link_type:
            details.append(f"LinkType: {link_type}")
        op_status = add_attrs.get("operationalStatus") or ""
        if op_status:
            details.append(f"OpStatus: {op_status}")
            
    elif asset_type == "compute.googleapis.com/InterconnectAttachment":
        bandwidth = add_attrs.get("bandwidth") or ""
        if bandwidth:
            details.append(f"Bandwidth: {bandwidth}")
        router = add_attrs.get("router") or ""
        if "/" in router:
            router = router.split("/")[-1]
        if router:
            details.append(f"Router: {router}")

    # Fallback: Extract key fields dynamically if no explicit rules matched or details is empty
    if not details and add_attrs:
        ignore_keys = {
            "id", "name", "selfLink", "self_link", "creationTimestamp", 
            "creation_timestamp", "status", "state", "displayName", "display_name", 
            "description", "location", "project", "organization", "folder", "networkInterfaceNames"
        }
        for key, val in add_attrs.items():
            if key in ignore_keys or val is None:
                continue
            if isinstance(val, (dict, list)):
                if not val:
                    continue
                if isinstance(val, list) and all(isinstance(x, (str, int, float, bool)) for x in val):
                    val_str = ", ".join(map(str, val))
                    if len(val_str) > 40:
                        val_str = val_str[:37] + "..."
                    details.append(f"{key}: [{val_str}]")
                continue
            val_str = str(val)
            if len(val_str) > 60:
                continue
            details.append(f"{key}: {val_str}")
            if len(details) >= 3:
                break

    detail_str = ", ".join(details) if details else "N/A"
    return short_type, status, detail_str

@click.command()
@click.option('--scope', '-s', required=True, help="GCP Scope (e.g., 'organizations/123456789', 'folders/456789', 'projects/my-project')")
@click.option('--query', '-q', default="", help="Query string for filtering assets (e.g. 'state: RUNNING')")
@click.option('--asset-type', '-t', multiple=True, help="Asset type(s) to filter by (e.g. 'compute.googleapis.com/Instance'). Can be specified multiple times. If omitted, lists all resource types.")
@click.option('--vms-only', is_flag=True, help="Shortcut to list only compute VM instances and show detailed columns.")
@click.option('--group-by', '-g', type=click.Choice(['project', 'type']), default=None, help="Group resources in the output by project or resource type.")
@click.option('--format', '-f', type=click.Choice(['table', 'json', 'csv']), default='table', help="Output format")
def main(scope, query, asset_type, vms_only, group_by, format):
    """GCP Cloud Asset Inventory CLI Tool.
    
    Searches for and displays resources inside the specified GCP scope.
    """
    console = Console()
    formatted_scope = format_scope(scope)
    
    # Determine the asset types to query
    actual_asset_types = list(asset_type)
    if vms_only:
        actual_asset_types = ["compute.googleapis.com/Instance"]
        
    is_vm_specific = len(actual_asset_types) == 1 and actual_asset_types[0] == "compute.googleapis.com/Instance"
    
    if format == 'table':
        if is_vm_specific:
            console.print(f"[bold blue]🔍 Cloud Asset CLI Tool searching for Compute VM Instances...[/bold blue]")
        else:
            console.print(f"[bold blue]🔍 Cloud Asset CLI Tool searching for GCP Resources...[/bold blue]")

        console.print(f"   Scope:    [green]{formatted_scope}[/green]")
        if actual_asset_types:
            console.print(f"   Types:    [yellow]{', '.join(actual_asset_types)}[/yellow]")
        if query:
            console.print(f"   Filter:   [yellow]'{query}'[/yellow]")
        if group_by:
            console.print(f"   Group By: [cyan]{group_by}[/cyan]")
        console.print()

    client = asset_v1.AssetServiceClient()
    
    try:
        request = asset_v1.SearchAllResourcesRequest(
            scope=formatted_scope,
            query=query,
            asset_types=actual_asset_types if actual_asset_types else None,
        )
        
        raw_resources = []
        
        # Display spinner while fetching assets
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
        else:
            response_iterator = client.search_all_resources(request=request)
            for resource in response_iterator:
                raw_resources.append(resource)
                
        if not raw_resources:
            if format == 'table':
                console.print("[yellow]⚠️  No resources found in the specified scope.[/yellow]")
            return

        # Convert to dictionary representation preserving field names (snake_case)
        resources = [MessageToDict(res._pb, preserving_proto_field_name=True) for res in raw_resources]

        # Standard Sorting (Helps group JSON/CSV exports cleanly too)
        if group_by == 'project':
            resources.sort(key=lambda x: clean_project(x.get("project", "")))
        elif group_by == 'type':
            resources.sort(key=lambda x: x.get("asset_type", ""))

        if format == 'json':
            print(json.dumps(resources, indent=2))
            return
            
        if format == 'csv':
            writer = csv.writer(sys.stdout)
            if is_vm_specific:
                writer.writerow(["Name", "Project", "Zone/Location", "Status", "Machine Type", "Internal IPs", "External IPs"])
                for inst in resources:
                    status, machine_type, internal_ips, external_ips = extract_vm_attrs(inst)
                    writer.writerow([
                        inst.get("display_name") or inst.get("displayName", "N/A"),
                        clean_project(inst.get("project", "")),
                        clean_zone(inst.get("location", "")),
                        status,
                        machine_type,
                        ",".join(internal_ips) if internal_ips else "N/A",
                        ",".join(external_ips) if external_ips else "N/A"
                    ])
            else:
                writer.writerow(["Name", "Type", "Project", "Zone/Location", "Status", "Details"])
                for inst in resources:
                    short_type, status, details = extract_generic_details(inst)
                    writer.writerow([
                        inst.get("display_name") or inst.get("displayName", "N/A"),
                        short_type,
                        clean_project(inst.get("project", "")),
                        clean_zone(inst.get("location", "")),
                        status,
                        details
                    ])
            return

        # Default format: Rich Table (with optional grouping layout)
        if group_by == 'project':
            # Group items by project name
            project_groups = defaultdict(list)
            for inst in resources:
                proj = clean_project(inst.get("project", ""))
                project_groups[proj].append(inst)
                
            for proj_name, items in sorted(project_groups.items()):
                title = f"Project: {proj_name} ({len(items)} resources)"
                if is_vm_specific:
                    table = Table(title=title, show_header=True, header_style="bold magenta", title_style="bold cyan")
                    table.add_column("VM Name", style="bold white")
                    table.add_column("Zone/Location", style="blue")
                    table.add_column("Status", justify="center")
                    table.add_column("Machine Type", style="dim yellow")
                    table.add_column("Internal IP(s)", style="cyan")
                    table.add_column("External IP(s)", style="magenta")
                    
                    for inst in items:
                        name = inst.get("display_name") or inst.get("displayName", "N/A")
                        zone = clean_zone(inst.get("location", ""))
                        status, machine_type, internal_ips, external_ips = extract_vm_attrs(inst)
                        
                        status_style = "dim"
                        status_str = status.upper()
                        if status_str == "RUNNING":
                            status_style = "bold green"
                        elif status_str in ("TERMINATED", "STOPPED"):
                            status_style = "bold red"
                        status_formatted = f"[{status_style}]{status_str}[/{status_style}]"
                        
                        table.add_row(
                            name, zone, status_formatted, machine_type,
                            ", ".join(internal_ips) if internal_ips else "N/A",
                            ", ".join(external_ips) if external_ips else "N/A"
                        )
                else:
                    table = Table(title=title, show_header=True, header_style="bold magenta", title_style="bold cyan")
                    table.add_column("Resource Name", style="bold white")
                    table.add_column("Type", style="yellow")
                    table.add_column("Zone/Location", style="blue")
                    table.add_column("Status", justify="center")
                    table.add_column("Details", style="dim cyan")
                    
                    for inst in items:
                        name = inst.get("display_name") or inst.get("displayName", "N/A")
                        zone = clean_zone(inst.get("location", ""))
                        short_type, status, details = extract_generic_details(inst)
                        
                        status_style = "dim"
                        status_str = status.upper()
                        if status_str in ("RUNNING", "ACTIVE", "READY", "TRUE"):
                            status_style = "bold green"
                        elif status_str in ("TERMINATED", "STOPPED", "DELETED", "FALSE"):
                            status_style = "bold red"
                        status_formatted = f"[{status_style}]{status_str}[/{status_style}]"
                        
                        table.add_row(name, short_type, zone, status_formatted, details)
                console.print(table)
                console.print()
                
        elif group_by == 'type':
            # Group items by asset type name
            type_groups = defaultdict(list)
            for inst in resources:
                asset_type = inst.get("asset_type") or inst.get("assetType", "Unknown")
                type_groups[asset_type].append(inst)
                
            for type_name, items in sorted(type_groups.items()):
                short_type = type_name.split("/")[-1] if "/" in type_name else type_name
                title = f"Resource Type: {short_type} ({len(items)} resources)"
                
                table = Table(title=title, show_header=True, header_style="bold magenta", title_style="bold cyan")
                table.add_column("Resource Name", style="bold white")
                table.add_column("Project", style="green")
                table.add_column("Zone/Location", style="blue")
                table.add_column("Status", justify="center")
                table.add_column("Details", style="dim cyan")
                
                for inst in items:
                    name = inst.get("display_name") or inst.get("displayName", "N/A")
                    project = clean_project(inst.get("project", ""))
                    zone = clean_zone(inst.get("location", ""))
                    _, status, details = extract_generic_details(inst)
                    
                    status_style = "dim"
                    status_str = status.upper()
                    if status_str in ("RUNNING", "ACTIVE", "READY", "TRUE"):
                        status_style = "bold green"
                    elif status_str in ("TERMINATED", "STOPPED", "DELETED", "FALSE"):
                        status_style = "bold red"
                    status_formatted = f"[{status_style}]{status_str}[/{status_style}]"
                    
                    table.add_row(name, project, zone, status_formatted, details)
                console.print(table)
                console.print()
                
        else:
            # Default single flat table format
            if is_vm_specific:
                table = Table(
                    title=f"Compute VM Instances in {formatted_scope}",
                    show_header=True,
                    header_style="bold magenta",
                    title_style="bold cyan"
                )
                table.add_column("VM Name", style="bold white")
                table.add_column("Project", style="green")
                table.add_column("Zone/Location", style="blue")
                table.add_column("Status", justify="center")
                table.add_column("Machine Type", style="dim yellow")
                table.add_column("Internal IP(s)", style="cyan")
                table.add_column("External IP(s)", style="magenta")

                for inst in resources:
                    name = inst.get("display_name") or inst.get("displayName", "N/A")
                    project = clean_project(inst.get("project", ""))
                    zone = clean_zone(inst.get("location", ""))
                    status, machine_type, internal_ips, external_ips = extract_vm_attrs(inst)

                    status_style = "dim"
                    status_str = status.upper()
                    if status_str == "RUNNING":
                        status_style = "bold green"
                    elif status_str in ("TERMINATED", "STOPPED"):
                        status_style = "bold red"
                    elif status_str in ("PROVISIONING", "STAGING"):
                        status_style = "bold yellow"
                    elif status_str in ("STOPPING", "SUSPENDING"):
                        status_style = "italic red"
                    status_formatted = f"[{status_style}]{status_str}[/{status_style}]"
                    
                    table.add_row(
                        name, project, zone, status_formatted, machine_type,
                        ", ".join(internal_ips) if internal_ips else "N/A",
                        ", ".join(external_ips) if external_ips else "N/A"
                    )
            else:
                table = Table(
                    title=f"GCP Resource Inventory in {formatted_scope}",
                    show_header=True,
                    header_style="bold magenta",
                    title_style="bold cyan"
                )
                table.add_column("Resource Name", style="bold white")
                table.add_column("Type", style="yellow")
                table.add_column("Project", style="green")
                table.add_column("Zone/Location", style="blue")
                table.add_column("Status", justify="center")
                table.add_column("Details", style="dim cyan")

                for inst in resources:
                    name = inst.get("display_name") or inst.get("displayName", "N/A")
                    project = clean_project(inst.get("project", ""))
                    zone = clean_zone(inst.get("location", ""))
                    short_type, status, details = extract_generic_details(inst)

                    status_style = "dim"
                    status_str = status.upper()
                    if status_str in ("RUNNING", "ACTIVE", "READY", "TRUE"):
                        status_style = "bold green"
                    elif status_str in ("TERMINATED", "STOPPED", "DELETED", "FALSE"):
                        status_style = "bold red"
                    elif status_str in ("PROVISIONING", "CREATING"):
                        status_style = "bold yellow"
                    elif status_str == "N/A":
                        status_style = "dim"
                    status_formatted = f"[{status_style}]{status_str}[/{status_style}]"
                    
                    table.add_row(name, short_type, project, zone, status_formatted, details)
            console.print(table)
            console.print()

        console.print(f"[bold green]✅ Total resources found: {len(resources)}[/bold green]")
        
    except Exception as e:
        console.print(f"\n[bold red]❌ Error listing assets: {str(e)}[/bold red]")
        console.print("[yellow]💡 Tip: Please verify that:[/yellow]")
        console.print("   1. You are authenticated with application default credentials:")
        console.print("      [bold white]gcloud auth application-default login[/bold white]")
        console.print("   2. Your credentialed account has the '[bold white]Cloud Asset Viewer[/bold white]' IAM role (roles/cloudasset.viewer) on the target scope.")
        sys.exit(1)

if __name__ == '__main__':
    main()
