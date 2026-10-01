#!/usr/bin/env python3
"""
Gorev 5 icin yerel YOLO etiketleme araci.

labelImg acilmazsa bunu calistirin:
    py -3.10 web_etiketle.py

Sonra tarayicida:
    http://127.0.0.1:8765
"""
from __future__ import annotations

import argparse
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

SINIFLAR = ["yaya", "tumsek", "hemzemin", "park"]
GORSEL_UZANTI = {".jpg", ".jpeg", ".png"}


HTML = r"""<!doctype html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Gorev 5 YOLO Etiketleme</title>
  <style>
    :root {
      --bg: #f6f7f8;
      --panel: #ffffff;
      --ink: #202329;
      --muted: #6b7280;
      --line: #d7dce2;
      --active: #0f766e;
      --danger: #b91c1c;
      --shadow: 0 1px 2px rgba(0,0,0,.08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      height: 100vh;
      overflow: hidden;
      background: var(--bg);
      color: var(--ink);
      font: 14px/1.35 system-ui, -apple-system, "Segoe UI", Arial, sans-serif;
    }
    button, select, input {
      font: inherit;
    }
    button {
      min-height: 32px;
      border: 1px solid var(--line);
      background: #fff;
      border-radius: 6px;
      padding: 6px 10px;
      cursor: pointer;
    }
    button:hover { border-color: #9aa5b1; }
    button.primary {
      background: var(--active);
      border-color: var(--active);
      color: #fff;
    }
    button.danger {
      color: var(--danger);
      border-color: #f0b4b4;
    }
    .app {
      height: 100vh;
      display: grid;
      grid-template-columns: 280px minmax(0, 1fr);
      grid-template-rows: 48px minmax(0, 1fr);
    }
    header {
      grid-column: 1 / 3;
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 8px 12px;
      background: #fff;
      border-bottom: 1px solid var(--line);
      box-shadow: var(--shadow);
      z-index: 2;
    }
    .title {
      font-weight: 700;
      min-width: 145px;
    }
    .status {
      color: var(--muted);
      white-space: nowrap;
    }
    .status.dirty {
      color: #a16207;
      font-weight: 650;
    }
    .toolbar {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }
    .classbar {
      display: flex;
      align-items: center;
      gap: 6px;
      margin-left: auto;
    }
    .classbtn {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      min-width: 92px;
      justify-content: center;
    }
    .classbtn.active {
      border-color: #111827;
      box-shadow: inset 0 0 0 2px #111827;
    }
    .swatch {
      width: 12px;
      height: 12px;
      border-radius: 50%;
      border: 1px solid rgba(0,0,0,.18);
    }
    aside {
      min-height: 0;
      border-right: 1px solid var(--line);
      background: #fff;
      display: flex;
      flex-direction: column;
    }
    .side-top {
      padding: 10px;
      border-bottom: 1px solid var(--line);
      display: grid;
      gap: 8px;
    }
    .search {
      width: 100%;
      height: 32px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 0 9px;
    }
    .summary {
      color: var(--muted);
      display: flex;
      justify-content: space-between;
      gap: 8px;
    }
    .list {
      overflow: auto;
      min-height: 0;
    }
    .row {
      width: 100%;
      height: 34px;
      display: grid;
      grid-template-columns: 1fr 44px;
      gap: 8px;
      align-items: center;
      border: 0;
      border-bottom: 1px solid #eef1f4;
      border-radius: 0;
      text-align: left;
      padding: 0 10px;
      background: #fff;
    }
    .row.active {
      background: #e7f5f3;
      color: #064e3b;
      font-weight: 700;
    }
    .row.empty .count {
      color: #9a3412;
    }
    .count {
      color: var(--muted);
      text-align: right;
      font-variant-numeric: tabular-nums;
    }
    main {
      min-width: 0;
      min-height: 0;
      display: grid;
      grid-template-rows: minmax(0, 1fr) 42px;
    }
    .stage {
      min-width: 0;
      min-height: 0;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 14px;
      background:
        linear-gradient(45deg, #e5e7eb 25%, transparent 25%),
        linear-gradient(-45deg, #e5e7eb 25%, transparent 25%),
        linear-gradient(45deg, transparent 75%, #e5e7eb 75%),
        linear-gradient(-45deg, transparent 75%, #e5e7eb 75%);
      background-size: 22px 22px;
      background-position: 0 0, 0 11px, 11px -11px, -11px 0;
    }
    canvas {
      max-width: 100%;
      max-height: 100%;
      background: #111;
      box-shadow: 0 2px 18px rgba(0,0,0,.18);
      cursor: crosshair;
    }
    footer {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      padding: 6px 12px;
      background: #fff;
      border-top: 1px solid var(--line);
      color: var(--muted);
    }
    kbd {
      border: 1px solid #cbd5e1;
      border-bottom-width: 2px;
      border-radius: 4px;
      padding: 1px 5px;
      background: #fff;
      color: #111827;
      font-size: 12px;
    }
    .hidden { display: none; }
  </style>
</head>
<body>
  <div class="app">
    <header>
      <div class="title">Gorev 5 Etiketleme</div>
      <div class="toolbar">
        <button id="prevBtn">A Onceki</button>
        <button id="nextBtn">D Sonraki</button>
        <button id="saveBtn" class="primary">S Kaydet</button>
        <button id="deleteBtn" class="danger">Delete Sil</button>
      </div>
      <div id="status" class="status">Yukleniyor...</div>
      <div id="classbar" class="classbar"></div>
    </header>

    <aside>
      <div class="side-top">
        <input id="search" class="search" placeholder="Gorsel ara: 0046">
        <div class="summary">
          <span id="progress">0 / 0</span>
          <span id="boxTotal">0 kutu</span>
        </div>
      </div>
      <div id="list" class="list"></div>
    </aside>

    <main>
      <div class="stage"><canvas id="canvas"></canvas></div>
      <footer>
        <span><kbd>1</kbd> yaya <kbd>2</kbd> tumsek <kbd>3</kbd> hemzemin <kbd>4</kbd> park</span>
        <span><kbd>Surukle</kbd> kutu ciz <kbd>Tikla</kbd> sec <kbd>Delete</kbd> sil</span>
      </footer>
    </main>
  </div>

<script>
const colors = ["#3ac66d", "#f08a2a", "#4385e8", "#e4ad29"];
let classes = [];
let images = [];
let filtered = [];
let index = 0;
let boxes = [];
let selectedClass = 0;
let selectedBox = -1;
let dirty = false;
let mode = null;
let start = null;
let originalBox = null;
let img = new Image();

const canvas = document.getElementById("canvas");
const ctx = canvas.getContext("2d");
const statusEl = document.getElementById("status");
const listEl = document.getElementById("list");
const progressEl = document.getElementById("progress");
const boxTotalEl = document.getElementById("boxTotal");
const searchEl = document.getElementById("search");

function currentImage() {
  return filtered[index] || images[index];
}

function setDirty(value) {
  dirty = value;
  statusEl.classList.toggle("dirty", dirty);
  updateStatus();
}

function updateStatus(extra = "") {
  const item = currentImage();
  if (!item) {
    statusEl.textContent = "Gorsel yok";
    return;
  }
  statusEl.textContent = `${item.name} | ${boxes.length} kutu${dirty ? " | kaydedilmedi" : ""}${extra ? " | " + extra : ""}`;
  progressEl.textContent = `${index + 1} / ${filtered.length}`;
  boxTotalEl.textContent = `${boxes.length} kutu`;
}

function buildClassButtons() {
  const bar = document.getElementById("classbar");
  bar.innerHTML = "";
  classes.forEach((name, i) => {
    const btn = document.createElement("button");
    btn.className = "classbtn";
    btn.innerHTML = `<span class="swatch" style="background:${colors[i]}"></span>${i + 1} ${name}`;
    btn.onclick = () => setClass(i);
    btn.id = `classBtn${i}`;
    bar.appendChild(btn);
  });
  updateClassButtons();
}

function updateClassButtons() {
  classes.forEach((_, i) => {
    const btn = document.getElementById(`classBtn${i}`);
    if (btn) btn.classList.toggle("active", i === selectedClass);
  });
}

function setClass(cls) {
  selectedClass = cls;
  if (selectedBox >= 0) {
    boxes[selectedBox].cls = cls;
    setDirty(true);
    draw();
  }
  updateClassButtons();
}

function denorm(box) {
  const w = canvas.width, h = canvas.height;
  const bw = box.w * w;
  const bh = box.h * h;
  return {
    x1: box.x * w - bw / 2,
    y1: box.y * h - bh / 2,
    x2: box.x * w + bw / 2,
    y2: box.y * h + bh / 2,
  };
}

function norm(rect, cls) {
  const x1 = Math.max(0, Math.min(canvas.width, Math.min(rect.x1, rect.x2)));
  const y1 = Math.max(0, Math.min(canvas.height, Math.min(rect.y1, rect.y2)));
  const x2 = Math.max(0, Math.min(canvas.width, Math.max(rect.x1, rect.x2)));
  const y2 = Math.max(0, Math.min(canvas.height, Math.max(rect.y1, rect.y2)));
  return {
    cls,
    x: ((x1 + x2) / 2) / canvas.width,
    y: ((y1 + y2) / 2) / canvas.height,
    w: (x2 - x1) / canvas.width,
    h: (y2 - y1) / canvas.height,
  };
}

function pointer(evt) {
  const rect = canvas.getBoundingClientRect();
  return {
    x: (evt.clientX - rect.left) * canvas.width / rect.width,
    y: (evt.clientY - rect.top) * canvas.height / rect.height,
    scale: canvas.width / rect.width,
  };
}

function hitTest(p) {
  const threshold = 10 * p.scale;
  for (let i = boxes.length - 1; i >= 0; i--) {
    const r = denorm(boxes[i]);
    const handles = [
      ["nw", r.x1, r.y1], ["ne", r.x2, r.y1],
      ["sw", r.x1, r.y2], ["se", r.x2, r.y2],
    ];
    for (const [name, x, y] of handles) {
      if (Math.abs(p.x - x) <= threshold && Math.abs(p.y - y) <= threshold) {
        return { index: i, handle: name };
      }
    }
    if (p.x >= r.x1 && p.x <= r.x2 && p.y >= r.y1 && p.y <= r.y2) {
      return { index: i, handle: "move" };
    }
  }
  return null;
}

function draw(preview = null) {
  if (!img.complete || !canvas.width) return;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

  boxes.forEach((box, i) => {
    const r = denorm(box);
    const color = colors[box.cls] || "#ffff00";
    ctx.lineWidth = i === selectedBox ? 4 : 2;
    ctx.strokeStyle = color;
    ctx.strokeRect(r.x1, r.y1, r.x2 - r.x1, r.y2 - r.y1);
    const label = classes[box.cls] || String(box.cls);
    ctx.font = "18px system-ui, Arial";
    const textW = ctx.measureText(label).width + 10;
    ctx.fillStyle = color;
    ctx.fillRect(r.x1, Math.max(0, r.y1 - 25), textW, 24);
    ctx.fillStyle = "#111";
    ctx.fillText(label, r.x1 + 5, Math.max(18, r.y1 - 7));
    if (i === selectedBox) drawHandles(r, color);
  });

  if (preview) {
    ctx.setLineDash([8, 5]);
    ctx.lineWidth = 2;
    ctx.strokeStyle = colors[selectedClass];
    ctx.strokeRect(preview.x1, preview.y1, preview.x2 - preview.x1, preview.y2 - preview.y1);
    ctx.setLineDash([]);
  }
}

function drawHandles(r, color) {
  ctx.fillStyle = "#fff";
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  for (const [x, y] of [[r.x1, r.y1], [r.x2, r.y1], [r.x1, r.y2], [r.x2, r.y2]]) {
    ctx.beginPath();
    ctx.rect(x - 5, y - 5, 10, 10);
    ctx.fill();
    ctx.stroke();
  }
}

async function loadList() {
  const res = await fetch("/api/images");
  const data = await res.json();
  classes = data.classes;
  images = data.images;
  filtered = images.slice();
  buildClassButtons();
  renderList();
  await loadImage(0);
}

async function loadImage(newIndex) {
  if (dirty) await saveLabels();
  index = Math.max(0, Math.min(filtered.length - 1, newIndex));
  const item = currentImage();
  if (!item) return;
  selectedBox = -1;
  const res = await fetch(`/api/labels?image=${encodeURIComponent(item.name)}`);
  const data = await res.json();
  boxes = data.boxes || [];
  img = new Image();
  img.onload = () => {
    canvas.width = img.naturalWidth;
    canvas.height = img.naturalHeight;
    setDirty(false);
    renderList();
    draw();
  };
  img.src = `/images/${encodeURIComponent(item.name)}?v=${Date.now()}`;
}

async function saveLabels() {
  const item = currentImage();
  if (!item) return;
  const clean = boxes
    .filter(b => b.w > 0.001 && b.h > 0.001)
    .map(b => ({
      cls: Number(b.cls),
      x: clamp01(b.x), y: clamp01(b.y),
      w: clamp01(b.w), h: clamp01(b.h),
    }));
  const res = await fetch("/api/labels", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({image: item.name, boxes: clean}),
  });
  if (!res.ok) {
    statusEl.textContent = "Kayit hatasi";
    return;
  }
  boxes = clean;
  item.count = boxes.length;
  setDirty(false);
  renderList();
}

function clamp01(v) { return Math.max(0, Math.min(1, Number(v))); }

function renderList() {
  listEl.innerHTML = "";
  filtered.forEach((item, i) => {
    const row = document.createElement("button");
    row.className = `row ${i === index ? "active" : ""} ${item.count ? "" : "empty"}`;
    row.innerHTML = `<span>${item.name}</span><span class="count">${item.count}</span>`;
    row.onclick = () => loadImage(i);
    listEl.appendChild(row);
  });
  updateStatus();
}

function applySearch() {
  const q = searchEl.value.trim().toLowerCase();
  const oldName = currentImage()?.name;
  filtered = q ? images.filter(i => i.name.toLowerCase().includes(q)) : images.slice();
  index = Math.max(0, filtered.findIndex(i => i.name === oldName));
  if (index < 0) index = 0;
  renderList();
}

canvas.addEventListener("mousedown", evt => {
  const p = pointer(evt);
  const hit = hitTest(p);
  start = p;
  if (hit) {
    selectedBox = hit.index;
    selectedClass = boxes[selectedBox].cls;
    updateClassButtons();
    originalBox = {...boxes[selectedBox]};
    mode = hit.handle;
  } else {
    selectedBox = -1;
    originalBox = null;
    mode = "draw";
  }
  draw();
});

canvas.addEventListener("mousemove", evt => {
  if (!mode || !start) return;
  const p = pointer(evt);
  if (mode === "draw") {
    draw({x1: start.x, y1: start.y, x2: p.x, y2: p.y});
    return;
  }
  if (selectedBox < 0 || !originalBox) return;
  let r = denorm(originalBox);
  if (mode === "move") {
    const dx = p.x - start.x;
    const dy = p.y - start.y;
    r.x1 += dx; r.x2 += dx; r.y1 += dy; r.y2 += dy;
  } else {
    if (mode.includes("n")) r.y1 = p.y;
    if (mode.includes("s")) r.y2 = p.y;
    if (mode.includes("w")) r.x1 = p.x;
    if (mode.includes("e")) r.x2 = p.x;
  }
  boxes[selectedBox] = norm(r, originalBox.cls);
  setDirty(true);
  draw();
});

window.addEventListener("mouseup", evt => {
  if (!mode || !start) return;
  const p = pointer(evt);
  if (mode === "draw") {
    const candidate = norm({x1: start.x, y1: start.y, x2: p.x, y2: p.y}, selectedClass);
    if (candidate.w * canvas.width > 5 && candidate.h * canvas.height > 5) {
      boxes.push(candidate);
      selectedBox = boxes.length - 1;
      setDirty(true);
    }
  }
  mode = null;
  start = null;
  originalBox = null;
  draw();
});

document.getElementById("prevBtn").onclick = () => loadImage(index - 1);
document.getElementById("nextBtn").onclick = () => loadImage(index + 1);
document.getElementById("saveBtn").onclick = () => saveLabels();
document.getElementById("deleteBtn").onclick = () => {
  if (selectedBox >= 0) {
    boxes.splice(selectedBox, 1);
    selectedBox = -1;
    setDirty(true);
    draw();
  }
};
searchEl.oninput = applySearch;

window.addEventListener("keydown", evt => {
  if (evt.target === searchEl) return;
  const key = evt.key.toLowerCase();
  if (["1", "2", "3", "4"].includes(key)) setClass(Number(key) - 1);
  if (key === "delete" || key === "backspace") document.getElementById("deleteBtn").click();
  if (key === "s") { evt.preventDefault(); saveLabels(); }
  if (key === "d") { evt.preventDefault(); loadImage(index + 1); }
  if (key === "a") { evt.preventDefault(); loadImage(index - 1); }
});

window.addEventListener("beforeunload", evt => {
  if (!dirty) return;
  evt.preventDefault();
  evt.returnValue = "";
});

loadList().catch(err => {
  statusEl.textContent = String(err);
});
</script>
</body>
</html>
"""


