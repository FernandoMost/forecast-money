"use client";

import { useEffect, useRef, useState } from "react";
import { api, UploadResponse, RecategorizeResponse } from "@/lib/api";
import { useT } from "@/lib/i18n";

export default function UploadPage() {
  const { t } = useT();
  const [file, setFile] = useState<File | null>(null);
  const [bank, setBank] = useState("santander");
  const [useAi, setUseAi] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<UploadResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sharedFile, setSharedFile] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [recatLoading, setRecatLoading] = useState(false);
  const [recatUseAi, setRecatUseAi] = useState(false);
  const [recatResult, setRecatResult] = useState<RecategorizeResponse | null>(null);
  const [recatError, setRecatError] = useState<string | null>(null);

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
        setFile(recovered);
        setSharedFile(true);
        await cache.delete("/shared-file");
        window.history.replaceState({}, "", "/upload");
      } catch { /* non-critical */ }
    }
    recoverSharedFile();
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setLoading(true); setError(null); setResult(null);
    try {
      const res = await api.upload(file, bank, useAi);
      setResult(res); setFile(null); setSharedFile(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally { setLoading(false); }
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

  const inputCls = "w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2.5 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500";

  return (
    <div className="max-w-xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{t("upload.title")}</h1>
        <p className="text-gray-500 dark:text-gray-400 text-sm mt-1">{t("upload.subtitle")}</p>
      </div>

      <form onSubmit={handleSubmit} className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-6 shadow-sm space-y-5">
        {sharedFile && file && (
          <div className="flex items-center gap-3 bg-indigo-50 dark:bg-indigo-900/30 border border-indigo-200 dark:border-indigo-700 rounded-lg px-4 py-3 text-sm text-indigo-800 dark:text-indigo-300">
            <svg className="w-5 h-5 shrink-0 text-indigo-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span>{t("upload.sharedBanner", { filename: file.name })}</span>
          </div>
        )}

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            {sharedFile ? t("upload.fileLabelShared") : t("upload.fileLabel")}
          </label>
          <input ref={fileInputRef} type="file"
            accept=".xlsx,.csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv"
            required={!sharedFile}
            onChange={(e) => { setFile(e.target.files?.[0] ?? null); setSharedFile(false); }}
            className="block w-full text-sm text-gray-600 dark:text-gray-400 file:mr-4 file:py-2.5 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-indigo-50 dark:file:bg-indigo-900/40 file:text-indigo-700 dark:file:text-indigo-300 hover:file:bg-indigo-100 cursor-pointer" />
          {file && !sharedFile && <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{file.name}</p>}
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

        <button type="submit" disabled={loading || (!file && !sharedFile)}
          className="w-full py-3 px-4 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors">
          {loading ? t("upload.submitting") : t("upload.submit")}
        </button>
      </form>

      {error && (
        <div className="bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 rounded-xl p-4 text-sm">
          <strong>{t("upload.errorPrefix")}</strong> {error}
        </div>
      )}

      {result && (
        <div className="bg-green-50 dark:bg-green-950 border border-green-200 dark:border-green-800 text-green-800 dark:text-green-300 rounded-xl p-5 text-sm space-y-2">
          <div className="font-semibold text-base">{t("upload.successTitle")}</div>
          <div>{t("upload.successBank")} {result.bank_id}</div>
          <div>{t("upload.successCount")} <strong>{result.transactions_imported}</strong></div>
          <div>{t("upload.successAccount")} {String(result.metadata.account_holder ?? "—")}</div>
          <div>{t("upload.successBalance")} {String(result.metadata.current_balance ?? "—")} EUR</div>
          {result.parse_warnings.length > 0 && (
            <div className="mt-2 text-yellow-700 dark:text-yellow-400">
              <div className="font-medium">{t("upload.warningsTitle")}</div>
              <ul className="list-disc list-inside">
                {result.parse_warnings.slice(0, 5).map((w, i) => <li key={i}>{w}</li>)}
              </ul>
            </div>
          )}
          <div className="mt-3">
            <a href="/" className="text-indigo-600 dark:text-indigo-400 font-medium hover:underline">
              {t("upload.dashboardLink")}
            </a>
          </div>
        </div>
      )}

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
  );
}
