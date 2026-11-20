import { NextResponse } from "next/server";
import { pool } from "@/lib/db";
import { getSession } from "@/lib/session";

export async function GET() {
  const session = await getSession();
  if (!session?.user)
    return NextResponse.json(
      { detail: "Sign in to use Procurement." },
      { status: 401 },
    );
  try {
    const result = await pool.query(
      "select w.id,w.name,m.role from business_workspaces w join workspace_members m on m.workspace_id=w.id where m.user_id=$1 order by w.name",
      [session.user.id],
    );
    return NextResponse.json(result.rows, {
      headers: { "Cache-Control": "no-store" },
    });
  } catch {
    return NextResponse.json(
      { detail: "Workspace service unavailable." },
      { status: 503 },
    );
  }
}
