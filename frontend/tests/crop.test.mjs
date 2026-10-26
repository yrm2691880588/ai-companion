import assert from "node:assert/strict";
import { cropGeometry } from "../src/crop.ts";

// 1) 正方形原图，zoom=1，无偏移：裁满整张
{
  const g = cropGeometry(1000, 1000, 256, 1, { x: 0, y: 0 });
  assert.equal(Math.round(g.sw), 1000);
  assert.equal(Math.round(g.sh), 1000);
  assert.equal(Math.round(g.sx), 0);
  assert.equal(Math.round(g.sy), 0);
}

// 2) 横图 1600x900，zoom=1：按高度覆盖，裁中间正方形
{
  const g = cropGeometry(1600, 900, 256, 1, { x: 0, y: 0 });
  assert.equal(Math.round(g.sh), 900);
  assert.equal(Math.round(g.sw), 900);
  assert.equal(Math.round(g.sx), 350);
  assert.equal(Math.round(g.sy), 0);
}

// 3) zoom=2：裁剪区域减半
{
  const g = cropGeometry(1000, 1000, 256, 2, { x: 0, y: 0 });
  assert.equal(Math.round(g.sw), 500);
  assert.equal(Math.round(g.sh), 500);
  assert.equal(Math.round(g.sx), 250);
  assert.equal(Math.round(g.sy), 250);
}

// 4) 向右拖 100px（zoom=1, 1000px 图）：图片右移，裁剪窗口在源图上左移
{
  const g = cropGeometry(1000, 1000, 256, 1, { x: 100, y: 0 });
  assert.ok(g.sx < 0.001 || g.sx === 0, "向右拖动应让裁剪窗口左移并贴边");
}

// 5) 边界：拖到极限不会越界
{
  const g = cropGeometry(1000, 1000, 256, 1, { x: 9999, y: -9999 });
  assert.ok(g.sx >= 0 && g.sx + g.sw <= 1000 + 0.001);
  assert.ok(g.sy >= 0 && g.sy + g.sh <= 1000 + 0.001);
}

// 6) 小图放大：800x600，zoom=1，覆盖后裁中间
{
  const g = cropGeometry(800, 600, 256, 1, { x: 0, y: 0 });
  assert.equal(Math.round(g.sh), 600);
  assert.equal(Math.round(g.sw), 600);
  assert.equal(Math.round(g.sx), 100);
}

console.log("crop geometry: 6 checks passed");
