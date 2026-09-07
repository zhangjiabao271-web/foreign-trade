const checkpoints = [
  { code: "LD", label: "线索", note: "找到值得跟进的买家" },
  { code: "QT", label: "报价", note: "看清成本、汇率与毛利" },
  { code: "SO", label: "订单", note: "锁定承诺与采购动作" },
  { code: "SH", label: "出货", note: "单证、物流和节点可追溯" },
  { code: "RC", label: "回款", note: "核销应收，完成归档" },
] as const;

export function RouteMap() {
  return (
    <section className="route-card" aria-labelledby="route-title">
      <div className="route-heading">
        <div>
          <p className="section-kicker">首单航线</p>
          <h2 id="route-title">从线索到回款，一条链看到底</h2>
        </div>
        <p>V1 的所有建设都服务于这条经营闭环。</p>
      </div>
      <ol className="route-track">
        {checkpoints.map((checkpoint, index) => (
          <li key={checkpoint.code}>
            <span className="checkpoint-code" aria-hidden="true">
              {checkpoint.code}
            </span>
            <div>
              <p>
                <span>{String(index + 1).padStart(2, "0")}</span>
                {checkpoint.label}
              </p>
              <small>{checkpoint.note}</small>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
