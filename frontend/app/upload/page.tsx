"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ImportItem, RecategorizeResponse, UploadResponse } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { formatDate, formatEur, toIntlLocale } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Tab type
// ---------------------------------------------------------------------------

type Tab = "import" | "history";

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function UploadPage() {
  const { t, locale } = useT();
  const intlLocale = toIntlLocale(locale);
  const [tab, setTab] = useState<Tab>("import");

  // ---- Upload state ----
  const [files, setFiles] = useState<File[]>([]);
  const [bank, setBank] = useState("santander");
  const [useAi, setUseAi] = useState(false);
  const [loading, setLoading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<{ current: number; total: number } | null>(null);
  const [results, setResults] = useState<UploadResponse[]>([]);
  const [errors, setErrors] = useState<{ filename: string; message: string }[]>([]);
  const [sharedFile, setSharedFile] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ---- Recategorize state ----
  const [recatLoading, setRecatLoading] = useState(false);
  const [recatUseAi, setRecatUseAi] = useState(false);
  const [recatResult, setRecatResult] = useState<RecategorizeResponse | null>(null);
  const [recatError, setRecatError] = useState<string | null>(null);

  // ---- History state ----
  const [imports, setImports] = useState<ImportItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [deleteMsg, setDeleteMsg] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deletingAll, setDeletingAll] = useState(false);

  // ---- Shared-file recovery ----
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("shared") !== "1") return;
    async function recoverSharedFile() {
      try {
        if (!("caches" in window)) return;
        const cache = await caches.open("share-target");
        const req = await cache.match("/shared-file");
        if (!req) return;
        const blob = await req.blob();
        const name = req.headers.get("X-Filename") ?? "statement.xlsx";
        const recovered = new File([blob], name, { type: blob.type });
        setFiles([recovered]);
        setSharedFile(true);
        await cache.delete("/shared-file");
        window.history.replaceState({}, "", "/upload");
      } catch { /* non-critical */ }
    }
    recoverSharedFile();
  }, []);

  // ---- Load imports history ----
  const loadImports = useCallback(async () => {
    setHistoryLoading(true);
    try {
      const res = await api.listImports();
      setImports(res.imports);
    } catch { /* ignore */ }
    finally { setHistoryLoading(false); }
  }, []);

  useEffect(() => {
    if (tab === "history") loadImports();
  }, [tab, loadImports]);

  // ---- Handlers ----
  function addFiles(incoming: FileList | null) {
    if (!incoming) return;
    const newFiles = Array.from(incoming);
    setFiles((prev) => {
      // deduplicate by name
      const names = new Set(prev.map((f) => f.name));
      return [...prev, ...newFiles.filter((f) => !names.has(f.name))];
    });
    setSharedFile(false);
  }

  function removeFile(index: number) {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (files.length === 0) return;
    setLoading(true);
    setErrors([]);
    setResults([]);
    setUploadProgress({ current: 0, total: files.length });
    const newResults: UploadResponse[] = [];
    const newErrors: { filename: string; message: string }[] = [];
    for (let i = 0; i < files.length; i++) {
      setUploadProgress({ current: i + 1, total: files.length });
      try {
        const res = await api.upload(files[i], bank, useAi);
        newResults.push(res);
      } catch (err: unknown) {
        newErrors.push({
          filename: files[i].name,
          message: err instanceof Error ? err.message : "Upload failed",
        });
      }
    }
    setResults(newResults);
    setErrors(newErrors);
    setFiles([]);
    setSharedFile(false);
    setUploadProgress(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
    setLoading(false);
  }

  async function handleRecategorize() {
    setRecatLoading(true); setRecatError(null); setRecatResult(null);
    try {
      const res = await api.recategorize(recatUseAi);
      setRecatResult(res);
    } catch (err: unknown) {
      setRecatError(err instanceof Error ? err.message : "Recategorize failed");
    } finally { setRecatLoading(false); }
  }

  async function handleDeleteImport(item: ImportItem) {
    if (!confirm(t("upload.confirmDeleteImport", { count: item.tx_count }))) return;
    setDeletingId(item.id); setDeleteMsg(null); setDeleteError(null);
    try {
      const res = await api.deleteImport(item.id);
      setDeleteMsg(t("upload.deleteImportSuccess", { count: res.deleted_transactions }));
      await loadImports();
    } catch (err: unknown) {
      setDeleteError(err instanceof Error ? err.message : "Delete failed");
    } finally { setDeletingId(null); }
  }

  async function handleDeleteAll() {
    if (!confirm(t("upload.deleteAllBody"))) return;
    setDeletingAll(true); setDeleteMsg(null); setDeleteError(null);
    try {
      const res = await api.clearAllData();
      setDeleteMsg(t("upload.deleteAllSuccess", { tx: res.deleted_transactions, imp: res.deleted_imports }));
      await loadImports();
    } catch (err: unknown) {
      setDeleteError(err instanceof Error ? err.message : "Delete failed");
    } finally { setDeletingAll(false); }
  }

  const inputCls = "w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2.5 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500";

  return (
    <div className="max-w-3xl space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{t("upload.title")}</h1>
        <p className="text-gray-500 dark:text-gray-400 text-sm mt-1">{t("upload.subtitle")}</p>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-gray-200 dark:border-gray-700">
        {(["import", "history"] as Tab[]).map((key) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`px-5 py-2.5 text-sm font-medium border-b-2 transition-colors ${
              tab === key
                ? "border-indigo-600 text-indigo-600 dark:text-indigo-400 dark:border-indigo-400"
                : "border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
            }`}
          >
            {t(`upload.tab${key.charAt(0).toUpperCase() + key.slice(1)}`)}
          </button>
        ))}
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* TAB: Import                                                          */}
      {/* ------------------------------------------------------------------ */}
      {tab === "import" && (
        <div className="space-y-6 max-w-xl">
          <form onSubmit={handleSubmit} className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-6 shadow-sm space-y-5">
            {sharedFile && files.length > 0 && (
              <div className="flex items-center gap-3 bg-indigo-50 dark:bg-indigo-900/30 border border-indigo-200 dark:border-indigo-700 rounded-lg px-4 py-3 text-sm text-indigo-800 dark:text-indigo-300">
                <svg className="w-5 h-5 shrink-0 text-indigo-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span>{t("upload.sharedBanner", { filename: files[0].name })}</span>
              </div>
            )}

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                {sharedFile ? t("upload.fileLabelShared") : t("upload.fileLabel")}
              </label>

              {/* File chips */}
              {files.length > 0 && (
                <div className="flex flex-wrap gap-2 mb-2">
                  {files.map((f, i) => (
                    <span
                      key={i}
                      className="inline-flex items-center gap-1.5 bg-indigo-50 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-300 text-xs font-medium px-2.5 py-1 rounded-full border border-indigo-200 dark:border-indigo-700"
                    >
                      <svg className="w-3 h-3 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                      </svg>
                      <span className="max-w-[160px] truncate" title={f.name}>{f.name}</span>
                      <button
                        type="button"
                        onClick={() => removeFile(i)}
                        className="ml-0.5 hover:text-red-500 dark:hover:text-red-400 transition-colors"
                        aria-label={`Eliminar ${f.name}`}
                      >
                        ✕
                      </button>
                    </span>
                  ))}
                </div>
              )}

              {/* File input — always visible to add more */}
              <label className="flex items-center gap-2 cursor-pointer">
                <span className="inline-flex items-center gap-1.5 py-2 px-4 rounded-lg border border-dashed border-gray-300 dark:border-gray-600 text-sm text-gray-600 dark:text-gray-400 hover:border-indigo-400 hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors bg-white dark:bg-gray-800">
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                  </svg>
                  {files.length === 0 ? t("upload.fileLabel") : t("upload.fileAddMore")}
                </span>
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  accept=".xlsx,.csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv"
                  onChange={(e) => { addFiles(e.target.files); if (fileInputRef.current) fileInputRef.current.value = ""; }}
                  className="sr-only"
                />
              </label>

              {files.length > 0 && (
                <p className="text-xs text-gray-400 dark:text-gray-500 mt-1.5">
                  {files.length === 1
                    ? t("upload.fileSelected").replace("{n}", "1")
                    : t("upload.filesSelected").replace("{n}", String(files.length))}
                </p>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t("upload.bankLabel")}</label>
              <select value={bank} onChange={(e) => setBank(e.target.value)} className={inputCls}>
                <option value="santander">Santander España</option>
              </select>
            </div>

            <div className="flex items-start gap-3">
              <input type="checkbox" id="use-ai" checked={useAi} onChange={(e) => setUseAi(e.target.checked)} className="rounded mt-0.5" />
              <label htmlFor="use-ai" className="text-sm text-gray-700 dark:text-gray-300 leading-snug">
                {t("upload.aiLabel")}
              </label>
            </div>

            <button type="submit" disabled={loading || files.length === 0}
              className="w-full py-3 px-4 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors">
              {loading && uploadProgress
                ? t("upload.submitting")
                    .replace("{current}", String(uploadProgress.current))
                    .replace("{total}", String(uploadProgress.total))
                : files.length > 1
                  ? t("upload.submitMulti").replace("{n}", String(files.length))
                  : t("upload.submit")}
            </button>

            {/* Progress bar while uploading */}
            {loading && uploadProgress && uploadProgress.total > 1 && (
              <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-1.5 overflow-hidden">
                <div
                  className="bg-indigo-500 h-1.5 rounded-full transition-all duration-300"
                  style={{ width: `${Math.round((uploadProgress.current / uploadProgress.total) * 100)}%` }}
                />
              </div>
            )}
          </form>

          {/* Per-file errors */}
          {errors.length > 0 && (
            <div className="bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 rounded-xl p-4 text-sm space-y-1">
              <strong>{t("upload.errorPrefix")}</strong>
              <ul className="list-disc list-inside mt-1">
                {errors.map((e, i) => (
                  <li key={i}><span className="font-medium">{e.filename}:</span> {e.message}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Per-file success results */}
          {results.length > 0 && (
            <div className="space-y-3">
              {results.map((result, i) => (
                <div key={i} className="bg-green-50 dark:bg-green-950 border border-green-200 dark:border-green-800 text-green-800 dark:text-green-300 rounded-xl p-5 text-sm space-y-1.5">
                  <div className="font-semibold text-base">{t("upload.successTitle")}</div>
                  <div>{t("upload.successBank")} {result.bank_id}</div>
                  <div>{t("upload.successCount")} <strong>{result.transactions_imported}</strong></div>
                  <div>{t("upload.successAccount")} {String(result.metadata.account_holder ?? "—")}</div>
                  <div>{t("upload.successBalance")} {String(result.metadata.current_balance ?? "—")} EUR</div>
                  {result.parse_warnings.length > 0 && (
                    <div className="mt-2 text-yellow-700 dark:text-yellow-400">
                      <div className="font-medium">{t("upload.warningsTitle")}</div>
                      <ul className="list-disc list-inside">
                        {result.parse_warnings.slice(0, 5).map((w, j) => <li key={j}>{w}</li>)}
                      </ul>
                    </div>
                  )}
                </div>
              ))}
              <div className="text-right">
                <a href="/" className="text-indigo-600 dark:text-indigo-400 font-medium hover:underline text-sm">
                  {t("upload.dashboardLink")}
                </a>
              </div>
            </div>
          )}

          {/* Recategorize */}
          <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-6 shadow-sm space-y-4">
            <div>
              <h2 className="text-base font-semibold text-gray-900 dark:text-white">{t("upload.recatTitle")}</h2>
              <p className="text-gray-500 dark:text-gray-400 text-xs mt-1">{t("upload.recatSubtitle")}</p>
            </div>
            <div className="flex items-center gap-3">
              <input type="checkbox" id="recat-ai" checked={recatUseAi} onChange={(e) => setRecatUseAi(e.target.checked)} className="rounded" />
              <label htmlFor="recat-ai" className="text-sm text-gray-700 dark:text-gray-300">{t("upload.recatAiLabel")}</label>
            </div>
            <button onClick={handleRecategorize} disabled={recatLoading}
              className="w-full py-3 px-4 bg-gray-800 dark:bg-gray-700 text-white rounded-lg text-sm font-medium hover:bg-gray-900 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors">
              {recatLoading ? t("upload.recatSubmitting") : t("upload.recatSubmit")}
            </button>
            {recatError && (
              <div className="bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 rounded-lg p-3 text-sm">
                <strong>{t("upload.errorPrefix")}</strong> {recatError}
              </div>
            )}
            {recatResult && (
              <div className="bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-4 text-sm space-y-2">
                <div className="font-semibold text-gray-800 dark:text-gray-200">
                  {t("upload.recatSuccess", { count: recatResult.updated })}
                </div>
                <div className="text-gray-600 dark:text-gray-400">
                  <span className="font-medium">{t("upload.recatCatSources")}</span>{" "}
                  {Object.entries(recatResult.category_sources).map(([src, n]) => (
                    <span key={src} className="mr-3">{src}: {n}</span>
                  ))}
                </div>
                <div className="text-gray-600 dark:text-gray-400">
                  <span className="font-medium">{t("upload.recatDescSources")}</span>{" "}
                  {Object.entries(recatResult.clean_description_sources).map(([src, n]) => (
                    <span key={src} className="mr-3">{src}: {n}</span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* TAB: History                                                         */}
      {/* ------------------------------------------------------------------ */}
      {tab === "history" && (
        <div className="space-y-4">
          {/* Feedback messages */}
          {deleteMsg && (
            <div className="bg-green-50 dark:bg-green-950 border border-green-200 dark:border-green-800 text-green-800 dark:text-green-300 rounded-lg px-4 py-3 text-sm">
              {deleteMsg}
            </div>
          )}
          {deleteError && (
            <div className="bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 rounded-lg px-4 py-3 text-sm">
              <strong>{t("upload.errorPrefix")}</strong> {deleteError}
            </div>
          )}

          {/* Imports table */}
          <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-100 dark:border-gray-800 flex items-center justify-between">
              <h2 className="text-base font-semibold text-gray-900 dark:text-white">{t("upload.historyTitle")}</h2>
              {imports.length > 0 && (
                <span className="text-xs text-gray-400 dark:text-gray-500">{imports.length} imports</span>
              )}
            </div>

            {historyLoading ? (
              <div className="px-6 py-8 text-sm text-gray-400 dark:text-gray-500 text-center">{t("upload.historyLoading")}</div>
            ) : imports.length === 0 ? (
              <div className="px-6 py-8 text-sm text-gray-400 dark:text-gray-500 text-center">{t("upload.historyEmpty")}</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-100 dark:border-gray-800 text-xs uppercase tracking-wide text-gray-400 dark:text-gray-500">
                      <th className="text-left px-6 py-3 font-medium">{t("upload.colBank")}</th>
                      <th className="text-left px-4 py-3 font-medium">{t("upload.colFile")}</th>
                      <th className="text-left px-4 py-3 font-medium">{t("upload.colDate")}</th>
                      <th className="text-right px-4 py-3 font-medium">{t("upload.colTxCount")}</th>
                      <th className="text-left px-4 py-3 font-medium">{t("upload.colAccount")}</th>
                      <th className="text-right px-4 py-3 font-medium">{t("upload.colBalance")}</th>
                      <th className="px-4 py-3" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50 dark:divide-gray-800">
                    {imports.map((imp) => (
                      <tr key={imp.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors">
                        <td className="px-6 py-3 font-medium text-gray-900 dark:text-white whitespace-nowrap capitalize">
                          {imp.bank_id}
                        </td>
                        <td className="px-4 py-3 text-gray-600 dark:text-gray-400 max-w-[200px] truncate" title={imp.filename}>
                          {imp.filename}
                        </td>
                        <td className="px-4 py-3 text-gray-500 dark:text-gray-400 whitespace-nowrap">
                          {formatDate(imp.imported_at.slice(0, 10), intlLocale)}
                        </td>
                        <td className="px-4 py-3 text-right tabular-nums text-gray-700 dark:text-gray-300">
                          {imp.tx_count}
                        </td>
                        <td className="px-4 py-3 text-gray-500 dark:text-gray-400 max-w-[150px] truncate" title={imp.metadata.account_holder ?? ""}>
                          {imp.metadata.account_holder ?? "—"}
                        </td>
                        <td className="px-4 py-3 text-right tabular-nums text-gray-700 dark:text-gray-300 whitespace-nowrap">
                          {imp.metadata.current_balance != null
                            ? formatEur(imp.metadata.current_balance as number, intlLocale)
                            : "—"}
                        </td>
                        <td className="px-4 py-3 text-right">
                          <button
                            onClick={() => handleDeleteImport(imp)}
                            disabled={deletingId === imp.id}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950 disabled:opacity-40 disabled:cursor-not-allowed transition-colors border border-red-200 dark:border-red-800"
                          >
                            {deletingId === imp.id ? (
                              t("upload.deleting")
                            ) : (
                              <>
                                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                </svg>
                                {t("upload.deleteImport")}
                              </>
                            )}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Danger zone — delete all */}
          <div className="bg-white dark:bg-gray-900 rounded-xl border border-red-200 dark:border-red-900 shadow-sm p-6 space-y-3">
            <h3 className="text-sm font-semibold text-red-700 dark:text-red-400">{t("upload.deleteAllTitle")}</h3>
            <p className="text-xs text-gray-500 dark:text-gray-400">{t("upload.deleteAllBody")}</p>
            <button
              onClick={handleDeleteAll}
              disabled={deletingAll}
              className="px-4 py-2 bg-red-600 text-white rounded-lg text-sm font-medium hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {deletingAll ? t("upload.deleting") : t("upload.deleteAllConfirm")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
