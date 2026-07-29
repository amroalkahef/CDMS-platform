import { useTranslations } from "next-intl";

/** Thrown by lib/api.ts for any failed request. `code` is a stable
 * machine-readable identifier (e.g. "workflow_not_found") that the backend
 * services attach to structured error responses (see
 * backend/app/errors.py and ai-platform/app/errors.py); `params` carries
 * any values to interpolate into the translated message. `detail` keeps
 * the raw server body for debugging/logging, never for display. */
export class ApiError extends Error {
  constructor(
    public code: "notAuthenticated" | "requestFailed" | string,
    public status?: number,
    public params?: Record<string, string | number>,
    public detail?: string
  ) {
    super(code);
    this.name = "ApiError";
  }
}

type CommonTranslator = ReturnType<typeof useTranslations<"common">>;

/** Renders an error caught from an `api.*` call using the `common`
 * translator (`useTranslations("common")`), which also holds one key per
 * backend `error_code` (see messages/en.json's `common` namespace). Falls
 * back to a generic message for codes without a translation. */
export function apiErrorMessage(e: unknown, tc: CommonTranslator): string {
  if (e instanceof ApiError) {
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      return tc(e.code as any, e.params);
    } catch {
      return tc("requestFailed");
    }
  }
  return tc("requestFailed");
}
