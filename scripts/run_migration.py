"""
Run SQL migration via a temporary Lambda inside the VPC.

This script:
1. Creates a temporary Lambda function in the VPC (with RDS Proxy access)
2. Invokes it with the SQL file contents
3. Prints the result
4. Deletes the temporary Lambda

Usage:
    python scripts/run_migration.py \\
        --stack anycompany-booking \\
        --db-name anycompany \\
        --db-user anycompany_admin \\
        --db-password <password> \\
        --sql-file scripts/migrations/003_pms_schema.sql \\
        --profile <your-profile> \\
        --region us-east-1

Note: --db-password is needed because the lambda_user DB role uses IAM auth,
but for DDL operations we connect as the master user (anycompany_admin) with
a password stored in Secrets Manager.
"""

import argparse
import base64
import json
import os
import sys
import time
import uuid
import zipfile
from io import BytesIO

import boto3


LAMBDA_CODE = '''
import json
import os
import boto3

def handler(event, context):
    sql = event["sql"]
    db_host = os.environ["DB_HOST"]
    db_name = os.environ["DB_NAME"]
    db_user = os.environ["DB_USER"]
    region = os.environ.get("AWS_REGION", "us-east-1")

    # Generate IAM auth token for RDS Proxy
    rds = boto3.client("rds", region_name=region)
    token = rds.generate_db_auth_token(
        DBHostname=db_host, Port=5432, DBUsername=db_user, Region=region
    )

    # Import psycopg from the layer
    import psycopg

    try:
        conn = psycopg.connect(
            host=db_host,
            dbname=db_name,
            user=db_user,
            password=token,
            port=5432,
            sslmode="require",
            connect_timeout=20,
        )
        with conn.cursor() as cur:
            cur.execute(sql)
            try:
                if cur.description:
                    rows = cur.fetchall()
                    result = f"Rows returned: {len(rows)}"
                else:
                    result = f"Statement executed. Rows affected: {cur.rowcount}"
            except Exception:
                result = "Statement executed."
        conn.commit()
        conn.close()
        return {"success": True, "message": result}
    except Exception as e:
        return {"success": False, "error": str(e)}
'''


def get_stack_output(cf_client, stack_name, key):
    response = cf_client.describe_stacks(StackName=stack_name)
    outputs = response["Stacks"][0]["Outputs"]
    for o in outputs:
        if o["OutputKey"] == key:
            return o["OutputValue"]
    return None


def get_stack_resource(cf_client, stack_name, logical_id):
    """Get a physical resource ID from a stack by logical ID (handles nested stacks)."""
    try:
        response = cf_client.describe_stack_resource(
            StackName=stack_name, LogicalResourceId=logical_id
        )
        return response["StackResourceDetail"]["PhysicalResourceId"]
    except Exception:
        return None


def get_nested_stack_name(cf_client, parent_stack, nested_logical_id):
    """Get the physical name of a nested stack."""
    try:
        response = cf_client.describe_stack_resource(
            StackName=parent_stack, LogicalResourceId=nested_logical_id
        )
        arn = response["StackResourceDetail"]["PhysicalResourceId"]
        # ARN format: arn:aws:cloudformation:region:account:stack/STACK_NAME/uuid
        return arn.split("/")[1]
    except Exception as e:
        print(f"ERROR: Could not find nested stack {nested_logical_id}: {e}")
        return None


