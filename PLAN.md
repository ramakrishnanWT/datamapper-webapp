# Implementation plan

Goal: render Kaoto's `<DataMapper />` React component inside our Flask-served
SPA, with Flask as the backing store.

## Status

| Phase | Item | State |
|---|---|---|
| 1 | Flask backend with sandboxed file API (`/api/files/*`)             | ✅ done |
| 1 | Sample bootstrap endpoints (`/api/samples`, `/api/samples/*/copy`) | ✅ done |
| 1 | Vite + React + TS frontend scaffold                                | ✅ done |
| 1 | `FlaskMetadataApi.ts` implementing the REST contract               | ✅ done (interface verified against Kaoto sources) |
| 1 | Flask serves the built React app                                   | ✅ done |
| 2 | Script: clone + patch + build Kaoto                                | ✅ scripted (`scripts/setup-kaoto.ps1`); needs first run |
| 2 | Confirm Kaoto build succeeds end-to-end on Windows / Node 24       | ⏳ pending hardware run |
| 2 | Mount `<DataMapper />` in `App.tsx` with `metadataApi` prop        | ⏳ pending — depends on phase-2 build output |
| 2 | Verify `IMetadataApi` surface matches Kaoto's current TS contract  | ⚠ at risk — Kaoto refactors this interface; we may need to adjust `FlaskMetadataApi.ts` |
| 2 | Import Kaoto's required PatternFly CSS in `main.tsx`               | ⏳ pending |
| 3 | XSLT runner endpoint that executes generated `.xsl` against JSON   | not started |
| 3 | Live "Test transform" panel in the UI                              | not started |
| 3 | Auth + multi-user workspaces                                       | out of scope for the POC |

## Known risks and unknowns

1. **`IMetadataApi` shape may drift.** Kaoto changes this interface
   frequently (recent commits added `isResourceExist`, will add more).
   Our `FlaskMetadataApi.ts` covers what's documented in the sources
   today; expect to extend it. The TypeScript compiler will tell us
   exactly which methods are missing the first time we import it.

2. **DataMapper has internal dependencies on Kaoto context providers.**
   Looking at `DataMapper.tsx`, it expects to live inside a Kaoto
   `RuntimeContext` / `EntitiesContext` / `SchemaBridgeProvider` etc.
   We may have to mount a stub provider tree, not just `<DataMapper />`
   in isolation. This is the highest-risk item.

3. **PatternFly + SCSS bundle.** Kaoto styles assume PatternFly is
   already imported. We must `import '@patternfly/react-core/dist/styles/base.css'`
   (or the bundle Kaoto ships) in `main.tsx`.

4. **Maven for `@kaoto/camel-catalog`.** The `yarn install` triggers a
   Maven build for the Camel catalog package. The setup script assumes
   `mvn` is available; if not, set
   `KAOTO_SKIP_CATALOG=true` and pre-download a release artifact.

5. **Bundle size.** The built SPA will be on the order of 5–10 MB
   gzipped. Acceptable for a POC; not for production.

## Next concrete steps

1. Run `pwsh scripts/setup-kaoto.ps1` and capture any failure (Yarn,
   Maven, Node version, etc.). Fix as needed.
2. After it finishes, in `frontend/src/App.tsx` try:
   ```tsx
   import { DataMapper } from "@kaoto/kaoto";
   ```
   The TS compiler / dev server will reveal:
   * any missing peer providers (point 2 above),
   * any missing `IMetadataApi` methods (point 1 above),
   * required CSS imports (point 3 above).
3. Iterate on `FlaskMetadataApi.ts` and `App.tsx` until the component
   renders and a sample mapping can be saved to the workspace.
4. Add Phase 3: an `/api/xslt-run` endpoint (Saxon via Java or
   `lxml`-XSLT-1.0) that the UI can call to test the generated mapping.

## Fallback if Phase 2 stalls

The earlier custom Flask DataMapper (commit history of this folder) is
functionally equivalent: source tree, target tree, drag-to-map, XSLT
generation, JSON→XML test. It can be resurrected if upstream Kaoto
proves too tightly coupled to its host application.
