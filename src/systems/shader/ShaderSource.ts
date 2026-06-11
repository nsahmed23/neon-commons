/**
 * GLSL source for the lensing showcase, generated as a template so the
 * physics constants come from ONE place (LENSING in LensingMath.ts).
 * The TS functions in LensingMath are line-for-line mirrors of the
 * GLSL helpers below; the unit tests pin the TS side AND assert that
 * every shared constant value is embedded in this source, so the tests
 * genuinely constrain the shader.
 */

import { LENSING } from './LensingMath';
import { PARAM_RANGES } from './ShaderParams';

/** Hard compile-time loop bound; uSteps breaks out earlier at runtime. */
export const MAX_RAY_STEPS = PARAM_RANGES.raySteps.max;

/** Format a number as a GLSL float literal (always with a decimal point). */
export function glslFloat(n: number): string {
  const s = String(n);
  return s.includes('.') || s.includes('e') ? s : `${s}.0`;
}

export const LENSING_VERTEX_SHADER = /* glsl */ `
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = vec4(position.xy, 0.0, 1.0);
}
`;

export function buildLensingFragmentShader(): string {
  return /* glsl */ `
precision highp float;

varying vec2 vUv;

uniform vec2 uResolution;
uniform float uTime;
uniform float uMass;
uniform float uDiskBrightness;
uniform float uDiskThickness;
uniform float uCamDist;
uniform float uCamYaw;
uniform float uCamPitch;
uniform int uSteps;

// ---- shared constants (injected from LENSING in LensingMath.ts) ----
const float RS_PER_MASS = ${glslFloat(LENSING.RS_PER_MASS)};
const float DEFLECT_K = ${glslFloat(LENSING.DEFLECT_K)};
const float PHOTON_SPHERE = ${glslFloat(LENSING.PHOTON_SPHERE)};
const float DISK_INNER = ${glslFloat(LENSING.DISK_INNER)};
const float DISK_OUTER = ${glslFloat(LENSING.DISK_OUTER)};
const float TEMP_EXPONENT = ${glslFloat(LENSING.TEMP_EXPONENT)};
const float ESCAPE_RADIUS = ${glslFloat(LENSING.ESCAPE_RADIUS)};
const float DOPPLER_STRENGTH = ${glslFloat(LENSING.DOPPLER_STRENGTH)};
const float PHOTON_GLOW_WIDTH = ${glslFloat(LENSING.PHOTON_GLOW_WIDTH)};
const int MAX_RAY_STEPS = ${MAX_RAY_STEPS};

// ---- procedural background (hash stars + faint value-noise nebula) ----
float hash13(vec3 p) {
  p = fract(p * 0.1031);
  p += dot(p, p.zyx + 31.32);
  return fract((p.x + p.y) * p.z);
}

float vnoise(vec3 p) {
  vec3 i = floor(p);
  vec3 f = fract(p);
  vec3 u = f * f * (3.0 - 2.0 * f);
  float a = hash13(i);
  float b = hash13(i + vec3(1.0, 0.0, 0.0));
  float c = hash13(i + vec3(0.0, 1.0, 0.0));
  float d = hash13(i + vec3(1.0, 1.0, 0.0));
  float e = hash13(i + vec3(0.0, 0.0, 1.0));
  float g = hash13(i + vec3(1.0, 0.0, 1.0));
  float h = hash13(i + vec3(0.0, 1.0, 1.0));
  float k = hash13(i + vec3(1.0, 1.0, 1.0));
  return mix(mix(mix(a, b, u.x), mix(c, d, u.x), u.y),
             mix(mix(e, g, u.x), mix(h, k, u.x), u.y), u.z);
}

vec3 background(vec3 d) {
  vec3 sd = normalize(d);
  // Stars: hash cells on the direction sphere, two density layers.
  vec3 col = vec3(0.0);
  for (int layer = 0; layer < 2; layer++) {
    float grid = layer == 0 ? 90.0 : 42.0;
    vec3 cell = floor(sd * grid);
    float h = hash13(cell);
    float thresh = layer == 0 ? 0.9982 : 0.9962;
    if (h > thresh) {
      vec3 centerDir = normalize(cell + 0.5);
      float prox = smoothstep(0.9999940 - float(layer) * 0.0000110, 1.0, dot(sd, centerDir));
      float tw = 0.72 + 0.28 * sin(uTime * (1.5 + h * 4.0) + h * 80.0);
      float bright = (layer == 0 ? 0.9 : 0.55) * tw;
      vec3 tint = mix(vec3(0.75, 0.85, 1.0), vec3(1.0, 0.9, 0.78), fract(h * 13.7));
      col += tint * prox * bright;
    }
  }
  // Faint nebula: layered value noise, teal/violet.
  float n = 0.62 * vnoise(sd * 2.7) + 0.27 * vnoise(sd * 6.1) + 0.11 * vnoise(sd * 13.0);
  n = max(0.0, n - 0.42) * 0.5;
  col += n * mix(vec3(0.10, 0.16, 0.34), vec3(0.30, 0.10, 0.36), vnoise(sd * 1.4));
  col += vec3(0.006, 0.008, 0.014);
  return col;
}

// ---- mirrors of LensingMath.ts (tested CPU-side) ----
float diskTemperature(float r, float rs) {
  float rIn = DISK_INNER * rs;
  return pow(rIn / max(r, rIn), TEMP_EXPONENT);
}

vec3 tempToColor(float t) {
  float c = clamp(t, 0.0, 1.0);
  return vec3(
    min(1.0, 0.55 + 0.45 * c),
    min(1.0, 0.18 + 0.72 * pow(c, 1.4)),
    min(1.0, 0.04 + 1.05 * pow(c, 2.2))
  );
}

float diskWeight(float r, float y, float rs, float halfThick) {
  float rIn = DISK_INNER * rs;
  float rOut = DISK_OUTER * rs;
  float radial = smoothstep(rIn, rIn * 1.18, r) * (1.0 - smoothstep(rOut * 0.8, rOut, r));
  float h = max(0.0001, halfThick);
  float vert = exp(-(y * y) / (2.0 * h * h));
  return radial * vert;
}

float dopplerBoost(float approach) {
  return clamp(1.0 + DOPPLER_STRENGTH * approach, 0.05, 2.5);
}

float photonRingGlow(float minR, float rs) {
  float d = (minR - PHOTON_SPHERE * rs) / (PHOTON_GLOW_WIDTH * rs);
  return exp(-d * d);
}

void main() {
  vec2 ndc = (vUv * 2.0 - 1.0) * vec2(uResolution.x / max(1.0, uResolution.y), 1.0);

  // Orbit camera around the hole at the origin.
  float cy = cos(uCamYaw);
  float sy = sin(uCamYaw);
  float cp = cos(uCamPitch);
  float sp = sin(uCamPitch);
  vec3 camPos = uCamDist * vec3(sy * cp, sp, cy * cp);
  vec3 fwd = normalize(-camPos);
  vec3 right = normalize(cross(fwd, vec3(0.0, 1.0, 0.0)));
  vec3 up = cross(right, fwd);
  vec3 dir = normalize(fwd * 1.55 + ndc.x * right + ndc.y * up);
  vec3 pos = camPos;

  float rs = RS_PER_MASS * uMass;
  // Step length: a fixed total path budget divided by the step count,
  // so the ray-steps slider trades accuracy (not reach).
  float pathLen = uCamDist * 2.0 + ESCAPE_RADIUS * rs;
  float ds = pathLen / float(uSteps);

  // Per-pixel ray-start jitter: dithers the step-quantization bands in
  // the disk into fine noise (static per pixel, so reduced motion stays
  // a calm frame).
  pos += dir * ds * hash13(vec3(gl_FragCoord.xy, 7.0));

  vec3 col = vec3(0.0);
  float minR = 1e9;
  float captured = 0.0;
  float escaped = 0.0;

  for (int i = 0; i < MAX_RAY_STEPS; i++) {
    if (i >= uSteps) break;
    float r = length(pos);
    minR = min(minR, r);
    if (r < rs) { captured = 1.0; break; }
    if (r > ESCAPE_RADIUS * rs && dot(pos, dir) > 0.0) { escaped = 1.0; break; }

    // Inverse-square deflection step (mirror of deflectStep in TS).
    dir = normalize(dir - DEFLECT_K * uMass * pos / (r * r * r) * ds);
    pos += dir * ds;

    // Accretion disk: thin equatorial annulus, accumulated as emission.
    float rc = length(pos.xz);
    float w = diskWeight(rc, pos.y, rs, uDiskThickness * rs);
    if (w > 0.0015) {
      float t = diskTemperature(rc, rs);
      // Orbital direction at this point (counter-clockwise seen from +Y).
      vec3 tangent = vec3(-pos.z, 0.0, pos.x) / max(1e-5, rc);
      // Approach factor: orbital motion toward the camera along the bent ray.
      float dop = dopplerBoost(dot(tangent, -dir));
      // Rotating spiral streaks driven by simulation time.
      float ang = atan(pos.z, pos.x);
      float swirl = 0.7 + 0.3 * sin(ang * 7.0 - uTime * 2.2 + rc / rs * 2.6);
      col += tempToColor(t) * (w * dop * swirl * uDiskBrightness * ds * 0.85 * (0.3 + 0.7 * t));
    }
  }

  // Background starfield only for rays that truly got away.
  if (captured < 0.5) {
    col += background(dir) * max(escaped, 0.65);
  }

  // Photon-ring brightening near the closest approach to 1.5 rs.
  // Escaped rays only: captured rays are the shadow and must stay
  // black (adding glow to them washed the shadow grey after gamma).
  col += vec3(1.0, 0.93, 0.80) * (photonRingGlow(minR, rs) * 0.85 * (1.0 - captured));

  // Tone map + gamma.
  col = col / (col + 1.0);
  col = pow(col, vec3(0.4545));
  gl_FragColor = vec4(col, 1.0);
}
`;
}
