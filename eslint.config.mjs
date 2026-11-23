// Lint for the editor (plain ES modules in the browser, no build step): catches undefined names and typos.
export default [{
  files: ["**/*.js"],
  languageOptions: { ecmaVersion: 2022, sourceType: "module", globals: {
    window: "readonly", document: "readonly", performance: "readonly", requestAnimationFrame: "readonly",
    cancelAnimationFrame: "readonly", setTimeout: "readonly", clearTimeout: "readonly", fetch: "readonly",
    URL: "readonly", atob: "readonly", TextDecoder: "readonly", Node: "readonly", console: "readonly",
    navigator: "readonly", Blob: "readonly", FormData: "readonly", location: "readonly", setInterval: "readonly",
    clearInterval: "readonly", Event: "readonly", KeyboardEvent: "readonly", encodeURIComponent: "readonly",
    localStorage: "readonly", alert: "readonly", confirm: "readonly", Image: "readonly", ResizeObserver: "readonly",
    getComputedStyle: "readonly", EventSource: "readonly", WebSocket: "readonly", AbortController: "readonly",
    Headers: "readonly", Response: "readonly", btoa: "readonly", TextEncoder: "readonly", queueMicrotask: "readonly",
    MediaRecorder: "readonly", File: "readonly",
  } },
  rules: { "no-undef": "error", "no-unused-vars": ["error", { args: "none", caughtErrors: "none" }], "no-dupe-keys": "error",
           "no-unreachable": "error", "no-redeclare": "error", "no-shadow-restricted-names": "error" },
}];
