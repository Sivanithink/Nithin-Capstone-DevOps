import boto3
import os
import click

def ensure_bucket(bucket):
    client = boto3.client("s3")
    region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
    try:
        if region == "us-east-1":
            client.create_bucket(Bucket=bucket)
        else:
            client.create_bucket(
                Bucket=bucket,
                CreateBucketConfiguration={"LocationConstraint": region}
            )
        print(f"Bucket '{bucket}' created.")
    except client.exceptions.BucketAlreadyOwnedByYou:
        print(f"Bucket '{bucket}' already exists.")
    except client.exceptions.BucketAlreadyExists:
        print(f"Bucket '{bucket}' (global) already exists.")

def set_website(bucket):
    client = boto3.client("s3")
    client.put_bucket_website(
        Bucket=bucket,
        WebsiteConfiguration={
            "IndexDocument": {"Suffix": "index.html"},
            "ErrorDocument": {"Key": "index.html"}
        }
    )

def upload_dir_to_s3(upload_path, bucket, prefix=""):
    client = boto3.client("s3")
    for root, dirs, files in os.walk(upload_path):
        for file in files:
            file_path = os.path.join(root, file)
            key = os.path.relpath(file_path, upload_path).replace("\\", "/")
            if prefix:
                key = f"{prefix.rstrip('/')}/{key}"
            client.upload_file(file_path, bucket, key)
            click.echo(f"Uploaded: {key}")
