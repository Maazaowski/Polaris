import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import type { FieldCatalogue } from "@/types";

/** The read-only vocabulary a profile picks its fields from. Fixed per build,
 * so it is cached for the session. */
export function useFieldCatalogue() {
  return useQuery({
    queryKey: ["field-catalogue"],
    queryFn: () => api.get<FieldCatalogue>("/profiles/field-catalogue"),
    staleTime: Infinity,
  });
}
