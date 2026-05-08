# The Twelve-Factor App Summary

This source document is a compact study note based on the public Twelve-Factor App methodology. It is included so the API can be indexed immediately in local development.

## Codebase

A twelve-factor app is tracked in one codebase in revision control. There can be many deploys of the same codebase, such as staging and production, but an app should not be split across multiple unrelated repositories when it represents one deployable service.

## Dependencies

Dependencies should be explicitly declared and isolated. A service should not rely on implicit system-wide packages. In Python this usually means a `requirements.txt`, `pyproject.toml`, or lock file plus an isolated environment.

## Config

Configuration is stored in the environment. Secrets, service URLs, API keys, and per-deploy settings should not be hardcoded in source code. This makes the same artifact portable between local, staging, and production.

## Backing Services

Backing services such as databases, caches, message queues, object storage, and external APIs are attached resources. The app should treat a local database and a managed cloud database through the same contract, normally a URL or credentials in environment variables.

## Build, Release, Run

The build stage converts source code into an executable artifact. The release stage combines the build with configuration. The run stage starts processes from that release. Keeping these stages separate makes rollbacks and reproducible deployments easier.

## Processes

Twelve-factor processes are stateless and share-nothing. Persistent data belongs in backing services, not in local process memory or local disk that disappears between deploys.

## Port Binding

The app exports HTTP as a service by binding to a port. It does not depend on a web server being injected into the runtime; instead the platform routes traffic to the port exposed by the app.

## Concurrency

Concurrency is handled by scaling process types. For an API service, multiple worker processes or machines can serve traffic, while background workers can process queues. This keeps scaling explicit and operationally visible.

## Disposability

Processes should start fast and shut down gracefully. This helps deploys, autoscaling, crash recovery, and local development. Long-running requests should react to cancellation when clients disconnect.

## Dev/Prod Parity

Development, staging, and production should stay as similar as possible. Differences in backing services, dependency versions, and deployment workflows create bugs that appear only after release.

## Logs

Logs are event streams. The app should write logs to standard output or structured log sinks and let the execution environment collect, route, and retain them.

## Admin Processes

Administrative tasks such as migrations, indexing, or one-off scripts should run as separate processes against the same release and configuration as the app.
