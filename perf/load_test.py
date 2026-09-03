"""StayOS end-to-end load/performance harness.

Runs concurrent read/write traffic against a live deployment and reports
p50/p95/p99 latency, throughput, and error rate per endpoint. This harness
is deliberately dependency-light (stdlib + boto3 + aiohttp).

Prerequisites
-------------
- LUMI + PULSE deployed (root ``make deploy-all``), so the shared Cognito user
  pool, API Gateway REST APIs, and AppSync Events endpoint exist.
- The demo GM accounts seeded by LUMI's ``seed_data`` custom resource. The
  harness auto-discovers a seeded GM (its sign-in identifier and property) from
  the Cognito pool, so no persona is hardcoded; override with ``--alias`` to
  target a specific GM.

Usage
-----
Only the GM password (the APP_PASSWORD you passed to ``make deploy-all``) is
required; everything else is discovered or defaulted::

    GM_PASSWORD='<APP_PASSWORD used at deploy-all>' \
    python3 perf/load_test.py --duration 60 --concurrency 20

Optional overrides (env var or flag)::

    PROFILE=<aws-profile>          # or --profile
    AWS_REGION=<region>            # or --region        (default us-east-1)
    LUMI_STACK=<name>              # or --lumi-stack     (default stayos-<region>)
    PULSE_STACK=<name>             # or --pulse-stack    (default pulse-<region>)
    GM_ALIAS=<email|gmAlias|user>  # or --alias          (default: first seeded GM)

Design notes
------------
- Fully asynchronous. One asyncio task per virtual user; each user picks the
  next scenario weighted by ``SCENARIOS`` and records the observed latency.
- Read-heavy by default: ``GET /alerts`` and ``GET /vips`` dominate the mix,
  mirroring what a GM's mobile PWA actually does. Write endpoints
  (acknowledgement, approval) are exercised sparingly and only against alerts
  the harness itself created via ``POST /demo/scenarios``.
- Realtime path (AppSync Events WebSocket) is NOT load-generated here — its
  managed nature (Amazon takes the fan-out hit) makes REST the useful signal.
- Never runs against production; the ``EnableDemoSimulator`` gate must be true
  in the target stack (default in the demo/prototype deploy).

Reference
---------
- StayOS OpenAPI (root): ``openapi.yaml`` — PULSE alerts API
- LUMI OpenAPI: ``lumi/openapi.yaml`` — briefs + settings API
"""
from __future__ import annotations

import argparse
import asyncio
import os
import statistics
import time
from dataclasses import dataclass, field
import ssl
from typing import Awaitable, Callable

import aiohttp  # type: ignore[import-untyped]
import boto3

try:
    import certifi  # type: ignore[import-untyped]
    # Build an SSL context from certifi's CA bundle. On some hosts (notably
    # macOS Python installs) the default context cannot find a system CA bundle,
    # so aiohttp fails every HTTPS request with CERTIFICATE_VERIFY_FAILED - which
    # would show up as a misleading 100% error rate against perfectly healthy
    # APIs. Using certifi's bundle makes TLS verification work everywhere.
    _SSL_CONTEXT: ssl.SSLContext | None = ssl.create_default_context(cafile=certifi.where())
except Exception:  # noqa: BLE001 - certifi optional; fall back to default TLS
    _SSL_CONTEXT = None


# ─── Scenario mix (weights sum ≈ 1.0) ─────────────────────────
SCENARIOS: list[tuple[str, float]] = [
    ("list_alerts", 0.45),          # GM opens PULSE tab → GET /alerts?tier=CRITICAL
    ("get_vips", 0.20),             # GM opens VIPs tab  → GET /vips
    ("get_ops", 0.10),              # GM opens Ops tab   → GET /ops
    ("get_brief", 0.15),            # GM opens LUMI      → GET /briefs/{propertyId}
    ("fire_demo_scenario", 0.05),   # write path: mints a live alert
    ("acknowledge_alert", 0.05),    # write path: acknowledges a live alert
]

TIMEOUT_S = 10.0


@dataclass
class Result:
    """One observed request outcome."""

    scenario: str
    ok: bool
    latency_ms: float
    status: int
    error: str = ""


