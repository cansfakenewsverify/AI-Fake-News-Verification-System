// Threads Web Intent link for "share to Threads" (S-08; FR-05; spec 5.3 share, 7.7).
// - text and url come verbatim from the backend share object (never composed here) and are
//   percent-encoded with encodeURIComponent, so "&", "#", "+", "%" and emoji survive intact.
// - No tag / reply_control parameters: Web Intent reply_control values differ from the Threads API.
// - Returns null when share is missing or incomplete; the caller then renders no share button.
// - Pure string building: works offline and needs no token.

export const THREADS_INTENT_URL = "https://www.threads.com/intent/post";

export function buildThreadsIntent(share) {
  const text = share?.text;
  const url = share?.url;
  if (typeof text !== "string" || text === "" || typeof url !== "string" || url === "") return null;
  try {
    return `${THREADS_INTENT_URL}?text=${encodeURIComponent(text)}&url=${encodeURIComponent(url)}`;
  } catch {
    return null; // encodeURIComponent throws on lone surrogates
  }
}
