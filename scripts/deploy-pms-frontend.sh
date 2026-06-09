#!/bin/bash
# Build and deploy PMS frontend to S3/CloudFront
# Usage: ./scripts/deploy-pms-frontend.sh [environment]

set -e

ENV=${1:-dev}
STACK_NAME="anycompany-booking"
REGION="${AWS_REGION:-us-east-1}"
PROFILE="${AWS_PROFILE:-default}"

echo "=== Deploying PMS Frontend ($ENV) ==="

# Get bucket and distribution from stack outputs
BUCKET=$(aws cloudformation describe-stacks \
  --profile "$PROFILE" \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='PmsFrontendBucketName'].OutputValue" \
  --output text)

DISTRIBUTION_ID=$(aws cloudformation describe-stacks \
  --profile "$PROFILE" \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='PmsCloudFrontDistributionId'].OutputValue" \
  --output text 2>/dev/null || echo "")

echo "Bucket: $BUCKET"
echo "Distribution: $DISTRIBUTION_ID"

# Build
echo "Building PMS frontend..."
cd pms-frontend
# npm ci installs strictly from package-lock.json (ignoring the caret ranges in
# package.json), so deploys are reproducible — matches deploy-frontend.sh.
npm ci
npm run build
cd ..

# Sync to S3
echo "Syncing to S3..."
aws s3 sync pms-frontend/dist/ "s3://$BUCKET/" \
  --profile "$PROFILE" \
  --delete \
  --region "$REGION"

# Invalidate CloudFront cache
if [ -n "$DISTRIBUTION_ID" ] && [ "$DISTRIBUTION_ID" != "None" ]; then
  echo "Invalidating CloudFront cache..."
  aws cloudfront create-invalidation \
    --profile "$PROFILE" \
    --distribution-id "$DISTRIBUTION_ID" \
    --paths "/*" \
    --region "$REGION"
fi

# Get URL
PMS_URL=$(aws cloudformation describe-stacks \
  --profile "$PROFILE" \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='PmsCloudFrontUrl'].OutputValue" \
  --output text)

echo ""
echo "=== PMS Frontend Deployed ==="
echo "URL: $PMS_URL"
echo ""
