import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { ToastProvider } from "./context/ToastContext";
import AppShell from "./components/layout/AppShell";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Timetable from "./pages/Timetable";
import SessionBuilder from "./pages/SessionBuilder";
import Sections from "./pages/Sections";
import FacultyPage from "./pages/Faculty";
import Courses from "./pages/Courses";
import Resources from "./pages/Resources";
import Constraints from "./pages/Constraints";
import GenerateOptimize from "./pages/GenerateOptimize";
import Conflicts from "./pages/Conflicts";
import Rescheduling from "./pages/Rescheduling";
import AcademicEvents from "./pages/AcademicEvents";
import Approvals from "./pages/Approvals";
import Reports from "./pages/Reports";
import Notifications from "./pages/Notifications";
import Settings from "./pages/Settings";
import NotFound from "./pages/NotFound";
import { ROLES } from "./context/AuthContext";

function RequireAuth({ children }) {
  const { isAuthenticated } = useAuth();
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return children;
}

function RequireRole({ roles, children }) {
  const { role } = useAuth();
  if (!roles.includes(role)) return <Navigate to="/" replace />;
  return children;
}

function AppRoutes() {
  const { isAuthenticated } = useAuth();

  return (
    <Routes>
      <Route path="/login" element={isAuthenticated ? <Navigate to="/" replace /> : <Login />} />

      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route path="/" element={<Dashboard />} />
        <Route path="/timetable" element={<Timetable />} />

        <Route
          path="/session-builder"
          element={
            <RequireRole roles={[ROLES.COORDINATOR]}>
              <SessionBuilder />
            </RequireRole>
          }
        />
        <Route
          path="/generate"
          element={
            <RequireRole roles={[ROLES.COORDINATOR]}>
              <GenerateOptimize />
            </RequireRole>
          }
        />
        <Route
          path="/conflicts"
          element={
            <RequireRole roles={[ROLES.COORDINATOR]}>
              <Conflicts />
            </RequireRole>
          }
        />
        <Route
          path="/rescheduling"
          element={
            <RequireRole roles={[ROLES.COORDINATOR]}>
              <Rescheduling />
            </RequireRole>
          }
        />
        <Route
          path="/events"
          element={
            <RequireRole roles={[ROLES.COORDINATOR]}>
              <AcademicEvents />
            </RequireRole>
          }
        />
        <Route
          path="/approvals"
          element={
            <RequireRole roles={[ROLES.COORDINATOR]}>
              <Approvals />
            </RequireRole>
          }
        />

        <Route
          path="/sections"
          element={
            <RequireRole roles={[ROLES.COORDINATOR]}>
              <Sections />
            </RequireRole>
          }
        />
        <Route
          path="/faculty"
          element={
            <RequireRole roles={[ROLES.COORDINATOR]}>
              <FacultyPage />
            </RequireRole>
          }
        />
        <Route
          path="/courses"
          element={
            <RequireRole roles={[ROLES.COORDINATOR]}>
              <Courses />
            </RequireRole>
          }
        />
        <Route
          path="/resources"
          element={
            <RequireRole roles={[ROLES.COORDINATOR]}>
              <Resources />
            </RequireRole>
          }
        />
        <Route
          path="/constraints"
          element={
            <RequireRole roles={[ROLES.COORDINATOR]}>
              <Constraints />
            </RequireRole>
          }
        />

        <Route
          path="/reports"
          element={
            <RequireRole roles={[ROLES.COORDINATOR, ROLES.ADMIN]}>
              <Reports />
            </RequireRole>
          }
        />
        <Route path="/notifications" element={<Notifications />} />
        <Route path="/settings" element={<Settings />} />

        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ToastProvider>
          <AppRoutes />
        </ToastProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}
