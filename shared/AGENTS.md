# Shared — Agent Guide (StayOS cross-feature layer)

`shared/` holds code genuinely shared across more than one StayOS feature. The
rule is strict: something moves here **only once a second real consumer exists**,
never speculatively. Today that bar is met by exactly one thing — the shared
StayOS auth module (`@stayos/auth`), consumed by the shell, LUMI, and PULSE. The
shared *infrastructure* carve-out (the Cognito user pool + WAF web ACL) is
**deliberately deferred** and does not live here yet.

The root [`../AGENTS.md`](../AGENTS.md) applies in full (safety rules, NAMING,
testing, runtime/stack). This file adds only `shared/` specifics. See
[`README.md`](./README.md) for the full rationale and the consumption mechanism.

## Structure

- `auth/` — the shared StayOS client-side authentication module, package name
  **`@stayos/auth`** (`shared/auth/package.json`). TypeScript, ESM, no build
  step — consumers import the `src/` directly via a path alias.
  - `src/index.ts` — public entry point (the only surface consumers import).
  - `src/auth.ts` — auth primitives: `signIn`, `refreshSession`, `signOut`,
    `getAccessToken`, `getIdToken`, `getCurrentUser`, `isAuthenticated`
    (Cognito `USER_PASSWORD_AUTH` + `REFRESH_TOKEN_AUTH`, JWT claim decoding).
  - `src/config.ts` — `initAuth({ cognitoClientId, cognitoRegion })` +
    `getAuthConfig()` / `getCognitoEndpoint()`. The module hardcodes **no**
    resource identifiers; each app injects its own env-derived config.
  - `src/storage.ts` — the `localStorage` session under the shared `stayos.*`
    key namespace (the mechanism that makes single sign-on work across the
    origin). SSR-safe (guards `typeof window`).
  - `src/types.ts` — `AuthTokens`, `AuthUser`, `AuthConfig`.
  - `src/__tests__/` — vitest unit tests + a fast-check property asserting all
    consumers agree on one session.

## How it is consumed (mechanism)

`@stayos/auth` is **not** an npm workspace package and has no build/publish step.
Each app resolves `@stayos/auth` to `shared/auth/src/index.ts` via a build-time
**TypeScript path alias**, wired in three places per app so build, typecheck, and
test all agree:

- `tsconfig.json` → `compilerOptions.paths["@stayos/auth"]`
- `next.config.js` → `transpilePackages: ['@stayos/auth']` + a webpack alias
- `vitest.config.ts` → `resolve.alias['@stayos/auth']`

Each app's `src/lib/auth.ts` is a thin adapter: it calls `initAuth()` once with
that app's Cognito config and re-exports the primitives, so existing
`@/lib/auth` imports keep working unchanged.

## Key invariants

- **Single source of truth.** `shared/auth/` is the one implementation of StayOS
  client-side auth. Do NOT fork or reimplement auth logic inside the shell, LUMI,
  or PULSE — those must consume `@stayos/auth`. A per-app auth copy (or a per-tab
  `sessionStorage` session) breaks single sign-on across the three apps.
- **No hardcoded resource identifiers.** The module carries no Cognito client ID,
  region, pool ID, or any environment value. Everything comes through
  `initAuth()` from each app's `NEXT_PUBLIC_*` build-time config. Keep it that
  way so the same code serves all three apps and all environments.
- **Shared session contract.** Tokens live in `localStorage` under the exact
  `stayos.*` keys (`ACCESS_TOKEN_KEY`, `ID_TOKEN_KEY`, `REFRESH_TOKEN_KEY`) on the
  one shared CloudFront origin. All three apps read/write these same keys — do
  NOT rename the namespace or switch to `sessionStorage`; that is what enables
  SSO and cross-app sign-out.
- **A change here is a coordinated three-consumer change.** Editing `shared/auth/`
  affects the shell + LUMI + PULSE at once. This is one of the two sanctioned
  cross-feature exceptions to the "one feature per change" rule (the other being
  the shared Gateway tool layer). Call it out explicitly, and verify all three
  consumers still build/test — do not silently change the session shape,
  `AuthUser` fields, or storage keys that any consumer relies on.
- **SSR-safe.** The apps are static-export Next.js; auth modules may be evaluated
  without a DOM. Guard every browser API (`typeof window`) as `storage.ts` does.
- **Populate `shared/` conservatively.** Add a new subdirectory here only when a
  second real consumer needs the code — not in anticipation. The shared
  infrastructure layer (Cognito/WAF) stays in `lumi/infrastructure/` until a
  second consumer's own stacks make the real dependency shape concrete; move
  `auth.yaml` (and, if genuinely shared, the WAF web ACL) into
  `shared/infrastructure/` only then.

## Commands

`shared/auth/` builds and tests in isolation (no deploy — it ships as source into
each consuming app's bundle):

```bash
cd shared/auth
npm install
npm test          # vitest (unit + fast-check SSO property), watch
npm run test:run  # vitest once (CI)
npm run typecheck # tsc --noEmit
```

To verify a change end to end, also run the consumers' test suites (they import
this module via the path alias): `stayos-shell`, `lumi`, and `pulse` — e.g.
`make test-all` from the repo root.

## Where to look first

- [`README.md`](./README.md) — full rationale, the consumption mechanism, and the
  deferred-infrastructure explanation.
- [`../AGENTS.md`](../AGENTS.md) — repo-wide rules and the shared-layer boundary.
- Each consumer's `src/lib/auth.ts` adapter (shell / LUMI / PULSE) for how
  `initAuth()` is wired per app.
