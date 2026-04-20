/**
 * Trigger a file download from a URL.
 *
 * Two paths:
 *  - bundled app (pywebview/WKWebView) → call Python save_file() via the JS
 *    bridge, which pops a native Save As dialog. WKWebView ignores both
 *    Content-Disposition: attachment and the <a download> attribute, so the
 *    browser-style flow only renders JSON inline there.
 *  - browser (dev / any real browser) → Blob + programmatic anchor click.
 */
declare global {
  interface Window {
    pywebview?: {
      api?: {
        save_file?: (filename: string, content: string) => Promise<boolean>;
      };
    };
  }
}

export async function downloadFromUrl(url: string, filename: string): Promise<void> {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Download failed: ${res.status} ${res.statusText}`);
  }

  if (window.pywebview?.api?.save_file) {
    const text = await res.text();
    await window.pywebview.api.save_file(filename, text);
    return;
  }

  const blob = await res.blob();
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objectUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(objectUrl);
}