def build_lambda_package():
    """Create a zip with the handler code."""
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("handler.py", LAMBDA_CODE)
    return buffer.getvalue()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stack", required=True, help="CloudFormation stack name (e.g., anycompany-booking)")
    parser.add_argument("--db-name", default="anycompany")
    parser.add_argument("--db-user", default="anycompany_admin")
    parser.add_argument("--sql-file", required=True, help="Path to SQL file")
    parser.add_argument("--profile", help="AWS profile name")
    parser.add_argument("--region", default="us-east-1")
    args = parser.parse_args()

    # Read SQL
    with open(args.sql_file, "r", encoding="utf-8") as f:
        sql = f.read()

    # Set up AWS clients
    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    cf = session.client("cloudformation")
    lambda_client = session.client("lambda")
    iam = session.client("iam")

    print(f"\n{'='*60}")
    print(f"Running migration: {args.sql_file}")
    print(f"Stack: {args.stack}")
    print(f"Database: {args.db_name}")
    print(f"{'='*60}\n")

    # Get DB proxy host
    db_host = get_stack_output(cf, args.stack, "DBProxyHost")
    if not db_host:
        print("ERROR: Could not find DBProxyHost in stack outputs")
        return 1

    # Get VPC details from VPCStack
    vpc_stack_name = get_nested_stack_name(cf, args.stack, "VPCStack")
    private_subnet_ids = get_stack_output(cf, vpc_stack_name, "PrivateSubnetIds").split(",")
    security_group_id = get_stack_output(cf, vpc_stack_name, "LambdaSecurityGroupId")

    # Get DB secret ARN from DatabaseStack
    db_stack_name = get_nested_stack_name(cf, args.stack, "DatabaseStack")
    secret_arn = get_stack_output(cf, db_stack_name, "DBSecretArn")

    # Get CommonLayer ARN — SAM hashes the logical ID, find by resource type
    layers = cf.list_stack_resources(StackName=args.stack)["StackResourceSummaries"]
    common_layer_arn = None
    for r in layers:
        if r["ResourceType"] == "AWS::Lambda::LayerVersion" and "CommonLayer" in r["LogicalResourceId"]:
            common_layer_arn = r["PhysicalResourceId"]
            break
    if not common_layer_arn:
        print("ERROR: Could not find CommonLayer")
        return 1

    # Get Lambda execution role name
    response = cf.describe_stack_resource(StackName=args.stack, LogicalResourceId="LambdaMigrationRole")
    role_name = response["StackResourceDetail"]["PhysicalResourceId"]
    account_id = session.client("sts").get_caller_identity()["Account"]
    role_arn_full = f"arn:aws:iam::{account_id}:role/{role_name}"

    # Create temporary Lambda
    function_name = f"migration-runner-{uuid.uuid4().hex[:8]}"
    print(f"Creating temporary Lambda: {function_name}")

    zip_bytes = build_lambda_package()

    try:
        lambda_client.create_function(
            FunctionName=function_name,
            Runtime="python3.12",
            # Must match the CommonLayer's build architecture (arm64). Without
            # this, create_function defaults to x86_64 and the arm64 psycopg
            # binary in the layer fails to load ("no pq wrapper available").
            Architectures=["arm64"],
            Role=role_arn_full,
            Handler="handler.handler",
            Code={"ZipFile": zip_bytes},
            Timeout=300,
            MemorySize=512,
            VpcConfig={
                "SubnetIds": private_subnet_ids,
                "SecurityGroupIds": [security_group_id],
            },
            Environment={
                "Variables": {
                    "DB_HOST": db_host,
                    "DB_NAME": args.db_name,
                    "DB_USER": args.db_user,
                }
            },
            Layers=[common_layer_arn],
        )

        # Wait for function to be active
        print("Waiting for Lambda to be ready...")
        waiter = lambda_client.get_waiter("function_active_v2")
        waiter.wait(FunctionName=function_name)

        print("Invoking Lambda with SQL...")
        response = lambda_client.invoke(
            FunctionName=function_name,
            Payload=json.dumps({"sql": sql}).encode(),
        )

        result = json.loads(response["Payload"].read())

        print(f"\n{'='*60}")
        if result.get("success"):
            print(f"✓ SUCCESS: {result.get('message', 'Done')}")
        else:
            print(f"✗ FAILED: {result.get('error', 'Unknown error')}")
            return 1
        print(f"{'='*60}\n")

    finally:
        # Cleanup
        print(f"Deleting temporary Lambda: {function_name}")
        try:
            lambda_client.delete_function(FunctionName=function_name)
        except Exception as e:
            print(f"Warning: Could not delete Lambda: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
