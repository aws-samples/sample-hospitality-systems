"""
Seed PMS loyalty data via a temporary Lambda inside the VPC.

Creates/updates guest profiles with loyalty tiers, points, and booking history.
"""

import argparse
import json
import sys
import uuid
import zipfile
from io import BytesIO

import boto3


# Guest data matching Cognito users (same as seed_pms_data.py)
GUESTS_JSON = '''[
    {"email": "sarah.chen@example.com", "first_name": "Sarah", "last_name": "Chen",
     "tier": "DIAMOND", "total_stays": 25, "points_balance": 45000, "lifetime_points": 125000},
    {"email": "james.wilson@example.com", "first_name": "James", "last_name": "Wilson",
     "tier": "GOLD", "total_stays": 14, "points_balance": 22000, "lifetime_points": 68000},
    {"email": "maria.garcia@example.com", "first_name": "Maria", "last_name": "Garcia",
     "tier": "GOLD", "total_stays": 11, "points_balance": 15500, "lifetime_points": 48000},
    {"email": "david.park@example.com", "first_name": "David", "last_name": "Park",
     "tier": "SILVER", "total_stays": 7, "points_balance": 8200, "lifetime_points": 24000},
    {"email": "priya.patel@example.com", "first_name": "Priya", "last_name": "Patel",
     "tier": "SILVER", "total_stays": 5, "points_balance": 5100, "lifetime_points": 15000},
    {"email": "alex.johnson@example.com", "first_name": "Alex", "last_name": "Johnson",
     "tier": "NONE", "total_stays": 2, "points_balance": 1200, "lifetime_points": 3600},
    {"email": "emma.thompson@example.com", "first_name": "Emma", "last_name": "Thompson",
     "tier": "NONE", "total_stays": 1, "points_balance": 450, "lifetime_points": 450},
    {"email": "carlos.rivera@example.com", "first_name": "Carlos", "last_name": "Rivera",
     "tier": "NONE", "total_stays": 0, "points_balance": 0, "lifetime_points": 0}
]'''


