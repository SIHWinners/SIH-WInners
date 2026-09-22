import { createApi, unwrap } from '@sm/contracts/client';

/** Browser client. Calls go to the same-origin proxy, which attaches the session cookie. */
export const api = createApi(typeof window === 'undefined' ? 'http://127.0.0.1:3000/api' : `${window.location.origin}/api`);
export { unwrap };
export { ApiError } from '@sm/contracts/client';
export type * from '@sm/contracts/client';
