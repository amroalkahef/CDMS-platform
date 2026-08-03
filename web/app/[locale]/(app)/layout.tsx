"use client";

import { Menu } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import Sidebar from "@/components/Sidebar";
import { useRouter } from "@/i18n/navigation";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const t = useTranslations("common");
  const tNav = useTranslations("nav");
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login");
    }
  }, [loading, user, router]);

  if (loading || !user) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: "100vh" }}>
        <p className="muted">{t("loading")}</p>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <div className="mobile-topbar">
        <button type="button" className="sidebar-menu-btn" onClick={() => setSidebarOpen(true)} aria-label={tNav("openMenu")}>
          <Menu size={20} />
        </button>
        <span className="mobile-topbar-brand">{tNav("brand")}</span>
      </div>
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <main className="content" id="main-content">
        {children}
      </main>
    </div>
  );
}