LAMBDA_CODE = '''
import json
import os
import uuid
import random
import boto3
from datetime import date, timedelta

def handler(event, context):
    db_host = os.environ["DB_HOST"]
    db_name = os.environ["DB_NAME"]
    db_user = os.environ["DB_USER"]
    region = os.environ.get("AWS_REGION", "us-east-1")
    guests = json.loads(event["guests"])

    # Generate IAM auth token
    rds = boto3.client("rds", region_name=region)
    token = rds.generate_db_auth_token(
        DBHostname=db_host, Port=5432, DBUsername=db_user, Region=region
    )

    import psycopg
    from psycopg.rows import dict_row

    log_messages = []
    try:
        conn = psycopg.connect(
            host=db_host, dbname=db_name, user=db_user, password=token,
            port=5432, sslmode="require", connect_timeout=20, row_factory=dict_row,
        )

        with conn.cursor() as cur:
            # Seed guests with loyalty data
            guest_ids = {}
            for guest in guests:
                cur.execute("SELECT guest_id FROM guests WHERE email = %s", [guest["email"]])
                row = cur.fetchone()
                if row:
                    guest_id = row["guest_id"]
                    cur.execute(
                        "UPDATE guests SET loyalty_tier = %s, total_stays = %s, "
                        "points_balance = %s, lifetime_points_earned = %s, updated_at = now() "
                        "WHERE guest_id = %s",
                        [guest["tier"], guest["total_stays"], guest["points_balance"],
                         guest["lifetime_points"], guest_id],
                    )
                    log_messages.append(f"Updated: {guest['email']} ({guest['tier']})")
                else:
                    guest_id = str(uuid.uuid4())
                    cur.execute(
                        "INSERT INTO guests (guest_id, cognito_sub, first_name, last_name, email, "
                        "loyalty_tier, total_stays, points_balance, lifetime_points_earned) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        [guest_id, guest.get("cognito_sub"), guest["first_name"], guest["last_name"], guest["email"],
                         guest["tier"], guest["total_stays"], guest["points_balance"],
                         guest["lifetime_points"]],
                    )
                    log_messages.append(f"Created: {guest['email']} ({guest['tier']})")
                guest_ids[guest["email"]] = str(guest_id)

            # Get property IDs and room types for booking history
            cur.execute("SELECT property_id FROM properties LIMIT 10")
            properties = [str(row["property_id"]) for row in cur.fetchall()]

            if not properties:
                conn.commit()
                return {"success": True, "messages": log_messages,
                        "warning": "No properties found; skipping booking history"}

            # Get a valid room_type_id for each property
            property_room_types = {}
            for prop_id in properties:
                cur.execute(
                    "SELECT room_type_id FROM room_types WHERE property_id = %s LIMIT 1",
                    [prop_id]
                )
                rt = cur.fetchone()
                if rt:
                    property_room_types[prop_id] = str(rt["room_type_id"])

            # Get a valid rate_plan_id for each property — reservations.rate_plan_id is NOT NULL.
            property_rate_plans = {}
            for prop_id in properties:
                cur.execute(
                    "SELECT rate_plan_id FROM rate_plans WHERE property_id = %s LIMIT 1",
                    [prop_id]
                )
                rp = cur.fetchone()
                if rp:
                    property_rate_plans[prop_id] = str(rp["rate_plan_id"])

            # Create booking history for guests with stays
            for guest in guests:
                if guest["total_stays"] == 0:
                    continue
                guest_id = guest_ids[guest["email"]]
                stays_to_create = min(guest["total_stays"], 3)

                created = 0
                for i in range(stays_to_create):
                    if not property_room_types:
                        break
                    property_id = random.choice(list(property_room_types.keys()))
                    room_type_id = property_room_types[property_id]
                    rate_plan_id = property_rate_plans.get(property_id)
                    if not rate_plan_id:
                        continue
                    check_in = date.today() - timedelta(days=random.randint(30, 365))
                    nights = random.randint(1, 5)
                    check_out = check_in + timedelta(days=nights)
                    rate = random.choice([149, 199, 249, 299, 349])
                    total = rate * nights
                    reservation_id = str(uuid.uuid4())
                    # confirmation_number must be unique; uuid hex slice works.
                    confirmation_number = f"RES-{uuid.uuid4().hex[:8].upper()}"

                    try:
                        cur.execute(
                            "INSERT INTO reservations "
                            "(reservation_id, confirmation_number, property_id, guest_id, "
                            "room_type_id, rate_plan_id, "
                            "check_in_date, check_out_date, status, total_after_tax, "
                            "checked_in_at, checked_out_at, adults, children) "
                            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, \\'CHECKED_OUT\\', %s, %s, %s, 2, 0)",
                            [reservation_id, confirmation_number, property_id, guest_id,
                             room_type_id, rate_plan_id,
                             check_in, check_out, total, check_in, check_out],
                        )

                        # Create loyalty transaction
                        multipliers = {"NONE": 1.0, "SILVER": 1.25, "GOLD": 1.5, "DIAMOND": 2.0}
                        points = int(rate * nights * multipliers.get(guest["tier"], 1.0))
                        cur.execute(
                            "INSERT INTO loyalty_transactions "
                            "(guest_id, reservation_id, transaction_type, points, "
                            "balance_after, description) "
                            "VALUES (%s, %s, \\'EARN_STAY\\', %s, %s, %s)",
                            [guest_id, reservation_id, points, guest["points_balance"],
                             f"Earned {points} points for {nights}-night stay"],
                        )
                        created += 1
                    except Exception as e:
                        log_messages.append(f"  Skipped reservation for {guest['email']}: {str(e)[:100]}")

                log_messages.append(f"{guest['email']}: created {created} past reservations")

        conn.commit()
        conn.close()
        return {"success": True, "messages": log_messages}
    except Exception as e:
        return {"success": False, "error": str(e), "messages": log_messages}
'''


def get_stack_output(cf_client, stack_name, key):
    response = cf_client.describe_stacks(StackName=stack_name)
    for o in response["Stacks"][0]["Outputs"]:
        if o["OutputKey"] == key:
            return o["OutputValue"]
    return None


