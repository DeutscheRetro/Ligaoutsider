import test from "node:test";
import assert from "node:assert/strict";
import { holeAlle } from "../functions/api.js";

test("holeAlle holt alle Seiten, auch über das 1000er-Limit hinaus", async () => {
  const aufgerufen = [];
  globalThis.fetch = async (url) => {
    const off = Number(new URL(url).searchParams.get("offset"));
    aufgerufen.push(off);
    const anzahl = off < 2000 ? 1000 : 5;
    return new Response(JSON.stringify(Array.from({ length: anzahl }, (_, i) => ({ i: off + i }))), { status: 200 });
  };
  const alle = await holeAlle("kommentare?select=id&order=id");
  assert.equal(alle.length, 2005);
  assert.deepEqual(aufgerufen, [0, 1000, 2000]);
});

test("holeAlle hört bei einer leeren Seite auf", async () => {
  globalThis.fetch = async () => new Response("[]", { status: 200 });
  assert.deepEqual(await holeAlle("x?select=id"), []);
});
