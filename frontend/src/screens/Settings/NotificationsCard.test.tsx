import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { NotificationsCard } from "./NotificationsCard";

// A 65-byte uncompressed point, base64url — the shape the server hands out.
const KEY_BYTES = new Uint8Array(65).map((_, i) => (i === 0 ? 4 : i));
const PUBLIC_KEY = btoa(String.fromCharCode(...KEY_BYTES))
  .replace(/\+/g, "-")
  .replace(/\//g, "_")
  .replace(/=+$/, "");

interface FakeSubscription {
  endpoint: string;
  options: { applicationServerKey: ArrayBuffer | null };
  toJSON: () => unknown;
  unsubscribe: ReturnType<typeof vi.fn>;
}

function fakeSubscription(key: Uint8Array = KEY_BYTES): FakeSubscription {
  return {
    endpoint: "https://web.push.apple.com/QGabc",
    options: { applicationServerKey: key.slice().buffer },
    toJSON: () => ({
      endpoint: "https://web.push.apple.com/QGabc",
      keys: { p256dh: "p", auth: "a" },
    }),
    unsubscribe: vi.fn(async () => true),
  };
}

function install({
  permission = "default" as NotificationPermission,
  answer = "granted" as NotificationPermission,
  existing = null as FakeSubscription | null,
} = {}) {
  let current = existing;
  const pushManager = {
    getSubscription: vi.fn(async () => current),
    subscribe: vi.fn(async () => {
      current = fakeSubscription();
      return current;
    }),
  };
  const requestPermission = vi.fn(async () => answer);
  vi.stubGlobal("Notification", { permission, requestPermission });
  vi.stubGlobal("PushManager", function PushManager() {});
  Object.defineProperty(navigator, "serviceWorker", {
    configurable: true,
    value: { ready: Promise.resolve({ pushManager }), register: vi.fn() },
  });

  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const body =
      url === "/api/push/vapid-public-key"
        ? { public_key: PUBLIC_KEY }
        : url === "/api/push/test"
          ? { subscriptions: 1, delivered: 1 }
          : undefined;
    void init;
    return {
      ok: true,
      status: body ? 200 : 204,
      text: async () => (body ? JSON.stringify(body) : ""),
    };
  });
  vi.stubGlobal("fetch", fetchMock);
  return { pushManager, requestPermission, fetchMock };
}

function calls(fetchMock: ReturnType<typeof install>["fetchMock"], method: string, url: string) {
  return fetchMock.mock.calls.filter(
    ([input, init]) => String(input) === url && (init?.method ?? "GET") === method,
  );
}

describe("NotificationsCard", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    Reflect.deleteProperty(navigator, "serviceWorker");
  });

  it("asks for permission first, then subscribes and saves", async () => {
    const { pushManager, requestPermission, fetchMock } = install();
    render(<NotificationsCard />);
    await waitFor(() =>
      expect(calls(fetchMock, "GET", "/api/push/vapid-public-key")).toHaveLength(1),
    );

    const toggle = screen.getByRole("switch", { name: "Touchdowns & big plays" });
    await act(async () => {
      fireEvent.click(toggle);
    });

    expect(requestPermission).toHaveBeenCalledOnce();
    expect(pushManager.subscribe).toHaveBeenCalledWith(
      expect.objectContaining({ userVisibleOnly: true }),
    );
    await waitFor(() => expect(toggle.getAttribute("aria-checked")).toBe("true"));
    expect(calls(fetchMock, "POST", "/api/push/subscriptions")).toHaveLength(1);
    expect(screen.getByText("Send a test notification")).toBeTruthy();
  });

  it("re-posts an existing subscription on open", async () => {
    const { fetchMock } = install({ permission: "granted", existing: fakeSubscription() });
    render(<NotificationsCard />);

    await waitFor(() =>
      expect(
        screen.getByRole("switch", { name: "Touchdowns & big plays" }).getAttribute("aria-checked"),
      ).toBe("true"),
    );
    expect(calls(fetchMock, "POST", "/api/push/subscriptions")).toHaveLength(1);
  });

  it("replaces a subscription made with an old server key", async () => {
    const stale = fakeSubscription(new Uint8Array(65).fill(9));
    const { pushManager } = install({ permission: "granted", existing: stale });
    render(<NotificationsCard />);

    await waitFor(() => expect(pushManager.subscribe).toHaveBeenCalledOnce());
    expect(stale.unsubscribe).toHaveBeenCalledOnce();
  });

  it("explains a denied prompt and locks the switch", async () => {
    install({ answer: "denied" });
    render(<NotificationsCard />);
    const toggle = screen.getByRole("switch", { name: "Touchdowns & big plays" });

    await act(async () => {
      fireEvent.click(toggle);
    });

    await waitFor(() => expect(toggle.getAttribute("aria-disabled")).toBe("true"));
    expect(screen.getByText(/Settings → Notifications → GridIron/)).toBeTruthy();
  });

  it("turning it off deletes the server copy and unsubscribes", async () => {
    const existing = fakeSubscription();
    const { fetchMock } = install({ permission: "granted", existing });
    render(<NotificationsCard />);
    const toggle = screen.getByRole("switch", { name: "Touchdowns & big plays" });
    await waitFor(() => expect(toggle.getAttribute("aria-checked")).toBe("true"));

    await act(async () => {
      fireEvent.click(toggle);
    });

    await waitFor(() => expect(toggle.getAttribute("aria-checked")).toBe("false"));
    expect(calls(fetchMock, "DELETE", "/api/push/subscriptions")).toHaveLength(1);
    expect(existing.unsubscribe).toHaveBeenCalledOnce();
  });

  it("sends a test and reports it", async () => {
    install({ permission: "granted", existing: fakeSubscription() });
    render(<NotificationsCard />);
    const send = await screen.findByRole("button", { name: "Send" });

    await act(async () => {
      fireEvent.click(send);
    });

    expect(await screen.findByText("Sent to 1 device.")).toBeTruthy();
  });

  it("tells an iPhone in Safari to add it to the Home Screen", () => {
    vi.spyOn(navigator, "userAgent", "get").mockReturnValue(
      "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15",
    );
    render(<NotificationsCard />);

    expect(screen.getByText(/Add GridIron to your Home Screen/)).toBeTruthy();
    vi.restoreAllMocks();
  });
});
