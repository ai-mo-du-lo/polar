# PolarEndpoint5xx

## Purpose

Investigate a burst of 5xx responses on one Polar API endpoint. The alert
names the endpoint and method in its labels and fires within two minutes of
the first server error.

## Instructions

1. Read the alert labels: `endpoint`, `method`, `environment` and, when
   present, `exception`. The `exception` label names the exception type and
   the innermost Polar function that raised it.
2. Find the route handler for the endpoint under `server/polar/` and follow
   the call into the function the `exception` label names.
3. Compare the failing requests in the API logs with what that function
   expects: which fields the request sends, and which the function reads.
4. Read the Sentry issue for the same endpoint for the full stack trace and
   the request that raised it.
5. Check whether a recent change touched that function or its callers.

## Expected evidence

- Server errors only on the endpoint and method in the alert; other
  endpoints stay healthy.
- One exception type in the API logs and in Sentry, raised from the function
  the alert names.
