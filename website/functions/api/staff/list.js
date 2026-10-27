/**
 * Cloudflare Pages Function: /api/staff/list
 * Returns registered website staff members.
 */
export async function onRequest(context) {
  const { request, env } = context;
  const url = new URL(request.url);

  // If backend is configured, attempt backend query first
  const backendBase = (
    env.BACKEND_URL ||
    env.KYOKA_BACKEND_URL ||
    'https://kyokasugisetsu.onrender.com'
  ).replace(/\/+$/, '');

  if (backendBase) {
    try {
      const res = await fetch(`${backendBase}/api/staff/list`, {
        headers: request.headers,
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

  // Authoritative edge staff roster
  const staff = [
    {
      user_id: '1505515188991033409',
      username: 'Aizen (ruthupavan)',
      role_level: 'admin',
      added_by: '1505515188991033409',
      added_at: '2026-01-01T00:00:00Z',
    },
    {
      user_id: '1532660258403647687',
      username: 'mrhowler01',
      role_level: 'admin',
      added_by: '1505515188991033409',
      added_at: '2026-10-27T11:46:50Z',
    },
  ];

  return new Response(JSON.stringify({ success: true, staff, total: staff.length }), {
    status: 200,
    headers: {
      'Content-Type': 'application/json',
      'Access-Control-Allow-Origin': url.origin,
      'Access-Control-Allow-Credentials': 'true',
    },
  });
}
