import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import ts from "typescript";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ReactMarkdown from "react-markdown";

const source = await readFile(new URL("../src/lib/markdown-security.ts", import.meta.url), "utf8");
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } });
const { safeMarkdownOptions, safeMarkdownUrl } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`);

test("stored and generated Markdown cannot render executable HTML or links", () => {
  const payloads = [
    '<script>alert(1)</script>',
    '<img src=x onerror=alert(1)>',
    '<svg onload=alert(1)>',
    '[click](javascript:alert%281%29)',
    '[click](jav&#x61;script:alert%281%29)',
    '[click][x]\n\n[x]: javascript:alert%281%29',
    '![image](data:image/svg+xml;base64,PHN2Zz4=)',
    '[click](vbscript:msgbox%281%29)',
  ];
  for (const content of payloads) {
    const html = renderToStaticMarkup(React.createElement(ReactMarkdown, safeMarkdownOptions, content));
    assert.doesNotMatch(html, /<(?:script|svg)\b|onerror=|onload=|(?:href|src)="(?:javascript|vbscript|data):/i, html);
  }
});

test("normal Markdown and trusted URL schemes still render", () => {
  const html = renderToStaticMarkup(React.createElement(ReactMarkdown, safeMarkdownOptions, '**Report** [source](https://example.com/report)'));
  assert.match(html, /<strong>Report<\/strong>/);
  assert.match(html, /href="https:\/\/example.com\/report"/);
  for (const url of ['https://example.com', '/privacy', '#section', 'mailto:team@example.com']) assert.equal(safeMarkdownUrl(url), url);
  for (const url of ['javascript:alert(1)', 'java\nscript:alert(1)', 'data:text/html,test', '//example.com', 'file:///etc/passwd']) assert.equal(safeMarkdownUrl(url), '');
});
