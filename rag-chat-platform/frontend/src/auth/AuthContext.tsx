import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { http, TOKEN_KEY, USER_KEY, clearSession } from '../api/http';
import { clearApiKey, clearApiKeyIfOwnerChanged } from '../lib/apiKeyStorage';

export interface AuthUser {
  id: number;
  username: string;
  role: 'admin' | 'user';
}

interface AuthState {
  user: AuthUser | null;
  ready: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

function storedUser(): AuthUser | null {
  try {
    const raw = localStorage.getItem(USER_KEY);
    if (!raw) return null;
    const user = JSON.parse(raw) as AuthUser;
    if (!user?.username || !user.role) return null;
    return user;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(storedUser);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem(TOKEN_KEY);
    if (!token) {
      setUser(null);
      setReady(true);
      return;
    }
    http
      .get<AuthUser>('/api/auth/me')
      .then((response) => {
        localStorage.setItem(USER_KEY, JSON.stringify(response.data));
        setUser(response.data);
      })
      .catch(() => {
        clearSession();
        clearApiKey();
        setUser(null);
      })
      .finally(() => setReady(true));
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      user,
      ready,
      async login(username: string, password: string) {
        const response = await http.post('/api/auth/login', { username, password });
        clearApiKeyIfOwnerChanged(response.data.user.id);
        localStorage.setItem(TOKEN_KEY, response.data.access_token);
        localStorage.setItem(USER_KEY, JSON.stringify(response.data.user));
        setUser(response.data.user);
      },
      logout() {
        clearApiKey();
        clearSession();
        setUser(null);
      },
    }),
    [ready, user]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error('AuthProvider 缺失');
  return value;
}
