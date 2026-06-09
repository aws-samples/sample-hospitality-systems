/**
 * Authentication context for PMS Staff Dashboard.
 * Uses Cognito User Pool (same as CRS, but staff groups).
 */

import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { Amplify } from 'aws-amplify';
import {
  signIn as amplifySignIn,
  signOut as amplifySignOut,
  getCurrentUser,
  fetchAuthSession,
} from 'aws-amplify/auth';

// The decoded ID-token claim set. Amplify types the payload as an index map of
// JSON values; this app reads a known subset of Cognito claims off it.
type IdTokenClaims = Record<string, unknown>;

const USER_POOL_ID = import.meta.env.VITE_USER_POOL_ID || '';
const CLIENT_ID = import.meta.env.VITE_USER_POOL_CLIENT_ID || '';

Amplify.configure({
  Auth: {
    Cognito: {
      userPoolId: USER_POOL_ID,
      userPoolClientId: CLIENT_ID,
    },
  },
});

interface AuthUser {
  email: string;
  sub: string;
}

interface AuthContextType {
  user: AuthUser | null;
  groups: string[];
  propertyId: string | null;
  region: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => void;
  error: string | null;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [groups, setGroups] = useState<string[]>([]);
  const [propertyId, setPropertyId] = useState<string | null>(null);
  const [region, setRegion] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Check for existing session
    const checkSession = async () => {
      try {
        await getCurrentUser();
        const session = await fetchAuthSession();
        if (session.tokens?.idToken) {
          _extractSessionData(session.tokens.idToken.payload, session.tokens.idToken.toString());
        }
      } catch {
        // No valid session — user is not authenticated
      } finally {
        setIsLoading(false);
      }
    };
    checkSession();
  }, []);

  function _extractSessionData(payload: IdTokenClaims, idToken: string) {
    setUser({ email: payload.email as string, sub: payload.sub as string });
    setGroups((payload['cognito:groups'] as string[]) || []);
    setPropertyId((payload['custom:property_id'] as string) || null);
    setRegion((payload['custom:region'] as string) || null);

    // Store token for API calls
    sessionStorage.setItem('pms_id_token', idToken);
  }

  async function signIn(email: string, password: string): Promise<void> {
    setError(null);

    try {
      // Amplify keeps one signed-in user per session; clear any stale session
      // first so re-login as a different staff user can't hit "already signed in".
      try {
        await amplifySignOut();
      } catch {
        // No existing session — nothing to clear.
      }

      const { nextStep } = await amplifySignIn({ username: email, password });

      if (nextStep.signInStep === 'CONFIRM_SIGN_IN_WITH_NEW_PASSWORD_REQUIRED') {
        setError('Password change required. Contact administrator.');
        throw new Error('New password required');
      }

      const session = await fetchAuthSession();
      if (session.tokens?.idToken) {
        _extractSessionData(session.tokens.idToken.payload, session.tokens.idToken.toString());
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Sign in failed';
      // Preserve the specific new-password message if it was already set.
      setError((prev) => prev ?? message);
      throw err;
    }
  }

  function signOut() {
    // Fire-and-forget; local state is cleared regardless of network outcome.
    void amplifySignOut();
    sessionStorage.removeItem('pms_id_token');
    setUser(null);
    setGroups([]);
    setPropertyId(null);
    setRegion(null);
  }

  return (
    <AuthContext.Provider value={{
      user,
      groups,
      propertyId,
      region,
      isAuthenticated: !!user,
      isLoading,
      signIn,
      signOut,
      error,
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
}
