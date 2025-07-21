variable "aws_region" {
  default     = "ap-south-1"
  description = "AWS region"
}

variable "bucket_name" {
  default     = "my-app-18"
  description = "Name of existing S3 bucket"
}

variable "key_name" {
  type        = string
  description = "EC2 Key Pair name"
}

variable "ec2_name" {
  type        = string
  description = "EC2 Name tag and project dir"
}

variable "artifact_key" {
  type        = string
  description = "S3 key of the artifact to deploy (for rollback or new deploy)"
  default     = ""
}
