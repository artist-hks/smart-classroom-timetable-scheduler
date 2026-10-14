import { createContext, useContext, useState, useMemo } from "react";

const AuthContext = createContext(null);

export const ROLES = {
  ADMIN: "System Administrator",
  COORDINATOR: "Timetable Coordinator",
  FACULTY: "Faculty",
  STUDENT: "Student",
};

const DEMO_USERS = {
  [ROLES.ADMIN]: { name: "Anil Kapoor", initials: "AK", department: null, email: "admin@piet.ac.in" },
  [ROLES.COORDINATOR]: { name: "Smita Bisht", initials: "SB", department: "CSE", email: "smita.bisht@piet.ac.in" },
  [ROLES.FACULTY]: { name: "Rakesh Sharma", initials: "RS", department: "CSE", email: "rakesh.sharma@piet.ac.in" },
  [ROLES.STUDENT]: { name: "Ananya Rathore", initials: "AR", department: "CSE", email: "ananya.rathore@students.piet.ac.in" },
};

export function AuthProvider({ children }) {
  const [role, setRole] = useState(null);

  const login = (selectedRole) => setRole(selectedRole);
  const logout = () => setRole(null);

  const value = useMemo(
    () => ({
      role,
      user: role ? DEMO_USERS[role] : null,
      isAuthenticated: !!role,
      login,
      logout,
      switchRole: setRole,
    }),
    [role]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