def get_nested_stack_name(cf_client, parent_stack, nested_logical_id):
    try:
        response = cf_client.describe_stack_resource(
            StackName=parent_stack, LogicalResourceId=nested_logical_id
        )
        arn = response["StackResourceDetail"]["PhysicalResourceId"]
        return arn.split("/")[1]
    except Exception:
        return None


def build_lambda_package():
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("handler.py", LAMBDA_CODE)
    return buffer.getvalue()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stack", required=True)
    parser.add_argument("--db-name", default="anycompany")
    parser.add_argument("--db-user", default="anycompany_admin")
    parser.add_argument("--user-pool-id", required=True, help="Cognito User Pool ID")
    parser.add_argument("--profile")
    parser.add_argument("--region", default="us-east-1")
    args = parser.parse_args()

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    cf = session.client("cloudformation")
    lambda_client = session.client("lambda")
    cognito = session.client("cognito-idp")

    # Enrich guest data with Cognito sub
    guests = json.loads(GUESTS_JSON)
    print("Looking up Cognito sub for each guest...")
    for guest in guests:
        try:
            response = cognito.admin_get_user(
                UserPoolId=args.user_pool_id, Username=guest["email"]
            )
            sub = next(attr["Value"] for attr in response["UserAttributes"] if attr["Name"] == "sub")
            guest["cognito_sub"] = sub
            print(f"  {guest['email']}: {sub}")
        except Exception as e:
            print(f"  WARNING: Could not find Cognito user for {guest['email']}: {e}")
            guest["cognito_sub"] = None

    guests_json = json.dumps(guests)

    print(f"\nSeeding PMS data for stack: {args.stack}\n")

    db_host = get_stack_output(cf, args.stack, "DBProxyHost")
    vpc_stack = get_nested_stack_name(cf, args.stack, "VPCStack")
    subnet_ids = get_stack_output(cf, vpc_stack, "PrivateSubnetIds").split(",")
    sg_id = get_stack_output(cf, vpc_stack, "LambdaSecurityGroupId")

    # Find CommonLayer
    layers = cf.list_stack_resources(StackName=args.stack)["StackResourceSummaries"]
    common_layer_arn = None
    for r in layers:
        if r["ResourceType"] == "AWS::Lambda::LayerVersion" and "CommonLayer" in r["LogicalResourceId"]:
            common_layer_arn = r["PhysicalResourceId"]
            break

    response = cf.describe_stack_resource(StackName=args.stack, LogicalResourceId="LambdaMigrationRole")
    role_name = response["StackResourceDetail"]["PhysicalResourceId"]
    account_id = session.client("sts").get_caller_identity()["Account"]
    role_arn = f"arn:aws:iam::{account_id}:role/{role_name}"

    function_name = f"pms-seed-runner-{uuid.uuid4().hex[:8]}"
    print(f"Creating temporary Lambda: {function_name}")

    zip_bytes = build_lambda_package()

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
            Timeout=300,
            MemorySize=512,
            VpcConfig={"SubnetIds": subnet_ids, "SecurityGroupIds": [sg_id]},
            Environment={
                "Variables": {
                    "DB_HOST": db_host,
                    "DB_NAME": args.db_name,
                    "DB_USER": args.db_user,
                }
            },
            Layers=[common_layer_arn],
        )

        print("Waiting for Lambda to be ready...")
        lambda_client.get_waiter("function_active_v2").wait(FunctionName=function_name)

        print("Invoking Lambda with seed data...\n")
        response = lambda_client.invoke(
            FunctionName=function_name,
            Payload=json.dumps({"guests": guests_json}).encode(),
        )

        result = json.loads(response["Payload"].read())
        for msg in result.get("messages", []):
            print(f"  {msg}")
        print()
        if result.get("success"):
            print("✓ PMS seed complete!")
        else:
            print(f"✗ FAILED: {result.get('error', 'Unknown')}")
            return 1

    finally:
        print(f"\nDeleting temporary Lambda: {function_name}")
        try:
            lambda_client.delete_function(FunctionName=function_name)
        except Exception as e:
            print(f"  (ignored) could not delete {function_name}: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