class EtiketSunucu(BaseHTTPRequestHandler):
    root: Path
    images_dir: Path
    labels_dir: Path
    classes: list[str]

    def log_message(self, fmt: str, *args) -> None:
        print("%s - %s" % (self.address_string(), fmt % args))

    def send_json(self, data: object, status: int = 200) -> None:
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def send_text(self, text: str, status: int = 200, content_type: str = "text/html") -> None:
        raw = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def safe_image(self, name: str) -> Path | None:
        name = Path(unquote(name)).name
        yol = self.images_dir / name
        if yol.is_file() and yol.suffix.lower() in GORSEL_UZANTI:
            return yol
        return None

    def image_names(self) -> list[str]:
        return sorted(p.name for p in self.images_dir.iterdir()
                      if p.is_file() and p.suffix.lower() in GORSEL_UZANTI)

    def label_path_for(self, image_name: str) -> Path:
        return self.labels_dir / f"{Path(image_name).stem}.txt"

    def read_boxes(self, image_name: str) -> list[dict[str, float | int]]:
        path = self.label_path_for(image_name)
        boxes: list[dict[str, float | int]] = []
        if not path.exists():
            return boxes
        for line in path.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) != 5:
                continue
            try:
                cls = int(parts[0])
                x, y, w, h = (float(v) for v in parts[1:])
            except ValueError:
                continue
            if 0 <= cls < len(self.classes):
                boxes.append({"cls": cls, "x": x, "y": y, "w": w, "h": h})
        return boxes

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.send_text(HTML)
            return
        if parsed.path == "/api/images":
            images = []
            for name in self.image_names():
                images.append({"name": name, "count": len(self.read_boxes(name))})
            self.send_json({"classes": self.classes, "images": images})
            return
        if parsed.path == "/api/labels":
            qs = parse_qs(parsed.query)
            name = qs.get("image", [""])[0]
            if not self.safe_image(name):
                self.send_json({"error": "gecersiz gorsel"}, 404)
                return
            self.send_json({"boxes": self.read_boxes(name)})
            return
        if parsed.path.startswith("/images/"):
            yol = self.safe_image(parsed.path.removeprefix("/images/"))
            if not yol:
                self.send_text("not found", 404, "text/plain")
                return
            raw = yol.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(yol.name)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        self.send_text("not found", 404, "text/plain")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/labels":
            self.send_json({"error": "not found"}, 404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception as exc:
            self.send_json({"error": f"json okunamadi: {exc}"}, 400)
            return

        image = data.get("image", "")
        if not self.safe_image(image):
            self.send_json({"error": "gecersiz gorsel"}, 404)
            return

        lines = []
        for box in data.get("boxes", []):
            try:
                cls = int(box["cls"])
                x = float(box["x"])
                y = float(box["y"])
                w = float(box["w"])
                h = float(box["h"])
            except (KeyError, TypeError, ValueError):
                self.send_json({"error": "bozuk kutu"}, 400)
                return
            if not (0 <= cls < len(self.classes) and 0 <= x <= 1 and 0 <= y <= 1 and
                    0 < w <= 1 and 0 < h <= 1):
                self.send_json({"error": "kutu aralik disinda"}, 400)
                return
            lines.append(f"{cls} {x:.6f} {y:.6f} {w:.6f} {h:.6f}")

        label_path = self.label_path_for(image)
        label_path.write_text(("\n".join(lines) + "\n") if lines else "", encoding="utf-8")
        self.send_json({"ok": True, "count": len(lines)})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="dataset")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()

    root = Path(args.dataset).resolve()
    images_dir = root / "images"
    labels_dir = root / "labels"
    if not images_dir.is_dir():
        raise SystemExit(f"Gorsel klasoru bulunamadi: {images_dir}")
    labels_dir.mkdir(parents=True, exist_ok=True)

    classes_path = root / "classes.txt"
    classes = SINIFLAR
    if classes_path.exists():
        okunan = [s.strip() for s in classes_path.read_text(encoding="utf-8").splitlines() if s.strip()]
        if okunan:
            classes = okunan

    handler = type("Gorev5EtiketSunucu", (EtiketSunucu,), {
        "root": root,
        "images_dir": images_dir,
        "labels_dir": labels_dir,
        "classes": classes,
    })
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Gorev 5 etiketleme araci: http://{args.host}:{args.port}")
    print("Kapatmak icin bu pencerede Ctrl+C.")
    server.serve_forever()


if __name__ == "__main__":
    main()
