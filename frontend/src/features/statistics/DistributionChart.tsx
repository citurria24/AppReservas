import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { Card, EmptyState } from "../../components/ui/primitives";
import type { StatisticsData } from "../../types/api";
import { percent, stateColors } from "../../utils/format";
export function DistributionChart({
  distribution,
  total,
}: {
  distribution: StatisticsData["distribution"];
  total: number;
}) {
  return (
    <Card className="chart-panel">
      <h2>Distribución de reservas</h2>
      <p className="muted">
        Estados de las reservas durante el período seleccionado.
      </p>
      {total === 0 ? (
        <EmptyState />
      ) : (
        <div className="distribution-layout">
          <div className="chart-container" aria-hidden="true">
            <ResponsiveContainer width="100%" height="100%" minWidth={0}>
              <PieChart>
                <Pie
                  data={distribution}
                  dataKey="count"
                  nameKey="label"
                  innerRadius="72%"
                  outerRadius="88%"
                  paddingAngle={distribution.length > 1 ? 2 : 0}
                  isAnimationActive={false}
                  stroke="none"
                >
                  {distribution.map((d) => (
                    <Cell key={d.status} fill={stateColors[d.status]} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    border: "1px solid #E7E7E4",
                    borderRadius: 8,
                    fontSize: 12,
                    boxShadow: "none",
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
            <div className="donut-center">
              <strong>{total}</strong>
              <span>reservas</span>
            </div>
          </div>
          <ul className="chart-legend" aria-label="Distribución de reservas">
            {distribution.map((d) => (
              <li key={d.status}>
                <span
                  className="legend-dot"
                  style={{ background: stateColors[d.status] }}
                  aria-hidden
                />
                <span>{d.label}</span>
                <strong>
                  {d.count} · {percent(d.count / total)}
                </strong>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}
