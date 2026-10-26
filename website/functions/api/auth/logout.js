/**
 * Cloudflare Pages Function: /api/auth/logout
 * Clears session cookie.
 */

export async function onRequest(context) {
  const { request } = context;
  const url = new URL(request.url);

  const clearCookie = `kyoka_session=; Path=/; Max-Age=0; Expires=Thu, 01 Jan 1970 00:00:00 GMT; SameSite=Lax${url.protocol === 'https:' ? '; Secure' : ''}`;

  return new Response(JSON.stringify({ success: true, message: 'Logged out successfully.' }), {
    status: 200,
    headers: {
      'Content-Type': 'application/json',
      'Set-Cookie': clearCookie,
      'Access-Control-Allow-Origin': url.origin,
      'Access-Control-Allow-Credentials': 'true',
    },
  });
}
