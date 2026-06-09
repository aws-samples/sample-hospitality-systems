#!/usr/bin/env bash
#
# teardown.sh — tear down the AnyCompany Hotels stack cleanly.
#
# With the sample's clean-teardown defaults (S3/Cognito/Aurora all delete with
# the stack), the only thing standing between you and a clean `sam delete` is
# that S3 will not delete a non-empty bucket — and versioned buckets need their
# object VERSIONS and DELETE MARKERS purged, not just the current objects. This
# script does that purge first, then deletes the stack, then sweeps the few
# secrets that are created out-of-band (and so are NOT part of the stack).
#
# Safe by default: it runs in DRY-RUN and prints what it would do. Pass --yes to
# actually perform the destructive steps.
#
# Usage:
#   scripts/teardown.sh [--stack NAME] [--region REGION] [--profile PROFILE] [--yes]
#
# Defaults: --stack anycompany-booking  --region us-east-1  --profile default
#
set -euo pipefail

STACK="anycompany-booking"
REGION="${AWS_REGION:-us-east-1}"
PROFILE="${AWS_PROFILE:-default}"
APPLY=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --stack)   STACK="$2"; shift 2 ;;
    --region)  REGION="$2"; shift 2 ;;
    --profile) PROFILE="$2"; shift 2 ;;
    --yes)     APPLY=true; shift ;;
    -h|--help)
      grep '^#' "$0" | sed 's/^#//'; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

AWS=(aws --region "$REGION" --profile "$PROFILE")

say()  { printf '\n=== %s ===\n' "$*"; }
note() { printf '  %s\n' "$*"; }
run()  {
  # Echo the command; only execute it when --yes was passed.
  printf '  $ %s\n' "$*"
  if $APPLY; then eval "$@"; fi
}

if $APPLY; then
  say "TEARDOWN (LIVE) — stack=$STACK region=$REGION profile=$PROFILE"
else
  say "TEARDOWN (DRY-RUN) — stack=$STACK region=$REGION profile=$PROFILE"
  note "No changes will be made. Re-run with --yes to execute."
fi

# ──────────────────────────────────────────────────────────────────────────
# 1. Discover the stack's S3 buckets (including nested stacks)
# ──────────────────────────────────────────────────────────────────────────
say "1. Discovering S3 buckets owned by the stack (and nested stacks)"

# Collect this stack plus any nested CloudFormation stacks it owns.
# (Portable to Bash 3.2 — no mapfile; split newline-delimited output via read.)
ALL_STACKS=()
while IFS= read -r s; do
  [[ -n "$s" ]] && ALL_STACKS+=("$s")
done < <(
  "${AWS[@]}" cloudformation list-stack-resources --stack-name "$STACK" \
    --query "StackResourceSummaries[?ResourceType=='AWS::CloudFormation::Stack'].PhysicalResourceId" \
    --output text 2>/dev/null | tr '\t' '\n'
)
ALL_STACKS+=("$STACK")

BUCKETS=()
for s in "${ALL_STACKS[@]}"; do
  [[ -z "$s" ]] && continue
  while IFS= read -r b; do
    [[ -n "$b" ]] && BUCKETS+=("$b")
  done < <(
    "${AWS[@]}" cloudformation list-stack-resources --stack-name "$s" \
      --query "StackResourceSummaries[?ResourceType=='AWS::S3::Bucket'].PhysicalResourceId" \
      --output text 2>/dev/null | tr '\t' '\n'
  )
done

