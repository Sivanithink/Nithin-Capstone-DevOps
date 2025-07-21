import os
import json
import yaml
import shutil
import boto3
import click
import subprocess
import requests
from datetime import datetime

# Import your project modules
from .build import detect_app_type, build_project
from .dockerfile_generator import write_dockerfile
from .framework_detection import detect_framework
from .aws_utils import upload_dir_to_s3

# Constants
KEY_NAME = os.path.abspath(".pem/key-18.pem")
DEPLOY_CONFIG = "deploy-tool.yml"
DEPLOY_HISTORY = "deploy_history.json"
ROLLBACK_INFO = "rollback-info.yml"
TERRAFORM_DIR = os.path.abspath("terraform")


@click.group()
def cli():
    """Deploy Tool CLI"""
    pass


@cli.command("init")
def init_command():
    repo_url = click.prompt("Enter your Git repo URL")
    folder = repo_url.rstrip('/').split('/')[-1].replace('.git', '')

    if not os.path.exists(folder):
        import git
        git.Repo.clone_from(repo_url, folder)
        click.echo(f"Repo cloned to: {folder}")
    else:
        click.echo(f"Folder {folder} already exists.")

    config = {"repo_url": repo_url, "folder": folder, "bucket": "my-app-18"}

    with open(DEPLOY_CONFIG, "w") as f:
        yaml.dump(config, f)

    click.echo("Config written to deploy-tool.yml")


@cli.command("deploy")
def deploy_command():
    with open(DEPLOY_CONFIG) as f:
        config = yaml.safe_load(f)

    project = config["folder"]
    bucket = config["bucket"]
    os.chdir(project)
    project_prefix = f"{project}/"

    framework = detect_framework(os.getcwd())
    click.echo(f"Detected framework: {framework}")

    write_dockerfile(os.getcwd(), framework)
    click.echo("Dockerfile written.")

    app_type = framework
    if app_type != "static":
        build_project(app_type, os.getcwd())

    upload_dir = {
        "next": "out",
        "vite": "dist",
        "react": "build"
    }.get(app_type, ".")

    upload_path = os.path.abspath(upload_dir)
    artifact_ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    artifact_basename = f"build_artifact_{artifact_ts}"
    artifact_name = f"{artifact_basename}.zip"

    for fname in ["Dockerfile", "package.json", "package-lock.json"]:
        src = os.path.abspath(fname)
        dst = os.path.join(upload_path, fname)
        if os.path.exists(src) and src != dst:
            shutil.copy(src, dst)
            click.echo(f"Copied {fname} to build directory.")

    shutil.make_archive(artifact_basename, 'zip', root_dir=upload_path)
    click.echo(f"Artifact zipped as {artifact_name}")

    s3 = boto3.client("s3")
    upload_dir_to_s3(upload_path, bucket, prefix=project_prefix)
    s3.upload_file(f"{artifact_basename}.zip", bucket, f"{project_prefix}{artifact_name}")
    click.echo("Artifact uploaded to S3")

    rollback_path = os.path.join(os.getcwd(), "..", ROLLBACK_INFO)
    if os.path.exists(rollback_path):
        with open(rollback_path) as f:
            rb_info = yaml.safe_load(f)
        artifact_key = rb_info["artifact_key"]
        os.remove(rollback_path)
        click.echo(f"Detected rollback. Using: {artifact_key}")
    else:
        artifact_key = f"{project_prefix}{artifact_name}"

    history_path = os.path.join("..", DEPLOY_HISTORY)
    if os.path.exists(history_path):
        with open(history_path) as f:
            history = json.load(f)
    else:
        history = {}

    is_first_deploy = "latest" not in history
    history["previous"] = history.get("latest")
    history["latest"] = artifact_key

    with open(history_path, "w") as f:
        json.dump(history, f, indent=2)

    if not os.path.exists(KEY_NAME):
        click.echo(f"ERROR: SSH key file not found at: {KEY_NAME}")
        return

    if is_first_deploy:
        click.echo("First deploy. Running Terraform to provision EC2...")
        subprocess.run(["terraform", "init"], cwd=TERRAFORM_DIR, check=True)
        subprocess.run([
            "terraform", "apply", "-auto-approve",
            f"-var=bucket_name={bucket}",
            f"-var=ec2_name={project}",
            f"-var=artifact_key={artifact_key}",
            f"-var=key_name={KEY_NAME}"
        ], cwd=TERRAFORM_DIR, check=True)

        result = subprocess.run(
            ["terraform", "output", "-raw", "ec2_public_ip"],
            cwd=TERRAFORM_DIR,
            capture_output=True, text=True
        )
        public_ip = result.stdout.strip()
        click.echo(f"Deployment complete at: http://{public_ip}")

    else:
        click.echo("EC2 already exists. Deploying remotely with SSH...")

        result = subprocess.run(
            ["terraform", "output", "-raw", "ec2_public_ip"],
            cwd=TERRAFORM_DIR,
            capture_output=True, text=True
        )
        public_ip = result.stdout.strip()

        ssh_command = f"""
        set -e
        cd /home/ubuntu
        aws s3 cp s3://{bucket}/{artifact_key} artifact.zip
        sudo rm -rf app && unzip -o artifact.zip -d app
        cd app
        sudo docker rm -f my-app || true
        sudo docker build -t my-app .
        sudo docker run -d --name my-app -p 80:80 my-app
        """

        try:
            subprocess.run([
                "ssh", "-o", "StrictHostKeyChecking=no",
                "-i", KEY_NAME,
                f"ubuntu@{public_ip}",
                ssh_command
            ], check=True)
            click.echo(f"App deployed via SSH to EC2: http://{public_ip}")
        except subprocess.CalledProcessError as e:
            click.echo("SSH deployment failed.")
            click.echo(str(e))


