import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type AuthUser = {
  user_id: string;
  role: "relationship_manager" | "credit_analyst";
};

type LoginInput = { user_id: string; password: string };
type RegisterInput = LoginInput & {
  confirm_password: string;
  role: AuthUser["role"];
};
type ChangePasswordInput = {
  current_password: string;
  new_password: string;
  confirm_password: string;
};
type ResetPasswordInput = {
  user_id: string;
  new_password: string;
  confirm_password: string;
};

type AuthContextValue = {
  user: AuthUser | null;
  loading: boolean;
  login: (input: LoginInput) => Promise<AuthUser>;
  register: (input: RegisterInput) => Promise<AuthUser>;
  logout: () => Promise<void>;
  changePassword: (input: ChangePasswordInput) => Promise<string>;
  resetPassword: (input: ResetPasswordInput) => Promise<string>;
  refresh: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

async function authRequest<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...options,
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(options?.headers as Record<string, string> | undefined),
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail || `Request failed (${response.status}).`);
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const current = await authRequest<AuthUser>("/api/auth/me");
      setUser(current);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const handleUnauthorized = () => setUser(null);
    window.addEventListener("auth:unauthorized", handleUnauthorized);
    return () => window.removeEventListener("auth:unauthorized", handleUnauthorized);
  }, [refresh]);

  const login = useCallback(async (input: LoginInput) => {
    const loggedIn = await authRequest<AuthUser>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify(input),
    });
    setUser(loggedIn);
    return loggedIn;
  }, []);

  const register = useCallback(async (input: RegisterInput) => {
    const registered = await authRequest<AuthUser>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify(input),
    });
    return registered;
  }, []);

  const changePassword = useCallback(async (input: ChangePasswordInput) => {
    const result = await authRequest<{ message: string }>("/api/auth/change-password", {
      method: "POST",
      body: JSON.stringify(input),
    });
    return result.message;
  }, []);

  const resetPassword = useCallback(async (input: ResetPasswordInput) => {
    const result = await authRequest<{ message: string }>("/api/auth/reset-password", {
      method: "POST",
      body: JSON.stringify(input),
    });
    return result.message;
  }, []);

  const logout = useCallback(async () => {
    try {
      await authRequest<void>("/api/auth/logout", { method: "POST" });
    } finally {
      setUser(null);
    }
  }, []);

  const value = useMemo(
    () => ({ user, loading, login, register, logout, changePassword, resetPassword, refresh }),
    [user, loading, login, register, logout, changePassword, resetPassword, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// The provider and its companion hook intentionally share one small module.
// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider.");
  return context;
}
