"use client";

import EntityDetail from "@/components/EntityDetail";

export default function CircularDetailPage({ params }: { params: { id: string } }) {
  return <EntityDetail entityType="circular" entityId={params.id} />;
}