@cli.command("rollback")
def rollback_command():
    with open(DEPLOY_CONFIG) as f:
        config = yaml.safe_load(f)

    project = config["folder"]
    bucket = config["bucket"]
    prefix = f"{project}/"

    s3 = boto3.client("s3")
    resp = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
    artifacts = sorted(
        [obj["Key"] for obj in resp.get("Contents", []) if obj["Key"].endswith(".zip")],
        reverse=True
    )

    if len(artifacts) < 2:
        click.echo("Not enough artifacts to roll back")
        return

    click.echo("Available artifacts:")
    for idx, key in enumerate(artifacts):
        click.echo(f"{idx+1}: {key}")

    choice = click.prompt("Enter number of artifact to roll back to", type=int, default=2)
    if not (1 <= choice <= len(artifacts)):
        click.echo("Invalid choice")
        return

    artifact_key = artifacts[choice - 1]
    rb_meta = {"artifact_key": artifact_key, "rolled_back_at": datetime.utcnow().isoformat()}
    with open(ROLLBACK_INFO, "w") as f:
        yaml.dump(rb_meta, f)

    click.echo(f"Marked rollback to {artifact_key}. Now run `python main.py deploy`")


@cli.command("monitor")
def monitor():
    """Set up Node Exporter + Prometheus + Grafana stack"""
    with open("deploy-tool.yml") as f:
        config = yaml.safe_load(f)

    ec2_ip = subprocess.check_output(
        ["terraform", "output", "-raw", "ec2_public_ip"],
        cwd=os.path.abspath("terraform")
    ).decode().strip()

    subprocess.run([
        "ssh", "-i", KEY_NAME, f"ubuntu@{ec2_ip}",
        "bash -c \"cd /tmp && wget -q https://github.com/prometheus/node_exporter/releases/download/v1.8.1/node_exporter-1.8.1.linux-amd64.tar.gz && tar xzf node_exporter-1.8.1.linux-amd64.tar.gz && sudo mv node_exporter-1.8.1.linux-amd64/node_exporter /usr/local/bin/ && sudo useradd -rs /bin/false node_exporter || true && sudo tee /etc/systemd/system/node_exporter.service > /dev/null <<EOL\n[Unit]\nDescription=Prometheus Node Exporter\nAfter=network.target\n[Service]\nUser=node_exporter\nGroup=node_exporter\nType=simple\nExecStart=/usr/local/bin/node_exporter\n[Install]\nWantedBy=multi-user.target\nEOL\nsudo systemctl daemon-reload && sudo systemctl restart node_exporter\""
    ], check=True)

    prom_conf = f"""
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'ec2-node-exporter'
    static_configs:
      - targets: ['{ec2_ip}:9100']
"""

    with open("prometheus.yml", "w") as f:
        f.write(prom_conf)

    subprocess.run([
        "docker", "run", "-d", "--name", "prometheus",
        "-p", "9090:9090",
        "-v", f"{os.path.abspath('prometheus.yml')}:/etc/prometheus/prometheus.yml",
        "prom/prometheus"
    ], check=False)

    subprocess.run([
        "docker", "run", "-d", "--name", "grafana",
        "-p", "3000:3000",
        "grafana/grafana"
    ], check=False)

    click.echo("Monitoring now available:")
    click.echo("  Prometheus: http://localhost:9090")
    click.echo("  Grafana: http://localhost:3000 (admin/admin)")
    click.echo(f"  Node Exporter: http://{ec2_ip}:9100/metrics")

