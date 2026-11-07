import { useCallback, useEffect, useRef, useState } from "react";
import Cropper from "react-easy-crop";
import type { Area } from "react-easy-crop";
import { RotateCcw } from "lucide-react";
import Modal from "./Modal";
import ErrorAlert from "./ErrorAlert";

interface Props {
  file: File | null;
  onCancel: () => void;
  onSave: (dataUrl: string) => void;
}

const OUTPUT_SIZE = 256;

/**
 * 头像裁剪。
 *
 * 交互交给 react-easy-crop（自带边界约束、滚轮缩放、双指手势），
 * 弹窗行为交给 Modal（Radix Dialog），我这边只负责：
 * 1. 把裁剪区画到 canvas 导出 JPEG；
 * 2. 实时生成一张小预览图，让用户保存前就知道头像长什么样。
 *
 * 为什么加预览：原来只能在 256px 的裁剪框里猜最终效果，
 * 而头像真正显示时只有 46px，两者观感差别很大。
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
  const [preview, setPreview] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const imageRef = useRef<HTMLImageElement | null>(null);

  // effect 只负责释放外部资源，不碰状态
  useEffect(() => () => URL.revokeObjectURL(imageUrl), [imageUrl]);

  /**
   * 裁剪区变化时同时更新裁剪参数与预览。
   *
   * 预览不能放进 useMemo：那会在渲染期间读 imageRef.current，
   * React 明确禁止「渲染期访问 ref」。
   * 放在这个回调里最自然——它由 react-easy-crop 在拖动结束时触发，本来就是事件。
   *
   * 预览用小尺寸 + 低质量：只给观感，不需要和最终结果同质量，
   * 每次拖动都编码一张 256px 的图会明显卡顿。
   */
  const onCropComplete = useCallback((_croppedArea: Area, pixels: Area) => {
    setAreaPixels(pixels);
    const image = imageRef.current;
    if (!image) return;
    const canvas = document.createElement("canvas");
    canvas.width = 96;
    canvas.height = 96;
    const context = canvas.getContext("2d");
    if (!context) return;
    context.drawImage(image, pixels.x, pixels.y, pixels.width, pixels.height, 0, 0, 96, 96);
    setPreview(canvas.toDataURL("image/jpeg", 0.7));
  }, []);

  /** 把裁剪区画到指定尺寸的 canvas，返回 data URL。 */
  const renderCrop = useCallback(
    (size: number, quality: number): string | null => {
      const image = imageRef.current;
      if (!image || !areaPixels) return null;
      const canvas = document.createElement("canvas");
      canvas.width = size;
      canvas.height = size;
      const context = canvas.getContext("2d");
      if (!context) return null;
      context.drawImage(
        image,
        areaPixels.x,
        areaPixels.y,
        areaPixels.width,
        areaPixels.height,
        0,
        0,
        size,
        size,
      );
      return canvas.toDataURL("image/jpeg", quality);
    },
    [areaPixels],
  );

  async function save() {
    if (!areaPixels) {
      setError("图片还没准备好，请稍等");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const dataUrl = renderCrop(OUTPUT_SIZE, 0.85);
      if (!dataUrl) throw new Error("浏览器不支持画布");
      onSave(dataUrl);
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
      description="拖动图片调整位置，滚轮或滑杆缩放。右侧是你保存后看到的实际效果。"
      className="cropper-modal"
      preventClose={busy}
      footer={
        <>
          <button
            className="btn ghost"
            disabled={busy}
            onClick={() => {
              setZoom(1);
              setCrop({ x: 0, y: 0 });
            }}
          >
            <RotateCcw size={14} aria-hidden="true" />
            重置
          </button>
          <button className="btn ghost" disabled={busy} onClick={onCancel}>
            取消
          </button>
          <button className="btn primary" disabled={busy} onClick={() => void save()}>
            {busy ? "保存中…" : "保存头像"}
          </button>
        </>
      }
    >
      {error && <ErrorAlert message={error} variant="inline" />}

      <div className="cropper-body">
        {/* 左侧：大裁剪区。背景用深色，让图片本身成为主角，
            原来的浅灰方块看起来像「图片没铺满」 */}
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

        {/* 右侧：实时预览，按头像的真实显示尺寸给出观感 */}
        <div className="cropper-preview">
          <span className="cropper-preview-label">实际效果</span>
          <div className="cropper-preview-avatar">
            {preview ? <img src={preview} alt="头像预览" /> : <span>…</span>}
          </div>
          <span className="cropper-preview-hint">她在这里显示</span>
        </div>
      </div>

      {/* 缩放滑杆：原生 range 样式与全站不搭，这里用 CSS 重绘 */}
      <div className="cropper-zoom">
        <span className="cropper-zoom-label">缩放</span>
        <input
          type="range"
          min={1}
          max={5}
          step={0.05}
          value={zoom}
          aria-label="缩放比例"
          onChange={(event) => setZoom(Number(event.target.value))}
        />
        <span className="cropper-zoom-value">{zoom.toFixed(1)}×</span>
      </div>
    </Modal>
  );
}
