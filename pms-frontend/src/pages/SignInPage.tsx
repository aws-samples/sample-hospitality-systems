import { useState, FormEvent } from 'react';
import { useAuth } from '../context/AuthContext';
import { Button, Input } from '../components/ui';

export default function SignInPage() {
  const { signIn, error } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      await signIn(email, password);
    } catch {
      // Error is set in context
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div
      className="min-h-screen bg-linear-to-br from-primary-900 via-primary-700 to-primary-600 flex items-center justify-center px-4 py-8"
      data-testid="sign-in-page"
    >
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <h1 className="font-display text-3xl font-bold text-white">AnyCompany</h1>
          <p className="font-display text-xs text-white/80 tracking-widest uppercase mt-1">
            Hotels &amp; Resorts
          </p>
          <div className="mt-3 mx-auto h-1 w-12 rounded-full bg-accent-500" />
          <p className="text-sm text-white/80 mt-4">Staff Dashboard Sign In</p>
        </div>

        <div className="rounded-2xl bg-white p-8 shadow-xl">
          <form onSubmit={handleSubmit} data-testid="sign-in-form" className="space-y-5">
            {error && (
              <div
                className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
                data-testid="sign-in-error"
              >
                {error}
              </div>
            )}

            <div>
              <label htmlFor="email" className="block text-sm font-medium text-neutral-700 mb-1.5">
                Email
              </label>
              <Input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                data-testid="sign-in-email-input"
                className="w-full"
                placeholder="staff@anycompanyhotels.com"
              />
            </div>

            <div>
              <label
                htmlFor="password"
                className="block text-sm font-medium text-neutral-700 mb-1.5"
              >
                Password
              </label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                data-testid="sign-in-password-input"
                className="w-full"
              />
            </div>

            <Button
              type="submit"
              variant="primary"
              loading={isSubmitting}
              disabled={isSubmitting}
              data-testid="sign-in-submit-button"
              className="w-full"
            >
              {isSubmitting ? 'Signing In...' : 'Sign In'}
            </Button>
          </form>
        </div>
      </div>
    </div>
  );
}
