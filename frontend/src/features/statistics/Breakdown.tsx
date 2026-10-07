import { Card } from "../../components/ui/primitives";
import type { Group } from "../../types/api";
export function Breakdown({ title, rows }: { title: string; rows: Group[] }) {
  return (
    <Card className="breakdown">
      <h2>{title}</h2>
      {rows.length === 0 ? (
        <p className="muted">No hay reservas para los filtros seleccionados.</p>
      ) : (
        <>
          <table>
            <thead>
              <tr>
                <th>Nombre</th>
                <th>Reservas</th>
                <th>Atendidas</th>
                <th>Ausencias</th>
                <th>Cancelaciones</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={`${r.name}-${i}`}>
                  <th scope="row">{r.name}</th>
                  <td>{r.total}</td>
                  <td>{r.attended}</td>
                  <td>{r.absent}</td>
                  <td>{r.cancelled}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="breakdown-mobile">
            {rows.map((r, i) => (
              <div key={`${r.name}-${i}`}>
                <h3>{r.name}</h3>
                <dl>
                  {[
                    ["Reservas", r.total],
                    ["Atendidas", r.attended],
                    ["Ausencias", r.absent],
                    ["Cancelaciones", r.cancelled],
                  ].map(([label, value]) => (
                    <div key={label}>
                      <dt>{label}</dt>
                      <dd>{value}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            ))}
          </div>
        </>
      )}
    </Card>
  );
}
