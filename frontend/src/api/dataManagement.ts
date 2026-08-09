// Mutation hooks for Settings' "Data Management" card (task 7.6): clear cache and
// export-as-download. "Refresh all data" reuses api/admin.ts's useRefresh and
// "Disconnect all platforms" reuses api/connections.ts's useDisconnect — both defined
// elsewhere already, so they aren't duplicated here.

import { useMutation } from "@tanstack/react-query";

import { apiClient } from "./client";

export function useClearCache() {
  return useMutation({
    mutationFn: () => apiClient.delete<void>("/api/cache"),
  });
}

/** Fetches the JSON export and triggers a browser download of it as a file. */
export function useExportData() {
  return useMutation({
    mutationFn: async () => {
      const data = await apiClient.get<unknown>("/api/export.json");
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      try {
        const link = document.createElement("a");
        link.href = url;
        link.download = "gridiron-export.json";
        document.body.appendChild(link);
        link.click();
        link.remove();
      } finally {
        URL.revokeObjectURL(url);
      }
    },
  });
}
