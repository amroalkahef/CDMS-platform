"use client";

import { ArrowLeft } from "lucide-react";
import { useTranslations } from "next-intl";
import DecisionForm from "@/components/DecisionForm";
import { Link } from "@/i18n/navigation";

export default function NewDecisionPage() {
  const t = useTranslations("decisionForm");
  const tc = useTranslations("common");

  return (
    <div>
      <Link href="/decisions" className="back-link">
        <ArrowLeft size={15} />
        {tc("back")}
      </Link>
      <h1>{t("newTitle")}</h1>
      <p className="page-subtitle">{t("newSubtitle")}</p>
      <DecisionForm />
    </div>
  );
}
