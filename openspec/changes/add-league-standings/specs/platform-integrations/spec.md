## ADDED Requirements

### Requirement: ESPN team logo fetching

The system SHALL fetch each fantasy team's logo from ESPN and serve it from local cache, so that logos render regardless of whether the upstream host will serve them to a browser.

#### Scenario: Logo source comes from the team payload

- **WHEN** a team is mapped from ESPN's `mTeam` view
- **THEN** its `logo` URL and `logoType` are read onto the team record
- **AND** a team with no logo records null rather than an empty string, so "has no logo" stays distinguishable from "has a logo whose URL is blank".

#### Scenario: Custom-uploaded logos require session credentials

- **WHEN** a logo whose type is a custom upload is fetched
- **THEN** the request SHALL carry the stored ESPN session cookies
- **AND** the fetch SHALL happen server-side, because that host returns **401 to an unauthenticated client** — a browser referencing the upstream URL directly receives an error, not an image, so proxying is required for correctness rather than for performance.

#### Scenario: Content type is stored, not inferred

- **WHEN** a logo is fetched and cached
- **THEN** the response's content type is recorded and echoed back when the image is served
- **AND** it SHALL NOT be inferred from the URL or assumed: a custom-upload URL carries no file extension, and the platform reports the nonstandard `image/jpg` for JPEG data.

#### Scenario: Vector logos are accepted only from the platform's own asset host

- **WHEN** a fetched logo reports an SVG content type
- **THEN** it is accepted only if its source host is the platform's stock-logo asset host, and otherwise falls back to a generic crest
- **AND** this is a security control, not a formatting preference: an SVG served from the application's own origin can execute script with same-origin access, and custom uploads are supplied by other league members rather than by the platform.

#### Scenario: Uploaded logos are restricted to raster formats

- **WHEN** a custom-uploaded logo is fetched
- **THEN** it is accepted only with a raster image content type, and any other type falls back to the crest
- **AND** the served response carries a header instructing the browser not to sniff the content type, so mislabeled bytes cannot be reinterpreted as markup.

#### Scenario: An authorization failure is retryable

- **WHEN** a logo fetch fails with 401
- **THEN** the failure SHALL NOT be cached, and the crest is returned for that request only
- **AND** the reason is that expired credentials are a recoverable state this application already handles: caching the failure would blank every team's logo until the cache was cleared by hand, and reconnecting would not restore them.

#### Scenario: A missing image may be cached

- **WHEN** a logo fetch returns 404
- **THEN** the outcome may be recorded, because the image is genuinely absent rather than temporarily unreachable.

#### Scenario: A changed source URL invalidates the cached image

- **WHEN** a team's stored logo source URL differs from the one the cached bytes were fetched for
- **THEN** the image is refetched
- **AND** this is how a logo change propagates: an uploaded logo's URL contains a generated identifier that changes when the image changes, so comparing the URL detects the change exactly, without guessing a refresh interval.

#### Scenario: No connected platform renders a crest

- **WHEN** a logo is requested and no platform credentials are stored
- **THEN** the crest is served rather than an error, so a fresh install renders placeholder logos instead of failing once per team.
