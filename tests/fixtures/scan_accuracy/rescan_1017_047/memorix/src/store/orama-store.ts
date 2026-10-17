}

/**
 * Search observations using Orama full-text search.
 * Returns L1 IndexEntry array (compact, ~50-100 tokens per result).
 *
 * Progressive Disclosure Layer 1 — adopted from claude-mem.
 */
export async function searchObservations(options: SearchOptions): Promise<IndexEntry[]> {
  const perf = !!process.env.MEMORIX_PERF;
  const t0 = perf ? performance.now() : 0;
  const mark = (label: string) => { if (perf) { const now = performance.now(); process.stderr.write(`  [search-perf] ${label}: ${(now - t0).toFixed(0)}ms\n`); } };
  const modeKey = options.projectId ?? SEARCH_MODE_DEFAULT_KEY;