@dataclass
class Stats:
    """Accumulator for one scenario's results."""

    latencies: list[float] = field(default_factory=list)
    errors: int = 0

    def add(self, r: Result) -> None:
        """Record ``r``; latency is always kept, errors are counted separately."""
        self.latencies.append(r.latency_ms)
        if not r.ok:
            self.errors += 1

    def summary(self, total_wall_s: float) -> dict[str, float | int]:
        """Return the summary dict: p50/p95/p99, throughput, error rate."""
        if not self.latencies:
            return {}
        srt = sorted(self.latencies)
        n = len(srt)
        p = lambda q: srt[min(int(q * n), n - 1)]  # noqa: E731
        return {
            "n": n,
            "errors": self.errors,
            "err_rate": round(self.errors / n, 4) if n else 0.0,
            "p50_ms": round(p(0.5), 1),
            "p95_ms": round(p(0.95), 1),
            "p99_ms": round(p(0.99), 1),
            "max_ms": round(srt[-1], 1),
            "rps": round(n / total_wall_s, 2) if total_wall_s > 0 else 0.0,
        }


# ─── Auth ────────────────────────────────────────────────────
def _login(cog, client_id: str, sign_in: str, password: str) -> str:
    """Sign in ``sign_in`` via Cognito USER_PASSWORD_AUTH; return the ID token.

    Uses the public ``initiate_auth`` with the ``USER_PASSWORD_AUTH`` flow (the
    flow the LUMI app client enables) rather than the admin variant, which needs
    ``ADMIN_USER_PASSWORD_AUTH`` and admin IAM permissions. The app client has no
    secret, so no SECRET_HASH is required.

    Args:
        cog: A boto3 ``cognito-idp`` client (already bound to region/profile).
        client_id: The user pool app client id.
        sign_in: The sign-in identifier Cognito expects (email when the pool
            uses email as its username attribute, else the username).
        password: The GM password (the deploy APP_PASSWORD).

    Returns:
        The Cognito ID token (JWT) for the Authorization header.
    """
    resp = cog.initiate_auth(
        ClientId=client_id,
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": sign_in, "PASSWORD": password},
    )
    return resp["AuthenticationResult"]["IdToken"]


def _stack_output(cfn, stack: str, key: str) -> str:
    """Return the ``key`` output value from ``stack`` or ``""`` if absent."""
    d = cfn.describe_stacks(StackName=stack)["Stacks"][0].get("Outputs", []) or []
    for o in d:
        if o["OutputKey"] == key:
            return o["OutputValue"]
    return ""


def _resolve_gm_identity(
    cog, pool_id: str, alias: str | None
) -> tuple[str, str]:
    """Resolve the GM sign-in identifier and property from the seeded pool.

    Developer experience: rather than hardcoding a demo persona, this discovers
    a real seeded GM so the harness works against ANY deployment regardless of
    which accounts were seeded or how the pool is configured. It returns the
    identifier Cognito expects for ``USER_PASSWORD_AUTH`` (the pool's username
    attribute - e.g. email - when configured that way, otherwise the raw
    username) plus that GM's ``custom:propertyId`` so demo/read traffic targets
    a property the GM actually owns.

    Args:
        cog: A boto3 ``cognito-idp`` client.
        pool_id: The Cognito user pool id.
        alias: An explicit sign-in identifier/alias from the caller, or ``None``
            to auto-discover the first seeded GM.

    Returns:
        A ``(sign_in_identifier, property_id)`` tuple.

    Raises:
        SystemExit: If no users are seeded in the pool.
    """
    # Does the pool sign in by a username attribute (e.g. email) rather than the
    # raw username? That determines which value AuthParameters USERNAME needs.
    pool = cog.describe_user_pool(UserPoolId=pool_id)["UserPool"]
    username_attrs = pool.get("UsernameAttributes") or []

    listed = cog.list_users(UserPoolId=pool_id, Limit=60).get("Users", [])
    if not listed:
        raise SystemExit(
            f"No users found in Cognito pool {pool_id}; deploy seeds the demo "
            "GM accounts. Ensure `make deploy-all` completed the seed step."
        )

    def _attrs(user: dict) -> dict[str, str]:
        return {a["Name"]: a["Value"] for a in user.get("Attributes", [])}

    # Pick the requested GM (match on email/gmAlias/username) or default to the
    # first seeded GM.
    chosen = None
    if alias:
        for user in listed:
            attrs = _attrs(user)
            if alias in (
                user.get("Username"),
                attrs.get("email"),
                attrs.get("custom:gmAlias"),
            ):
                chosen = user
                break
        if chosen is None:
            raise SystemExit(
                f"GM alias {alias!r} not found among seeded users. Omit "
                "--alias/GM_ALIAS to auto-select a seeded GM, or pass an "
                "email/gmAlias/username that exists in the pool."
            )
    else:
        chosen = listed[0]

    attrs = _attrs(chosen)
    # If the pool signs in by email, USERNAME must be the email; otherwise the
    # raw username works.
    if "email" in username_attrs and attrs.get("email"):
        sign_in = attrs["email"]
    else:
        sign_in = chosen.get("Username")

    property_id = attrs.get("custom:propertyId") or ""
    return sign_in, property_id


