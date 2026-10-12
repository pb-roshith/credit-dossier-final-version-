import { createFileRoute, Link } from "@tanstack/react-router";

export const Route = createFileRoute("/privacy")({
  head: () => ({ meta: [{ title: "Privacy Policy | Credit Dossier" }] }),
  component: PrivacyPolicy,
});

function PrivacyPolicy() {
  return (
    <main className="mx-auto max-w-3xl space-y-6 px-6 py-12 text-foreground">
      <h1 className="text-3xl font-semibold">Privacy Policy</h1>
      <p className="text-sm text-muted-foreground">Updated 12 October 2026</p>
      <p>This notice explains how Credit Dossier handles information when you use the application. Your organization operates your account and determines how its credit dossiers are used.</p>
      <section className="space-y-2">
        <h2 className="text-xl font-semibold">Information processed</h2>
        <p>The application processes account identifiers, roles, password hashes, security-question answer hashes, login sessions, and account approval information. It also processes customer and deal information, uploaded documents, templates, instructions, generated narratives, report versions, and review activity.</p>
        <p>Security and audit records can include account identifiers, IP addresses, timestamps, requested actions, and operation results. Upload only information your organization has authorized you to use.</p>
      </section>
      <section className="space-y-2">
        <h2 className="text-xl font-semibold">How information is used</h2>
        <p>Information supports sign-in, access control, credit assessment workflows, document processing, narrative generation, review, report export, troubleshooting, and security auditing.</p>
      </section>
      <section className="space-y-2">
        <h2 className="text-xl font-semibold">Service providers and connected sources</h2>
        <p>Document content and instructions may be sent to Mistral AI for configured document processing, moderation, and narrative generation. Connected company-data services supply information for dossiers. Hosting, database, and diagnostic services process information needed to operate the application. Configured telemetry may send diagnostic traces to Mistral.</p>
        <p>Provider arrangements and processing locations depend on your organization's deployment. Ask your administrator for the applicable details.</p>
      </section>
      <section className="space-y-2">
        <h2 className="text-xl font-semibold">Cookies and account security</h2>
        <p>A session cookie keeps you signed in. It is configured with Secure, HttpOnly, and SameSite restrictions. Passwords and security-question answers are stored as hashes. Server-side session and role checks restrict access to protected operations.</p>
      </section>
      <section className="space-y-2">
        <h2 className="text-xl font-semibold">Retention and requests</h2>
        <p>Account records, dossiers, uploaded files, audit records, and backups may have different retention periods. Your organization must confirm the applicable schedules; this notice does not specify an automatic deletion period.</p>
        <p>Contact your organization's application administrator or privacy team to ask about access, correction, deletion, retention, service providers, or a privacy concern. They can identify the organization responsible for your deployment and its privacy contact.</p>
      </section>
      <section className="space-y-2">
        <h2 className="text-xl font-semibold">Changes to this notice</h2>
        <p>Review this page for updates when the application's data handling changes.</p>
      </section>
      <Link to="/login" className="inline-block text-primary underline">Go to sign in</Link>
    </main>
  );
}
