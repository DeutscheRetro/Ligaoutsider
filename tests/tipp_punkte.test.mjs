// node --test tests/tipp_punkte.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { tippPunkte } from "../functions/api.js";

test("Tippspiel: 4 exakt, 3 Tordifferenz, 2 Tendenz, 0 falsch", () => {
  assert.equal(tippPunkte([2, 1], [2, 1]), 4);
  assert.equal(tippPunkte([3, 2], [2, 1]), 3);
  assert.equal(tippPunkte([1, 1], [2, 2]), 3);
  assert.equal(tippPunkte([3, 0], [1, 0]), 2);
  assert.equal(tippPunkte([0, 1], [1, 0]), 0);
});