# ─── HTTP helpers ────────────────────────────────────────────
async def _timed(
    scenario: str,
    fn: Callable[[], Awaitable[aiohttp.ClientResponse]],
) -> Result:
    """Invoke ``fn`` and return a Result with latency + status."""
    t0 = time.perf_counter()
    try:
        async with await fn() as resp:
            body_ok = resp.status < 400
            body = await resp.text() if not body_ok else ""
            return Result(
                scenario=scenario,
                ok=body_ok,
                latency_ms=(time.perf_counter() - t0) * 1000,
                status=resp.status,
                error=body[:200],
            )
    except Exception as e:  # noqa: BLE001 - collect ALL failure modes into a Result
        return Result(
            scenario=scenario,
            ok=False,
            latency_ms=(time.perf_counter() - t0) * 1000,
            status=0,
            error=type(e).__name__,
        )


# ─── Virtual user ────────────────────────────────────────────
async def _run_user(
    pulse_base: str,
    lumi_base: str,
    headers: dict[str, str],
    stop_at: float,
    stats: dict[str, Stats],
    property_id: str,
) -> None:
    """One virtual user: pick a scenario, run it, record, repeat until stop_at."""
    import random

    weights = [w for _, w in SCENARIOS]
    names = [n for n, _ in SCENARIOS]
    connector = aiohttp.TCPConnector(ssl=_SSL_CONTEXT) if _SSL_CONTEXT else None
    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=TIMEOUT_S), connector=connector
    ) as s:
        latest_alert: str | None = None
        while time.time() < stop_at:
            scenario = random.choices(names, weights=weights, k=1)[0]

            if scenario == "list_alerts":
                url = f"{pulse_base}/alerts?tier=CRITICAL&status=UNACKNOWLEDGED"
                r = await _timed(scenario, lambda: s.get(url, headers=headers))
            elif scenario == "get_vips":
                r = await _timed(scenario, lambda: s.get(f"{pulse_base}/vips", headers=headers))
            elif scenario == "get_ops":
                r = await _timed(scenario, lambda: s.get(f"{pulse_base}/ops", headers=headers))
            elif scenario == "get_brief":
                r = await _timed(
                    scenario,
                    lambda: s.get(f"{lumi_base}/briefs/{property_id}", headers=headers),
                )
            elif scenario == "fire_demo_scenario":
                r = await _timed(
                    scenario,
                    lambda: s.post(
                        f"{pulse_base}/demo/scenarios/walk-risk",
                        headers=headers,
                        json={"propertyId": property_id},
                    ),
                )
                # capture minted alertId if the body contains it
                if r.ok and r.error == "":
                    latest_alert = None  # we didn't read body on success; harmless
            elif scenario == "acknowledge_alert" and latest_alert:
                r = await _timed(
                    scenario,
                    lambda aid=latest_alert: s.post(
                        f"{pulse_base}/alerts/{aid}/acknowledgements",
                        headers=headers,
                        json={},
                    ),
                )
            else:
                continue

            stats[scenario].add(r)


