import type { DesignEditing } from "@canva/design";

// A session that records what the app asks Canva to do.
export type Calls = {
  created: unknown[];
  inserted: { after: unknown; state: unknown }[];
  grouped: unknown[][];
  syncs: number;
};

export function fakeSession(
  o: Partial<{
    existing: { type: string; id: string }[];
    locked: boolean;
    pageType: string;
    groupFails: boolean;
    syncFails: boolean;
    insertFails: boolean;
    dimensions: { width: number; height: number } | undefined;
  }> = {},
) {
  const calls: Calls = { created: [], inserted: [], grouped: [], syncs: 0 };
  const existing = o.existing ?? [];
  let n = 0;
  const session = {
    page: {
      type: o.pageType ?? "absolute",
      locked: o.locked ?? false,
      dimensions:
        "dimensions" in o ? o.dimensions : { width: 1080, height: 1080 },
      elements: {
        toArray: () => existing,
        insertAfter: (after: unknown, state: { text: unknown }) => {
          calls.inserted.push({ after, state });
          return o.insertFails ? undefined : { type: "text", id: `new${n++}` };
        },
      },
    },
    helpers: {
      elementStateBuilder: {
        createTextElement: (opts: unknown) => {
          calls.created.push(opts);
          return { text: opts };
        },
      },
      group: async ({ elements }: { elements: unknown[] }) => {
        calls.grouped.push(elements);
        if (o.groupFails) {
          throw new Error("[internal_error]: cannot group");
        }
        return { type: "group" };
      },
    },
    sync: async () => {
      if (o.syncFails) {
        throw new Error("[internal_error]: Something went wrong on our end");
      }
      calls.syncs++;
    },
  };
  return {
    session: session as unknown as DesignEditing.CurrentPageSession,
    calls,
  };
}
