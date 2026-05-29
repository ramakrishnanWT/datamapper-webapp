/**
 * Thin wrapper around the Flask file-system API that Kaoto's
 * DataMapper component consumes via its `IMetadataApi` interface.
 *
 * Once the Kaoto build with DataMapper export is in place, hand an
 * instance of this class to <DataMapper /> as its `metadataApi` prop.
 *
 * Reference (Kaoto sources):
 *   packages/ui/src/components/DataMapper/DataMapper.tsx
 *   packages/ui/src/multiplying-architecture/IMetadataApi.ts
 */
export class FlaskMetadataApi {
  // ---- file IO -----------------------------------------------------------
  async getResourceContent(path: string): Promise<string | undefined> {
    const r = await fetch(`/api/files/${encodeURI(path)}`);
    if (r.status === 404) return undefined;
    if (!r.ok) throw new Error(`GET ${path} -> ${r.status}`);
    return await r.text();
  }

  async saveResourceContent(path: string, content: string): Promise<void> {
    const r = await fetch(`/api/files/${encodeURI(path)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/octet-stream" },
      body: content,
    });
    if (!r.ok) throw new Error(`PUT ${path} -> ${r.status}`);
  }

  async deleteResource(path: string): Promise<boolean> {
    const r = await fetch(`/api/files/${encodeURI(path)}`, { method: "DELETE" });
    return r.ok;
  }

  async isResourceExist(path: string): Promise<boolean> {
    const r = await fetch(`/api/files/${encodeURI(path)}`, { method: "HEAD" });
    return r.ok;
  }

  async listResources(): Promise<string[]> {
    const r = await fetch("/api/files");
    if (!r.ok) throw new Error(`GET /api/files -> ${r.status}`);
    const data = (await r.json()) as { files: { path: string }[] };
    return data.files.map((f) => f.path);
  }

  // ---- metadata (no-op stubs the DataMapper tolerates) -------------------
  async getMetadata(_key: string): Promise<unknown> {
    return undefined;
  }
  async setMetadata(_key: string, _value: unknown): Promise<void> {
    /* no-op */
  }
}

export const metadataApi = new FlaskMetadataApi();
