import { drizzle } from "drizzle-orm/node-postgres";
import { Pool } from "pg";

import { appEnv } from "@/lib/env";

const globalForDb = globalThis as typeof globalThis & {
  ownerPilotPool?: Pool;
};

export const pool =
  globalForDb.ownerPilotPool ??
  new Pool({
    connectionString: appEnv.databaseUrl,
  });

if (process.env.NODE_ENV !== "production") {
  globalForDb.ownerPilotPool = pool;
}

export const db = drizzle(pool);
