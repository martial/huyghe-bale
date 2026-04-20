/**
 * Trigger a file download from a URL.
 *
 * Fetches the URL and creates a Blob so the browser/webview treats it as a
 * download regardless of Content-Disposition headers. The native WKWebView used
 * by pywebview ignores `download` attributes on <a> tags and renders JSON
 * inline, so this path is necessary for the bundled desktop app.
 */
export async function downloadFromUrl(url: string, filename: string): Promise<void> {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Download failed: ${res.status} ${res.statusText}`);
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