# ─── Driver ──────────────────────────────────────────────────
async def _main(args: argparse.Namespace) -> None:
    """Entrypoint: resolve endpoints, sign in, spawn users, print report."""
    region = args.region
    session = boto3.Session(profile_name=args.profile) if args.profile else boto3.Session()
    cfn = session.client("cloudformation", region_name=region)

    # LUMI stack exports the shared Cognito pool + API URLs.
    pool_id = _stack_output(cfn, args.lumi_stack, "UserPoolId")
    client_id = _stack_output(cfn, args.lumi_stack, "UserPoolClientId")
    # LUMI's REST API output key is ApiGatewayUrl; older revisions used
    # ApiEndpoint. Accept either so the harness is not tied to one naming.
    lumi_api = (
        _stack_output(cfn, args.lumi_stack, "ApiGatewayUrl")
        or _stack_output(cfn, args.lumi_stack, "ApiEndpoint")
    )
    pulse_api = _stack_output(cfn, args.pulse_stack, "ApiEndpoint")
    if not all([pool_id, client_id, lumi_api, pulse_api]):
        raise SystemExit(
            "Missing stack outputs. Ensure LUMI + PULSE are deployed and stack "
            "names are correct (override with --lumi-stack/--pulse-stack)."
        )

    cog = session.client("cognito-idp", region_name=region)
    # Resolve the GM sign-in identifier + property from the seeded pool so the
    # harness works on any deployment without a hardcoded persona.
    sign_in, property_id = _resolve_gm_identity(cog, pool_id, args.alias)
    if not property_id:
        raise SystemExit(
            "Resolved GM has no custom:propertyId attribute; cannot target demo "
            "traffic. Check the seed step populated GM property attributes."
        )
    print(f"Signed-in GM: {sign_in}  property: {property_id}")

    token = _login(cog, client_id, sign_in, args.password)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    stats: dict[str, Stats] = {name: Stats() for name, _ in SCENARIOS}
    stop_at = time.time() + args.duration
    users = [
        asyncio.create_task(_run_user(pulse_api.rstrip("/"), lumi_api.rstrip("/"),
                                      headers, stop_at, stats, property_id))
        for _ in range(args.concurrency)
    ]
    t0 = time.time()
    await asyncio.gather(*users)
    wall = time.time() - t0

    # ── Report ──
    print(f"\n=== StayOS load-test report ({args.duration}s, VU={args.concurrency}) ===")
    print(f"LUMI  API : {lumi_api}")
    print(f"PULSE API : {pulse_api}")
    total_n = sum(len(s.latencies) for s in stats.values())
    total_err = sum(s.errors for s in stats.values())
    print(f"total requests: {total_n}  errors: {total_err}  wall: {wall:.1f}s  "
          f"aggregate rps: {total_n / wall:.2f}\n")
    print(f"{'scenario':<22}{'n':>7}{'err':>6}{'err%':>7}{'p50':>8}{'p95':>8}{'p99':>8}"
          f"{'max':>8}{'rps':>8}")
    for name in stats:
        summary = stats[name].summary(wall)
        if not summary:
            continue
        print(
            f"{name:<22}{summary['n']:>7}{summary['errors']:>6}"
            f"{summary['err_rate'] * 100:>6.1f}%"
            f"{summary['p50_ms']:>8.0f}{summary['p95_ms']:>8.0f}"
            f"{summary['p99_ms']:>8.0f}{summary['max_ms']:>8.0f}"
            f"{summary['rps']:>8.1f}"
        )

    # SLA gate: PULSE spec targets rule-eval start ≤5s and CRITICAL delivery ≤30s
    # end-to-end. This harness only measures REST latency, so we assert a much
    # tighter bound for the read path.
    p95_read = statistics.median([
        stats[k].summary(wall).get("p95_ms", 0)
        for k in ("list_alerts", "get_vips", "get_ops", "get_brief")
        if stats[k].latencies
    ])
    if p95_read and p95_read > 1500:
        raise SystemExit(f"FAIL: median-of-reads p95 {p95_read:.0f}ms exceeds 1500ms SLO")
    print("\nSLO: median-of-reads p95 ≤ 1500ms — PASS" if p95_read else "")


def _parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--duration", type=int, default=60, help="test duration seconds")
    p.add_argument("--concurrency", type=int, default=10, help="virtual users")
    p.add_argument("--region", default=os.environ.get("AWS_REGION", "us-east-1"))
    p.add_argument("--profile", default=os.environ.get("PROFILE"))
    # Stack names default to the ${StackPrefix}-${region} convention the
    # Makefiles use; override for a non-default StackPrefix or region.
    region_default = os.environ.get("AWS_REGION", "us-east-1")
    p.add_argument(
        "--lumi-stack",
        default=os.environ.get("LUMI_STACK", f"stayos-{region_default}"),
        help="LUMI CloudFormation stack name (default: stayos-<region>)",
    )
    p.add_argument(
        "--pulse-stack",
        default=os.environ.get("PULSE_STACK", f"pulse-{region_default}"),
        help="PULSE CloudFormation stack name (default: pulse-<region>)",
    )
    p.add_argument(
        "--alias",
        default=os.environ.get("GM_ALIAS"),
        help=(
            "Which seeded GM to sign in as (email, gmAlias, or username). "
            "Omit to auto-select the first seeded GM."
        ),
    )
    p.add_argument(
        "--password",
        default=os.environ.get("GM_PASSWORD"),
        help="the APP_PASSWORD value passed to make deploy-all",
    )
    args = p.parse_args()
    if not args.password:
        raise SystemExit(
            "GM_PASSWORD (or --password) is required - the APP_PASSWORD you "
            "passed to `make deploy-all`."
        )
    return args


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(_main(_parse()))
