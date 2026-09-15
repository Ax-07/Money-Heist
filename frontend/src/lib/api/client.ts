import { z } from "zod";

export class ApiContractError extends Error {
  constructor(public readonly endpoint: string, cause: unknown) {
    super(`Données incompatibles reçues depuis ${endpoint}`);
    this.name = "ApiContractError";
    this.cause = cause;
  }
}

async function requestJson<Schema extends z.ZodTypeAny>(
  endpoint: string,
  schema: Schema,
  init?: RequestInit,
): Promise<z.output<Schema>> {
  const response = await fetch(`/api/money-heist${endpoint}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`${response.status} ${response.statusText}${body ? ` — ${body}` : ""}`);
  }
  const raw: unknown = await response.json();
  const parsed = schema.safeParse(raw);
  if (!parsed.success) throw new ApiContractError(endpoint, parsed.error);
  return parsed.data;
}

export const api = {
  get: <Schema extends z.ZodTypeAny>(endpoint: string, schema: Schema) =>
    requestJson(endpoint, schema),
  post: <Schema extends z.ZodTypeAny>(endpoint: string, schema: Schema, body: unknown) =>
    requestJson(endpoint, schema, { method: "POST", body: JSON.stringify(body) }),
  postRaw: <Schema extends z.ZodTypeAny>(
    endpoint: string,
    schema: Schema,
    body: BodyInit,
    contentType: string,
  ) => requestJson(endpoint, schema, { method: "POST", body, headers: { "Content-Type": contentType } }),
};
