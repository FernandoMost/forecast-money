"use client";

import { useRef, useState } from "react";
import { api, AuthError } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { useRouter } from "next/navigation";

export default function SettingsPage() {
  const { t } = useT();
  const router = useRouter();

  // Export state
  const [exportPassword, setExportPassword] = useState("");
  const [exportConfirm, setExportConfirm] = useState("");
  const [exportLoading, setExportLoading] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  // Restore state
  const [restoreFile, setRestoreFile] = useState<File | null>(null);
  const [restorePassword, setRestorePassword] = useState("");
  const [restoreConfirm, setRestoreConfirm] = useState(false);
  const [restoreLoading, setRestoreLoading] = useState(false);
  const [restoreResult, setRestoreResult] = useState<{ files: string[]; previousBackup: string | null } | null>(null);
  const [restoreError, setRestoreError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const inputCls =
    "block w-full rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 focus:border-indigo-500 focus:ring-indigo-500";

  const handleExport = async (e: React.FormEvent) => {
    e.preventDefault();
    setExportError(null);
    if (exportPassword.length < 8) {
      setExportError(t("settings.errorShortPassword"));
      return;
    }
    if (exportPassword !== exportConfirm) {
      setExportError(t("settings.errorPasswordMatch"));
      return;
    }
    setExportLoading(true);
    try {
      const blob = await api.exportBackup(exportPassword);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      const date = new Date().toISOString().slice(0, 10);
      a.href = url;
      a.download = `forecast-money-backup-${date}.zip`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      setExportPassword("");
      setExportConfirm("");
    } catch (err) {
      if (err instanceof AuthError) {
        router.push("/login");
        return;
      }
      setExportError(err instanceof Error ? err.message : "Export failed");
    } finally {
      setExportLoading(false);
    }
  };

  const handleRestore = async (e: React.FormEvent) => {
    e.preventDefault();
    setRestoreError(null);
    setRestoreResult(null);
    if (!restoreFile) {
      setRestoreError(t("settings.errorNoFile"));
      return;
    }
    setRestoreLoading(true);
    try {
      const res = await api.restoreBackup(restoreFile, restorePassword);
      setRestoreResult({ files: res.restored, previousBackup: res.previous_backup });
      setRestoreFile(null);
      setRestorePassword("");
      setRestoreConfirm(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
      // Auth.db likely changed; clear the stale cookie and ask to log in again
      try {
        await api.logout();
      } catch { /* ignore */ }
    } catch (err) {
      if (err instanceof AuthError) {
        router.push("/login");
        return;
      }
      setRestoreError(err instanceof Error ? err.message : "Restore failed");
    } finally {
      setRestoreLoading(false);
    }
  };

  return (
    <main className="min-h-screen bg-gray-50 dark:bg-gray-950 text-gray-900 dark:text-gray-100 p-4 md:p-6">
      <div className="max-w-2xl mx-auto space-y-6">
        <div>
          <h1 className="text-2xl font-bold">{t("settings.title")}</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{t("settings.subtitle")}</p>
        </div>

        {/* Export */}
        <section className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5 shadow-sm">
          <h2 className="text-lg font-semibold mb-2">{t("settings.exportCard")}</h2>
          <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">{t("settings.exportDesc")}</p>
          <form onSubmit={handleExport} className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">{t("settings.exportPassword")}</label>
              <input
                type="password"
                value={exportPassword}
                onChange={(e) => setExportPassword(e.target.value)}
                className={inputCls}
                placeholder={t("settings.exportPasswordHint")}
                minLength={8}
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">{t("settings.exportConfirmPassword")}</label>
              <input
                type="password"
                value={exportConfirm}
                onChange={(e) => setExportConfirm(e.target.value)}
                className={inputCls}
                placeholder={t("settings.exportConfirmPassword")}
                required
              />
            </div>
            {exportError && <p className="text-sm text-red-600 dark:text-red-400">{exportError}</p>}
            <button
              type="submit"
              disabled={exportLoading}
              className="inline-flex items-center rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {exportLoading ? t("settings.exportLoading") : t("settings.exportButton")}
            </button>
          </form>
        </section>

        {/* Restore */}
        <section className="bg-white dark:bg-gray-900 rounded-xl border border-red-200 dark:border-red-900/40 p-5 shadow-sm">
          <h2 className="text-lg font-semibold mb-2 text-red-700 dark:text-red-400">{t("settings.restoreCard")}</h2>
          <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">{t("settings.restoreDesc")}</p>
          <form onSubmit={handleRestore} className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">{t("settings.restoreFile")}</label>
              <input
                ref={fileInputRef}
                type="file"
                accept=".zip"
                onChange={(e) => setRestoreFile(e.target.files?.[0] ?? null)}
                className={inputCls}
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">{t("settings.restorePassword")}</label>
              <input
                type="password"
                value={restorePassword}
                onChange={(e) => setRestorePassword(e.target.value)}
                className={inputCls}
                required
              />
            </div>
            <div className="flex items-start gap-2">
              <input
                id="restore-confirm"
                type="checkbox"
                checked={restoreConfirm}
                onChange={(e) => setRestoreConfirm(e.target.checked)}
                className="mt-1 h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                required
              />
              <label htmlFor="restore-confirm" className="text-sm text-red-700 dark:text-red-400">
                {t("settings.restoreWarning")} {t("settings.restoreConfirmLabel")}
              </label>
            </div>
            {restoreError && <p className="text-sm text-red-600 dark:text-red-400">{restoreError}</p>}
            {restoreResult && (
              <div className="rounded-lg bg-green-50 dark:bg-green-900/20 p-3 text-sm text-green-800 dark:text-green-300">
                <p>
                  {t("settings.restoreSuccess")
                    .replace("{files}", restoreResult.files.join(", "))
                    .replace("{previousBackup}", restoreResult.previousBackup ?? "-")}
                </p>
                <p className="mt-1 font-medium">{t("settings.restoreLoginAgain")}</p>
              </div>
            )}
            <button
              type="submit"
              disabled={restoreLoading || !restoreConfirm}
              className="inline-flex items-center rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {restoreLoading ? t("settings.restoreLoading") : t("settings.restoreButton")}
            </button>
          </form>
        </section>
      </div>
    </main>
  );
}
