// Web Push on the client (add-push-notifications): service worker registration, the
// subscribe/unsubscribe round trip with /api/push/*, and the support checks the Settings
// card branches on. Delivery and display live in public/sw.js.
//
// iOS rules that shape this file:
// - Push exists only in a Home Screen app (iOS 16.4+). In Safari proper there is no
//   `PushManager`, which `pushSupport` reports as "needs-install" rather than "no".
// - `Notification.requestPermission()` only prompts from a user gesture, so it has to be
//   the FIRST await in the tap handler — see `enablePush`.

import { apiClient } from "./client";

export type PushSupport = "supported" | "needs-install" | "unsupported";

export function pushSupport(): PushSupport {
  if (
    typeof navigator !== "undefined" &&
    "serviceWorker" in navigator &&
    typeof window !== "undefined" &&
    "PushManager" in window &&
    "Notification" in window
  ) {
    return "supported";
  }
  return isAppleMobile() && !isStandalone() ? "needs-install" : "unsupported";
}

function isAppleMobile(): boolean {
  if (typeof navigator === "undefined") return false;
  // iPadOS reports itself as a Mac; the touch points give it away.
  return /iPhone|iPad|iPod/.test(navigator.userAgent) || navigator.maxTouchPoints > 1;
}

function isStandalone(): boolean {
  const legacy = (navigator as Navigator & { standalone?: boolean }).standalone;
  return legacy === true || window.matchMedia?.("(display-mode: standalone)").matches === true;
}

/** Register /sw.js. Called once from main.tsx; harmless where push is unsupported. */
export function registerServiceWorker(): void {
  if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) return;
  navigator.serviceWorker.register("/sw.js").catch(() => {
    // No worker means no push, which the Settings card already reports. Nothing else
    // in the app depends on it.
  });
}

export async function fetchPublicKey(): Promise<string> {
  const { public_key } = await apiClient.get<{ public_key: string }>("/api/push/vapid-public-key");
  return public_key;
}

export function decodeBase64Url(value: string): Uint8Array<ArrayBuffer> {
  const base64 = (value + "=".repeat((4 - (value.length % 4)) % 4))
    .replace(/-/g, "+")
    .replace(/_/g, "/");
  const binary = atob(base64);
  const bytes = new Uint8Array(new ArrayBuffer(binary.length));
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

function sameKey(subscription: PushSubscription, publicKey: string): boolean {
  const current = subscription.options?.applicationServerKey;
  if (!current) return true; // Can't tell (older WebKit): trust it, the server will say.
  const a = new Uint8Array(current);
  const b = decodeBase64Url(publicKey);
  return a.length === b.length && a.every((byte, i) => byte === b[i]);
}

async function registration(): Promise<ServiceWorkerRegistration> {
  return navigator.serviceWorker.ready;
}

async function saveSubscription(subscription: PushSubscription): Promise<void> {
  await apiClient.post("/api/push/subscriptions", subscription.toJSON());
}

/**
 * The current subscription, kept in step with the server: re-posted on every call (that
 * repairs a server that lost it) and replaced when the server's key has changed (every
 * old subscription is dead then). Returns null when this browser isn't subscribed.
 */
export async function syncSubscription(publicKey: string): Promise<PushSubscription | null> {
  const reg = await registration();
  let subscription = await reg.pushManager.getSubscription();
  if (!subscription) return null;
  if (!sameKey(subscription, publicKey)) {
    await subscription.unsubscribe();
    if (Notification.permission !== "granted") return null;
    subscription = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: decodeBase64Url(publicKey),
    });
  }
  await saveSubscription(subscription);
  return subscription;
}

export type EnableResult = "enabled" | "denied" | "dismissed";

/** The toggle turned on. Call straight from the tap handler (see the file comment). */
export async function enablePush(publicKey: string | null): Promise<EnableResult> {
  const permission = await Notification.requestPermission();
  if (permission !== "granted") return permission === "denied" ? "denied" : "dismissed";
  const key = publicKey ?? (await fetchPublicKey());
  const reg = await registration();
  const subscription = await reg.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: decodeBase64Url(key),
  });
  await saveSubscription(subscription);
  return "enabled";
}

export async function disablePush(): Promise<void> {
  const subscription = await (await registration()).pushManager.getSubscription();
  if (!subscription) return;
  await apiClient.delete("/api/push/subscriptions", { endpoint: subscription.endpoint });
  await subscription.unsubscribe();
}

export interface PushTestResult {
  subscriptions: number;
  delivered: number;
}

export function sendTestPush(): Promise<PushTestResult> {
  return apiClient.post<PushTestResult>("/api/push/test");
}
