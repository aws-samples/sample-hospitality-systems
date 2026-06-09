#!/bin/bash
# Generate PMS frontend .env from CloudFormation stack outputs
# Usage: ./scripts/setup-pms-env.sh [environment]

set -e

ENV=${1:-dev}
STACK_NAME="anycompany-booking"
REGION="${AWS_REGION:-us-east-1}"
PROFILE="${AWS_PROFILE:-default}"

echo "Fetching stack outputs for $STACK_NAME ($ENV)..."

PMS_API_URL=$(aws cloudformation describe-stacks \
  --profile "$PROFILE" \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='PmsApiUrl'].OutputValue" \
  --output text)

USER_POOL_ID=$(aws cloudformation describe-stacks \
  --profile "$PROFILE" \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='UserPoolId'].OutputValue" \
  --output text)

USER_POOL_CLIENT_ID=$(aws cloudformation describe-stacks \
  --profile "$PROFILE" \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='UserPoolClientId'].OutputValue" \
  --output text)

echo "Writing pms-frontend/.env..."

cat > pms-frontend/.env << EOF
VITE_PMS_API_URL=$PMS_API_URL
VITE_USER_POOL_ID=$USER_POOL_ID
VITE_USER_POOL_CLIENT_ID=$USER_POOL_CLIENT_ID
VITE_ENVIRONMENT=$ENV
EOF

echo "Done! PMS frontend .env generated:"
cat pms-frontend/.env
