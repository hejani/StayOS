# StayOS Shell — Agent Guide

The StayOS shell is the unified entry point: it owns the site root (`/`) on the
shared StayOS CloudFront distribution, presenting the login form when
unauthenticated and the feature launcher grid (LUMI at `/lumi`, PULSE at
`/pulse`) when authenticated. It is what makes single sign-on across StayOS work
— a GM signs in here once and both features trust the shared session.

The root [`../AGENTS.md`](../AGENTS.md) applies in full (safety rules, PYQUALITY
where relevant, NAMING, testing, runtime/stack). This file adds only shell
specifics. Region `us-east-1`.

## Structure

- `frontend/` — Next.js 15 App Router PWA, static export (`output: 'export'`,
  `basePath` unset so it serves from `/`). Consumes the shared `@stayos/auth`
  module. `src/app/page.tsx` is the whole app: login vs. feature grid.
- No backend, no infrastructure of its own — the shell is static assets served
  from the shared LUMI S3 bucket / CloudFront distribution (deploy wiring is
  part of the shared-hosting change).

## Key invariants

- **The shell is the ONE place a GM logs in.** LUMI and PULSE must not present
  their own login as an entry point; they trust the shared session and redirect
  unauthenticated users back here (`/`).
- **Auth is the shared module, not a copy.** All auth logic lives in
  `shared/auth/` and is consumed via the `@stayos/auth` path alias. `src/lib/auth.ts`
  only calls `initAuth()` with the shell's env config and re-exports primitives —
  do not fork auth logic into the shell.
- **Session config must match LUMI/PULSE.** The shell authenticates against the
  shared LUMI Cognito user pool; `NEXT_PUBLIC_COGNITO_CLIENT_ID` /
  `NEXT_PUBLIC_COGNITO_REGION` MUST equal LUMI's so the issued token is valid for
  all three apps.
- **Launcher routing is fixed:** active features link out with raw `<a>` (full
  navigation across basePath) — LUMI to `/lumi/`, PULSE to `/pulse/`.

## Commands

```bash
cd frontend
npm install          # .npmrc pins legacy-peer-deps (React 19 / testing-library 15)
npm run test:run     # vitest component + property tests
npm run build        # static export to out/
```

## Testing

- vitest + @testing-library/react for the login/grid views; fast-check for the
  launcher routing property. Mock the auth boundary (`@/lib/auth`) in component
  tests.
