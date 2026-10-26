import { useEffect, useRef, useState } from "react";
import { cropGeometry } from "../crop";

interface Props {
  file: File | null;
  onCancel: () => void;
  onSave: (dataUrl: string) => void;
}

const SIZE = 256;

export default function AvatarCropper({ file, onCancel, onSave }: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const imageRef = useRef<HTMLImageElement | null>(null);
  const [zoom, setZoom] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const dragRef = useRef<{ x: number; y: number } | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!file) return;
    const url = URL.createObjectURL(file);
    const image = new Image();
    image.onload = () => {
      imageRef.current = image;
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
    const limit = SIZE * 0.6;
    setOffset({
      x: Math.max(-limit, Math.min(limit, event.clientX - dragRef.current.x)),
      y: Math.max(-limit, Math.min(limit, event.clientY - dragRef.current.y)),
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
        <p className="muted">拖动图片调整位置，滑动缩放；圆形区域就是最终头像。</p>
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
          min={0.6}
          max={3}
          step={0.05}
          value={zoom}
          onChange={(event) => setZoom(Number(event.target.value))}
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
