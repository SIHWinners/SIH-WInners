import createClient, { type Middleware } from 'openapi-fetch';

import type { components, paths } from './generated/api';

export type Schemas = components['schemas'];
export type ApplicantFacts = Schemas['ApplicantFacts'];
export type EvaluateResponse = Schemas['EvaluateResponse'];
export type SchemeResult = Schemas['SchemeResult'];
export type TraceRow = Schemas['TraceRow'];
export type EmiRequest = Schemas['EmiRequest'];
export type EmiResponse = Schemas['EmiResponse'];
export type NearbyResponse = Schemas['NearbyResponse'];
export type PartnerCard = Schemas['PartnerCard'];
export type ExcludedPartner = Schemas['ExcludedPartner'];

/** RFC 7807 body the core returns; clients map user_message_key to localized text. */
export interface Problem {
  status: number;
  title?: string;
  detail?: string;
  user_message_key: string;
  [extra: string]: unknown;
}

export class ApiError extends Error {
  constructor(public readonly problem: Problem) {
    super(problem.title ?? problem.user_message_key);
  }
}

export function createApi(baseUrl: string, getToken?: () => string | null | undefined) {
  const client = createClient<paths>({ baseUrl });
  if (getToken) {
    const auth: Middleware = {
      onRequest({ request }) {
        const token = getToken();
        if (token) request.headers.set('authorization', `Bearer ${token}`);
        return request;
      },
    };
    client.use(auth);
  }
  return client;
}

/** Unwraps an openapi-fetch result or throws ApiError with a localisable key. */
export async function unwrap<T>(promise: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  let result;
  try {
    result = await promise;
  } catch {
    throw new ApiError({ status: 0, user_message_key: 'errors.offline' });
  }
  if (result.data !== undefined && result.response.ok) return result.data;
  const err = (result.error ?? {}) as Partial<Problem>;
  throw new ApiError({
    ...err,
    status: result.response.status,
    user_message_key: err.user_message_key ?? (result.response.status >= 500 ? 'errors.server_down' : 'errors.generic'),
  });
}

export type Api = ReturnType<typeof createApi>;
export type { components, paths };
