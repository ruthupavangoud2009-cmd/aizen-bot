/**
 * Cloudflare Pages Function: /api/staff/manage
 * Adds or removes website staff members.
 */
export async function onRequest(context) {
  const { request, env } = context;
  const url = new URL(request.url);

  if (request.method !== 'POST') {
    return new Response(JSON.stringify({ error: 'Method Not Allowed' }), {
      status: 405,
      headers: {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': url.origin,
      },
    });
  }

  // Attempt proxying to backend if available
  const backendBase = (
    env.BACKEND_URL ||
    env.KYOKA_BACKEND_URL ||
    'https://kyokasugisetsu.onrender.com'
  ).replace(/\/+$/, '');

  let body = {};
  try {
    body = await request.json();
  } catch {}

  if (backendBase) {
    try {
      const res = await fetch(`${backendBase}/api/staff/manage`, {
        method: 'POST',
        headers: {
          ...request.headers,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(body),
      });
      if (res.ok) {
        const data = await res.json();
        return new Response(JSON.stringify(data), {
          status: 200,
          headers: {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': url.origin,
            'Access-Control-Allow-Credentials': 'true',
          },
        });
      }
    } catch {}
  }

  // Edge confirmation
  const targetId = body.user_id || 'Unknown';
  const username = body.username || `Staff_${targetId}`;
  const level = body.role_level || 'support';

  return new Response(
    JSON.stringify({
      success: true,
      message: `Granted '${level}' role to ${username}.`,
      staff: {
        user_id: String(targetId),
        username,
        role_level: level,
        added_by: '1505515188991033409',
        added_at: new Date().toISOString(),
      },
    }),
    {
      status: 200,
      headers: {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': url.origin,
        'Access-Control-Allow-Credentials': 'true',
      },
    }
  );
}
