import { useEffect, useState } from "react";
import { metadataApi } from "./FlaskMetadataApi";

/**
 * Phase 1 shell.
 *
 * Right now this page only proves the Flask <-> React file-API plumbing
 * works. Once `scripts/setup-kaoto.ps1` has built a patched
 * `@kaoto/kaoto` that exports the DataMapper component, swap the body
 * of this component for something like:
 *
 *   import { DataMapper } from "@kaoto/kaoto";
 *   ...
 *   return <DataMapper metadataApi={metadataApi}
 *                      initialXsltPath="datamapper.xsl" />;
 */
export function App() {
  const [files, setFiles] = useState<string[]>([]);
  const [samples, setSamples] = useState<{ name: string; size: number }[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = async () => {
    setError(null);
    try {
      setFiles(await metadataApi.listResources());
      const r = await fetch("/api/samples");
      setSamples((await r.json()).samples);
    } catch (e) {
      setError(String(e));
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const copySample = async (name: string) => {
    setBusy(true);
    try {
      await fetch(`/api/samples/${encodeURIComponent(name)}/copy`, { method: "POST" });
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  const deleteFile = async (p: string) => {
    if (!confirm(`Delete ${p}?`)) return;
    await metadataApi.deleteResource(p);
    await refresh();
  };

  return (
    <div style={{ font: "14px/1.5 system-ui, sans-serif", padding: 24, maxWidth: 960 }}>
      <h1>Kaoto DataMapper — Flask host (Phase 1)</h1>

      <div
        style={{
          background: "#fff8e1",
          border: "1px solid #f0c36d",
          padding: "10px 14px",
          borderRadius: 6,
          marginBottom: 20,
        }}
      >
        <strong>Status:</strong> Backend file-system API is wired. The actual{" "}
        <code>&lt;DataMapper /&gt;</code> component is not yet mounted &mdash; that
        requires building a patched <code>@kaoto/kaoto</code>. See{" "}
        <code>PLAN.md</code> for the next steps.
      </div>

      {error && (
        <div style={{ color: "#b00020", marginBottom: 12 }}>Error: {error}</div>
      )}

      <h2>Workspace files</h2>
      {files.length === 0 ? (
        <p style={{ color: "#666" }}>(empty)</p>
      ) : (
        <ul>
          {files.map((f) => (
            <li key={f}>
              <a href={`/api/files/${encodeURI(f)}`} target="_blank" rel="noreferrer">
                {f}
              </a>{" "}
              <button onClick={() => deleteFile(f)} style={{ marginLeft: 8 }}>
                delete
              </button>
            </li>
          ))}
        </ul>
      )}

      <h2>Bundled samples</h2>
      <ul>
        {samples.map((s) => (
          <li key={s.name}>
            {s.name} <span style={{ color: "#888" }}>({s.size} bytes)</span>{" "}
            <button disabled={busy} onClick={() => copySample(s.name)}>
              copy into workspace
            </button>
          </li>
        ))}
      </ul>

      <p style={{ color: "#888", marginTop: 30 }}>
        Backend health: <a href="/api/health">/api/health</a>
      </p>
    </div>
  );
}
