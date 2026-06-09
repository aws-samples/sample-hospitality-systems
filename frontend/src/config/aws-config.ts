export interface AppConfig {
  apiUrl: string;
  region: string;
  userPoolId: string;
  clientId: string;
  stripePublishableKey: string;
}

const config: AppConfig = {
  apiUrl: import.meta.env.VITE_API_URL ?? 'https://api.anycompanyhotels.com/v1',
  region: import.meta.env.VITE_AWS_REGION ?? 'us-east-1',
  userPoolId: import.meta.env.VITE_COGNITO_USER_POOL_ID ?? '',
  clientId: import.meta.env.VITE_COGNITO_CLIENT_ID ?? '',
  stripePublishableKey: import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY ?? '',
};

export default config;
