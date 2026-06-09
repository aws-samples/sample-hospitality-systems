/**
 * Playwright global setup.
 *
 * Resolves the deployed frontend URLs from CloudFormation outputs and the
 * seeded test-user password from Secrets Manager, then exposes them to the
 * specs via environment variables. This keeps URLs and credentials out of the
 * committed config — they're discovered from the live stack at run time.
 *
 * Requires AWS creds (set AWS_PROFILE to your profile) and the seeded test
 * users (scripts/seed_test_users.py).
 */
import { CloudFormationClient, DescribeStacksCommand } from '@aws-sdk/client-cloudformation';
import { SecretsManagerClient, GetSecretValueCommand } from '@aws-sdk/client-secrets-manager';

const REGION = process.env.AWS_REGION || 'us-east-1';
const STACK = process.env.TEST_STACK_NAME || 'anycompany-booking';
const ENV = process.env.TEST_ENV || 'dev';

export default async function globalSetup() {
  const cfn = new CloudFormationClient({ region: REGION });
  const out = await cfn.send(new DescribeStacksCommand({ StackName: STACK }));
  const outputs = Object.fromEntries(
    (out.Stacks?.[0].Outputs ?? []).map((o) => [o.OutputKey, o.OutputValue]),
  );

  process.env.CRS_URL = outputs.CloudFrontUrl ?? '';
  process.env.PMS_URL = outputs.PmsCloudFrontUrl ?? '';

  const sm = new SecretsManagerClient({ region: REGION });
  const secret = await sm.send(
    new GetSecretValueCommand({ SecretId: `anycompany-booking-testsuite-creds-${ENV}` }),
  );
  const creds = JSON.parse(secret.SecretString ?? '{}');
  process.env.TEST_PASSWORD = creds.password ?? '';
  process.env.TEST_ADMIN_EMAIL = creds.users?.admin?.email ?? '';

  if (!process.env.PMS_URL || !process.env.TEST_PASSWORD) {
    throw new Error(
      'E2E setup failed: missing PMS URL or test creds. Is the stack deployed ' +
      'and seed_test_users.py run?',
    );
  }
}
