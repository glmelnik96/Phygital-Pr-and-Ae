# Открытые вопросы для следующего аудита (после V1.1)

Этот документ — backlog того, что НЕ вошло в V1.1, но требует архитектурного
ответа перед V1.2. Каждый пункт — формулировка проблемы + ответ/предлагаемый
план фикса.

---

## 1. Re-import после перезагрузки панели (вопрос пользователя, 2026-05-23)

### Симптом

Сейчас при перезапуске Premiere Pro (или перезагрузке CEP-панели) панель
импортирует файлы в bin `PhygitalStudio` повторно, даже если они уже есть в
проекте. Получаются дубликаты ProjectItem'ов с одинаковым `getMediaPath()`.

### Можно ли добавить проверку? — Да, технически и архитектурно

**Кратко: да, это безопасно делается двумя слоями защиты — JS-side cache hit и
host-side path-lookup.** Базовая инфраструктура уже на месте, нужен ~15 LOC.

### Почему сейчас дублируется

В `cep-premiere/client/components/App.js` (poll-tick, строки 75–131):

```js
const cur  = store.get().jobs || [];       // ← после reload — пустой массив
const remote = r.jobs || [];
const { completedNow } = diffJobs(cur, remote);
store.set({ jobs: mergeJobs(cur, remote) });  // ← merge с persisted meta — ПОСЛЕ diff
for (const j of completedNow) { ... importToBin(localPath) ... }
```

На первом poll-tick'е после reload:

1. `cur` пустой → `diffJobs` считает «новыми completed» ВСЕ remote-completed.
2. `mergeJobs` дальше восстанавливает `localPath` + `projectItemId` из
   `JOB_META_KEY` localStorage — но это уже после того, как `completedNow`
   решён.
3. Каждый completed job → `importToBin(localPath)` → Pr радостно создаёт
   второй ProjectItem на тот же путь.

### План фикса (для V1.2)

**Layer 1 (JS, дешёвый — фильтрация перед import):**

В `App.js` поменять порядок: сначала `mergeJobs`, потом `diffJobs` на merged
снэпшоте; либо в auto-import loop'е проверять `patchJobMetaCache`:

```js
const merged = mergeJobs(cur, remote);
store.set({ jobs: merged });
const { completedNow } = diffJobs(cur, merged);   // diff на merged
const meta = loadJobMetaCache();
for (const j of completedNow) {
  if (meta[j.job_id]?.projectItemId) continue;     // уже импортирован
  if (meta[j.job_id]?.localPath) {
    // путь сохранён, но Pr-проект мог быть пересоздан → layer 2
  }
  ...
}
```

**Layer 2 (host, защита от stale projectItemId):**

В `host.jsx` уже есть `_findImportedByPath(targetPath)` (строки 793–811),
которое walk'ит дерево и ищет ProjectItem по `getMediaPath()`. Достаточно
экспонировать его как отдельную функцию `findByPath(path)` и вызывать перед
`importToBin`:

```js
// host.jsx — новая API-функция
function findByPath(path) {
  var hit = _findImportedByPath(path);
  if (!hit) return _err('not_found');
  return _ok({
    projectItemId: String(hit.item.nodeId),
    binName: String(hit.parent.name || 'root'),
  });
}
```

```js
// App.js — обёртка над importToBin
async function importIfMissing(localPath) {
  try {
    const f = await hostQueued('findByPath', localPath);
    return { projectItemId: f.projectItemId, reused: true };
  } catch (_) { /* not_found — нормально */ }
  const r = await hostQueued('importToBin', localPath);
  return { projectItemId: r.projectItemId, reused: false };
}
```

Это закрывает три кейса разом:
1. **Reload панели, проект Pr тот же** — layer 1 (cache hit на projectItemId).
2. **Reload панели, проект Pr пересоздан/переоткрыт** — layer 2 (path lookup).
3. **Пользователь руками удалил ProjectItem из бина** — layer 2 не найдёт →
   честный re-import (это уже не дубль).

### Риски и edge-cases

- **getMediaPath нормализация.** `_findImportedByPath` уже делает
  `toLowerCase().replace(/\//g, '\\')`. На macOS это нужно адаптировать (там
  case-sensitive FS на APFS-noncasefolding и forward-slash separator). Сейчас
  весь импорт — на Windows, для V1.2 переноса нужен платформо-специфичный
  компаратор.
- **Стоимость walk'а дерева.** На больших проектах (1000+ ProjectItem) каждый
  `findByPath` — это full DFS. Cache miss на N completed-джобов = N*O(tree).
  Mitigation: добавить `_pathCache: {mediaPath → ProjectItem}`, инвалидация на
  `importToBin` (так же как `_piCache`). +20 LOC, идёт вместе с фиксом.
- **HEIC/HEIF и другие форматы, которые Pr транскодирует.** Если Pr внутри
  переименовал файл, `getMediaPath` может вернуть staged-путь, отличающийся
  от того, что мы сохранили в `localPath`. Маловероятно для PNG/MP4/JPEG из
  Phygital, но стоит проверить на live recon.

### Acceptance criteria

- [ ] Reload панели с 5 completed-джобами → 0 повторных импортов (в bin
      остаётся ровно 5 ProjectItem).
- [ ] Юзер удалил один ProjectItem руками → следующий reload → 1 re-import
      (только удалённого).
- [ ] Юзер переоткрыл другой Pr-проект → reload панели → 5 импортов в новый
      bin.
- [ ] Тест в `cep-premiere/tests/test_app_jobs.test.js` на `findByPath`-fast-path.

---

## 2. L1–L3, L9, L12, M13, M16 audit codes — содержание не определено

В sub-project S6 backlog'е были перечислены коды без расшифровки. Перед V1.2
нужно определить их формулировки или подтвердить, что они уже закрыты
смежными фиксами.

---

## 3. Symlink installer — verification

Установщик `scripts/install_mac.sh` symlink-based, поэтому новые модули V1.1
(`app/services/idempotency.py`, `QueueWidget.js`) подхватываются автоматически
без переустановки. `pip install -e ".[dev]"` идемпотентен. Новые зависимости
не добавлены — `idempotency.py` использует только stdlib.

Однако CHANGELOG-bump в `sidecar/pyproject.toml` (`version = "0.1.0"`) ещё не
сделан — для V1.2 стоит синхронизировать с тегом V1.x.

---

## 4. AE-панель (sub-project C) — не начата

Roadmap-документ помечает её как "не начато". V1.1 затрагивает только Pr.
Перенос фич V1.1 на AE — отдельный sub-project, не блокер для V1.1 release.
