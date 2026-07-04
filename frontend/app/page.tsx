// app/page.tsx — Dashboard: score + alerts + monthly overview + recent transactions

import { api } from "@/lib/api";
import { formatEur, STATUS_COLORS, STATUS_BADGE } from "@/lib/utils";
import Link from "next/link";

export const dynamic = "force-dynamic";

function ScoreDial({ score, grade }: { score: number; grade: string }) {
  const color =
    score >= 80 ? "text-green-600" : score >= 55 ? "text-yellow-600" : "text-red-600";
  return (
    <div className="flex flex-col items-center justify-center p-8 bg-white rounded-2xl border border-gray-200 shadow-sm">
      <div className={`text-7xl font-black tabular-nums ${color}`}>{score}</div>
      <div className="text-gray-400 text-sm mt-1">out of 100</div>
      <div className={`mt-3 text-4xl font-bold ${color}`}>Grade {grade}</div>
      <div className="text-gray-500 text-sm mt-2">Overall Financial Health</div>
    </div>
  );
}

function RuleCard({ rule }: { rule: { rule_id: string; name: string; status: string; score: number; message: string } }) {
  const badgeColor =
    rule.status === "green"
      ? "bg-green-100 text-green-800"
      : rule.status === "amber"
      ? "bg-yellow-100 text-yellow-800"
      : "bg-red-100 text-red-800";
  return (
    <div className={`p-4 rounded-xl border ${STATUS_COLORS[rule.status]}`}>
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="font-semibold text-sm">{rule.name}</div>
          <div className="text-xs mt-1 opacity-80">{rule.message}</div>
        </div>
        <div className="text-right shrink-0">
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${badgeColor}`}>
            {rule.status.toUpperCase()}
          </span>
          <div className="text-lg font-bold mt-1">{rule.score.toFixed(0)}</div>
        </div>
      </div>
    </div>
  );
}

function AlertBanner({ alerts }: { alerts: { rule_id: string; name: string; status: string; message: string }[] }) {
  if (!alerts.length) return null;
  return (
    <div className="space-y-2">
      <h3 className="font-semibold text-gray-700 text-sm uppercase tracking-wide">Prioritized Alerts</h3>
      {alerts.map((a) => (
        <div
          key={a.rule_id}
          className={`flex gap-3 p-3 rounded-lg border text-sm ${STATUS_COLORS[a.status]}`}
        >
          <span>{a.status === "red" ? "🔴" : "🟡"}</span>
          <div>
            <span className="font-semibold">{a.name}:</span> {a.message}
          </div>
        </div>
      ))}
    </div>
  );
}

function SummaryCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
      <div className="text-xs text-gray-500 uppercase tracking-wide">{label}</div>
      <div className="text-2xl font-bold text-gray-900 mt-1">{value}</div>
      {sub && <div className="text-xs text-gray-400 mt-0.5">{sub}</div>}
    </div>
  );
}

export default async function DashboardPage() {
  let health;
  try {
    health = await api.healthScore();
  } catch {
    return (
      <div className="text-center py-24">
        <div className="text-6xl mb-4">📂</div>
        <h2 className="text-xl font-semibold text-gray-700">No data yet</h2>
        <p className="text-gray-500 mt-2">
          Upload your bank statement to get started.
        </p>
        <Link
          href="/upload"
          className="mt-6 inline-block px-6 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700"
        >
          Upload Statement
        </Link>
      </div>
    );
  }

  // Fetch recent transactions for the dashboard widget
  let recentTxs: Awaited<ReturnType<typeof api.transactions>>["items"] = [];
  try {
    const txData = await api.transactions({ limit: 8 });
    recentTxs = txData.items;
  } catch {
    // non-critical — dashboard still works without it
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <p className="text-gray-500 text-sm mt-1">
          {health.months_analyzed.length} months analyzed:{" "}
          {health.months_analyzed[0]} → {health.months_analyzed[health.months_analyzed.length - 1]}
        </p>
      </div>

      {/* Score + summary cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="md:col-span-1">
          <ScoreDial score={health.overall_score} grade={health.grade} />
        </div>
        <div className="md:col-span-3 grid grid-cols-2 sm:grid-cols-3 gap-4">
          <SummaryCard label="Total Income" value={formatEur(health.summary.total_income)} sub={`${health.summary.months_analyzed} months`} />
          <SummaryCard label="Total Expenses" value={formatEur(health.summary.total_expenses)} />
          <SummaryCard
            label="Net Savings"
            value={formatEur(health.summary.net_savings)}
            sub={health.summary.net_savings >= 0 ? "positive" : "deficit"}
          />
          <SummaryCard label="Transactions" value={String(health.summary.transaction_count)} />
          <SummaryCard label="Months" value={String(health.summary.months_analyzed)} />
          <SummaryCard
            label="Avg Monthly Savings"
            value={formatEur(health.summary.net_savings / (health.summary.months_analyzed || 1))}
          />
        </div>
      </div>

      {/* Alerts */}
      <AlertBanner alerts={health.alerts} />

      {/* Recent Transactions */}
      {recentTxs.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-semibold text-gray-700 text-sm uppercase tracking-wide">
              Recent Transactions
            </h3>
            <Link href="/transactions" className="text-xs text-indigo-600 hover:underline font-medium">
              View all →
            </Link>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
            <table className="w-full text-sm">
              <tbody className="divide-y divide-gray-100">
                {recentTxs.map((tx) => (
                  <tr key={tx.id} className={`hover:bg-gray-50 ${tx.is_reversal ? "opacity-50" : ""}`}>
                    <td className="px-4 py-2.5 text-gray-400 whitespace-nowrap w-24">{tx.date}</td>
                    <td className="px-4 py-2.5 text-gray-800 max-w-xs" title={tx.description}>
                      {tx.clean_description ? (
                        <span className="font-medium">{tx.clean_description}</span>
                      ) : (
                        <span className="text-gray-500 truncate block">{tx.description}</span>
                      )}
                    </td>
                    <td className="px-4 py-2.5">
                      {tx.category && (
                        <span className="px-2 py-0.5 rounded-full text-xs bg-indigo-50 text-indigo-700 font-medium whitespace-nowrap">
                          {tx.subcategory ?? tx.category}
                        </span>
                      )}
                    </td>
                    <td className={`px-4 py-2.5 text-right font-medium tabular-nums whitespace-nowrap ${tx.amount < 0 ? "text-red-600" : "text-green-600"}`}>
                      {formatEur(tx.amount)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Rules grid */}
      <div>
        <h3 className="font-semibold text-gray-700 text-sm uppercase tracking-wide mb-3">
          Rule-by-Rule Breakdown
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {health.rules.map((rule) => (
            <RuleCard key={rule.rule_id} rule={rule} />
          ))}
        </div>
      </div>

      <div className="text-xs text-gray-400 text-right">
        All data is stored locally. No external calls.
      </div>
    </div>
  );
}
