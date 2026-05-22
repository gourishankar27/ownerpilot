import { betterAuth } from "better-auth";

import { appEnv } from "@/lib/env";
import { pool } from "@/lib/db";

export const auth = betterAuth({
  appName: "OwnerPilot",
  baseURL: appEnv.appUrl,
  secret: appEnv.authSecret,
  database: pool,
  trustedOrigins: [appEnv.appUrl],
  emailAndPassword: {
    enabled: true,
    autoSignIn: true,
    requireEmailVerification: false,
  },
  session: {
    cookieCache: {
      enabled: true,
      maxAge: 60 * 5,
    },
  },
});
