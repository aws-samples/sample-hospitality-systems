"""
Finalize the simulator service user after `sam deploy`.

CFN creates the simulator user in FORCE_CHANGE_PASSWORD state with no real password.
This script:
  1. Reads the auto-generated password from Secrets Manager.
  2. Calls AdminSetUserPassword with Permanent=True to flip the user to CONFIRMED.

Run after every `sam deploy` that recreates the SimulatorUser resource. Idempotent —
re-running just re-applies the same password.

Usage:
    python scripts/finalize_simulator_user.py \\
        --stack anycompany-booking \\
        --profile <your-profile> \\
        --region us-east-1
"""

import argparse
import json
import sys

import boto3


def get_stack_output(cf_client, stack_name, key):
    response = cf_client.describe_stacks(StackName=stack_name)
    for output in response["Stacks"][0]["Outputs"]:
        if output["OutputKey"] == key:
            return output["OutputValue"]
    return None


def get_stack_resource_physical_id(cf_client, stack_name, logical_id):
    response = cf_client.describe_stack_resource(
        StackName=stack_name, LogicalResourceId=logical_id,
    )
    return response["StackResourceDetail"]["PhysicalResourceId"]


def main():
    parser = argparse.ArgumentParser(description="Finalize the simulator user post-deploy")
    parser.add_argument("--stack", default="anycompany-booking", help="Root CloudFormation stack name")
    parser.add_argument("--profile", help="AWS profile name")
    parser.add_argument("--region", default="us-east-1")
    args = parser.parse_args()

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    cf = session.client("cloudformation")
    cognito = session.client("cognito-idp")
    sm = session.client("secretsmanager")

    print(f"\n{'=' * 60}")
    print("Finalizing simulator user")
    print(f"Stack: {args.stack}")
    print(f"{'=' * 60}\n")

    user_pool_id = get_stack_output(cf, args.stack, "UserPoolId")
    if not user_pool_id:
        print("ERROR: Could not find UserPoolId in stack outputs")
        return 1

    secret_arn = get_stack_resource_physical_id(cf, args.stack, "SimulatorCredsSecret")

    secret_value = sm.get_secret_value(SecretId=secret_arn)
    creds = json.loads(secret_value["SecretString"])
    username = creds["username"]
    password = creds["password"]

    print(f"User pool: {user_pool_id}")
    print(f"User: {username}")
    print("Setting permanent password...")

    cognito.admin_set_user_password(
        UserPoolId=user_pool_id,
        Username=username,
        Password=password,
        Permanent=True,
    )

    user = cognito.admin_get_user(UserPoolId=user_pool_id, Username=username)
    status = user["UserStatus"]
    print(f"\n{'=' * 60}")
    if status == "CONFIRMED":
        print("✓ User is CONFIRMED and ready to authenticate.")
    else:
        print(f"⚠ User status is '{status}' (expected CONFIRMED).")
    print(f"{'=' * 60}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
