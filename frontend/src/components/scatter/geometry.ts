import type { QuadrantKey } from "../../types";
import { quadrantDomain } from "../../lib/quadrant";

export const VIEW = { w: 820, h: 600 };
export const PAD = { left: 52, right: 20, top: 20, bottom: 44 };
export const PLOT_W = VIEW.w - PAD.left - PAD.right;
export const PLOT_H = VIEW.h - PAD.top - PAD.bottom;

export const scaleX = (v: number) => PAD.left + (v / 100) * PLOT_W;
export const scaleY = (v: number) => PAD.top + (1 - v / 100) * PLOT_H;

export const dotRadius = (marketCap: number) => 2.6 + Math.sqrt(marketCap) * 0.22;

export type ZoomTransform = { scale: number; tx: number; ty: number };

export const IDENTITY: ZoomTransform = { scale: 1, tx: 0, ty: 0 };

export function zoomFor(key: QuadrantKey): ZoomTransform {
  const { x0, x1, y0, y1 } = quadrantDomain(key);
  const left = scaleX(x0);
  const right = scaleX(x1);
  const top = scaleY(y1);
  const bottom = scaleY(y0);
  const scale = Math.min(PLOT_W / (right - left), PLOT_H / (bottom - top));
  const qcx = (left + right) / 2;
  const qcy = (top + bottom) / 2;
  return {
    scale,
    tx: PAD.left + PLOT_W / 2 - scale * qcx,
    ty: PAD.top + PLOT_H / 2 - scale * qcy,
  };
}

export function quadrantScreenRect(key: QuadrantKey) {
  const { x0, x1, y0, y1 } = quadrantDomain(key);
  const left = scaleX(x0);
  const top = scaleY(y1);
  return {
    x: left,
    y: top,
    width: scaleX(x1) - left,
    height: scaleY(y0) - top,
  };
}
