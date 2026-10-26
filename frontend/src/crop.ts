export interface CropGeometry {
  sx: number;
  sy: number;
  sw: number;
  sh: number;
}

/**
 * 计算把原图按“覆盖圆形”方式裁剪到 size×size 时，源图上的裁剪区域。
 * zoom 越大，源图裁剪区域越小（放大）；offset 为预览里的像素偏移。
 */
export function cropGeometry(
  imageWidth: number,
  imageHeight: number,
  size: number,
  zoom: number,
  offset: { x: number; y: number },
): CropGeometry {
  const base = Math.max(size / imageWidth, size / imageHeight);
  const scale = base * Math.max(zoom, 0.1);
  const sw = size / scale;
  const sh = size / scale;
  const cx = imageWidth / 2 - offset.x / scale;
  const cy = imageHeight / 2 - offset.y / scale;
  const sx = clamp(cx - sw / 2, 0, Math.max(imageWidth - sw, 0));
  const sy = clamp(cy - sh / 2, 0, Math.max(imageHeight - sh, 0));
  return { sx, sy, sw, sh };
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}
