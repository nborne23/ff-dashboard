// GridIron's service worker — Web Push only (add-push-notifications).
//
// Deliberately no `fetch` handler and no caching: the app is served fresh by the iMac
// on every load, and a caching worker is how a deploy ends up never reaching the phone.
// The backend serves this file with `Cache-Control: no-cache` for the same reason.
//
// iOS revokes push permission from a site whose push doesn't show a notification, so
// the push handler ALWAYS shows one, even for a payload it can't read.

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("push", (event) => {
  let message = {};
  try {
    message = event.data ? event.data.json() : {};
  } catch {
    message = { body: event.data ? event.data.text() : "" };
  }
  event.waitUntil(
    self.registration.showNotification(message.title || "GridIron", {
      body: message.body || "",
      tag: message.tag,
      icon: "/icon-192.png",
      data: { url: message.url || "/" },
    }),
  );
});

// Open the app at the notification's URL (`/?highlight=<id>` plays that celebration),
// reusing an open window when there is one.
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = new URL(event.notification.data?.url || "/", self.location.origin).href;
  event.waitUntil(
    (async () => {
      const windows = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
      for (const client of windows) {
        if (new URL(client.url).origin !== self.location.origin) continue;
        await client.focus();
        try {
          await client.navigate(url);
        } catch {
          // An uncontrolled window can't be navigated; focusing it is the next best thing.
        }
        return;
      }
      await self.clients.openWindow(url);
    })(),
  );
});
