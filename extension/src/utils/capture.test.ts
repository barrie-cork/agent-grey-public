/**
 * Self-check for wasCapturedIncognito (provenance correctness). Run with:
 *   cd extension && npx tsx src/utils/capture.test.ts
 *
 * The null case is the one that matters: when incognito create is
 * policy-blocked it resolves to null, and that must read as NOT de-personalised.
 */
import assert from "node:assert/strict";

import { wasCapturedIncognito } from "./capture";

assert.equal(wasCapturedIncognito({ incognito: true }), true);
assert.equal(wasCapturedIncognito({ incognito: false }), false);
assert.equal(wasCapturedIncognito(null), false, "null window (policy-blocked) is not incognito");
assert.equal(wasCapturedIncognito(undefined), false);
assert.equal(wasCapturedIncognito({}), false, "missing flag defaults to not-incognito");

console.log("capture.test.ts: all assertions passed");
