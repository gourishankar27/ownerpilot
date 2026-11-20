import { defineConfig } from "drizzle-kit";

export default defineConfig({
  schema: "./lib/schema.ts",
  out: "./drizzle",
  dialect: "postgresql",
  // RFQ tables live in the separately owned procurement schema.
  schemaFilter: ["public"],
  tablesFilter: [
    "business_workspaces",
    "workspace_members",
    "suppliers",
    "products",
    "expense_entries",
    "recurring_obligations",
    "sales_transactions",
    "purchase_transactions",
    "business_documents",
    "import_jobs",
    "import_job_rows",
    "model_provider_settings",
    "document_chunks",
    "action_center_items",
    "scheduler_runs",
  ],
  dbCredentials: {
    url:
      process.env.DATABASE_URL ??
      "postgresql://postgres:postgres@localhost:5433/ownerpilot",
  },
});
