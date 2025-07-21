#!/bin/bash
set -e


exec > >(tee /var/log/user-data.log | logger -t user-data | tee -a /home/ubuntu/deploy-debug.log) 2>&1


SECTION() {
  echo -e "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo -e "INFO: $1"
  echo -e "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
}


SECTION "Starting EC2 boot init"


SECTION "Updating system and installing basic tools"
sudo apt-get update -y
sudo apt-get install -y unzip curl ca-certificates gnupg lsb-release


SECTION "Installing AWS CLI v2"
cd /tmp
curl -s https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip -o awscliv2.zip
unzip -q awscliv2.zip
sudo ./aws/install
export PATH=$PATH:/usr/local/bin
aws --version || { echo "ERROR: AWS CLI installation failed"; exit 1; }


SECTION "Installing Docker"
sudo apt-get remove -y docker docker-engine docker.io containerd runc || true
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update -y
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin
sudo systemctl enable docker
sudo systemctl start docker
docker --version || { echo "ERROR: Docker installation failed"; exit 1; }


SECTION "Fetching and deploying app from S3"
cd /home/ubuntu


ARTIFACT=$(aws s3 ls s3://${bucket_name}/${project_name}/ | awk '{print $4}' | grep build_artifact | sort | tail -n 1)


if [ -z "$ARTIFACT" ]; then
  echo "ERROR: No artifact found in s3://${bucket_name}/${project_name}/"
  exit 1
fi


echo "Artifact found: $ARTIFACT"
aws s3 cp s3://${bucket_name}/${project_name}/$ARTIFACT artifact.zip || { echo "ERROR: Failed to download artifact from S3"; exit 1; }


SECTION "Unzipping artifact"
unzip -o artifact.zip -d app || { echo "ERROR: Failed to unzip artifact"; exit 1; }


SECTION "Validating Dockerfile"
if [ ! -f app/Dockerfile ]; then
  echo "ERROR: Dockerfile missing inside artifact"
  exit 1
fi


cd app


SECTION "Cleaning up old Docker container (if any)"
sudo docker rm -f my-app || true


SECTION "Building Docker image"
sudo docker build -t my-app . || { echo "ERROR: Docker build failed"; exit 1; }


SECTION "Running Docker container on port 80"
sudo docker run -d --name my-app -p 80:80 my-app || { echo "ERROR: Docker run failed"; exit 1; }




SECTION "Installing Prometheus Node Exporter"
cd /tmp
NODE_EXPORTER_VERSION="1.8.1"
wget -q https://github.com/prometheus/node_exporter/releases/download/v${NODE_EXPORTER_VERSION}/node_exporter-${NODE_EXPORTER_VERSION}.linux-amd64.tar.gz
tar xzvf node_exporter-${NODE_EXPORTER_VERSION}.linux-amd64.tar.gz
sudo mv node_exporter-${NODE_EXPORTER_VERSION}.linux-amd64/node_exporter /usr/local/bin/
sudo useradd -rs /bin/false node_exporter || true


sudo tee /etc/systemd/system/node_exporter.service > /dev/null <<EOF
[Unit]
Description=Prometheus Node Exporter
After=network.target


[Service]
User=node_exporter
Group=node_exporter
Type=simple
ExecStart=/usr/local/bin/node_exporter


[Install]
WantedBy=multi-user.target
EOF


sudo systemctl daemon-reload
sudo systemctl enable node_exporter
sudo systemctl start node_exporter


echo "Node Exporter is running and exposing metrics on port 9100

