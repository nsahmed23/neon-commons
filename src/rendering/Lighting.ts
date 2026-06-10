/**
 * Hemisphere + directional (sun/moon) lighting with a real day/night
 * switch. Shadows come only from the directional light and only when
 * the quality profile enables them.
 */

import * as THREE from 'three';

export class Lighting {
  readonly hemi: THREE.HemisphereLight;
  readonly sun: THREE.DirectionalLight;
  /** normalized direction TOWARD the light, fed to custom shaders */
  readonly sunDir = new THREE.Vector3(0.45, 0.8, 0.3).normalize();

  constructor(scene: THREE.Scene) {
    this.hemi = new THREE.HemisphereLight(0x3a4470, 0x10121f, 0.7);
    scene.add(this.hemi);

    this.sun = new THREE.DirectionalLight(0x8899ff, 0.35);
    this.sun.position.copy(this.sunDir).multiplyScalar(220);
    this.sun.castShadow = false;
    this.sun.shadow.mapSize.set(2048, 2048);
    const cam = this.sun.shadow.camera;
    cam.left = -160;
    cam.right = 160;
    cam.top = 160;
    cam.bottom = -160;
    cam.far = 600;
    scene.add(this.sun);
    scene.add(this.sun.target);
  }

  setNight(night: boolean): void {
    if (night) {
      this.hemi.color.setHex(0x3a4470);
      this.hemi.groundColor.setHex(0x10121f);
      this.hemi.intensity = 0.7;
      this.sun.color.setHex(0x8899ff); // moon
      this.sun.intensity = 0.35;
    } else {
      this.hemi.color.setHex(0xbdd4f5);
      this.hemi.groundColor.setHex(0x6b7a5e);
      this.hemi.intensity = 1.0;
      this.sun.color.setHex(0xfff2dd);
      this.sun.intensity = 1.4;
    }
  }

  setShadows(enabled: boolean): void {
    this.sun.castShadow = enabled;
  }
}
