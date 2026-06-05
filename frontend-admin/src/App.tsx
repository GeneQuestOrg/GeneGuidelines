import { useUser } from "@clerk/clerk-react";
import { AppHeader } from "@gene-guidelines/ui";
import { AdminSidebar } from "./components/AdminSidebar";
import { PublicAppLink } from "./components/PublicAppLink";
import { isClerkSuperAdmin } from "./auth/clerkRole";
import { useHashRouter } from "./router/useHashRouter";
import { adminSectionContent } from "./views/adminSectionContent";
import "./components/admin-header.css";
import "./admin-shell.css";

export default function App() {
  const { route, navigate } = useHashRouter();
  const { user } = useUser();
  const isSuperAdmin = isClerkSuperAdmin(user);

  return (
    <div className="admin-shell">
      <AppHeader variant="admin" navLinks={[]}>
        <div className="admin-hdr-actions">
          <PublicAppLink />
        </div>
      </AppHeader>
      <div className="admin-shell__body">
        <AdminSidebar route={route} onNav={navigate} />
        <div className="admin-shell__main">
          <div className="admin-shell__content">{adminSectionContent(route, isSuperAdmin)}</div>
        </div>
      </div>
    </div>
  );
}
