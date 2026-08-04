import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { BookOpen, Eye, EyeOff, Loader2, ShieldCheck } from "lucide-react";
import { useState } from "react";

import { useAuth } from "@/lib/auth";

export const Route = createFileRoute("/login")({
  head: () => ({ meta: [{ title: "Sign in | Credit Pitch Book" }] }),
  component: LoginPage,
});

function LoginPage() {
  const { login, register } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [userId, setUserId] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    if (mode === "register" && password !== confirmPassword) {
      setError("Password and confirm password must match.");
      return;
    }
    setSubmitting(true);
    try {
      if (mode === "login") {
        await login({ user_id: userId.trim(), password });
      } else {
        await register({
          user_id: userId.trim(),
          password,
          confirm_password: confirmPassword,
        });
      }
      await navigate({ to: "/" });
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to continue.");
    } finally {
      setSubmitting(false);
    }
  }

  function changeMode(nextMode: "login" | "register") {
    setMode(nextMode);
    setError(null);
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
              Create, review, and finalize credit narratives with controlled access to
              administrative data tools.
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
            {mode === "login" ? "Welcome back" : "Create your account"}
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {mode === "login"
              ? "Enter your user ID and password to continue."
              : "New accounts are created with normal-user access."}
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
              Password
              <div className="relative">
                <input
                  autoComplete={mode === "login" ? "current-password" : "new-password"}
                  required
                  minLength={8}
                  maxLength={128}
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  className="h-11 w-full rounded-md border border-input bg-background px-3 pr-11 font-normal outline-none focus:ring-2 focus:ring-ring"
                  placeholder="Minimum 8 characters"
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

            {mode === "register" && (
              <label className="block space-y-1.5 text-sm font-medium">
                Confirm password
                <div className="relative">
                  <input
                    autoComplete="new-password"
                    required
                    minLength={8}
                    maxLength={128}
                    type={showConfirmPassword ? "text" : "password"}
                    value={confirmPassword}
                    onChange={(event) => setConfirmPassword(event.target.value)}
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

            {error && (
              <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2.5 text-sm text-destructive">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={submitting}
              className="inline-flex h-11 w-full items-center justify-center gap-2 rounded-md bg-primary px-4 text-sm font-semibold text-primary-foreground shadow hover:bg-primary/90 disabled:opacity-60"
            >
              {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
              {submitting ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
            </button>
          </form>

          <div className="mt-6 border-t pt-5 text-center text-sm text-muted-foreground">
            {mode === "login" ? "New to the application?" : "Already have an account?"}{" "}
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
