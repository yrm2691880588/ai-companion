import { useEffect, useRef, useState } from "react";
import { cropGeometry } from "../crop";

interface Props {
  file: File | null;
  onCancel: () => void;
  onSave: (dataUrl: string) => void;
}

const SIZE = 256;
const MIN_ZOOM = 1;
const MAX_ZOOM = 5;

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

export default function AvatarCropper({ file, onCancel, onSave }: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const imageRef = useRef<HTMLImageElement | null>(null);
  const [zoom, setZoom] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const dragRef = useRef<{ x: number; y: number } | null>(null);
  const [error, setError] = useState("");

  function maxOffset(nextZoom: number): { x: number; y: number } {
    const image = imageRef.current;
    if (!image) return { x: 0, y: 0 };
    const scale = Math.max(SIZE / image.width, SIZE / image.height) * nextZoom;
    return {
      x: Math.max(0, (image.width * scale - SIZE) / 2),
      y: Math.max(0, (image.height * scale - SIZE) / 2),
    };
  }

  function applyZoom(nextZoom: number) {
    const bounded = clamp(nextZoom, MIN_ZOOM, MAX_ZOOM);
    const limit = maxOffset(bounded);
    setOffset((prev) => ({
      x: clamp(prev.x, -limit.x, limit.x),
      y: clamp(prev.y, -limit.y, limit.y),
    }));
    setZoom(bounded);
  }

  useEffect(() => {
    if (!file) return;
    const url = URL.createObjectURL(file);
    const image = new Image();
    image.onload = () => {
      imageRef.current = image;
      setZoom(1);
      setOffset({ x: 0, y: 0 });
      draw();
    };
    image.onerror = () => setError("图片读取失败，请换一张");
    image.src = url;
    return () => URL.revokeObjectURL(url);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [file]);

  useEffect(() => {
    draw();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [zoom, offset]);

  // 鼠标滚轮缩放（必须非 passive 才能 preventDefault）
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const handler = (event: WheelEvent) => {
      event.preventDefault();
      setZoom((current) => {
        const next = clamp(
          current * (event.deltaY < 0 ? 1.1 : 0.9),
          MIN_ZOOM,
          MAX_ZOOM,
        );
        const limit = maxOffset(next);
        setOffset((prev) => ({
          x: clamp(prev.x, -limit.x, limit.x),
          y: clamp(prev.y, -limit.y, limit.y),
        }));
        return next;
      });
    };
    canvas.addEventListener("wheel", handler, { passive: false });
    return () => canvas.removeEventListener("wheel", handler);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [file]);

  function draw() {
    const canvas = canvasRef.current;
    const image = imageRef.current;
    if (!canvas || !image) return;
    const context = canvas.getContext("2d");
    if (!context) return;
    context.clearRect(0, 0, SIZE, SIZE);
    context.save();
    context.beginPath();
    context.arc(SIZE / 2, SIZE / 2, SIZE / 2, 0, Math.PI * 2);
    context.clip();
    const geometry = cropGeometry(image.width, image.height, SIZE, zoom, offset);
    context.drawImage(
      image,
      geometry.sx,
      geometry.sy,
      geometry.sw,
      geometry.sh,
      0,
      0,
      SIZE,
      SIZE,
    );
    context.restore();
  }

  function onPointerDown(event: React.PointerEvent<HTMLCanvasElement>) {
    dragRef.current = { x: event.clientX - offset.x, y: event.clientY - offset.y };
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function onPointerMove(event: React.PointerEvent<HTMLCanvasElement>) {
    if (!dragRef.current) return;
    const limit = maxOffset(zoom);
    setOffset({
      x: clamp(event.clientX - dragRef.current.x, -limit.x, limit.x),
      y: clamp(event.clientY - dragRef.current.y, -limit.y, limit.y),
    });
  }

  function onPointerUp() {
    dragRef.current = null;
  }

  function save() {
    const canvas = canvasRef.current;
    if (!canvas) return;
    onSave(canvas.toDataURL("image/jpeg", 0.85));
  }

  if (!file) return null;

  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <div className="modal" onClick={(event) => event.stopPropagation()}>
        <h2>调整头像</h2>
        <p className="muted">
          拖动图片调整位置；鼠标滚轮或下方滑杆缩放；圆形区域就是最终头像。
        </p>
        {error && <div className="alert">{error}</div>}
        <canvas
          ref={canvasRef}
          width={SIZE}
          height={SIZE}
          className="avatar-canvas"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
        />
        <label className="muted" style={{ display: "block", marginTop: 10 }}>
          缩放 {zoom.toFixed(1)}×
        </label>
        <input
          type="range"
          min={MIN_ZOOM}
          max={MAX_ZOOM}
          step={0.05}
          value={zoom}
          onChange={(event) => applyZoom(Number(event.target.value))}
        />
        <div className="toolbar">
          <button className="primary" onClick={save}>
            保存头像
          </button>
          <button className="ghost" onClick={onCancel}>
            取消
          </button>
          <button
            className="ghost"
            onClick={() => {
              setZoom(1);
              setOffset({ x: 0, y: 0 });
            }}
          >
            重置
          </button>
        </div>
      </div>
    </div>
  );
}
