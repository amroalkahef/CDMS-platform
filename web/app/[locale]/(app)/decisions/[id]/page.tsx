"use client";

import EntityDetail from "@/components/EntityDetail";

export default function DecisionDetailPage({ params }: { params: { id: string } }) {
  return <EntityDetail entityType="decision" entityId={params.id} />;
}
