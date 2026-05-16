import { ADMIN_NAV } from "../config/adminNav";
import type { AdminRoute } from "../router/types";
import "./admin-sidebar.css";

export interface AdminSidebarProps {
  route: AdminRoute;
  onNav: (path: string) => void;
}

export function AdminSidebar({ route, onNav }: AdminSidebarProps) {
  return (
    <aside className="admin-sidebar" aria-label="Admin navigation">
      <p className="admin-sidebar__label">Operations</p>
      <nav className="admin-sidebar__nav">
        {ADMIN_NAV.map((item) => {
          const active = route.name === item.section;
          return (
            <a
              key={item.section}
              href={item.path}
              className={active ? "is-active" : undefined}
              aria-current={active ? "page" : undefined}
              onClick={(e) => {
                e.preventDefault();
                onNav(item.path.replace(/^#/, ""));
              }}
            >
              <span className="admin-sidebar__item-label">{item.label}</span>
              <span className="admin-sidebar__item-desc">{item.description}</span>
            </a>
          );
        })}
      </nav>
    </aside>
  );
}
