# Stream A requests for contracts (from stream/a-web-shell)

Nothing here blocks M1; the web shell works around each one.

1. **`Point` generates as `[unknown, unknown]`** in `contracts/ts/src/generated/overlay.ts` (the `prefixItems`
   tuple is not understood by json-schema-to-typescript). The web casts with `toVec()`. Ask: post-process the
   generated type to `[number, number]`, or switch the schema to `items: {type: number}` with min/max 2.
2. **A light entry without ajv.** `strokeStartMs` lives in `index.ts`, which also imports ajv and all schemas,
   so importing it adds about 120 kB to the web bundle. Ask: move pure helpers (`strokeStartMs`, types) to
   `@chalktalk/contracts/timing` (or similar) and keep `validate` in the main entry.
3. **Hub message envelope.** The web accepts `{"type": "overlay", "overlay": <Overlay>}` on `/ws/match/:id`
   and ignores other types (the hub already sends `{"type": "hello", "viewers": n}`). Ask: add a `hub_message`
   schema (`hello` | `overlay` | later `clock`) so stream D and the web share one shape.
