"use client";

import { ArrowLeft } from "lucide-react";
import { useTranslations } from "next-intl";
import DecisionForm from "@/components/DecisionForm";
import { Link } from "@/i18n/navigation";

export default function EditDecisionPage({ params }: { params: { id: string } }) {
  const t = useTranslations("decisionForm");
  const tc = useTranslations("common");

  return (
    <div>
      <Link href={`/decisions/${params.id}`} className="back-link">
        <ArrowLeft size={15} />
        {tc("back")}
      </Link>
      <h1>{t("editTitle")}</h1>
      <p className="page-subtitle">{t("editSubtitle")}</p>
      <DecisionForm decisionId={params.id} />
    </div>
  );
}
