"use client";

import { useTranslations } from "next-intl";
import { useEffect } from "react";
import { useAuth } from "@/components/AuthProvider";
import Sidebar from "@/components/Sidebar";
import { useRouter } from "@/i18n/navigation";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const t = useTranslations("common");

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
      <Sidebar />
      <main className="content">{children}</main>
    </div>
  );
}
