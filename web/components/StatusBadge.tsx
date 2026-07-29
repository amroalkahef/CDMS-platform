"use client";

import { useTranslations } from "next-intl";

export default function StatusBadge({ status }: { status: string }) {
  const t = useTranslations("statuses");
  return <span className={`badge badge-${status}`}>{t.has(status) ? t(status) : status}</span>;
}