if [[ ${#BUCKETS[@]} -eq 0 ]]; then
  note "No stack-owned buckets found (stack may already be gone)."
else
  for b in "${BUCKETS[@]}"; do note "bucket: $b"; done
fi

# ──────────────────────────────────────────────────────────────────────────
# 2. Empty each bucket — current objects AND all versions + delete markers
# ──────────────────────────────────────────────────────────────────────────
say "2. Emptying buckets (objects + versions + delete markers)"
note "Plain 'aws s3 rm' leaves versions/delete-markers behind on versioned"
note "buckets, which then block the stack delete. We purge versions explicitly."

for b in "${BUCKETS[@]}"; do
  [[ -z "$b" ]] && continue
  note "-- $b --"
  # Current objects (fast path).
  run "${AWS[*]} s3 rm \"s3://$b\" --recursive || true"
  # Versions + delete markers (needed for versioned buckets).
  run "${AWS[*]} s3api delete-objects --bucket \"$b\" \
        --delete \"\$(${AWS[*]} s3api list-object-versions --bucket \"$b\" \
          --query '{Objects: Versions[].{Key:Key,VersionId:VersionId}}' --output json)\" \
        >/dev/null 2>&1 || true"
  run "${AWS[*]} s3api delete-objects --bucket \"$b\" \
        --delete \"\$(${AWS[*]} s3api list-object-versions --bucket \"$b\" \
          --query '{Objects: DeleteMarkers[].{Key:Key,VersionId:VersionId}}' --output json)\" \
        >/dev/null 2>&1 || true"
done

# ──────────────────────────────────────────────────────────────────────────
# 3. Disable Aurora deletion protection if still enabled
# ──────────────────────────────────────────────────────────────────────────
say "3. Aurora deletion protection (defensive)"
note "Sample default is DeletionProtection: false, but a prod-flipped or older"
note "stack may still have it on — that would block the stack delete."

CLUSTER_ID="$(
  "${AWS[@]}" rds describe-db-clusters \
    --query "DBClusters[?starts_with(DBClusterIdentifier,'anycompany')].DBClusterIdentifier | [0]" \
    --output text 2>/dev/null || echo "None"
)"
if [[ "$CLUSTER_ID" != "None" && -n "$CLUSTER_ID" ]]; then
  PROT="$(
    "${AWS[@]}" rds describe-db-clusters --db-cluster-identifier "$CLUSTER_ID" \
      --query "DBClusters[0].DeletionProtection" --output text 2>/dev/null || echo "false"
  )"
  note "cluster: $CLUSTER_ID  (DeletionProtection=$PROT)"
  if [[ "$PROT" == "True" || "$PROT" == "true" ]]; then
    run "${AWS[*]} rds modify-db-cluster --db-cluster-identifier \"$CLUSTER_ID\" \
          --no-deletion-protection --apply-immediately >/dev/null"
  else
    note "Already off — nothing to do."
  fi
else
  note "No anycompany Aurora cluster found."
fi

# ──────────────────────────────────────────────────────────────────────────
# 4. Delete the CloudFormation stack
# ──────────────────────────────────────────────────────────────────────────
say "4. Deleting the stack with SAM"
run "sam delete --stack-name \"$STACK\" --region \"$REGION\" --profile \"$PROFILE\" --no-prompts"

# ──────────────────────────────────────────────────────────────────────────
# 5. Sweep secrets created out-of-band (NOT part of the stack)
# ──────────────────────────────────────────────────────────────────────────
say "5. Sweeping out-of-band secrets"
note "These are created by setup/seed scripts, not by the template, so they"
note "survive 'sam delete'. The simulator creds secret IS in the stack and is"
note "removed above (when the simulator is deployed)."

ENV_SUFFIX="dev"   # matches the committed samconfig Environment
for secret in \
  "anycompany-booking-stripe-${ENV_SUFFIX}" \
  "anycompany-booking-testsuite-creds-${ENV_SUFFIX}"
do
  if "${AWS[@]}" secretsmanager describe-secret --secret-id "$secret" >/dev/null 2>&1; then
    note "found: $secret"
    run "${AWS[*]} secretsmanager delete-secret --secret-id \"$secret\" \
          --force-delete-without-recovery >/dev/null"
  else
    note "absent: $secret (nothing to delete)"
  fi
done

# ──────────────────────────────────────────────────────────────────────────
# 6. Done
# ──────────────────────────────────────────────────────────────────────────
say "Done"
if $APPLY; then
  note "Teardown complete. Verify nothing remains:"
else
  note "Dry-run complete. Re-run with --yes to execute. Then verify with:"
fi
note "  ${AWS[*]} cloudformation describe-stacks --stack-name $STACK   # should error: not found"
note "  ${AWS[*]} s3 ls | grep anycompany                              # should be empty"
note "  ${AWS[*]} rds describe-db-clusters --query \"DBClusters[?starts_with(DBClusterIdentifier,'anycompany')]\""
