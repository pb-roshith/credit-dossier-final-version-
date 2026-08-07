import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { BookOpen, Eye, EyeOff, Loader2, ShieldCheck } from "lucide-react";
import { useState } from "react";

import { useAuth } from "@/lib/auth";

export const Route = createFileRoute("/login")({
  head: () => ({ meta: [{ title: "Sign in | Credit Pitch Book" }] }),
  component: LoginPage,
});

function LoginPage() {
  const { login, register, resetPassword } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState<"login" | "register" | "reset">("login");
  const [userId, setUserId] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [role, setRole] = useState<"relationship_manager" | "credit_analyst">("credit_analyst");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSuccess(null);
    if (mode !== "login" && password !== confirmPassword) {
      setError("New password and confirm password must match.");
      return;
    }
    setSubmitting(true);
    try {
      if (mode === "login") {
        await login({ user_id: userId.trim(), password });
      } else if (mode === "register") {
        await register({
          user_id: userId.trim(),
          password,
          confirm_password: confirmPassword,
          role,
        });
        setSuccess("Account created successfully. You can now sign in.");
        setMode("login");
        setPassword("");
        setConfirmPassword("");
        setShowPassword(false);
        setShowConfirmPassword(false);
        return;
      } else {
        const message = await resetPassword({
          user_id: userId.trim(),
          new_password: password,
          confirm_password: confirmPassword,
        });
        setSuccess(message);
        setMode("login");
        setPassword("");
        setConfirmPassword("");
        setShowPassword(false);
        setShowConfirmPassword(false);
        return;
      }
      await navigate({ to: "/" });
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to continue.");
    } finally {
      setSubmitting(false);
    }
  }

  function changeMode(nextMode: "login" | "register" | "reset") {
    setMode(nextMode);
    setError(null);
    setSuccess(null);
    setConfirmPassword("");
    setShowPassword(false);
    setShowConfirmPassword(false);
  }

  return (
    <main className="relative flex min-h-screen items-center justify-center overflow-hidden bg-slate-950 px-4 py-10">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(37,99,235,0.25),transparent_36%),radial-gradient(circle_at_bottom_right,rgba(14,116,144,0.18),transparent_34%)]" />
      <div className="relative grid w-full max-w-4xl overflow-hidden rounded-2xl border border-white/10 bg-white shadow-2xl md:grid-cols-[1.05fr_1fr]">
        <section className="hidden bg-primary p-10 text-primary-foreground md:flex md:flex-col md:justify-between">
          <div className="flex items-center gap-3 text-xl font-semibold">
            <span className="rounded-lg bg-white/10 p-2">
              <BookOpen className="h-6 w-6" />
            </span>
            Credit Pitch Book
          </div>
          <div>
            <ShieldCheck className="mb-5 h-10 w-10 opacity-90" />
            <h1 className="text-3xl font-bold leading-tight">Secure credit dossier workspace</h1>
            <p className="mt-3 text-sm leading-6 text-primary-foreground/75">
              Create, review, and finalize private credit narratives with secure access to
              manufacturing tools.
            </p>
          </div>
          <p className="text-xs text-primary-foreground/60">Credit Dossier Pipeline</p>
        </section>

        <section className="p-6 sm:p-10">
          <div className="mb-7 md:hidden">
            <div className="flex items-center gap-2 font-semibold text-primary">
              <BookOpen className="h-5 w-5" /> Credit Pitch Book
            </div>
          </div>
          <h2 className="text-2xl font-bold tracking-tight">
            {mode === "login"
              ? "Welcome back"
              : mode === "register"
                ? "Create your account"
                : "Reset your password"}
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {mode === "login"
              ? "Enter your user ID and password to continue."
              : mode === "register"
                ? "Choose the role that matches your credit workflow."
                : "Enter your user ID and choose a new password."}
          </p>

          <form className="mt-7 space-y-4" onSubmit={submit}>
            <label className="block space-y-1.5 text-sm font-medium">
              User ID
              <input
                autoComplete="username"
                required
                minLength={3}
                maxLength={64}
                value={userId}
                onChange={(event) => setUserId(event.target.value)}
                className="h-11 w-full rounded-md border border-input bg-background px-3 font-normal outline-none focus:ring-2 focus:ring-ring"
                placeholder="Enter your user ID"
              />
            </label>
            <label className="block space-y-1.5 text-sm font-medium">
              {mode === "reset" ? "New password" : "Password"}
              <div className="relative">
                <input
                  autoComplete={mode === "login" ? "current-password" : "new-password"}
                  required
                  minLength={12}
                  maxLength={128}
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  onCopy={(event) => event.preventDefault()}
                  onCut={(event) => event.preventDefault()}
                  onPaste={(event) => event.preventDefault()}
                  className="h-11 w-full rounded-md border border-input bg-background px-3 pr-11 font-normal outline-none focus:ring-2 focus:ring-ring"
                  placeholder={mode === "login" ? "Enter your password" : "Minimum 12 characters"}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((value) => !value)}
                  className="absolute right-0 top-0 flex h-11 w-11 items-center justify-center text-muted-foreground"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </label>

            {mode !== "login" && (
              <label className="block space-y-1.5 text-sm font-medium">
                Confirm {mode === "reset" ? "new " : ""}password
                <div className="relative">
                  <input
                    autoComplete="new-password"
                    required
                    minLength={12}
                    maxLength={128}
                    type={showConfirmPassword ? "text" : "password"}
                    value={confirmPassword}
                    onChange={(event) => setConfirmPassword(event.target.value)}
                    onCopy={(event) => event.preventDefault()}
                    onCut={(event) => event.preventDefault()}
                    onPaste={(event) => event.preventDefault()}
                    className="h-11 w-full rounded-md border border-input bg-background px-3 pr-11 font-normal outline-none focus:ring-2 focus:ring-ring"
                    placeholder="Re-enter your password"
                  />
                  <button
                    type="button"
                    onClick={() => setShowConfirmPassword((value) => !value)}
                    className="absolute right-0 top-0 flex h-11 w-11 items-center justify-center text-muted-foreground"
                    aria-label={
                      showConfirmPassword ? "Hide confirm password" : "Show confirm password"
                    }
                  >
                    {showConfirmPassword ? (
                      <EyeOff className="h-4 w-4" />
                    ) : (
                      <Eye className="h-4 w-4" />
                    )}
                  </button>
                </div>
              </label>
            )}

            {mode === "register" && (
              <label className="block space-y-1.5 text-sm font-medium">
                Role
                <select
                  value={role}
                  onChange={(event) =>
                    setRole(event.target.value as "relationship_manager" | "credit_analyst")
                  }
                  className="h-11 w-full rounded-md border border-input bg-background px-3 font-normal outline-none focus:ring-2 focus:ring-ring"
                >
                  <option value="credit_analyst">Credit Analyst</option>
                  <option value="relationship_manager">Relationship Manager</option>
                </select>
              </label>
            )}

            {mode === "login" && (
              <div className="text-right">
                <button
                  type="button"
                  onClick={() => changeMode("reset")}
                  className="text-sm font-semibold text-primary hover:underline"
                >
                  Forgot password?
                </button>
              </div>
            )}

            {mode !== "login" && (
              <p className="text-xs leading-5 text-muted-foreground">
                Use at least 12 characters with uppercase, lowercase, a number, and a special
                character. Copy and paste are disabled for password fields.
              </p>
            )}

            {error && (
              <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2.5 text-sm text-destructive">
                {error}
              </div>
            )}

            {success && (
              <div className="rounded-md border border-emerald-300 bg-emerald-50 px-3 py-2.5 text-sm text-emerald-700">
                {success}
              </div>
            )}

            <button
              type="submit"
              disabled={submitting}
              className="inline-flex h-11 w-full items-center justify-center gap-2 rounded-md bg-primary px-4 text-sm font-semibold text-primary-foreground shadow hover:bg-primary/90 disabled:opacity-60"
            >
              {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
              {submitting
                ? "Please wait…"
                : mode === "login"
                  ? "Sign in"
                  : mode === "register"
                    ? "Create account"
                    : "Reset password"}
            </button>
          </form>

          <div className="mt-6 border-t pt-5 text-center text-sm text-muted-foreground">
            {mode === "login" ? "New to the application?" : "Return to the login page?"}{" "}
            <button
              type="button"
              onClick={() => changeMode(mode === "login" ? "register" : "login")}
              className="font-semibold text-primary hover:underline"
            >
              {mode === "login" ? "Create new user" : "Sign in"}
            </button>
          </div>
        </section>
      </div>
    </main>
  );
}
