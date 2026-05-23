import { html } from '../lib/html.js';
import { useState, useEffect, useRef } from '../vendor/preact-hooks.module.js';
import { Header } from './Header.js';
import { Tabs } from './Tabs.js';
import { GenerateTab } from './GenerateTab.js';
import { HistoryTab } from './HistoryTab.js';
import { ToastStack } from './Toast.js';
import { createDraftActions, makeInitialDraft, loadDraftFromStorage, mergeJobs, diffJobs } from '../lib/state.js';
import { saveBlobToDisk, mimeToExt } from '../lib/disk_save.js';
import { hostQueued } from '../lib/host.js';
import { toast } from '../lib/toast.js';

export function App({ store, api }) {
  const [snap, setSnap] = useState(store.get());
  const [tab, setTab] = useState('generate');
  const prevStatus = useRef(null);

  useEffect(() => store.subscribe(setSnap), []);

  useEffect(() => {
    let cancelled = false;
    async function tick() {
      try {
        const h = await api.getHealth();
        if (cancelled) return;
        const status =
          h && h.jwt_ttl_sec && h.jwt_ttl_sec > 0 ? 'online' :
          h ? 'no_session' : 'offline';
        const prev = prevStatus.current;
        if (prev !== null && prev !== status) {
          if (prev === 'offline' && status === 'online') {
            toast.success('Sidecar connected');
          } else if (prev === 'online' && status === 'offline') {
            toast.warning('Sidecar offline — retrying');
          }
        }
        prevStatus.current = status;
        store.set({ health: { status, jwt_ttl_sec: h && h.jwt_ttl_sec } });
      } catch (e) {
        if (cancelled) return;
        const prev = prevStatus.current;
        if (prev !== null && prev === 'online') {
          toast.warning('Sidecar offline — retrying');
        }
        prevStatus.current = 'offline';
        store.set({ health: { status: 'offline', jwt_ttl_sec: null } });
      }
    }
    tick();
    const id = setInterval(tick, 5000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  // Bootstrap draft once
  useEffect(() => {
    const cur = store.get();
    if (!cur.draft) {
      const restored = loadDraftFromStorage() || makeInitialDraft();
      store.set({ draft: restored });
    }
  }, []);

  // Fetch videoNodes every time sidecar transitions to online (if still missing).
  // Bootstrap-once was broken when sidecar wasn't up at panel mount — videoNodes
  // stayed null forever, model picker showed only Nano Banana.
  useEffect(() => {
    if (snap.health.status !== 'online') return;
    if (snap.videoNodes && snap.videoNodes.length) return;
    api.listVideoNodes()
      .then(r => store.set({ videoNodes: r.nodes }))
      .catch(() => {});
  }, [snap.health.status, snap.videoNodes]);

  // Job polling — 2s tick when sidecar online
  useEffect(() => {
    let cancelled = false;
    async function tick() {
      if (store.get().health.status !== 'online') return;
      try {
        const r = await api.listJobs({ limit: 50 });
        if (cancelled) return;
        const cur = store.get().jobs || [];
        const remote = r.jobs || [];
        const { completedNow } = diffJobs(cur, remote);
        store.set({ jobs: mergeJobs(cur, remote) });
        // Auto-download + auto-import for completed ones we haven't processed yet
        for (const j of completedNow) {
          if (!j.result_paths || !j.result_paths.length) continue;
          try {
            const blob = await api.downloadJob(j.job_id, 0);
            const ext = mimeToExt(blob.type);
            const localPath = await saveBlobToDisk(blob, `${j.job_id}.${ext}`);
            const url = URL.createObjectURL(blob);
            const enriched = { resultBlobUrl: url, localPath };
            // Try Pr import — keep blob even if Pr offline
            let imported = false;
            try {
              const rImp = await hostQueued('importToBin', localPath);
              enriched.projectItemId = rImp.projectItemId;
              imported = true;
            } catch (_) { /* keep download even if Pr offline */ }
            const s = store.get();
            store.set({
              jobs: s.jobs.map(x => x.job_id === j.job_id ? { ...x, ...enriched } : x),
            });
            if (imported) {
              toast.success('Imported ' + j.job_id);
            } else {
              toast.warning('Imported but Pr offline');
            }
          } catch (_) {
            toast.error(`Download failed for ${j.job_id}`);
          }
        }
      } catch (_) { /* sidecar might be flaky; health toast covers it */ }
    }
    tick();
    const id = setInterval(tick, 2000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  const actions = createDraftActions(store);

  return html`
    <${ToastStack} />
    <${Header} health=${snap.health} api=${api} />
    <${Tabs} active=${tab} onChange=${setTab} tabs=${[
      { id: 'generate', label: 'Generate' },
      { id: 'history', label: 'History' },
    ]} />
    <div class="tab-body">
      ${tab === 'generate'
        ? (snap.draft
            ? html`<${GenerateTab} snap=${snap} actions=${actions} api=${api} store=${store}
                onSubmitted=${() => setTab('history')} />`
            : html`<div class="placeholder">Loading...</div>`)
        : html`<${HistoryTab} snap=${snap} api=${api} videoNodes=${snap.videoNodes}
            onAction=${async (action, job) => {
              if (action === 'delete') {
                if (job.resultBlobUrl) {
                  try { URL.revokeObjectURL(job.resultBlobUrl); } catch (_) {}
                }
                // Optimistic local removal so UI doesn't flash the deleted job
                // until the next 2s poll tick.
                const s = store.get();
                store.set({ jobs: (s.jobs || []).filter(j => j.job_id !== job.job_id) });
                try { await api.deleteJob(job.job_id); }
                catch (e) { toast.error('Delete failed: ' + (e.message || 'unknown')); }
              }
              if (action === 'download') {
                const blob = await api.downloadJob(job.job_id, 0);
                const a = document.createElement('a');
                a.href = URL.createObjectURL(blob);
                a.download = `${job.job_id}.${mimeToExt(blob.type)}`;
                a.click();
                setTimeout(() => { try { URL.revokeObjectURL(a.href); } catch (_) {} }, 1000);
              }
              if (action === 'show') {
                try {
                  // Если панель перезагружалась после completion — projectItemId
                  // пропал. Импортируем «по требованию» (скачиваем артефакт →
                  // saveBlob → importToBin) и потом reveal.
                  let pid = job.projectItemId;
                  if (!pid) {
                    if (!job.localPath) {
                      const blob = await api.downloadJob(job.job_id, 0);
                      const ext = mimeToExt(blob.type);
                      job.localPath = await saveBlobToDisk(blob, `${job.job_id}.${ext}`);
                    }
                    const rImp = await hostQueued('importToBin', job.localPath);
                    pid = rImp.projectItemId;
                    const s = store.get();
                    store.set({
                      jobs: s.jobs.map(x => x.job_id === job.job_id
                        ? { ...x, projectItemId: pid, localPath: job.localPath } : x),
                    });
                  }
                  const r = await hostQueued('revealInBin', pid);
                  toast.success(r.binName ? `Selected in bin "${r.binName}"` : 'Selected in project');
                } catch (e) {
                  const reason = (e.result && e.result.reason) || e.message || 'unknown';
                  toast.error('Show in bin failed: ' + reason);
                }
              }
              if (action === 'retry') {
                // Restore draft form from the job's saved params + init_files,
                // then switch the user back to the Generate tab.
                const jp = job.params || {};
                const restored = {
                  model_id: job.node_id,
                  scenario: jp.scenario || 'start_prompt',
                  prompt: jp.prompt || jp.text_prompt || '',
                  slots: {}, // user re-picks files (we only kept paths server-side)
                  params: { ...jp },
                };
                // Strip top-level fields and internal markers — they're owned by
                // draft.scenario / draft.prompt / draft.slots, not draft.params.
                delete restored.params.scenario;
                delete restored.params._init_files;
                delete restored.params.prompt;
                delete restored.params.text_prompt;
                store.set({ draft: restored });
                setTab('generate');
                toast.success('Form restored — re-pick files and submit');
              }
            }} />`}
    </div>
  `;
}
