"use client";

import { Eye, Pencil, Plus, Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { Link } from "@/i18n/navigation";
import { api, Circular, Constants } from "@/lib/api";
import { apiErrorMessage } from "@/lib/errors";

export default function CircularsPage() {
  const t = useTranslations("circulars");
  const tc = useTranslations("common");
  const tDept = useTranslations("departments");
  const tFreq = useTranslations("frequencies");
  const tStatus = useTranslations("statuses");
  const { user } = useAuth();
  const isEditor = user?.role === "editor";

  const [circulars, setCirculars] = useState<Circular[] | null>(null);
  const [constants, setConstants] = useState<Constants | null>(null);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [department, setDepartment] = useState("");
  const [error, setError] = useState<string | null>(null);

  function load() {
    api
      .listCirculars({ q: q || undefined, status: status || undefined, department: department || undefined })
      .then(setCirculars)
      .catch((e) => setError(apiErrorMessage(e, tc)));
  }

  useEffect(() => {
    api.getConstants().then(setConstants).catch(() => {});
  }, []);

  useEffect(() => {
    const handle = setTimeout(load, 300);
    return () => clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, status, department]);

  async function handleDelete(id: string) {
    if (!confirm(tc("confirmDelete"))) return;
    await api.deleteCircular(id);
    load();
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>{t("title")}</h1>
          <p className="page-subtitle">{t("subtitle")}</p>
        </div>
        {isEditor && (
          <Link href="/circulars/new" className="btn btn-primary">
            <Plus size={16} />
            {t("newCircular")}
          </Link>
        )}
      </div>

      <div className="filter-row">
        <input className="search-input" placeholder={t("searchPlaceholder")} value={q} onChange={(e) => setQ(e.target.value)} />
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">{tc("allStatuses")}</option>
          {constants?.circular_statuses.map((s) => (
            <option key={s} value={s}>
              {tStatus(s)}
            </option>
          ))}
        </select>
        <select value={department} onChange={(e) => setDepartment(e.target.value)}>
          <option value="">{tc("allDepartments")}</option>
          {constants?.departments.map((d) => (
            <option key={d} value={d}>
              {tDept(d)}
            </option>
          ))}
        </select>
      </div>

      {error && (
        <div className="card">
          <strong>{tc("error")}</strong>
          <p className="muted">{error}</p>
        </div>
      )}

      <div className="card" style={{ padding: 0, overflowX: "auto" }}>
        <table>
          <thead>
            <tr>
              <th>{t("columns.circularNumber")}</th>
              <th>{t("columns.title")}</th>
              <th>{t("columns.department")}</th>
              <th>{t("columns.frequency")}</th>
              <th>{t("columns.publicationDate")}</th>
              <th>{t("columns.status")}</th>
              <th>{t("columns.actions")}</th>
            </tr>
          </thead>
          <tbody>
            {circulars?.map((c) => (
              <tr key={c.id}>
                <td dir="ltr">{c.circular_number ?? "—"}</td>
                <td>{c.title}</td>
                <td>{tDept(c.department)}</td>
                <td>{tFreq(c.frequency)}</td>
                <td dir="ltr">{c.publication_date ?? "—"}</td>
                <td>
                  <span className={`badge badge-${c.status}`}>{tStatus(c.status)}</span>
                </td>
                <td>
                  <div className="actions-cell">
                    <Link href={`/circulars/${c.id}`} className="btn-icon">
                      <Eye size={16} />
                    </Link>
                    {isEditor && (
                      <>
                        <Link href={`/circulars/${c.id}/edit`} className="btn-icon">
                          <Pencil size={16} />
                        </Link>
                        <button className="btn-icon" onClick={() => handleDelete(c.id)}>
                          <Trash2 size={16} />
                        </button>
                      </>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {circulars?.length === 0 && <p className="empty-state">{t("empty")}</p>}
        {circulars === null && !error && <p className="empty-state">{tc("loading")}</p>}
      </div>
    </div>
  );
}
