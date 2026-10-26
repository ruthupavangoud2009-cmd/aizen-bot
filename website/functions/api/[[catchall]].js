/**
 * Cloudflare Pages Function: Transparent Edge Proxy for /api/* requests.
 * Proxies API traffic from https://aizen-bot.pages.dev/api/* to the active Render backend.
 *
 * This provides 1st-party cookie support on aizen-bot.pages.dev, completely
 * avoiding 3rd-party cookie blocking and cross-origin preflight overhead.
 */

export async function onRequest(context) {
  const { request, env } = context;
  const url = new URL(request.url);

  // Handle CORS preflight directly at the Cloudflare edge
  if (request.method === 'OPTIONS') {
    return new Response(null, {
      status: 204,
      headers: {
        'Access-Control-Allow-Origin': url.origin,
        'Access-Control-Allow-Credentials': 'true',
        'Access-Control-Allow-Methods': 'GET, POST, PATCH, PUT, DELETE, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Requested-With, Accept',
        'Access-Control-Max-Age': '86400',
      },
    });
  }

  // Read backend base URL from Cloudflare environment variable, or use Render backend default
  const backendBase = (
    env.BACKEND_URL ||
    env.KYOKA_BACKEND_URL ||
    'https://kyoka-discord-bot.onrender.com'
  ).replace(/\/+$/, '');

  // Target path: e.g. https://kyoka-discord-bot.onrender.com/api/auth/me
  const targetUrl = new URL(`${backendBase}${url.pathname}${url.search}`);

  // Clone headers and preserve client IP, host, and cookies
  const headers = new Headers(request.headers);
  headers.set('X-Forwarded-Host', url.host);
  headers.set('X-Forwarded-Proto', url.protocol.replace(':', ''));
  if (!headers.get('Origin')) {
    headers.set('Origin', url.origin);
  }

  // Build outbound fetch request
  const init = {
    method: request.method,
    headers: headers,
    redirect: 'manual', // preserve 302 redirects (such as OAuth authorization redirects)
  };

  // Only attach body for non-GET/HEAD methods
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    init.body = request.body;
  }

  try {
    const response = await fetch(targetUrl.toString(), init);

    // Clone response headers
    const responseHeaders = new Headers(response.headers);

    // Adjust CORS headers for same-origin client
    responseHeaders.set('Access-Control-Allow-Origin', url.origin);
    responseHeaders.set('Access-Control-Allow-Credentials', 'true');
    responseHeaders.set('Access-Control-Allow-Methods', 'GET, POST, PATCH, PUT, DELETE, OPTIONS');
    responseHeaders.set('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With, Accept');

    // Preserve redirect Location header
    if (response.status >= 300 && response.status < 400) {
      const loc = response.headers.get('location');
      if (loc) {
        responseHeaders.set('Location', loc);
      }
    }

    // Return response directly (including Set-Cookie headers)
    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders,
    });
  } catch (err) {
    return new Response(
      JSON.stringify({
        error: 'Backend Service Waking Up',
        message: `Cloudflare Pages connecting to Render backend (${backendBase}). Please allow 20-30 seconds if service was sleeping.`,
        hint: 'If this persists, verify your Render backend deployment.',
        details: err.message,
      }),
      {
        status: 503,
        headers: {
          'Content-Type': 'application/json',
          'Access-Control-Allow-Origin': url.origin,
          'Access-Control-Allow-Credentials': 'true',
          'Retry-After': '10',
        },
      }
    );
  }
}
