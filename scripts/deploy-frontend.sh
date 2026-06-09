#!/bin/bash
# Deploy frontend to S3 and invalidate CloudFront
set -euo pipefail

ENVIRONMENT="${1:-dev}"
REGION="${AWS_REGION:-us-east-1}"
STACK_NAME="anycompany-booking"
FRONTEND_DIR="$(dirname "$0")/../frontend"

echo "=== AnyCompany Hotel - Frontend Deployment ==="
echo "Environment: ${ENVIRONMENT}"

# Get S3 bucket and CloudFront distribution
BUCKET_NAME=$(aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}" \
    --query "Stacks[0].Outputs[?OutputKey=='FrontendBucket'].OutputValue" \
    --output text)

DISTRIBUTION_ID=$(aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}" \
    --query "Stacks[0].Outputs[?OutputKey=='CloudFrontDistributionId'].OutputValue" \
    --output text 2>/dev/null || echo "")

echo "S3 Bucket: ${BUCKET_NAME}"
echo "CloudFront: ${DISTRIBUTION_ID}"

# Build frontend
echo "Building frontend..."
cd "${FRONTEND_DIR}"
npm ci
npm run build

# Sync to S3
echo "Syncing to S3..."
aws s3 sync dist/ "s3://${BUCKET_NAME}/" \
    --delete \
    --cache-control "public, max-age=31536000, immutable" \
    --exclude "index.html" \
    --exclude "*.json"

# Upload index.html and JSON with no-cache
aws s3 cp dist/index.html "s3://${BUCKET_NAME}/index.html" \
    --cache-control "no-cache, no-store, must-revalidate"

# Upload any JSON config files with no-cache
find dist -name "*.json" -exec aws s3 cp {} "s3://${BUCKET_NAME}/{}" \
    --cache-control "no-cache" \; 2>/dev/null || true

# Invalidate CloudFront
if [ -n "${DISTRIBUTION_ID}" ] && [ "${DISTRIBUTION_ID}" != "None" ]; then
    echo "Invalidating CloudFront cache..."
    aws cloudfront create-invalidation \
        --distribution-id "${DISTRIBUTION_ID}" \
        --paths "/*" \
        --query "Invalidation.Id" \
        --output text
    echo "CloudFront invalidation initiated"
fi

CLOUDFRONT_URL=$(aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}" \
    --query "Stacks[0].Outputs[?OutputKey=='CloudFrontUrl'].OutputValue" \
    --output text 2>/dev/null || echo "")

echo ""
echo "=== Deployment Complete ==="
echo "URL: ${CLOUDFRONT_URL}"
