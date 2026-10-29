/* Shared mutable app context.
 *
 * app.js owns the session and metadata; the secondary view modules need to read
 * them without importing app.js (which would be a cycle). A single object keeps
 * that handoff explicit and cheap.
 */
export const ctx = {
  ME: null,
  META: null,
  setSession(me, meta) { this.ME = me; this.META = meta; },
};
