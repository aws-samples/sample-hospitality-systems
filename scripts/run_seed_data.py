"""
Run scripts/seed_data.py via a temporary Lambda inside the VPC.

The CRS database lives in private subnets, so a laptop can't reach RDS Proxy
directly. This wrapper ships seed_data.py to a short-lived Lambda that has
VPC access and IAM-auth permissions to RDS Proxy, runs seed_database(), and
deletes itself afterward.

Usage:
    python scripts/run_seed_data.py \\
        --stack anycompany-booking \\
        --db-name anycompany \\
        --db-user anycompany_admin \\
        --profile <aws-profile> \\
        --region us-east-1
"""

import argparse
import json
import time
import uuid
import zipfile
from io import BytesIO
from pathlib import Path

import boto3


HANDLER_CODE = '''
import json
import os
import sys

import boto3


def handler(event, context):
    db_host = os.environ["DB_HOST"]
    db_name = os.environ["DB_NAME"]
    db_user = os.environ["DB_USER"]
    region = os.environ.get("AWS_REGION", "us-east-1")

    rds = boto3.client("rds", region_name=region)
    token = rds.generate_db_auth_token(
        DBHostname=db_host, Port=5432, DBUsername=db_user, Region=region
    )

    import psycopg
    from psycopg.rows import dict_row

    # seed_data.py is shipped alongside this handler in the zip.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import seed_data

    try:
        with psycopg.connect(
            host=db_host,
            dbname=db_name,
            user=db_user,
            password=token,
            port=5432,
            sslmode="require",
            connect_timeout=20,
            row_factory=dict_row,
        ) as conn:
            seed_data.seed_database(conn)
        return {"success": True, "message": "Seed complete"}
    except Exception as e:
        import traceback
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }
'''


def _stack_output(cf, stack, key):
    for o in cf.describe_stacks(StackName=stack)["Stacks"][0]["Outputs"]:
        if o["OutputKey"] == key:
            return o["OutputValue"]
    return None


def _nested_stack(cf, parent, logical_id):
    arn = cf.describe_stack_resource(
        StackName=parent, LogicalResourceId=logical_id
    )["StackResourceDetail"]["PhysicalResourceId"]
    return arn.split("/")[1]


def _common_layer(cf, stack):
    for r in cf.list_stack_resources(StackName=stack)["StackResourceSummaries"]:
        if (
            r["ResourceType"] == "AWS::Lambda::LayerVersion"
            and "CommonLayer" in r["LogicalResourceId"]
        ):
            return r["PhysicalResourceId"]
    return None


def _build_zip(seed_data_path: Path) -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("handler.py", HANDLER_CODE)
        zf.writestr("seed_data.py", seed_data_path.read_text(encoding="utf-8"))
    return buf.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stack", required=True)
    parser.add_argument("--db-name", default="anycompany")
    parser.add_argument("--db-user", default="anycompany_admin")
    parser.add_argument("--profile")
    parser.add_argument("--region", default="us-east-1")
    args = parser.parse_args()

    seed_data_path = Path(__file__).parent / "seed_data.py"
    if not seed_data_path.exists():
        print(f"ERROR: {seed_data_path} not found")
        return 1

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    cf = session.client("cloudformation")
    # Boto3 default read timeout is 60s — way too short for a multi-minute
    # synchronous Lambda invoke. Bump it so we wait for completion instead of
    # racing into a duplicate retry.
    from botocore.config import Config
    lambda_client = session.client(
        "lambda",
        config=Config(read_timeout=900, connect_timeout=10, retries={"max_attempts": 0}),
    )

    print(f"\n{'='*60}\nSeeding CRS data via temporary Lambda\nStack: {args.stack}\n{'='*60}")

    db_host = _stack_output(cf, args.stack, "DBProxyHost")
    if not db_host:
        print("ERROR: DBProxyHost not in stack outputs")
        return 1

    vpc_stack = _nested_stack(cf, args.stack, "VPCStack")
    private_subnets = _stack_output(cf, vpc_stack, "PrivateSubnetIds").split(",")
    sg_id = _stack_output(cf, vpc_stack, "LambdaSecurityGroupId")

    layer_arn = _common_layer(cf, args.stack)
    if not layer_arn:
        print("ERROR: CommonLayer not found")
        return 1

    role_name = cf.describe_stack_resource(
        StackName=args.stack, LogicalResourceId="LambdaMigrationRole"
    )["StackResourceDetail"]["PhysicalResourceId"]
    account_id = session.client("sts").get_caller_identity()["Account"]
    role_arn = f"arn:aws:iam::{account_id}:role/{role_name}"

    function_name = f"crs-seed-{uuid.uuid4().hex[:8]}"
    print(f"\nCreating temporary Lambda: {function_name}")

    zip_bytes = _build_zip(seed_data_path)

    try:
        lambda_client.create_function(
            FunctionName=function_name,
            Runtime="python3.12",
            # Match the CommonLayer's arm64 build (else the arm64 psycopg
            # binary won't load — "no pq wrapper available").
            Architectures=["arm64"],
            Role=role_arn,
            Handler="handler.handler",
            Code={"ZipFile": zip_bytes},
            Timeout=900,  # seed_data needs a few minutes (50 properties × 365 days)
            MemorySize=1024,
            VpcConfig={"SubnetIds": private_subnets, "SecurityGroupIds": [sg_id]},
            Environment={
                "Variables": {
                    "DB_HOST": db_host,
                    "DB_NAME": args.db_name,
                    "DB_USER": args.db_user,
                }
            },
            Layers=[layer_arn],
        )

        print("Waiting for Lambda to be ready...")
        lambda_client.get_waiter("function_active_v2").wait(FunctionName=function_name)

        print("Invoking Lambda (this can take 2–5 minutes)...")
        start = time.time()
        response = lambda_client.invoke(
            FunctionName=function_name,
            Payload=json.dumps({}).encode(),
            InvocationType="RequestResponse",
        )
        elapsed = time.time() - start
        print(f"Lambda finished in {elapsed:.1f}s")

        result = json.loads(response["Payload"].read())

        print(f"\n{'='*60}")
        if result.get("success"):
            print(f"✓ SUCCESS: {result.get('message', 'Done')}")
        else:
            print(f"✗ FAILED: {result.get('error', 'unknown error')}")
            if result.get("traceback"):
                print(result["traceback"])
            return 1
        print(f"{'='*60}\n")

    finally:
        print(f"Deleting temporary Lambda: {function_name}")
        try:
            lambda_client.delete_function(FunctionName=function_name)
        except Exception as e:
            print(f"Warning: could not delete Lambda: {e}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
