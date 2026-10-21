// Stored and generated Markdown stays untrusted, including legacy records.
export function safeMarkdownUrl(value: string): string {
  if (/[\u0000-\u0020\u007f<>"'\\]/.test(value)) return "";
  if (value.startsWith("//")) return "";
  const scheme = /^([a-z][a-z0-9+.-]*):/i.exec(value)?.[1].toLowerCase();
  return !scheme || ["http", "https", "mailto"].includes(scheme) ? value : "";
}

export const safeMarkdownOptions = { skipHtml: true, urlTransform: safeMarkdownUrl };
