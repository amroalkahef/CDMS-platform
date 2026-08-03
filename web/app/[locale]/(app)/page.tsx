"use client";

import { AlertCircle, CheckCircle2, ClipboardEdit, FileText } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import ErrorCard from "@/components/ErrorCard";
import PageHeader from "@/components/PageHeader";
import { api, Stats } from "@/lib/api";
import { apiErrorMessage } from "@/lib/errors";

export default function Dashboard() {
  const t = useTranslations("dashboard");
  const tc = useTranslations("common");
  const tDept = useTranslations("departments");
  const locale = useLocale();
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getStats().then(setStats).catch((e) => setError(apiErrorMessage(e, tc)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div>
      <PageHeader title={t("title")} subtitle={t("subtitle")} />

      {error && <ErrorCard title={tc("unreachableBackend")} message={error} />}

      <div className="stat-grid">
        <div className="card stat-card">
          <div>
            <div className="muted">{t("totalCirculars")}</div>
            <div className="stat-value">{stats ? stats.total_circulars : "—"}</div>
          </div>
          <div className="stat-icon">
            <FileText size={18} />
          </div>
        </div>
        <div className="card stat-card">
          <div>
            <div className="muted">{t("totalDecisions")}</div>
            <div className="stat-value">{stats ? stats.total_decisions : "—"}</div>
          </div>
          <div className="stat-icon">
            <ClipboardEdit size={18} />
          </div>
        </div>
        <div className="card stat-card">
          <div>
            <div className="muted">{t("pendingDrafts")}</div>
            <div className="stat-value">{stats ? stats.pending_drafts : "—"}</div>
          </div>
          <div className="stat-icon" style={{ color: "var(--warning)" }}>
            <AlertCircle size={18} />
          </div>
        </div>
        <div className="card stat-card">
          <div>
            <div className="muted">{t("published")}</div>
            <div className="stat-value">{stats ? stats.published : "—"}</div>
          </div>
          <div className="stat-icon" style={{ color: "var(--success)" }}>
            <CheckCircle2 size={18} />
          </div>
        </div>
      </div>

      <div className="two-col" style={{ gridTemplateColumns: "1.6fr 1fr" }}>
        <div className="card">
          <h3>{t("recentActivity")}</h3>
          <p className="muted" style={{ marginTop: 0 }}>
            {t("recentActivitySubtitle")}
          </p>
          {stats?.recent_activity.length === 0 && <p className="empty-state">{t("noActivity")}</p>}
          {stats?.recent_activity.map((item, i) => (
            <div key={i} style={{ display: "flex", gap: "0.75rem", padding: "0.6rem 0", borderTop: i > 0 ? "1px solid var(--border)" : "none" }}>
              <FileText size={16} style={{ marginTop: "0.2rem", color: "var(--muted)", flexShrink: 0 }} />
              <div>
                <strong>{item.action}</strong> {item.detail}
                <p className="muted" style={{ margin: 0 }}>
                  {item.user} · {new Date(item.timestamp).toLocaleString(locale, { numberingSystem: "latn" })}
                </p>
              </div>
            </div>
          ))}
        </div>

        <div className="card">
          <h3>{t("upcomingDeadlines")}</h3>
          <p className="muted" style={{ marginTop: 0 }}>
            {t("upcomingDeadlinesSubtitle")}
          </p>
          {stats?.upcoming_deadlines.length === 0 && <p className="empty-state">{t("noUpcomingDeadlines")}</p>}
          {stats?.upcoming_deadlines.map((d) => (
            <div key={d.id} style={{ padding: "0.5rem 0", borderTop: "1px solid var(--border)" }}>
              <strong>{d.title}</strong>
              <p className="muted" style={{ margin: 0 }}>
                {tDept(d.department)} · <span dir="ltr">{d.publication_date}</span>
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
