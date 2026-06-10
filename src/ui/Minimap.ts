/**
 * Top-down minimap drawn from the ACTUAL WorldData: building
 * footprints, lake rect, tower, pedestals. The static layer renders
 * once to an offscreen canvas; per frame we blit it and draw the
 * player arrow from the live position/yaw. No allocation per frame.
 */

import { WORLD, type WorldData } from '../world/WorldGeneration';

const SIZE = 190;

export class Minimap {
  private canvas: HTMLCanvasElement;
  private ctx: CanvasRenderingContext2D | null;
  private staticLayer: HTMLCanvasElement;
  private readonly scale: number;

  constructor(parent: HTMLElement, world: WorldData) {
    this.scale = SIZE / (WORLD.half * 2);

    this.canvas = document.createElement('canvas');
    this.canvas.id = 'minimap';
    this.canvas.width = SIZE;
    this.canvas.height = SIZE;
    parent.appendChild(this.canvas);
    this.ctx = this.canvas.getContext('2d');

    this.staticLayer = document.createElement('canvas');
    this.staticLayer.width = SIZE;
    this.staticLayer.height = SIZE;
    this.renderStatic(world);
  }

  private toPx(v: number): number {
    return (v + WORLD.half) * this.scale;
  }

  private renderStatic(world: WorldData): void {
    const g = this.staticLayer.getContext('2d');
    if (!g) return;
    // Wilderness base.
    g.fillStyle = '#0d1a12';
    g.fillRect(0, 0, SIZE, SIZE);
    // City square.
    g.fillStyle = '#15161f';
    const c0 = this.toPx(-WORLD.cityHalf);
    const cw = WORLD.cityHalf * 2 * this.scale;
    g.fillRect(c0, c0, cw, cw);
    // Lake.
    const L = WORLD.lake;
    g.fillStyle = '#123347';
    g.fillRect(
      this.toPx(L.minX),
      this.toPx(L.minZ),
      (L.maxX - L.minX) * this.scale,
      (L.maxZ - L.minZ) * this.scale,
    );
    // Buildings: real footprints.
    g.fillStyle = '#3c4258';
    for (const b of world.buildings) {
      g.fillRect(
        this.toPx(b.x - b.w / 2),
        this.toPx(b.z - b.d / 2),
        Math.max(1, b.w * this.scale),
        Math.max(1, b.d * this.scale),
      );
    }
    // Tower.
    g.fillStyle = '#ff4d6d';
    const t = world.tower;
    g.fillRect(this.toPx(t.x - t.w / 2), this.toPx(t.z - t.d / 2), t.w * this.scale + 1, t.d * this.scale + 1);
    // Pedestals.
    for (const p of world.pedestals) {
      g.fillStyle = `hsl(${Math.round(p.hue * 360)}, 90%, 60%)`;
      g.beginPath();
      g.arc(this.toPx(p.x), this.toPx(p.z), 2.2, 0, Math.PI * 2);
      g.fill();
    }
    // Border.
    g.strokeStyle = '#3a3f55';
    g.strokeRect(0.5, 0.5, SIZE - 1, SIZE - 1);
  }

  /** Per-frame: blit static layer + live player marker. */
  update(playerX: number, playerZ: number, yaw: number): void {
    const g = this.ctx;
    if (!g) return;
    g.clearRect(0, 0, SIZE, SIZE);
    g.drawImage(this.staticLayer, 0, 0);
    const px = this.toPx(playerX);
    const pz = this.toPx(playerZ);
    g.save();
    g.translate(px, pz);
    g.rotate(-yaw); // world yaw -> map rotation (map +y is +z/south)
    g.fillStyle = '#7df9ff';
    g.beginPath();
    g.moveTo(0, -5);
    g.lineTo(3.4, 4);
    g.lineTo(-3.4, 4);
    g.closePath();
    g.fill();
    g.restore();
  }
}
