"use client";

import { Library } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import ErrorCard from "@/components/ErrorCard";
import PageHeader from "@/components/PageHeader";
import { api } from "@/lib/api";
import { apiErrorMessage } from "@/lib/errors";

export default function KnowledgePage() {
  const t = useTranslations("knowledge");
  const tc = useTranslations("common");

  const [title, setTitle] = useState("");
  const [docType, setDocType] = useState("policy");
  const [content, setContent] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ document_id: string; chunks_created: number } | null>(null);

  const docTypes = ["policy", "circular", "decision", "regulation", "procedure", "template", "faq"];

  async function handleIngest() {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const r = file
        ? await api.uploadDocument(file, docType, title || undefined)
        : await api.ingest({ title, doc_type: docType, source: "web-console", content });
      setResult(r);
      setTitle("");
      setContent("");
      setFile(null);
    } catch (e) {
      setError(apiErrorMessage(e, tc));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <PageHeader icon={Library} title={t("title")} subtitle={t("subtitle")} />

      <div className="card" style={{ maxWidth: 640 }}>
        <label>{t("titleField")}</label>
        <input value={title} onChange={(e) => setTitle(e.target.value)} />

        <label>{t("docTypeField")}</label>
        <select value={docType} onChange={(e) => setDocType(e.target.value)}>
          {docTypes.map((dt) => (
            <option key={dt} value={dt}>
              {t(`docTypes.${dt}`)}
            </option>
          ))}
        </select>

        <label>{t("uploadField")}</label>
        <input type="file" accept=".txt,.pdf,.png,.jpg,.jpeg,.tiff,.bmp,.webp" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />

        {!file && (
          <>
            <label>{t("contentField")}</label>
            <textarea value={content} onChange={(e) => setContent(e.target.value)} placeholder={t("contentPlaceholder")} style={{ minHeight: 200 }} />
          </>
        )}

        <button className="btn-primary" onClick={handleIngest} disabled={loading || !docType || (!file && (!title || !content))} style={{ marginTop: "1.2rem" }}>
          {loading ? t("ingesting") : t("submit")}
        </button>
      </div>

      {error && (
        <div className="card">
          <strong>{tc("error")}</strong>
          <p className="muted">{error}</p>
        </div>
      )}

      {result && (
        <div className="card">
          {t("ingested", { id: result.document_id, count: result.chunks_created })}
        </div>
      )}
    </div>
  );
}
