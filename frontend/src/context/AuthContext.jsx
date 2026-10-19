import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, tokenStore, setUnauthorizedHandler, USE_MOCK } from "../services/api";

const AuthContext = createContext(null);

export const ROLES = {
  ADMIN: "System Administrator",
  COORDINATOR: "Timetable Coordinator",
  FACULTY: "Faculty",
  STUDENT: "Student",
};

// Backend UserRole enum values -> UI role labels.
const BACKEND_ROLES = {
  SYSTEM_ADMIN: ROLES.ADMIN,
  COORDINATOR: ROLES.COORDINATOR,
  FACULTY: ROLES.FACULTY,
  STUDENT: ROLES.STUDENT,
};

const DEMO_USERS = {
  [ROLES.ADMIN]: { name: "Anil Kapoor", initials: "AK", department: null, email: "admin@piet.ac.in" },
  [ROLES.COORDINATOR]: { name: "Smita Bisht", initials: "SB", department: "CSE", email: "smita.bisht@piet.ac.in" },
  [ROLES.FACULTY]: { name: "Rakesh Sharma", initials: "RS", department: "CSE", email: "rakesh.sharma@piet.ac.in" },
  [ROLES.STUDENT]: { name: "Ananya Rathore", initials: "AR", department: "CSE", email: "ananya.rathore@students.piet.ac.in" },
};

const initialsOf = (name) =>
  name
    .split(/\s+/)
    .map((w) => w[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

function fromBackendUser(u) {
  return {
    role: BACKEND_ROLES[u.role] ?? ROLES.STUDENT,
    user: { name: u.full_name, initials: initialsOf(u.full_name), department: null, email: u.email },
  };
}

export function AuthProvider({ children }) {
  const [role, setRole] = useState(null);
  const [realUser, setRealUser] = useState(null);
  // Restoring a saved session takes one /me round trip; hold routing until it resolves.
  const [initializing, setInitializing] = useState(!USE_MOCK && !!tokenStore.get());

  const logout = useCallback(() => {
    tokenStore.clear();
    setRealUser(null);
    setRole(null);
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(logout);
  }, [logout]);

  useEffect(() => {
    if (!initializing) return;
    api
      .get("/api/auth/me")
      .then((u) => {
        const mapped = fromBackendUser(u);
        setRealUser(mapped.user);
        setRole(mapped.role);
      })
      .catch(() => tokenStore.clear())
      .finally(() => setInitializing(false));
  }, [initializing]);

  // Mock mode: pick a demo role. Real mode: POST /api/auth/login, then GET /api/auth/me.
  const signIn = useCallback(async (email, password, demoRole) => {
    if (USE_MOCK) {
      setRole(demoRole);
      return;
    }
    const tokens = await api.post("/api/auth/login", { email, password });
    tokenStore.set(tokens.access_token, tokens.refresh_token);
    const mapped = fromBackendUser(await api.get("/api/auth/me"));
    setRealUser(mapped.user);
    setRole(mapped.role);
  }, []);

  const value = useMemo(
    () => ({
      role,
      user: role ? realUser || DEMO_USERS[role] : null,
      isAuthenticated: !!role,
      initializing,
      signIn,
      logout,
      // Demo role switching only exists in mock mode.
      switchRole: USE_MOCK ? setRole : () => {},
    }),
    [role, realUser, initializing, signIn, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
