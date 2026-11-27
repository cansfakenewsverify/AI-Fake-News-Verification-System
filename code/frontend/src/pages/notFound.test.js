import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { t } from "../i18n.js";

test("unknown-route 404 has its own copy, not the result 404 or a placeholder", async () => {
  assert.ok(t("route_not_found_title"));
  assert.ok(t("route_not_found_body"));
  assert.notEqual(t("route_not_found_title"), t("result_not_found_title"));
  const src = await readFile(new URL("./NotFound.jsx", import.meta.url), "utf-8");
  assert.ok(!src.includes("screens lane"));
  assert.ok(!src.includes("result_not_found"));
});