@cli.command("rollback")
def rollback_command():
    click.echo("===== Starting automatic rollback =====")

    # Load deploy-tool config
    with open(DEPLOY_CONFIG) as f:
        config = yaml.safe_load(f)

    folder = config["folder"]
    bucket = config["bucket"]
    project = config.get("project", folder)
    key_path =  r"C:\Users\Minfy\Downloads\key-18.pem"
    ssh_user = config.get("ssh_user", "ubuntu")

    if not key_path or not os.path.exists(key_path):
        click.echo(f"ERROR: SSH key not found at {key_path}")
        return

    # Load deploy history
    history_path = os.path.join("deploy_history.json")
    if not os.path.exists(history_path):
        click.echo("ERROR: deploy_history.json missing.")
        return

    with open(history_path) as f:
        history = json.load(f)

    previous_artifact = history.get("previous")
    if not previous_artifact:
        click.echo("There's no previous version to roll back to.")
        return

    # Get EC2 public IP from terraform output
    result = subprocess.run(
        ["terraform", "output", "-raw", "ec2_public_ip"],
        cwd=os.path.abspath("terraform"),
        capture_output=True, text=True
    )
    ec2_ip = result.stdout.strip()

    click.echo(f"Rolling back to: {previous_artifact}")
    click.echo(f"Deploying to EC2 instance: {ec2_ip}")

    # Remote SSH command to replace container
    ssh_command = f"""
        set -e
        cd /home/ubuntu
        aws s3 cp s3://{bucket}/{previous_artifact} artifact.zip
        sudo rm -rf app && unzip -o artifact.zip -d app
        cd app
        sudo docker rm -f my-app || true
        sudo docker build -t my-app .
        sudo docker run -d --name my-app -p 80:80 my-app
    """

    try:
        subprocess.run([
            "ssh", "-o", "StrictHostKeyChecking=no",
            "-i", key_path,
            f"{ssh_user}@{ec2_ip}",
            ssh_command
        ], check=True)
        click.echo("Rollback completed successfully.")
        click.echo(f" App is now live at: http://{ec2_ip}")

        # Also update history: rollback reversed latest/previous
        history["latest"], history["previous"] = history["previous"], history["latest"]
        with open(history_path, "w") as f:
            json.dump(history, f, indent=2)
        click.echo("Updated deploy_history.json after rollback.")

    except subprocess.CalledProcessError as e:
        click.echo("Rollback failed during SSH or deployment.")
        click.echo(str(e))
