import gzip, json
from pathlib import Path
from typing import Dict, Any, List

class CompactJsonlGzipWriter:
    def __init__(self, out_path: str, batch_size: int = 1000):
        self.out_path = Path(out_path)
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        self.batch_size = batch_size
        self.buf: List[Dict[str,Any]] = []
        self.f = gzip.open(self.out_path, "at", encoding="utf-8")  # append text
    def compact(self, rec: Dict[str,Any]) -> Dict[str,Any]:
        c = {}
        c["ts"] = rec.get("timestamp")
        c["sym"] = rec.get("symbol") or rec.get("sym")
        c["operacion"] = rec.get("operacion")
        c["entry_p"] = rec.get("precio")
        c["exit_p"] = rec.get("exit_p") or rec.get("exit_price")
        c["pl"] = rec.get("pl")
        cond = rec.get("condiciones", {})
        if "RSI" in cond: c["rsi"] = cond["RSI"]
        if "MACD" in cond and isinstance(cond["MACD"], (list,tuple)): c["macd_hist"] = cond["MACD"][0]
        adx = cond.get("ADX")
        if isinstance(adx, (list,tuple)):
            for i,v in enumerate(adx[:3], start=1): c[f"adx{i}"] = v
        c["resultado"] = rec.get("resultado")
        c["params"] = rec.get("params") or rec.get("version")
        return c
    def write(self, rec: Dict[str,Any]):
        self.buf.append(self.compact(rec))
        if len(self.buf) >= self.batch_size:
            self.flush()
    def flush(self):
        for r in self.buf:
            self.f.write(json.dumps(r, ensure_ascii=False) + "\n")
        self.f.flush()
        self.buf = []
    def close(self):
        if self.buf: self.flush()
        self.f.close()