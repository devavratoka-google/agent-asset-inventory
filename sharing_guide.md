# Guide: Sharing the GCP Asset Inventory Agent with Your Team

Here are the three easiest ways to package and share this agent with your team, depending on how they want to run it:

---

## Option 1: Git Repository (Best for Developers)

By committing the code to a Git repository, anyone on your team can clone and run it locally.

### Steps to Set Up:
1.  **Initialize Git** inside the directory `/Users/devavratoka/Documents/agent-asset-inventory`:
    ```bash
    git init
    ```
2.  **Add a `.gitignore` file** to make sure you do not commit the virtual environment or logs:
    ```bash
    echo "venv/" > .gitignore
    echo "*.log" >> .gitignore
    echo ".config/" >> .gitignore
    ```
3.  **Commit and push to your team's Git server** (GitHub, GitLab, Bitbucket, etc.):
    ```bash
    git add .
    git commit -m "Initialize GCP Asset Inventory Agent"
    git remote add origin <your-internal-git-url>
    git push -u origin main
    ```

### How Your Team Runs It:
```bash
git clone <your-internal-git-url> agent-asset-inventory
cd agent-asset-inventory
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
gcloud auth application-default login
./run.sh --scope "YOUR_ORG_ID"
```

---

## Option 2: Model Context Protocol (MCP) Server (Best for AI Assistant Integration)

If your team uses AI assistants (like Cursor, Cline, or Claude Desktop), you can expose this script as an **MCP Tool**. This lets the AI assistants query your GCP infrastructure automatically when your team asks them questions!

### Steps to Set Up:
1.  Add the MCP library to your script dependencies:
    ```bash
    ./venv/bin/pip install mcp
    ```
2.  Create a file named `mcp_server.py` in your folder:
    ```python
    import subprocess
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("GCP-Asset-Agent")

    @mcp.tool()
    def search_gcp_resources(scope: str, query: str = "", asset_type: str = "") -> str:
        """
        Queries GCP Cloud Asset Inventory to list resources in a scope (org, folder, or project).
        scope: organization ID, folder ID, or project ID
        query: optional filter (e.g. 'state: RUNNING')
        asset_type: optional filter (e.g. 'compute.googleapis.com/Instance')
        """
        cmd = ["./run.sh", "--scope", scope, "--format", "json"]
        if query:
            cmd.extend(["--query", query])
        if asset_type:
            cmd.extend(["--asset-type", asset_type])
            
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.stdout

    if __name__ == "__main__":
        mcp.run()
    ```
3.  Register it in Claude Desktop or Cursor settings under MCP servers, pointing to `python /Users/devavratoka/Documents/agent-asset-inventory/mcp_server.py`.

---

## Option 3: Docker Container (Best for Pipelines and CLI Tooling)

To share this without requiring anyone to install Python or Pip, you can wrap it in a lightweight Docker image.

### Steps to Set Up:
1.  Create a `Dockerfile` in the directory:
    ```dockerfile
    FROM python:3.13-slim
    
    WORKDIR /app
    
    COPY requirements.txt .
    RUN pip install --no-cache-dir -r requirements.txt
    
    COPY agent.py .
    
    ENTRYPOINT ["python", "agent.py"]
    ```
2.  Build and push to your team's container registry (e.g. Artifact Registry):
    ```bash
    docker build -t gcr.io/YOUR_PROJECT_ID/gcp-asset-agent:v1 .
    docker push gcr.io/YOUR_PROJECT_ID/gcp-asset-agent:v1
    ```

### How Your Team Runs It:
They only need Docker installed. They mount their local Google credentials folder so the container can authenticate:
```bash
docker run --rm \
  -v ~/.config/gcloud:/root/.config/gcloud \
  gcr.io/YOUR_PROJECT_ID/gcp-asset-agent:v1 --scope "organizations/340934488751"
```
