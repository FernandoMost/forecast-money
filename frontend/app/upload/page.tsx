"use client";

import { useState } from "react";
import { api, UploadResponse } from "@/lib/api";

export default function UploadPage() {
  const [file, setFile] = useState<File | null>(null);
  const [bank, setBank] = useState("santander");
  const [useAi, setUseAi] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<UploadResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const res = await api.upload(file, bank, useAi);
      setResult(res);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Upload Statement</h1>
        <p className="text-gray-500 text-sm mt-1">
          Upload your bank statement Excel export. All data stays on your machine.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm space-y-5">
        {/* File picker */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Excel file (.xlsx)
          </label>
          <input
            type="file"
            accept=".xlsx"
            required
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="block w-full text-sm text-gray-600 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100"
          />
        </div>

        {/* Bank selector */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Bank</label>
          <select
            value={bank}
            onChange={(e) => setBank(e.target.value)}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white"
          >
            <option value="santander">Santander España</option>
          </select>
        </div>

        {/* AI toggle */}
        <div className="flex items-center gap-3">
          <input
            type="checkbox"
            id="use-ai"
            checked={useAi}
            onChange={(e) => setUseAi(e.target.checked)}
            className="rounded"
          />
          <label htmlFor="use-ai" className="text-sm text-gray-700">
            Use AI categorization (requires{" "}
            <a
              href="https://ollama.ai"
              target="_blank"
              rel="noopener noreferrer"
              className="text-indigo-600 underline"
            >
              Ollama
            </a>{" "}
            running locally)
          </label>
        </div>

        <button
          type="submit"
          disabled={loading || !file}
          className="w-full py-2.5 px-4 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {loading ? "Processing..." : "Upload & Analyze"}
        </button>
      </form>

      {/* Error */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-xl p-4 text-sm">
          <strong>Error:</strong> {error}
        </div>
      )}

      {/* Success */}
      {result && (
        <div className="bg-green-50 border border-green-200 text-green-800 rounded-xl p-5 text-sm space-y-2">
          <div className="font-semibold text-base">Upload successful!</div>
          <div>Bank: {result.bank_id}</div>
          <div>Transactions imported: <strong>{result.transactions_imported}</strong></div>
          <div>Account: {String(result.metadata.account_holder ?? "—")}</div>
          <div>Balance: {String(result.metadata.current_balance ?? "—")} EUR</div>
          {result.parse_warnings.length > 0 && (
            <div className="mt-2 text-yellow-700">
              <div className="font-medium">Warnings:</div>
              <ul className="list-disc list-inside">
                {result.parse_warnings.slice(0, 5).map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </div>
          )}
          <div className="mt-3">
            <a href="/" className="text-indigo-600 font-medium hover:underline">
              View Dashboard →
            </a>
          </div>
        </div>
      )}
    </div>
  );
}
