"use client";

import { ArrowLeft } from "lucide-react";
import { useTranslations } from "next-intl";
import CircularForm from "@/components/CircularForm";
import { Link } from "@/i18n/navigation";

export default function NewCircularPage() {
  const t = useTranslations("circularForm");
  const tc = useTranslations("common");

  return (
    <div>
      <Link href="/circulars" className="back-link">
        <ArrowLeft size={15} />
        {tc("back")}
      </Link>
      <h1>{t("newTitle")}</h1>
      <p className="page-subtitle">{t("newSubtitle")}</p>
      <CircularForm />
    </div>
  );
}
