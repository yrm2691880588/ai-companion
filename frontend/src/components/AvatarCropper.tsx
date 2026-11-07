import { useCallback, useEffect, useRef, useState } from "react";
import Cropper from "react-easy-crop";
import type { Area } from "react-easy-crop";
import Modal from "./Modal";
import ErrorAlert from "./ErrorAlert";

interface Props {
  file: File | null;
  onCancel: () => void;
  onSave: (dataUrl: string) => void;
}

const OUTPUT_SIZE = 256;

/**
 * 头像裁剪：交互交给 react-easy-crop（自带边界约束、滚轮缩放、双指手势），
 * 弹窗行为交给 Modal（Radix Dialog），我这边只负责把裁剪区画到 canvas 导出 JPEG。
 */
export default function AvatarCropper({ file, onCancel, onSave }: Props) {
  // 换文件时用 key 重挂载，状态自然回到初值；不需要在 effect 里重置
  if (!file) return null;
  return <CropperDialog key={file.name + file.size} file={file} onCancel={onCancel} onSave={onSave} />;
}

function CropperDialog({ file, onCancel, onSave }: Props & { file: File }) {
  const [imageUrl] = useState(() => URL.createObjectURL(file));
  const [crop, setCrop] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const [areaPixels, setAreaPixels] = useState<Area | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const imageRef = useRef<HTMLImageElement | null>(null);

  // effect 只负责释放外部资源，不碰状态
  useEffect(() => () => URL.revokeObjectURL(imageUrl), [imageUrl]);

  const onCropComplete = useCallback((_croppedArea: Area, pixels: Area) => {
    setAreaPixels(pixels);
  }, []);

  async function save() {
    const image = imageRef.current;
    if (!image || !areaPixels) {
      setError("图片还没准备好，请稍等");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const canvas = document.createElement("canvas");
      canvas.width = OUTPUT_SIZE;
      canvas.height = OUTPUT_SIZE;
      const context = canvas.getContext("2d");
      if (!context) throw new Error("浏览器不支持画布");
      context.drawImage(
        image,
        areaPixels.x,
        areaPixels.y,
        areaPixels.width,
        areaPixels.height,
        0,
        0,
        OUTPUT_SIZE,
        OUTPUT_SIZE,
      );
      onSave(canvas.toDataURL("image/jpeg", 0.85));
    } catch (event) {
      setError((event as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open
      onClose={onCancel}
      title="调整头像"
      description="拖动图片调整位置；滚轮或下方滑杆缩放；圆形区域就是最终头像。"
      preventClose={busy}
      footer={
        <>
          <button className="primary" disabled={busy} onClick={() => void save()}>
            {busy ? "保存中…" : "保存头像"}
          </button>
          <button className="ghost" disabled={busy} onClick={onCancel}>
            取消
          </button>
          <button
            className="ghost"
            disabled={busy}
            onClick={() => {
              setZoom(1);
              setCrop({ x: 0, y: 0 });
            }}
          >
            重置
          </button>
        </>
      }
    >
      {error && <ErrorAlert message={error} variant="inline" />}

      <div className="avatar-crop-box">
        {imageUrl && (
          <Cropper
            image={imageUrl}
            crop={crop}
            zoom={zoom}
            aspect={1}
            cropShape="round"
            showGrid={false}
            minZoom={1}
            maxZoom={5}
            restrictPosition
            onCropChange={setCrop}
            onZoomChange={setZoom}
            onCropComplete={onCropComplete}
            objectFit="contain"
          />
        )}
        <img
          ref={imageRef}
          src={imageUrl}
          alt=""
          style={{ display: "none" }}
          onLoad={() => setError("")}
        />
      </div>

      <label className="muted" style={{ display: "block", marginTop: 10 }}>
        缩放 {zoom.toFixed(1)}×
      </label>
      <input
        type="range"
        min={1}
        max={5}
        step={0.05}
        value={zoom}
        onChange={(event) => setZoom(Number(event.target.value))}
      />
    </Modal>
  );
}
