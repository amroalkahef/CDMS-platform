"use client";

import { LayoutDashboard, FileText, ClipboardEdit, MessageSquare, Library, Languages, LogOut } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useAuth } from "@/components/AuthProvider";
import { Link, usePathname, useRouter } from "@/i18n/navigation";

const NAV_ITEMS = [
  { href: "/", key: "dashboard", icon: LayoutDashboard },
  { href: "/circulars", key: "circulars", icon: FileText },
  { href: "/decisions", key: "decisions", icon: ClipboardEdit },
  { href: "/assistant", key: "assistant", icon: MessageSquare },
  { href: "/knowledge", key: "knowledge", icon: Library },
] as const;

export default function Sidebar() {
  const t = useTranslations("nav");
  const tAuth = useTranslations("auth");
  const locale = useLocale();
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout } = useAuth();

  function handleLogout() {
    logout();
    router.replace("/login");
  }

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <span className="sidebar-brand">{t("brand")}</span>
        <Link href={pathname} locale={locale === "en" ? "ar" : "en"} className="lang-toggle">
          <Languages size={14} />
          {locale === "en" ? "AR" : "EN"}
        </Link>
      </div>

      {user && (
        <div className="sidebar-user">
          <div className="sidebar-user-name">{user.name}</div>
          <span className={`badge sidebar-role-badge role-${user.role}`}>
            {user.role === "editor" ? tAuth("roleEditor") : tAuth("roleReviewer")}
          </span>
        </div>
      )}

      <div className="sidebar-menu-label">{t("menu")}</div>
      <nav className="sidebar-nav">
        {NAV_ITEMS.map(({ href, key, icon: Icon }) => {
          const isActive = href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link key={href} href={href} className={`sidebar-link${isActive ? " active" : ""}`}>
              <Icon />
              {t(key)}
            </Link>
          );
        })}
      </nav>

      <button type="button" className="sidebar-link sidebar-logout" onClick={handleLogout}>
        <LogOut />
        {tAuth("logout")}
      </button>
    </aside>
  );
}
