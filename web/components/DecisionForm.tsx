"use client";

import { Info, Sparkles } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import SimilarityResults from "@/components/SimilarityResults";
import { useRouter } from "@/i18n/navigation";
import { api, Constants, Decision, SimilarityHit } from "@/lib/api";
import { apiErrorMessage } from "@/lib/errors";

export default function DecisionForm({ decisionId }: { decisionId?: string }) {
  const t = useTranslations("decisionForm");
  const tc = useTranslations("common");
  const tSim = useTranslations("similarity");
  const tDept = useTranslations("departments");
  const tStatus = useTranslations("statuses");
  const locale = useLocale();
  const router = useRouter();
  const { user } = useAuth();

  const [constants, setConstants] = useState<Constants | null>(null);
  const [decisionNumber, setDecisionNumber] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [department, setDepartment] = useState("Administration");
  const [effectiveDate, setEffectiveDate] = useState("");
  const [status, setStatus] = useState("draft");

  const [aiPrompt, setAiPrompt] = useState("");
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [similarity, setSimilarity] = useState<SimilarityHit[] | null>(null);
  const [checkingSimilarity, setCheckingSimilarity] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    api.getConstants().then(setConstants).catch(() => {});
  }, []);

  useEffect(() => {
    if (!decisionId) return;
    api.getDecision(decisionId).then((d) => {
      setDecisionNumber(d.decision_number);
      setTitle(d.title);
      setContent(d.content);
      setDepartment(d.department);
      setEffectiveDate(d.effective_date ?? "");
      setStatus(d.status);
    });
  }, [decisionId]);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!title.trim() && !content.trim()) {
      setSimilarity(null);
      return;
    }
    debounceRef.current = setTimeout(async () => {
      setCheckingSimilarity(true);
      try {
        const r = await api.checkSimilarity({ entity_type: "decision", title, content, exclude_id: decisionId });
        setSimilarity(r.results);
      } catch {
        setSimilarity(null);
      } finally {
        setCheckingSimilarity(false);
      }
    }, 600);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [title, content, decisionId]);

  async function handleGenerate() {
    setGenerating(true);
    setError(null);
    try {
      const r = await api.draft({ task_type: "generate_decision", user_prompt: aiPrompt, doc_type_filter: "decision", language: locale });
      setContent(r.draft);
    } catch (e) {
      setError(apiErrorMessage(e, tc));
    } finally {
      setGenerating(false);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    const payload = {
      title,
      content,
      department,
      effective_date: effectiveDate || undefined,
      status,
    };
    try {
      const saved: Decision = decisionId ? await api.updateDecision(decisionId, payload) : await api.createDecision(payload);
      router.push(`/decisions/${saved.id}`);
    } catch (e2) {
      setError(apiErrorMessage(e2, tc));
    } finally {
      setSaving(false);
    }
  }

  if (user && user.role !== "editor") {
    return (
      <div className="card">
        <p className="muted">{tc("editorsOnly")}</p>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="two-col">
      <div>
        <div className="card ai-panel">
          <div className="ai-title">
            <Sparkles size={16} />
            {t("aiPanelTitle")}
          </div>
          <p className="muted">{t("aiPanelDesc")}</p>
          <textarea value={aiPrompt} onChange={(e) => setAiPrompt(e.target.value)} placeholder={t("aiPlaceholder")} />
          <button type="button" className="btn-primary" disabled={generating || !aiPrompt} onClick={handleGenerate} style={{ width: "100%" }}>
            <Sparkles size={15} />
            {generating ? tc("generating") : tc("generateWithAi")}
          </button>
        </div>

        <div className="card">
          <div className="ai-title" style={{ color: "var(--text)" }}>
            <Info size={16} />
            {tSim("title")}
          </div>
          <p className="muted">{tSim("desc")}</p>

          <SimilarityResults checking={checkingSimilarity} results={similarity} />
        </div>
      </div>

      <div className="card">
        <h3>{t("detailsHeading")}</h3>

        <div className="field-row">
          <div>
            <label>{t("decisionNumberField")}</label>
            <input dir={decisionNumber ? "ltr" : undefined} value={decisionNumber ?? t("decisionNumberAutoHint")} disabled />
          </div>
          <div>
            <label>{t("effectiveDateField")}</label>
            <input type="date" value={effectiveDate} onChange={(e) => setEffectiveDate(e.target.value)} />
          </div>
        </div>

        <label>{t("titleField")}</label>
        <input value={title} onChange={(e) => setTitle(e.target.value)} required />

        <label>{t("contentField")}</label>
        <textarea value={content} onChange={(e) => setContent(e.target.value)} style={{ minHeight: 220 }} required />

        <div className="field-row">
          <div>
            <label>{t("departmentField")}</label>
            <select value={department} onChange={(e) => setDepartment(e.target.value)}>
              {(constants?.departments ?? [department]).map((d) => (
                <option key={d} value={d}>
                  {tDept(d)}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label>{t("statusField")}</label>
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              {(constants?.decision_statuses ?? [status]).map((s) => (
                <option key={s} value={s}>
                  {tStatus(s)}
                </option>
              ))}
            </select>
          </div>
        </div>

        {error && (
          <p className="muted" style={{ color: "var(--error)" }}>
            {error}
          </p>
        )}

        <div style={{ display: "flex", gap: "0.6rem", marginTop: "1.5rem", borderTop: "1px solid var(--border)", paddingTop: "1rem" }}>
          <button type="button" className="btn-secondary" onClick={() => router.back()}>
            {tc("cancel")}
          </button>
          <button type="submit" className="btn-primary" disabled={saving}>
            {saving ? tc("loading") : decisionId ? tc("saveChanges") : tc("create")}
          </button>
        </div>
      </div>
    </form>
  );
}
