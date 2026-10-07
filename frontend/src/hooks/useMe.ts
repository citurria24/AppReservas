import { useQuery } from "@tanstack/react-query";
import { api, setCsrfToken } from "../api/client";
import type { Me } from "../types/api";
export function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: async () => {
      const me = await api<Me>("/me/");
      setCsrfToken(me.csrf_token);
      return me;
    },
    staleTime: 60_000,
    retry: false,
  });
}
