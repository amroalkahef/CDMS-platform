"use client";

import { ArrowLeft } from "lucide-react";
import { useTranslations } from "next-intl";
import EntityForm from "@/components/EntityForm";
import PageHeader from "@/components/PageHeader";
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
      <PageHeader title={t("editTitle")} subtitle={t("editSubtitle")} />
      <EntityForm entityType="circular" entityId={params.id} />
    </div>
  );
}
