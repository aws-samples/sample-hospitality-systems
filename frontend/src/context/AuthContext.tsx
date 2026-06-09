import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import { Amplify } from 'aws-amplify';
import {
  signIn as amplifySignIn,
  signOut as amplifySignOut,
  getCurrentUser,
  fetchAuthSession,
  fetchUserAttributes,
} from 'aws-amplify/auth';
import config from '@/config/aws-config';
import { createGuest } from '@/services/guestService';
import { setTokenGetter } from '@/services/api';

// Auth is configured only when the pool settings are present (local dev without
// a backend leaves them empty). isConfigured gates every auth call so the app
// renders without throwing when Cognito isn't wired up.
const isConfigured = Boolean(config.userPoolId && config.clientId);
if (isConfigured) {
  Amplify.configure({
    Auth: {
      Cognito: {
        userPoolId: config.userPoolId,
        userPoolClientId: config.clientId,
      },
    },
  });
}

export interface AuthUser {
  sub: string;
  email: string;
  name: string;
  guestId: string;
}

interface AuthContextType {
  user: AuthUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => void;
  getToken: () => Promise<string | null>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

function parseUserFromAttributes(
  attributes: Record<string, string | undefined>
): Omit<AuthUser, 'guestId'> {
  return {
    sub: attributes['sub'] ?? '',
    email: attributes['email'] ?? '',
    name: `${attributes['given_name'] ?? ''} ${attributes['family_name'] ?? ''}`.trim(),
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const isAuthenticated = user !== null;

  // Check for existing session on mount
  useEffect(() => {
    const checkSession = async () => {
      try {
        if (!isConfigured) {
          setIsLoading(false);
          return;
        }
        // Throws if there is no signed-in user.
        await getCurrentUser();

        const session = await fetchAuthSession();
        if (!session.tokens?.idToken) {
          setIsLoading(false);
          return;
        }

        const attributes = await fetchUserAttributes();
        const parsed = parseUserFromAttributes(attributes);

        const storedGuestId = sessionStorage.getItem(`guestId_${parsed.sub}`);
        setUser({
          ...parsed,
          guestId: storedGuestId ?? '',
        });
      } catch {
        // No valid session — user is not authenticated
      } finally {
        setIsLoading(false);
      }
    };

    checkSession();
  }, []);

  const signIn = useCallback(async (email: string, password: string): Promise<void> => {
    if (!isConfigured) throw new Error('Auth not configured');

    // Amplify keeps one signed-in user per session; sign out any stale session
    // first so a re-login with a different account can't hit "already signed in".
    try {
      await amplifySignOut();
    } catch {
      // No existing session — nothing to clear.
    }

    await amplifySignIn({ username: email, password });

    const attributes = await fetchUserAttributes();
    const parsed = parseUserFromAttributes(attributes);

    // Create or retrieve guest profile
    let guestId = sessionStorage.getItem(`guestId_${parsed.sub}`) ?? '';
    if (!guestId) {
      try {
        const session = await fetchAuthSession();
        const idToken = session.tokens?.idToken?.toString() ?? '';
        const nameParts = parsed.name.split(' ');
        const guestResponse = await createGuest(
          {
            firstName: nameParts[0] ?? '',
            lastName: nameParts.slice(1).join(' ') ?? '',
            email: parsed.email,
            cognitoSub: parsed.sub,
          },
          idToken
        );
        guestId = guestResponse.guestId;
        sessionStorage.setItem(`guestId_${parsed.sub}`, guestId);
      } catch {
        // Guest profile creation failed — continue without guestId
      }
    }

    setUser({
      ...parsed,
      guestId,
    });
  }, []);

  const signOut = useCallback(() => {
    if (isConfigured) {
      // Fire-and-forget; local state is cleared regardless of network outcome.
      void amplifySignOut();
    }
    if (user) {
      sessionStorage.removeItem(`guestId_${user.sub}`);
    }
    setUser(null);
  }, [user]);

  const getToken = useCallback(async (): Promise<string | null> => {
    if (!isConfigured) return null;
    try {
      const session = await fetchAuthSession();
      return session.tokens?.idToken?.toString() ?? null;
    } catch {
      return null;
    }
  }, []);

  // Wire up the API interceptor so all requests include the auth token
  useEffect(() => {
    setTokenGetter(getToken);
  }, [getToken]);

  const value: AuthContextType = {
    user,
    isAuthenticated,
    isLoading,
    signIn,
    signOut,
    getToken,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
