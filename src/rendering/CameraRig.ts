/**
 * First-person camera: yaw/pitch from mouse, position follows the
 * player with optional head bob (motion-effects setting). All vector
 * work uses preallocated scratch objects.
 */

import * as THREE from 'three';

const PITCH_LIMIT = Math.PI / 2 - 0.05;
const LOOK_SCALE = 0.0022;

export class CameraRig {
  readonly camera: THREE.PerspectiveCamera;
  yaw = 0; // forward is -Z: spawn faces the plaza/tower
  pitch = 0;
  eyeHeight = 1.7;
  bobEnabled = true;

  private bobPhase = 0;
  private bobAmp = 0;
  private euler = new THREE.Euler(0, 0, 0, 'YXZ');

  constructor(fov: number, far: number) {
    this.camera = new THREE.PerspectiveCamera(fov, innerWidth / innerHeight, 0.1, far);
    window.addEventListener('resize', () => {
      this.camera.aspect = innerWidth / innerHeight;
      this.camera.updateProjectionMatrix();
    });
  }

  setFov(fov: number): void {
    this.camera.fov = fov;
    this.camera.updateProjectionMatrix();
  }

  setFar(far: number): void {
    this.camera.far = far;
    this.camera.updateProjectionMatrix();
  }

  applyLook(dx: number, dy: number): void {
    this.yaw -= dx * LOOK_SCALE;
    this.pitch -= dy * LOOK_SCALE;
    this.pitch = Math.max(-PITCH_LIMIT, Math.min(PITCH_LIMIT, this.pitch));
  }

  /** Advance head-bob from horizontal speed; call once per fixed step. */
  updateBob(speed: number, grounded: boolean, dt: number): void {
    if (this.bobEnabled && grounded && speed > 0.5) {
      this.bobPhase += dt * speed * 1.8;
      this.bobAmp = Math.min(1, this.bobAmp + dt * 6);
    } else {
      this.bobAmp = Math.max(0, this.bobAmp - dt * 6);
    }
  }

  /** Place the camera at the player position (call every render). */
  follow(x: number, y: number, z: number): void {
    const bob = Math.sin(this.bobPhase) * 0.045 * this.bobAmp;
    this.camera.position.set(x, y + this.eyeHeight + bob, z);
    this.euler.set(this.pitch, this.yaw, 0);
    this.camera.quaternion.setFromEuler(this.euler);
  }
}
