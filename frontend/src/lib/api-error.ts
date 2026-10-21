export type ApiErrorEnvelope = {
  error_code?: string;
  detail?: string;
  event_id?: string;
};

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly errorCode?: string,
    readonly eventId?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function apiErrorFromResponse(
  response: Response,
  fallback = "The request could not be completed.",
): Promise<ApiError> {
  const body = (await response.json().catch(() => null)) as ApiErrorEnvelope | null;
  const detail = typeof body?.detail === "string" ? body.detail : fallback;
  return new ApiError(detail, response.status, body?.error_code, body?.event_id);
}
