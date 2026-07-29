"use client";

import { ArrowLeft } from "lucide-react";
import { useTranslations } from "next-intl";
import CircularForm from "@/components/CircularForm";
import { Link } from "@/i18n/navigation";

export default function EditCircularPage({ params }: { params: { id: string } }) {
  const t = useTranslations("circularForm");
  const tc = useTranslations("common");

  return (
    <div>
      <Link href={`/circulars/${params.id}`} className="back-link">
        <ArrowLeft size={15} />
        {tc("back")}
      </Link>
      <h1>{t("editTitle")}</h1>
      <p className="page-subtitle">{t("editSubtitle")}</p>
      <CircularForm circularId={params.id} />
    </div>
  );
}
