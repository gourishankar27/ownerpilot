import { createHmac } from "node:crypto";
import { NextResponse } from "next/server";
import { pool } from "@/lib/db";
import { getSession } from "@/lib/session";

export const runtime = "nodejs";

async function proxy(
  request: Request,
  context: { params: Promise<{ path: string[] }> },
) {
  const session = await getSession();
  if (
    request.method !== "GET" &&
    request.headers.get("origin") !== new URL(request.url).origin
  ) {
    return NextResponse.json(
      { detail: "Same-origin request required." },
      { status: 403 },
    );
  }
  if (!session?.user)
    return NextResponse.json(
      { detail: "Sign in to use Procurement." },
      { status: 401 },
    );
  const { path } = await context.params;
  if (
    !/^(rfqs|rfq-jobs|rfq-health|catalogs|catalog-health|catalog-import-jobs|catalog-match-runs|agent-health|agent-runs|supplier-offers|quotes)$/.test(
      path[0] ?? "",
    ) ||
    path.some((p) => !/^[a-zA-Z0-9-]+$/.test(p))
  ) {
    return NextResponse.json(
      { detail: "Unknown procurement route." },
      { status: 404 },
    );
  }
  const secret = process.env.RFQ_AUTH_SECRET ?? "";
  if (secret.length < 32)
    return NextResponse.json(
      {
        detail:
          "Set the same RFQ_AUTH_SECRET on the web server and API (at least 32 random characters).",
      },
      { status: 503 },
    );
  try {
    const requested = request.headers.get("x-workspace-id");
    const membership = await pool.query<{ workspace_id: string }>(
      "select workspace_id from workspace_members where user_id=$1 and ($2::text is null or workspace_id::text=$2) order by created_at limit 1",
      [session.user.id, requested],
    );
    const workspace = membership.rows[0]?.workspace_id;
    if (!workspace)
      return NextResponse.json(
        {
          detail:
            "Create or select a workspace you belong to before using Procurement.",
        },
        { status: 403 },
      );
    const apiPath = `/api/${path.join("/")}`;
    const issued = Math.floor(Date.now() / 1000);
    const claims = Buffer.from(
      JSON.stringify({
        sub: session.user.id,
        workspace,
        iat: issued,
        exp: issued + 60,
        method: request.method,
        path: apiPath,
      }),
    ).toString("base64url");
    const signature = createHmac("sha256", secret).update(claims).digest("hex");
    const base =
      process.env.INTERNAL_API_BASE_URL ??
      process.env.NEXT_PUBLIC_API_BASE_URL ??
      "http://localhost:8000";
    const headers = new Headers({
      Authorization: `Bearer ${claims}.${signature}`,
    });
    const contentType = request.headers.get("content-type");
    if (contentType) headers.set("Content-Type", contentType);
    // Streaming avoids buffering multipart uploads a second time in the web process.
    const options: RequestInit & { duplex?: string } = {
      method: request.method,
      headers,
      cache: "no-store",
      signal: AbortSignal.timeout(30000),
    };
    if (request.method !== "GET") {
      options.body = request.body;
      options.duplex = "half";
    }
    const upstream = await fetch(
      `${base}${apiPath}${new URL(request.url).search}`,
      options,
    );
    const responseHeaders = new Headers({
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    });
    for (const key of ["content-type", "content-disposition"]) {
      const value = upstream.headers.get(key);
      if (value) responseHeaders.set(key, value);
    }
    return new Response(upstream.body, {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch {
    return NextResponse.json(
      {
        detail:
          "Procurement service unavailable. Check the API and database, then retry.",
      },
      { status: 503 },
    );
  }
}

export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
