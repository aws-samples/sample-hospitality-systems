#!/bin/bash
# Setup environment for AnyCompany Hotel Booking Platform
set -euo pipefail

ENVIRONMENT="${1:-dev}"
REGION="${AWS_REGION:-us-east-1}"
STACK_NAME="anycompany-booking"

echo "=== AnyCompany Hotel - Environment Setup ==="
echo "Environment: ${ENVIRONMENT}"
echo "Region: ${REGION}"

# Get stack outputs
echo "Fetching stack outputs..."
API_URL=$(aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}" \
    --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" \
    --output text 2>/dev/null || echo "")

USER_POOL_ID=$(aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}" \
    --query "Stacks[0].Outputs[?OutputKey=='UserPoolId'].OutputValue" \
    --output text 2>/dev/null || echo "")

USER_POOL_CLIENT_ID=$(aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}" \
    --query "Stacks[0].Outputs[?OutputKey=='UserPoolClientId'].OutputValue" \
    --output text 2>/dev/null || echo "")

CLOUDFRONT_URL=$(aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}" \
    --query "Stacks[0].Outputs[?OutputKey=='CloudFrontUrl'].OutputValue" \
    --output text 2>/dev/null || echo "")

STRIPE_PK="${STRIPE_PUBLISHABLE_KEY:-pk_test_placeholder}"

# Warn if using the placeholder — Stripe will reject payments
if [ "${STRIPE_PK}" = "pk_test_placeholder" ]; then
    echo ""
    echo "⚠️  WARNING: STRIPE_PUBLISHABLE_KEY is not set."
    echo "   The frontend will be built with a placeholder key and Stripe"
    echo "   will reject all payment attempts."
    echo ""
    echo "   To fix: export STRIPE_PUBLISHABLE_KEY='pk_test_YOUR_KEY' before running this script."
    echo "   Get your key from: https://dashboard.stripe.com/test/apikeys"
    echo ""
    read -p "Continue with placeholder key? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted. Set STRIPE_PUBLISHABLE_KEY and try again."
        exit 1
    fi
fi

# Create frontend .env file
FRONTEND_ENV="$(dirname "$0")/../frontend/.env.${ENVIRONMENT}"
cat > "${FRONTEND_ENV}" <<EOF
VITE_API_URL=${API_URL}
VITE_AWS_REGION=${REGION}
VITE_COGNITO_USER_POOL_ID=${USER_POOL_ID}
VITE_COGNITO_CLIENT_ID=${USER_POOL_CLIENT_ID}
VITE_STRIPE_PUBLISHABLE_KEY=${STRIPE_PK}
VITE_ENVIRONMENT=${ENVIRONMENT}
EOF

echo "Frontend env written to: ${FRONTEND_ENV}"

# Also create a .env.local for development
if [ "${ENVIRONMENT}" = "dev" ]; then
    cp "${FRONTEND_ENV}" "$(dirname "$0")/../frontend/.env.local"
    echo "Copied to .env.local for local development"
fi

echo ""
echo "=== Stack Outputs ==="
echo "API URL:           ${API_URL}"
echo "User Pool ID:      ${USER_POOL_ID}"
echo "Client ID:         ${USER_POOL_CLIENT_ID}"
echo "CloudFront URL:    ${CLOUDFRONT_URL}"
echo ""
echo "Setup complete!"
