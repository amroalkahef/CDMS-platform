"use client";

import { ArrowLeft, Pencil, Trash2, UploadCloud } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useAuth } from "@/components/AuthProvider";
import { Link, useRouter } from "@/i18n/navigation";
import { api, Circular, Decision, DocumentVersion, Workflow } from "@/lib/api";
import { apiErrorMessage } from "@/lib/errors";

type EntityType = "circular" | "decision";

function roleLabel(role: string, tAuth: (key: string) => string): string {
  if (role === "editor") return tAuth("roleEditor");
  if (role === "reviewer") return tAuth("roleReviewer");
  return role;
}

export default function EntityDetail({ entityType, entityId }: { entityType: EntityType; entityId: string }) {
  const t = useTranslations("detail");
  const tc = useTranslations("common");
  const tDept = useTranslations("departments");
  const tFreq = useTranslations("frequencies");
  const tStatus = useTranslations("statuses");
  const tAuth = useTranslations("auth");
  const locale = useLocale();
  const router = useRouter();
  const { user } = useAuth();
  const isEditor = user?.role === "editor";
  const isReviewer = user?.role === "reviewer";

  const [entity, setEntity] = useState<Circular | Decision | null>(null);
  const [versions, setVersions] = useState<DocumentVersion[] | null>(null);
  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function load() {
    const getEntity = entityType === "circular" ? api.getCircular(entityId) : api.getDecision(entityId);
    getEntity.then(setEntity).catch((e) => setError(apiErrorMessage(e, tc)));
    api.listVersions(entityType, entityId).then((r) => setVersions(r.versions)).catch(() => {});
    api
      .listWorkflows(entityId)
      .then((rows) => setWorkflow(rows[0] ?? null))
      .catch(() => {});
  }

  useEffect(load, [entityType, entityId]);

  async function handleDecision(approve: boolean) {
    if (!workflow) return;
    setBusy(true);
    setError(null);
    try {
      await api.decideWorkflow(workflow.id, approve, comment || undefined);
      setComment("");
      load();
    } catch (e) {
      setError(apiErrorMessage(e, tc));
    } finally {
      setBusy(false);
    }
  }

  async function handlePublish() {
    setBusy(true);
    setError(null);
    try {
      entityType === "circular" ? await api.publishCircular(entityId) : await api.publishDecision(entityId);
      load();
    } catch (e) {
      setError(apiErrorMessage(e, tc));
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    if (!confirm(tc("confirmDelete"))) return;
    const del = entityType === "circular" ? api.deleteCircular(entityId) : api.deleteDecision(entityId);
    await del;
    router.push(entityType === "circular" ? "/circulars" : "/decisions");
  }

  if (error && !entity) {
    return (
      <div className="card">
        <strong>{tc("error")}</strong>
        <p className="muted">{error}</p>
      </div>
    );
  }

  if (!entity) {
    return <p className="muted">{tc("loading")}</p>;
  }

  const currentStep = workflow?.steps.find((s) => s.step_order === workflow.current_step_order);
  const canReview = isReviewer && workflow?.status === "pending_approval" && currentStep?.role === "reviewer";
  const canPublish = isEditor && entity.status === "approved";
  const listHref = entityType === "circular" ? "/circulars" : "/decisions";

  return (
    <div>
      <Link href={listHref} className="back-link">
        <ArrowLeft size={15} />
        {t("backToList")}
      </Link>

      <div className="page-header">
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
            <h1 style={{ marginBottom: 0 }}>{entity.title}</h1>
            <span className={`badge badge-${entity.status}`}>{tStatus(entity.status)}</span>
          </div>
          <p className="muted">
            {entityType === "circular" && (entity as Circular).circular_number && (
              <span dir="ltr">{(entity as Circular).circular_number} · </span>
            )}
            {entityType === "decision" && (entity as Decision).decision_number && (
              <span dir="ltr">{(entity as Decision).decision_number} · </span>
            )}
            {tDept(entity.department)}
            {entityType === "circular" && (entity as Circular).frequency && ` · ${tFreq((entity as Circular).frequency)}`}
            {" · "}
            {t("version")} {entity.version}
          </p>
        </div>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          {canPublish && (
            <button className="btn-primary" disabled={busy} onClick={handlePublish}>
              <UploadCloud size={15} />
              {busy ? tc("publishing") : t("publishButton")}
            </button>
          )}
          {isEditor && (
            <>
              <Link href={`${listHref}/${entityId}/edit`} className="btn btn-secondary">
                <Pencil size={15} />
                {t("editButton")}
              </Link>
              <button className="btn-danger" onClick={handleDelete}>
                <Trash2 size={15} />
                {t("deleteButton")}
              </button>
            </>
          )}
        </div>
      </div>

      {error && (
        <div className="card">
          <strong>{tc("error")}</strong>
          <p className="muted">{error}</p>
        </div>
      )}

      {canPublish && (
        <div className="card ai-panel">
          <p style={{ margin: 0 }}>{t("approvedReadyToPublish")}</p>
        </div>
      )}

      <div className="card">
        <h3>{t("contentHeading")}</h3>
        <div className="markdown-content">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{entity.content}</ReactMarkdown>
        </div>
      </div>

      {entity.references.length > 0 && (
        <div className="card">
          <h3>{t("referencesHeading")}</h3>
          {entity.references.map((ref, i) => (
            <p key={i} className="muted" style={{ margin: "0.25rem 0" }}>
              {String((ref as Record<string, unknown>).title ?? JSON.stringify(ref))}
            </p>
          ))}
        </div>
      )}

      {workflow && (
        <div className="card">
          <h3>{t("approvalChain")}</h3>
          <p className="muted">
            {t("requestedBy")}: {workflow.requested_by}
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", margin: "0.75rem 0" }}>
            {workflow.steps.map((s) => (
              <div key={s.id}>
                <span className={`badge badge-${s.status === "pending" ? "draft" : s.status}`}>
                  {s.step_order + 1}. {roleLabel(s.role, tAuth)}: {tStatus(s.status) || s.status}
                </span>
                {s.decided_by && (
                  <span className="muted" style={{ marginInlineStart: "0.5rem" }}>
                    — {s.decided_by}
                  </span>
                )}
                {s.comment && (
                  <p className="muted" style={{ margin: "0.25rem 0 0" }}>
                    {t("reviewerNote")}: “{s.comment}”
                  </p>
                )}
              </div>
            ))}
          </div>
          {canReview && (
            <div>
              <p className="muted">{t("awaitingApproval", { role: roleLabel(currentStep!.role, tAuth) })}</p>
              <label>{t("commentField")}</label>
              <textarea value={comment} onChange={(e) => setComment(e.target.value)} placeholder={t("commentPlaceholder")} />
              <div style={{ marginTop: "0.75rem" }}>
                <button className="btn-primary" disabled={busy} onClick={() => handleDecision(true)}>
                  {tc("approve")}
                </button>{" "}
                <button className="btn-secondary" disabled={busy} onClick={() => handleDecision(false)}>
                  {tc("reject")}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      <div className="card">
        <h3>{t("versionHistory")}</h3>
        {versions?.length === 0 && <p className="muted">{t("noVersions")}</p>}
        {versions?.map((v) => (
          <div key={v.version} style={{ padding: "0.5rem 0", borderTop: "1px solid var(--border)" }}>
            <span className="badge badge-draft">v{v.version}</span>{" "}
            <span className={`badge badge-${v.status}`}>{tStatus(v.status)}</span>{" "}
            <span className="muted" dir="ltr">{new Date(v.created_at).toLocaleString(locale, { numberingSystem: "latn" })}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
