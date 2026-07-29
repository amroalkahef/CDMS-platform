"use client";

import { Sparkles } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { useRouter } from "@/i18n/navigation";
import { apiErrorMessage } from "@/lib/errors";

export default function LoginPage() {
  const t = useTranslations("auth");
  const tc = useTranslations("common");
  const { user, login, register } = useAuth();
  const router = useRouter();

  const [mode, setMode] = useState<"login" | "register">("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<"editor" | "reviewer">("editor");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (user) router.replace("/");
  }, [user, router]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await register(name, email, password, role);
      }
      router.replace("/");
    } catch (e2) {
      setError(apiErrorMessage(e2, tc));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", padding: "1.5rem" }}>
      <div className="card" style={{ width: "100%", maxWidth: 420 }}>
        <div className="eyebrow" style={{ fontSize: "1.3rem", marginBottom: "0.3rem" }}>
          <Sparkles className="sparkle" size={22} />
          {t("brand")}
        </div>
        <p className="muted" style={{ marginTop: 0 }}>
          {mode === "login" ? t("loginSubtitle") : t("registerSubtitle")}
        </p>

        <form onSubmit={handleSubmit}>
          {mode === "register" && (
            <>
              <label>{t("nameField")}</label>
              <input value={name} onChange={(e) => setName(e.target.value)} required />
            </>
          )}

          <label>{t("emailField")}</label>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />

          <label>{t("passwordField")}</label>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={6} />

          {mode === "register" && (
            <>
              <label>{t("roleField")}</label>
              <select value={role} onChange={(e) => setRole(e.target.value as "editor" | "reviewer")}>
                <option value="editor">{t("roleEditor")}</option>
                <option value="reviewer">{t("roleReviewer")}</option>
              </select>
            </>
          )}

          {error && (
            <p className="muted" style={{ color: "var(--error)" }}>
              {error}
            </p>
          )}

          <button type="submit" className="btn-primary" disabled={loading} style={{ width: "100%", marginTop: "1.25rem" }}>
            {loading ? tc("loading") : mode === "login" ? t("loginButton") : t("registerButton")}
          </button>
        </form>

        <p className="muted" style={{ textAlign: "center", marginTop: "1rem" }}>
          {mode === "login" ? (
            <>
              {t("noAccount")}{" "}
              <button type="button" className="btn-secondary btn-sm" onClick={() => setMode("register")}>
                {t("registerButton")}
              </button>
            </>
          ) : (
            <>
              {t("haveAccount")}{" "}
              <button type="button" className="btn-secondary btn-sm" onClick={() => setMode("login")}>
                {t("loginButton")}
              </button>
            </>
          )}
        </p>

        {mode === "login" && (
          <p className="muted" style={{ fontSize: "0.78rem", textAlign: "center", marginTop: "1.5rem", borderTop: "1px solid var(--border)", paddingTop: "1rem" }}>
            {t("demoHint")}
            <br />
            <span dir="ltr">editor@demo.local / Editor123!</span>
            <br />
            <span dir="ltr">reviewer@demo.local / Reviewer123!</span>
          </p>
        )}
      </div>
    </div>
  );
}
