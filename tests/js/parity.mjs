// Run by tests/test_js_parity.py: the editor's interpolation (state.js) on cases computed by Python.
// Usage: node parity.mjs <state.js url> <cases.json>  -> prints a JSON list of the editor's values
import { readFileSync } from 'node:fs';

const [stateUrl, casesFile] = process.argv.slice(2);
const { S, valueAt, easeValue } = await import(stateUrl);
const data = JSON.parse(readFileSync(casesFile, 'utf8'));
S.types = data.types;
S.defaultPalette = data.palette;
S.project = { palette: data.palette, objects: [] };
const out = data.cases.map((c) => (c.ease !== undefined
  ? easeValue(c.ease, c.u, c.bez)
  : valueAt(c.obj, c.prop, c.t)));
process.stdout.write(JSON.stringify(out));
