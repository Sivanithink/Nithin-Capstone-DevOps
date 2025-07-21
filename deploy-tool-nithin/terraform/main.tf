provider "aws" {
  region = var.aws_region
}

data "aws_iam_role" "ec2_deploy_role" {
  name = "deploy-tool-role"
}

data "aws_vpc" "default" {
  default = true
}

resource "aws_security_group" "deploy_sg" {
  name        = "deploy-tool-sg"
  description = "Allow HTTP, SSH, and app port"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    description = "Grafana"
    from_port   = 3000
    to_port     = 3000
    protocol    = "tcp"
    cidr_blocks =  ["0.0.0.0/0"] 
  }

  ingress {
    description = "Prometheus"
    from_port   = 9090
    to_port     = 9090
    protocol    = "tcp"
    cidr_blocks =  ["0.0.0.0/0"] 
  }
    ingress {
    description = "Node Exporter"
    from_port   = 9100
    to_port     = 9100
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }


  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "deploy_ec2" {
  ami                    = "ami-08e5424edfe926b43"
  instance_type          = "t3.micro"
  key_name               = "key-18"
  vpc_security_group_ids = [aws_security_group.deploy_sg.id]
  iam_instance_profile   = data.aws_iam_role.ec2_deploy_role.name

  user_data = templatefile("${path.module}/user_data.sh.tpl", {
  bucket_name           = var.bucket_name
  project_name          = var.ec2_name
  NODE_EXPORTER_VERSION = "1.8.1"
})


  tags = {
    Name = var.ec2_name
  }
}

output "ec2_public_ip" {
  value = aws_instance.deploy_ec2.public_ip
}

output "s3_bucket_used" {
  value = var.bucket_name
}