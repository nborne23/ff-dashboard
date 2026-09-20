"""Typed exceptions shared across services and platform clients."""


class GridironError(Exception):
    """Base class for all GridIron application errors."""


class CredentialDecryptError(GridironError):
    """Raised when a stored credential can't be decrypted (bad key or corrupt token)."""


class AuthRequiredError(GridironError):
    """Raised when a platform call needs re-authentication (expired/invalid credentials)."""


class RateLimitedError(GridironError):
    """Raised when a platform keeps returning a rate-limit status after backoff retries."""


class MatchupNotFoundError(GridironError):
    """Raised when a league's schedule has no matchup for the requested week and team.

    Normal for a league that hasn't started (ESPN reports `current_week` 0 for one that
    hasn't drafted), so callers skip that league's matchup rather than failing the sync.
    """


class DraftPickConflictError(GridironError):
    """Raised by `draft_state.record_pick` when a manual pick names an `overall_pick`
    that's already taken by a *different* player. ESPN-sourced picks (phase 5) are
    allowed to overwrite/confirm a manual guess at the same slot -- only a manual ->
    manual collision on a different player is an error."""

    def __init__(self, overall_pick: int, existing_player_name: str) -> None:
        self.overall_pick = overall_pick
        self.existing_player_name = existing_player_name
        super().__init__(f"pick {overall_pick} is already recorded for {existing_player_name!r}")
