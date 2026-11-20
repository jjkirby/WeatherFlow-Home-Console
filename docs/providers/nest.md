# Google Nest SDM provider

**Status** — Framework/scaffold only. Authentication and live collection are unimplemented. The planned first release is read-only and polls the SDM API at a configurable interval. Pub/Sub is deferred. No devices are verified with this provider. Ownership and reports go through the Home Telemetry fork.

| Device family | Framework verification |
| --- | --- |
| Nest thermostats exposed by SDM | Planned. No live device verified. |

## Account and project setup for a future implementation

1. Use a consumer Google Account that has access to a supported, activated Nest device. Register for Device Access and complete Google’s registration prerequisites. Create a Google Cloud project, enable the Smart Device Management API, configure OAuth consent, and create a user OAuth client ID and secret with an approved redirect URI. Create a Device Access project associated with that client ID. The Device Access Project ID identifies the enterprise in the device endpoint. [Device Access setup](https://developers.google.com/nest/device-access/get-started)
2. Use Partner Connections Manager to link the Device Access project with the user’s Google Account and grant the `https://www.googleapis.com/auth/sdm.service` scope to the selected devices. The user approves access interactively. Request offline access with `access_type=offline`. Use `prompt=consent` when fresh consent and a refresh token are needed. Exchange the one-time authorization code through Google OAuth. A client that receives no refresh token should surface authorization as incomplete without exposing the response. [Authorize an account](https://developers.google.com/nest/device-access/authorize) · [Google OAuth 2.0](https://developers.google.com/identity/protocols/oauth2)
3. Make the required `devices.list` call after authorization. Send `Authorization: Bearer <ACCESS_TOKEN>` with a space after `Bearer` and the current user access token. Access tokens normally expire after one hour. Refresh them using the user refresh token. For unattended operation, publish the external consent screen to Production and follow any verification requirements that apply. An external project left in Testing can receive refresh tokens that expire after seven days. Revocation, prolonged disuse, or an unrecoverable `invalid_grant` can require reauthorization. [Authorize an account](https://developers.google.com/nest/device-access/authorize) · [Authorization errors](https://developers.google.com/nest/device-access/reference/errors/authorization)

Device access uses the consumer user’s delegated grant from Partner Connections Manager. Service-account JWT flows authenticate a service identity, IAM impersonation changes that service identity, and Workspace domain-wide delegation with `with_subject` assumes a managed-domain user. These flows cannot grant a service account the consumer’s Nest device authorization. [Authorize an account](https://developers.google.com/nest/device-access/authorize) · [Google OAuth 2.0](https://developers.google.com/identity/protocols/oauth2)

## Planned measurements and data handling

Read `Temperature`, `Humidity`, `Connectivity`, `ThermostatMode`, `ThermostatEco`, `ThermostatTemperatureSetpoint`, and `ThermostatHvac` when present. Store separate nullable heating and cooling setpoints in Celsius. Missing traits remain unknown. Mode describes the requested behavior, while HVAC status describes active equipment state. Polling records observed changes and may miss changes between polls. The first release will use device reads and no thermostat commands. [Thermostat API](https://developers.google.com/nest/device-access/api/thermostat)

The framework caps SDM-derived retention at ten trailing days from receipt, runs expiry on startup and periodically, and supports explicit purge. Do not retain long-term aggregates, backups, or logs containing expired SDM-derived data. Keep client secrets and refresh tokens in restricted local configuration or a secret store, referenced through the environment. Thermostat state and timestamps can reveal household schedules. Share only synthetic data in fixtures and reports. [Device Access policies](https://developers.google.com/nest/device-access/policies)

```toml
[[providers]]
id = "future-entryway-thermostat"
type = "nest_sdm"
enabled = false
room = "Example entryway"
retention_days = 10

[providers.settings]
project_id = "DEVICE-ACCESS-PROJECT-PLACEHOLDER"
client_id = "${EXAMPLE_NEST_CLIENT_ID}"
client_secret = "${EXAMPLE_NEST_CLIENT_SECRET}"
refresh_token = "${EXAMPLE_NEST_REFRESH_TOKEN}"
poll_seconds = 120
```

## Troubleshooting and test requirements

| Response | What to check |
| --- | --- |
| `401` | Check the Bearer header and token expiry. Refresh once and retry the read. Repeated authorization failure should enter authentication-required health. |
| `invalid_grant` | Check expired or revoked refresh tokens, Testing-mode expiry, and an expired or consumed authorization code. Start fresh user authorization when recovery requires it. |
| `unauthorized_client` | Check the OAuth client type, allowed flow, scopes, and association with the Device Access project. |
| `invalid_scope` | Check the exact SDM scope and consent configuration. |
| Enterprise not found | Confirm the Device Access Project ID rather than the Cloud project ID, the associated OAuth client, and that the account granted device access. |

Tests must use mocked endpoints for token expiry and refresh, invalid grants, rate limits, missing traits, connectivity, mode changes, dual setpoints, state persistence, retention, and redaction. A real authorization test should run only when a maintainer deliberately configures a test account and device. [Google authorization errors](https://developers.google.com/nest/device-access/reference/errors/authorization)
