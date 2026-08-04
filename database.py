import os

import boto3
from dotenv import load_dotenv

load_dotenv()

_resource_kwargs = {
    "region_name": os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
}
_endpoint_url = os.environ.get("DYNAMODB_ENDPOINT_URL")
if _endpoint_url:
    # DynamoDB Local doesn't validate credentials but boto3 still requires
    # some value to be present; everywhere else, omit these so boto3's
    # default credential chain (IRSA on EKS) is used instead.
    _resource_kwargs["endpoint_url"] = _endpoint_url
    _resource_kwargs["aws_access_key_id"] = os.environ.get("AWS_ACCESS_KEY_ID", "local")
    _resource_kwargs["aws_secret_access_key"] = os.environ.get("AWS_SECRET_ACCESS_KEY", "local")
dynamodb = boto3.resource("dynamodb", **_resource_kwargs)

orders_table = dynamodb.Table(os.environ.get("DYNAMODB_TABLE_NAME", "order-service-table"))
