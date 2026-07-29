"use client";

import { useTranslations } from "next-intl";
import { SimilarityHit } from "@/lib/api";

const VERDICT_BADGE: Record<string, string> = {
  duplicate: "badge-rejected",
  related: "badge-pending_approval",
  different: "badge-draft",
  unknown: "badge-draft",
};

export default function SimilarityResults({
  checking,
  results,
}: {
  checking: boolean;
  results: SimilarityHit[] | null;
}) {
  const tSim = useTranslations("similarity");
  const tDept = useTranslations("departments");

  if (checking) return <p className="muted">{tSim("checking")}</p>;
  if (results === null) return <p className="muted">{tSim("idle")}</p>;
  if (results.length === 0) return <p className="muted">{tSim("noMatches")}</p>;

  return (
    <>
      {results.map((hit) => (
        <div key={hit.id} className="similarity-hit" style={{ alignItems: "flex-start" }}>
          <div>
            <strong>{hit.title}</strong>{" "}
            <span className={`badge ${VERDICT_BADGE[hit.verdict] ?? "badge-draft"}`}>
              {tSim(`verdict${hit.verdict.charAt(0).toUpperCase()}${hit.verdict.slice(1)}` as "verdictDuplicate")}
            </span>
            <p className="muted" style={{ margin: "0.2rem 0 0" }}>
              {tDept(hit.department)}
            </p>
            {hit.explanation && (
              <p className="muted" style={{ margin: "0.2rem 0 0", fontStyle: "italic" }}>
                {hit.explanation}
              </p>
            )}
          </div>
          <span className="muted" style={{ whiteSpace: "nowrap" }}>
            {Math.round(hit.similarity * 100)}%
          </span>
        </div>
      ))}
    </>
  );
}
