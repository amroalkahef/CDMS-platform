"use client";

import { ArrowLeft } from "lucide-react";
import { useTranslations } from "next-intl";
import EntityForm from "@/components/EntityForm";
import PageHeader from "@/components/PageHeader";
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
      <PageHeader title={t("editTitle")} subtitle={t("editSubtitle")} />
      <EntityForm entityType="decision" entityId={params.id} />
    </div>
  );
}
