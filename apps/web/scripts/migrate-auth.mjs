// Use the already-installed Better Auth migrator; no floating CLI download.
import { getMigrations } from "better-auth/db/migration";
import { Pool } from "pg";

if (!process.env.DATABASE_URL)
  throw new Error("Set DATABASE_URL explicitly before migration.");
const pool = new Pool({ connectionString: process.env.DATABASE_URL });
try {
  const migrations = await getMigrations({
    database: pool,
    emailAndPassword: { enabled: true },
  });
  await migrations.runMigrations();
  console.log("Better Auth schema migration completed.");
} finally {
  await pool.end();
}
