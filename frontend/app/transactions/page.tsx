"use client";

import { useEffect, useState } from "react";
import { api, Transaction, TransactionList } from "@/lib/api";
import { formatEur } from "@/lib/utils";

const CATEGORIES = [
  "income", "housing", "groceries", "restaurants", "transport",
  "subscriptions", "shopping", "entertainment", "health",
  "transfers", "cash", "admin", "uncategorized",
];

const SOURCE_BADGE: Record<string, string> = {
  rule:  "bg-gray-100 text-gray-500",
  ai:    "bg-purple-100 text-purple-700",
  cache: "bg-blue-100 text-blue-600",
};

export default function TransactionsPage() {
  const [months, setMonths] = useState<string[]>([]);
  const [selectedMonth, setSelectedMonth] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("");
  const [data, setData] = useState<TransactionList | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.months().then((d) => {
      setMonths(d.months);
      if (d.months.length > 0) setSelectedMonth(d.months[0]);
    });
  }, []);

  useEffect(() => {
    setLoading(true);
    api
      .transactions({
        month: selectedMonth || undefined,
        category: selectedCategory || undefined,
        limit: 200,
      })
      .then(setData)
      .finally(() => setLoading(false));
  }, [selectedMonth, selectedCategory]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Transactions</h1>
        <p className="text-gray-500 text-sm mt-1">Filter and explore your spending.</p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <select
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white"
          value={selectedMonth}
          onChange={(e) => setSelectedMonth(e.target.value)}
        >
          <option value="">All months</option>
          {months.map((m) => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>
        <select
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white"
          value={selectedCategory}
          onChange={(e) => setSelectedCategory(e.target.value)}
        >
          <option value="">All categories</option>
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
        {data && (
          <span className="text-sm text-gray-500 self-center">
            {data.items.length} transactions
          </span>
        )}
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                <th className="px-4 py-3 text-left font-medium text-gray-600">Date</th>
                <th className="px-4 py-3 text-left font-medium text-gray-600">Description</th>
                <th className="px-4 py-3 text-left font-medium text-gray-600">Category</th>
                <th className="px-4 py-3 text-right font-medium text-gray-600">Amount</th>
                <th className="px-4 py-3 text-right font-medium text-gray-600">Balance</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {loading && (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-gray-400">
                    Loading...
                  </td>
                </tr>
              )}
              {!loading && data?.items.map((tx) => (
                <tr key={tx.id} className={`hover:bg-gray-50 ${tx.is_reversal ? "opacity-50" : ""}`}>
                  <td className="px-4 py-2.5 text-gray-500 whitespace-nowrap">{tx.date}</td>
                  <td className="px-4 py-2.5 max-w-xs" title={tx.description}>
                    {tx.clean_description ? (
                      <span className="text-gray-900 font-medium">{tx.clean_description}</span>
                    ) : (
                      <span className="text-gray-500 truncate block">{tx.description}</span>
                    )}
                  </td>
                  <td className="px-4 py-2.5">
                    {tx.category ? (
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="px-2 py-0.5 rounded-full text-xs bg-indigo-50 text-indigo-700 font-medium">
                          {tx.subcategory ?? tx.category}
                        </span>
                        {tx.category_source && (
                          <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${SOURCE_BADGE[tx.category_source] ?? "bg-gray-100 text-gray-400"}`}>
                            {tx.category_source}
                          </span>
                        )}
                      </div>
                    ) : (
                      <span className="text-gray-300">—</span>
                    )}
                  </td>
                  <td className={`px-4 py-2.5 text-right font-medium tabular-nums ${tx.amount < 0 ? "text-red-600" : "text-green-600"}`}>
                    {formatEur(tx.amount)}
                  </td>
                  <td className="px-4 py-2.5 text-right text-gray-500 tabular-nums">
                    {formatEur(tx.balance)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
