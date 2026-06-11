/**
 * CPU-side mirror of the black-hole lensing fragment shader's math.
 * Pure, no Three.js, zero allocations (callers own the out objects).
 *
 * HONESTY NOTE (mirrored on the in-mode placard): this is a visual
 * physics sketch, NOT a geodesic integrator. Real light follows null
 * geodesics of the Schwarzschild metric; here each raymarch step bends
 * the ray direction toward the mass with a Newtonian-style
 * inverse-square pull:
 *
 *     d' = normalize(d - k * M * (p / |p|^3) * ds)
 *
 * which reproduces the look (lensed arcs, shadow, photon ring) but not
 * the exact deflection angles. The GLSL in ShaderSource.ts is generated
 * from the SAME constants exported here, so the unit tests on these
 * functions genuinely constrain the shader.
 */

/** Shared lensing constants. Injected verbatim into the GLSL template. */
export const LENSING = {
  /** Schwarzschild radius per unit mass (visual scale): rs = RS_PER_MASS * M */
  RS_PER_MASS: 1.0,
  /** per-step deflection constant k in d' = normalize(d - k*M*(p/|p|^3)*ds) */
  DEFLECT_K: 2.6,
  /** photon sphere radius, in units of rs (Schwarzschild: 1.5 rs) */
  PHOTON_SPHERE: 1.5,
  /** accretion disk inner edge, in units of rs (near the ISCO at 3 rs) */
  DISK_INNER: 2.6,
  /** accretion disk outer edge, in units of rs */
  DISK_OUTER: 7.8,
  /** Shakura-Sunyaev-ish temperature falloff: T = (rIn/r)^TEMP_EXPONENT */
  TEMP_EXPONENT: 0.75,
  /** rays beyond this many rs, moving outward, count as escaped */
  ESCAPE_RADIUS: 42.0,
  /** doppler-ish brightness asymmetry strength (0 = symmetric disk) */
  DOPPLER_STRENGTH: 0.65,
  /** gaussian width of the photon-ring glow, in units of rs */
  PHOTON_GLOW_WIDTH: 0.35,
} as const;

export interface Vec3 {
  x: number;
  y: number;
  z: number;
}

/** rs = RS_PER_MASS * mass (the capture/shadow radius). */
export function schwarzschildRadius(mass: number): number {
  return LENSING.RS_PER_MASS * mass;
}

/**
 * One raymarch deflection step: bend `dir` toward the mass at the
 * origin by an inverse-square pull, renormalize, write into `out`.
 * Mirrors the GLSL line:
 *   dir = normalize(dir - DEFLECT_K * uMass * pos / (r*r*r) * ds);
 */
export function deflectStep(pos: Vec3, dir: Vec3, mass: number, ds: number, out: Vec3): void {
  const r = Math.sqrt(pos.x * pos.x + pos.y * pos.y + pos.z * pos.z);
  const r3 = Math.max(1e-9, r * r * r);
  const k = (LENSING.DEFLECT_K * mass * ds) / r3;
  let nx = dir.x - k * pos.x;
  let ny = dir.y - k * pos.y;
  let nz = dir.z - k * pos.z;
  const len = Math.max(1e-12, Math.sqrt(nx * nx + ny * ny + nz * nz));
  nx /= len;
  ny /= len;
  nz /= len;
  out.x = nx;
  out.y = ny;
  out.z = nz;
}

/**
 * Disk temperature in (0, 1]: T = (rIn / max(r, rIn))^TEMP_EXPONENT.
 * Monotonically non-increasing in r; 1 at/inside the inner edge.
 */
export function diskTemperature(r: number, rs: number): number {
  const rIn = LENSING.DISK_INNER * rs;
  return Math.pow(rIn / Math.max(r, rIn), LENSING.TEMP_EXPONENT);
}

/**
 * Temperature -> emission color ramp (artistic, not blackbody): cool
 * outer disk is a deep ember orange, hot inner edge is blue-white.
 * Every channel is monotonically non-decreasing in t, and blue rises
 * faster than red so hotter genuinely reads bluer.
 */
export function tempToColor(t: number, out: Vec3): void {
  const c = Math.min(1, Math.max(0, t));
  out.x = Math.min(1, 0.55 + 0.45 * c);
  out.y = Math.min(1, 0.18 + 0.72 * Math.pow(c, 1.4));
  out.z = Math.min(1, 0.04 + 1.05 * Math.pow(c, 2.2));
}

/** smoothstep, mirrored so the TS and GLSL annulus edges agree. */
export function smoothstep(edge0: number, edge1: number, x: number): number {
  const t = Math.min(1, Math.max(0, (x - edge0) / (edge1 - edge0)));
  return t * t * (3 - 2 * t);
}

/**
 * Accretion-disk sample weight at cylindrical radius `r`, height `y`:
 * smooth annulus [DISK_INNER*rs, DISK_OUTER*rs] times a vertical
 * gaussian of half-thickness `halfThick` (world units). 0 outside.
 */
export function diskWeight(r: number, y: number, rs: number, halfThick: number): number {
  const rIn = LENSING.DISK_INNER * rs;
  const rOut = LENSING.DISK_OUTER * rs;
  const radial = smoothstep(rIn, rIn * 1.18, r) * (1 - smoothstep(rOut * 0.8, rOut, r));
  const h = Math.max(1e-4, halfThick);
  const vert = Math.exp(-(y * y) / (2 * h * h));
  return radial * vert;
}

/**
 * Doppler-ish brightness boost. `approach` is the cosine between the
 * disk's local orbital direction and the direction TOWARD the camera
 * along the (bent) ray. Linear in `approach` (real relativistic
 * beaming is not), clamped positive. 1 when moving across the view.
 */
export function dopplerBoost(approach: number): number {
  return Math.min(2.5, Math.max(0.05, 1 + LENSING.DOPPLER_STRENGTH * approach));
}

/**
 * Photon-ring brightening: a gaussian in the ray's closest approach
 * `minR`, peaked at the photon sphere (1.5 rs).
 */
export function photonRingGlow(minR: number, rs: number): number {
  const d = (minR - LENSING.PHOTON_SPHERE * rs) / (LENSING.PHOTON_GLOW_WIDTH * rs);
  return Math.exp(-d * d);
}
