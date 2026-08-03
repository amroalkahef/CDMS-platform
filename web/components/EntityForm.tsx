"use client";

import { Info, Sparkles } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import SimilarityResults from "@/components/SimilarityResults";
import { useRouter } from "@/i18n/navigation";
import { api, Circular, Constants, Decision, SimilarityHit } from "@/lib/api";
import { apiErrorMessage } from "@/lib/errors";

type EntityType = "circular" | "decision";

export default function EntityForm({ entityType, entityId }: { entityType: EntityType; entityId?: string }) {
  const isCircular = entityType === "circular";
  const t = useTranslations(isCircular ? "circularForm" : "decisionForm");
  const tc = useTranslations("common");
  const tSim = useTranslations("similarity");
  const tDept = useTranslations("departments");
  const tFreq = useTranslations("frequencies");
  const tStatus = useTranslations("statuses");
  const locale = useLocale();
  const router = useRouter();
  const { user } = useAuth();

  const [constants, setConstants] = useState<Constants | null>(null);
  const [entityNumber, setEntityNumber] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [department, setDepartment] = useState("Administration");
  const [primaryDate, setPrimaryDate] = useState("");
  const [frequency, setFrequency] = useState("One-Time");
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
    if (!entityId) return;
    const load = isCircular ? api.getCircular(entityId) : api.getDecision(entityId);
    load.then((e) => {
      setEntityNumber(isCircular ? (e as Circular).circular_number : (e as Decision).decision_number);
      setTitle(e.title);
      setContent(e.content);
      setDepartment(e.department);
      setPrimaryDate((isCircular ? (e as Circular).publication_date : (e as Decision).effective_date) ?? "");
      if (isCircular) setFrequency((e as Circular).frequency);
      setStatus(e.status);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entityId, entityType]);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!title.trim() && !content.trim()) {
      setSimilarity(null);
      return;
    }
    debounceRef.current = setTimeout(async () => {
      setCheckingSimilarity(true);
      try {
        const r = await api.checkSimilarity({ entity_type: entityType, title, content, exclude_id: entityId });
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
  }, [title, content, entityId, entityType]);

  async function handleGenerate() {
    setGenerating(true);
    setError(null);
    try {
      const r = await api.draft({
        task_type: isCircular ? "generate_circular" : "generate_decision",
        user_prompt: aiPrompt,
        doc_type_filter: entityType,
        language: locale,
      });
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
    try {
      let saved: Circular | Decision;
      if (isCircular) {
        const payload = { title, content, department, frequency, publication_date: primaryDate || undefined, status };
        saved = entityId ? await api.updateCircular(entityId, payload) : await api.createCircular(payload);
      } else {
        const payload = { title, content, department, effective_date: primaryDate || undefined, status };
        saved = entityId ? await api.updateDecision(entityId, payload) : await api.createDecision(payload);
      }
      router.push(`/${isCircular ? "circulars" : "decisions"}/${saved.id}`);
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

  const statuses = isCircular ? constants?.circular_statuses : constants?.decision_statuses;

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
            <label>{isCircular ? t("circularNumberField") : t("decisionNumberField")}</label>
            <input
              dir={entityNumber ? "ltr" : undefined}
              value={entityNumber ?? (isCircular ? t("circularNumberAutoHint") : t("decisionNumberAutoHint"))}
              disabled
            />
          </div>
          <div>
            <label>{isCircular ? t("publicationDateField") : t("effectiveDateField")}</label>
            <input type="date" value={primaryDate} onChange={(e) => setPrimaryDate(e.target.value)} />
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
          {isCircular ? (
            <div>
              <label>{t("frequencyField")}</label>
              <select value={frequency} onChange={(e) => setFrequency(e.target.value)}>
                {(constants?.circular_frequencies ?? [frequency]).map((f) => (
                  <option key={f} value={f}>
                    {tFreq(f)}
                  </option>
                ))}
              </select>
            </div>
          ) : (
            <div>
              <label>{t("statusField")}</label>
              <select value={status} onChange={(e) => setStatus(e.target.value)}>
                {(statuses ?? [status]).map((s) => (
                  <option key={s} value={s}>
                    {tStatus(s)}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        {isCircular && (
          <>
            <label>{t("statusField")}</label>
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              {(statuses ?? [status]).map((s) => (
                <option key={s} value={s}>
                  {tStatus(s)}
                </option>
              ))}
            </select>
          </>
        )}

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
            {saving ? tc("loading") : entityId ? tc("saveChanges") : tc("create")}
          </button>
        </div>
      </div>
    </form>
  );
}
