import { NextRequest } from "next/server";

const upstream = (process.env.MONEY_HEIST_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

async function proxy(request: NextRequest, context: {params: Promise<{path: string[]}>}) {
  const {path} = await context.params;
  const url = new URL(`${upstream}/${path.map(encodeURIComponent).join("/")}`);
  request.nextUrl.searchParams.forEach((value, key) => url.searchParams.append(key, value));
  const method = request.method.toUpperCase();
  const body = method === "GET" || method === "HEAD" ? undefined : request.body ?? undefined;
  const init: RequestInit & {duplex?: "half"} = {
    method,
    body,
    headers: {
      "accept": request.headers.get("accept") ?? "application/json",
      "content-type": request.headers.get("content-type") ?? "application/json"
    },
    cache: "no-store"
  };
  if (body) init.duplex = "half";
  const response = await fetch(url, init);
  const headers = new Headers();
  const contentType = response.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);
  const disposition = response.headers.get("content-disposition");
  if (disposition) headers.set("content-disposition", disposition);
  return new Response(response.body, {status: response.status, headers});
}

export const GET = proxy;
export const POST = proxy;
export const HEAD = proxy;
