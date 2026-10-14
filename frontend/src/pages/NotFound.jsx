import { Link } from "react-router-dom";
import { CompassIcon } from "lucide-react";
import Button from "../components/ui/Button";

export default function NotFound() {
  return (
    <div className="min-h-[70vh] flex flex-col items-center justify-center text-center px-4">
      <div className="h-14 w-14 rounded-full bg-ink-50 flex items-center justify-center mb-4">
        <CompassIcon size={26} className="text-ink-400" />
      </div>
      <h1 className="text-2xl font-semibold text-ink mb-1.5">Page not found</h1>
      <p className="text-sm text-slate-500 max-w-sm mb-5">
        The page you're looking for doesn't exist or may have moved. Check the sidebar for the module you need.
      </p>
      <Button as={Link} to="/">Back to dashboard</Button>
    </div>
  );
}
