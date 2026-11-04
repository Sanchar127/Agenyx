const SESSION_COOKIE_NAME = "agenyx_session";
const SESSION_TTL_MS = 24 * 60 * 60 * 1000; // 24 hours

export function setSessionCookie(
  response: Response,
  token: string,
  secure: boolean,
): void {
  response.headers.set(
    "Set-Cookie",
    `${SESSION_COOKIE_NAME}=${token}; Path=/; HttpOnly; SameSite=Lax${
      secure ? "; Secure" : ""
    }; Max-Age=${SESSION_TTL_MS / 1000}`,
  );
}

export function clearSessionCookie(response: Response): void {
  response.headers.set(
    "Set-Cookie",
    `${SESSION_COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0`,
  );
}

export function getSessionCookie(request: Request): string | undefined {
  const cookie = request.headers.get("cookie");
  if (!cookie) return undefined;

  for (const part of cookie.split(";")) {
    const [name, ...valueParts] = part.split("=").map((s) => s.trim());
    if (name === SESSION_COOKIE_NAME) {
      return valueParts.join("=");
    }
  }
  return undefined;
}
