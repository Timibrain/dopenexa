# Google sign-in

Set `GOOGLE_CLIENT_ID` on the existing Railway API service to a Google Cloud **Web application** OAuth client ID. Add authorized JavaScript origins:

- https://staging.dopenexa.com
- https://dopenexa.com
- https://www.dopenexa.com

No client secret or redirect URI is used by this popup credential flow. The frontend fetches the public client ID at runtime from `/auth/google/config`; it hides Google sign-in until configured. Existing Redis stores five-minute one-use challenges. Google credentials are verified against Google's rotating RSA keys, audience, issuer, expiry, issued time, authorized party, verified email and server-generated nonce before issuing the existing Dopenexa access/refresh tokens.

Existing Google identities retain their Dopenexa role. New identities create customer accounts. An email collision with an existing account is rejected; users must use their original sign-in method. Automatic account linking by email is deliberately unsupported. No database migration is needed: Google uses the existing `auth_identities` table.

Validation: Google/Apple auth unit tests and host health checks; frontend Google success, collision/retry and disabled configuration browser tests. Real Google popup verification requires the configured client ID and a user selecting their Google account. Never log Google identity tokens.
