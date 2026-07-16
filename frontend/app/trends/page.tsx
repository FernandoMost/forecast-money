"use client";

import { useEffect, useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer,
  PieChart, Pie, Cell, LineChart, Line, CartesianGrid,
} from "recharts";
import { api, MonthlySummary } from "@/lib/api";
import { formatEur } from "@/lib/utils";
import { useCategoryTree } from "@/components/CategoryTree";
import { useT } from "@/lib/i18n";

export default function TrendsPage() {
  const { t } = useT();
  const [months, setMonths] = useState<string[]>([]);
  const [summaries, setSummaries] = useState<MonthlySummary[]>([]);
  const [selectedMonth, setSelectedMonth] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const { categoryColor } = useCategoryTree();

  useEffect(() => {
    api.months().then(async (d) => {
      setMonths(d.months);
      const all = await Promise.all(
        d.months.slice(0, 8).map((m) => api.summary(m))
      );
      setSummaries(all.reverse()); // chronological order
      if (d.months.length > 0) setSelectedMonth(d.months[0]);
      setLoading(false);
    });
  }, []);

  const currentSummary = summaries.find((s) => s.month === selectedMonth) ?? summaries[summaries.length - 1];

  const barData = summaries.map((s) => ({
    month: s.month.slice(5),
    Income: s.total_income,
    Expenses: s.total_expenses,
    Savings: s.net_savings,
  }));

  const lineData = summaries.map((s) => ({
    month: s.month.slice(5),
    "Savings rate (%)": s.savings_rate,
  }));

  const pieData = currentSummary?.by_category
    .filter((c) => c.total < 0)
    .map((c) => ({ name: c.category, value: Math.abs(c.total) }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 10) ?? [];

  if (loading) {
    return <div className="py-24 text-center text-gray-400 dark:text-gray-500">{t("trends.loading")}</div>;
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{t("trends.title")}</h1>
        <p className="text-gray-500 dark:text-gray-400 text-sm mt-1">{t("trends.subtitle")}</p>
      </div>

      {/* Month-over-month bar chart */}
      <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-6 shadow-sm">
        <h2 className="font-semibold text-gray-700 dark:text-gray-300 mb-4">{t("trends.incomeExpSavings")}</h2>
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={barData} margin={{ top: 5, right: 20, left: 20, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis dataKey="month" tick={{ fontSize: 12 }} />
            <YAxis tickFormatter={(v) => `€${(v / 1000).toFixed(1)}k`} tick={{ fontSize: 11 }} />
            <Tooltip formatter={(v) => formatEur(Number(v))} />
            <Legend />
            <Bar dataKey="Income" name={t("trends.income")} fill="#84cc16" radius={[4, 4, 0, 0]} />
            <Bar dataKey="Expenses" name={t("trends.expenses")} fill="#f97316" radius={[4, 4, 0, 0]} />
            <Bar dataKey="Savings" name={t("trends.savings")} fill="#6366f1" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Savings rate line chart */}
      <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-6 shadow-sm">
        <h2 className="font-semibold text-gray-700 dark:text-gray-300 mb-4">{t("trends.savingsRate")}</h2>
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={lineData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis dataKey="month" tick={{ fontSize: 12 }} />
            <YAxis tickFormatter={(v) => `${v.toFixed(0)}%`} tick={{ fontSize: 11 }} />
            <Tooltip formatter={(v) => `${Number(v).toFixed(1)}%`} />
            <Line type="monotone" dataKey="Savings rate (%)" name={t("trends.savingsRateKey")} stroke="#6366f1" strokeWidth={2} dot />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Spending breakdown pie */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-6 shadow-sm">
          <div className="flex items-center gap-3 mb-4">
            <h2 className="font-semibold text-gray-700 dark:text-gray-300">{t("trends.spendingByCategory")}</h2>
            <select
              className="ml-auto border border-gray-200 dark:border-gray-700 rounded px-2 py-1 text-xs bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
              value={selectedMonth}
              onChange={(e) => setSelectedMonth(e.target.value)}
            >
              {months.slice(0, 8).map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
          </div>
          <ResponsiveContainer width="100%" height={240}>
            <PieChart>
              <Pie
                data={pieData}
                cx="50%"
                cy="50%"
                outerRadius={90}
                dataKey="value"
                label={({ name, percent }) => `${name} ${((percent ?? 0) * 100).toFixed(0)}%`}
                labelLine={false}
              >
                {pieData.map((entry) => (
                  <Cell
                    key={entry.name}
                    fill={categoryColor(entry.name)}
                  />
                ))}
              </Pie>
              <Tooltip formatter={(v) => formatEur(Number(v))} />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* Category table */}
        <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-6 shadow-sm overflow-auto">
          <h2 className="font-semibold text-gray-700 dark:text-gray-300 mb-4">{t("trends.categoryBreakdown", { month: selectedMonth })}</h2>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 dark:text-gray-400 border-b border-gray-100 dark:border-gray-800">
                <th className="pb-2">{t("trends.colCategory")}</th>
                <th className="pb-2 text-right">{t("trends.colTotal")}</th>
                <th className="pb-2 text-right">{t("trends.colTxns")}</th>
              </tr>
            </thead>
            <tbody>
              {currentSummary?.by_category
                .sort((a, b) => a.total - b.total)
                .map((c) => (
                  <tr key={c.category} className="border-b border-gray-50 dark:border-gray-800">
                    <td className="py-1.5 flex items-center gap-2">
                      <span
                        className="w-2.5 h-2.5 rounded-full inline-block"
                        style={{ background: categoryColor(c.category) }}
                      />
                      <span className="text-gray-700 dark:text-gray-300">{c.category}</span>
                    </td>
                    <td className={`py-1.5 text-right tabular-nums ${c.total < 0 ? "text-red-600" : "text-green-600"}`}>
                      {formatEur(c.total)}
                    </td>
                    <td className="py-1.5 text-right text-gray-400 dark:text-gray-500">{c.count}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
