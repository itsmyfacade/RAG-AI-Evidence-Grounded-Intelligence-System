(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (root) root.AegisFingerprint = api;
})(typeof window !== "undefined" ? window : globalThis, function () {
  "use strict";

  const FINGERPRINT_CONTRACT = "aegis-phase3-fingerprint-v3";
  const SCALE = 1000000000;
  const NUMBER_LIMIT = 1000000;

  function assertScalarString(value) {
    for (let index = 0; index < value.length; index += 1) {
      const code = value.charCodeAt(index);
      if (code >= 0xd800 && code <= 0xdbff) {
        const next = value.charCodeAt(index + 1);
        if (!(next >= 0xdc00 && next <= 0xdfff)) throw new TypeError("Canonical fingerprints reject unpaired UTF-16 surrogate characters.");
        index += 1;
      } else if (code >= 0xdc00 && code <= 0xdfff) {
        throw new TypeError("Canonical fingerprints reject unpaired UTF-16 surrogate characters.");
      }
    }
  }

  function canonicalNumber(value) {
    if (typeof value !== "number" || !Number.isFinite(value)) throw new TypeError("Canonical fingerprints support only finite numbers.");
    if (Math.abs(value) > NUMBER_LIMIT) throw new RangeError("Canonical fingerprint number exceeds the supported absolute-value limit.");
    if (Object.is(value, -0) || value === 0) return "0";
    const scaled = Math.floor(Math.abs(value) * SCALE + 0.5);
    const whole = Math.floor(scaled / SCALE);
    const fraction = scaled % SCALE;
    let output = String(whole);
    if (fraction) output += `.${String(fraction).padStart(9, "0").replace(/0+$/, "")}`;
    return value < 0 ? `-${output}` : output;
  }

  function canonicalString(value) {
    assertScalarString(value);
    return JSON.stringify(value);
  }

  function canonicalJSONString(value) {
    if (value === null) return "null";
    if (typeof value === "boolean") return value ? "true" : "false";
    if (typeof value === "string") return canonicalString(value);
    if (typeof value === "number") return canonicalNumber(value);
    if (Array.isArray(value)) return `[${value.map(canonicalJSONString).join(",")}]`;
    if (typeof value === "object") {
      const keys = Object.keys(value).sort();
      return `{${keys.map((key) => `${canonicalString(key)}:${canonicalJSONString(value[key])}`).join(",")}}`;
    }
    throw new TypeError(`Unsupported canonical fingerprint value: ${typeof value}`);
  }

  async function sha256(value) {
    const bytes = new TextEncoder().encode(value);
    if (typeof crypto !== "undefined" && crypto.subtle) {
      const digest = await crypto.subtle.digest("SHA-256", bytes);
      return Array.from(new Uint8Array(digest)).map((item) => item.toString(16).padStart(2, "0")).join("");
    }
    if (typeof require === "function") return require("crypto").createHash("sha256").update(Buffer.from(bytes)).digest("hex");
    throw new Error("No SHA-256 implementation is available.");
  }

  function fingerprint(value) { return sha256(canonicalJSONString(value)); }
  function legacyFingerprint(sourceRunId, cases) { return sha256(JSON.stringify({ source_run_id: sourceRunId || "unknown", cases })); }

  return { FINGERPRINT_CONTRACT, canonicalJSONString, fingerprint, legacyFingerprint };
});
