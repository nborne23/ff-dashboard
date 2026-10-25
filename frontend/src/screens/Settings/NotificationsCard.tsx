// "Notifications" settings-group (add-push-notifications): the one real push toggle —
// this device, the user's starters' touchdowns and 40+ yd plays — plus a test send.
//
// It replaced three Preferences toggles (score change / red zone / final recap) that
// persisted a choice nothing ever read. Like the theme switch before them, a control
// that does nothing is a control that lies.

import { useEffect, useState } from "react";

import {
  disablePush,
  enablePush,
  fetchPublicKey,
  pushSupport,
  sendTestPush,
  syncSubscription,
} from "../../api/push";
import { SettingsRow } from "./SettingsRow";
import { Switch } from "./Switch";

const LABEL = "Touchdowns & big plays";

function permission(): NotificationPermission {
  return typeof Notification === "undefined" ? "default" : Notification.permission;
}

export function NotificationsCard() {
  const support = pushSupport();
  const [publicKey, setPublicKey] = useState<string | null>(null);
  const [subscribed, setSubscribed] = useState(false);
  const [blocked, setBlocked] = useState(
    () => support === "supported" && permission() === "denied",
  );
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);

  // Fetch the key and resync up front, so the tap handler's first await can be the
  // permission prompt — iOS drops the prompt if anything else is awaited first.
  useEffect(() => {
    if (support !== "supported") return;
    let cancelled = false;
    fetchPublicKey()
      .then(async (key) => {
        if (cancelled) return;
        setPublicKey(key);
        const subscription = await syncSubscription(key);
        if (!cancelled) setSubscribed(subscription !== null);
      })
      .catch(() => {
        if (!cancelled) setStatus("Couldn't reach GridIron to check notifications.");
      });
    return () => {
      cancelled = true;
    };
  }, [support]);

  function onToggle(next: boolean) {
    setBusy(true);
    setStatus(null);
    const action = next
      ? enablePush(publicKey).then((result) => {
          setSubscribed(result === "enabled");
          setBlocked(result === "denied");
        })
      : disablePush().then(() => setSubscribed(false));
    action
      .catch(() => setStatus("That didn't work. Try again in a moment."))
      .finally(() => setBusy(false));
  }

  function onTest() {
    setBusy(true);
    setStatus(null);
    sendTestPush()
      .then(({ delivered }) =>
        setStatus(
          delivered > 0
            ? `Sent to ${delivered} ${delivered === 1 ? "device" : "devices"}.`
            : "No device accepted it. Turn the switch off and on again.",
        ),
      )
      .catch(() => setStatus("Couldn't send the test."))
      .finally(() => setBusy(false));
  }

  let sub: string;
  if (support === "needs-install") {
    sub = "Add GridIron to your Home Screen (Share → Add to Home Screen), then open it from there.";
  } else if (support === "unsupported") {
    sub = "This browser can't receive push notifications.";
  } else if (blocked) {
    sub = "Blocked for GridIron. Turn it back on in Settings → Notifications → GridIron.";
  } else {
    sub = "Alert this device when a starter scores or breaks a 40+ yd play";
  }
  const disabled = support !== "supported" || blocked || busy;

  return (
    <div className="settings-group">
      <h3>Notifications</h3>
      <SettingsRow
        label={LABEL}
        sub={sub}
        right={<Switch on={subscribed} onChange={onToggle} disabled={disabled} label={LABEL} />}
      />
      {subscribed && (
        <SettingsRow
          label="Send a test notification"
          sub={status ?? "Checks the whole path to this device"}
          right={
            <button type="button" className="btn" disabled={busy} onClick={onTest}>
              Send
            </button>
          }
        />
      )}
      {!subscribed && status && <SettingsRow label={status} />}
    </div>
  );
}
