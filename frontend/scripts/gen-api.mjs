// Regenerates src/api/schema.d.ts from the backend's OpenAPI schema.
// Usage: npm run gen:api  (backend running on :8000, or CUTLASS_OPENAPI=path/to/openapi.json)
import { writeFile } from 'node:fs/promises'
import openapiTS, { astToString } from 'openapi-typescript'

const source = process.env.CUTLASS_OPENAPI ?? 'http://localhost:8000/openapi.json'
const ast = await openapiTS(source)
const banner = `/* eslint-disable */\n// AUTO-GENERATED from ${source} — regenerate with: npm run gen:api\n\n`
await writeFile(new URL('../src/api/schema.d.ts', import.meta.url), banner + astToString(ast))
console.log(`src/api/schema.d.ts generated from ${source}`)
