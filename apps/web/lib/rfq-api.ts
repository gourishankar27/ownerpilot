export async function rfqApi<T>(
  path: string,
  workspace: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(`/api/procurement/${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      "x-workspace-id": workspace,
      ...(init?.body instanceof FormData
        ? {}
        : { "Content-Type": "application/json" }),
      ...init?.headers,
    },
  });
  const data = await response.json();
  if (!response.ok) {
    const detail = data.detail;
    throw new Error(
      response.status === 409
        ? "This RFQ changed or is locked. Reload to continue. " +
            (typeof detail === "string" ? detail : "")
        : typeof detail === "string"
          ? detail
          : (detail?.message ??
            "Request failed. Check the fields and try again."),
    );
  }
  return data as T;
}
