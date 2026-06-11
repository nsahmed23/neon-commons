/**
 * Enemy drone state machines + the course-end boss. Pure (no Three.js,
 * no DOM, no Math.random at runtime): every decision derives from
 * positions, hp, sim time and dt, so a scripted run is reproducible
 * bit for bit. Each step mutates caller-owned state and writes its
 * outputs (fired flag, phase transitions) onto that state; nothing is
 * allocated per tick.
 *
 * Escort drones: patrol (orbit an anchor) -> engage (pursue to a
 * standoff ring and fire) -> evade (flee + weave once hp is low).
 * Boss: shielded orbit (invulnerable while any escort add lives, spread
 * volleys) -> vulnerable (holds the arena center, aimed fire) ->
 * enraged below 40% hp (fast strafing orbit, double fire rate).
 */

export const ENEMY = {
  maxHp: 30,
  radius: 1.9,
  /** player within this range flips patrol -> engage */
  engageRange: 70,
  /** player beyond this range flips engage -> patrol (hysteresis) */
  loseRange: 100,
  fireRange: 58,
  /** engage keeps this distance from the player (orbit-at-range) */
  standoff: 26,
  speedPatrol: 8,
  speedEngage: 17,
  speedEvade: 22,
  fireInterval: 1.15,
  /** hp fraction at which engage -> evade */
  evadeHpFrac: 0.34,
  patrolRadius: 17,
  patrolAngular: 0.45,
  weaveAmp: 9,
} as const;

export const BOSS = {
  maxHp: 220,
  radius: 4.2,
  /** hp fraction at which vulnerable -> enraged */
  enrageHpFrac: 0.4,
  orbitRadius: 26,
  orbitAngularShielded: 0.55,
  orbitAngularEnraged: 1.15,
  speed: 14,
  fireIntervalShielded: 2.1,
  fireIntervalVulnerable: 0.95,
  fireIntervalEnraged: 0.45,
  /** shielded phase fires a fan of this many bolts */
  spreadCount: 3,
  spreadAngle: 0.22,
} as const;

export type EnemyAIState = 'patrol' | 'engage' | 'evade';

export interface EnemyDrone {
  id: number;
  x: number;
  y: number;
  z: number;
  hp: number;
  alive: boolean;
  state: EnemyAIState;
  /** patrol anchor */
  ax: number;
  ay: number;
  az: number;
  /** deterministic per-drone phase (weave + patrol offset) */
  phase: number;
  fireCooldown: number;
  /** outputs of the last step */
  fired: boolean;
  /** set when the state changed THIS step (mode emits the event) */
  transitioned: EnemyAIState | null;
}

export function createEnemy(id: number, ax: number, ay: number, az: number): EnemyDrone {
  const phase = (id * 2.399963) % (Math.PI * 2); // golden-angle spacing
  return {
    id,
    x: ax + Math.sin(phase) * ENEMY.patrolRadius,
    y: ay,
    z: az + Math.cos(phase) * ENEMY.patrolRadius,
    hp: ENEMY.maxHp,
    alive: true,
    state: 'patrol',
    ax,
    ay,
    az,
    phase,
    fireCooldown: ENEMY.fireInterval,
    fired: false,
    transitioned: null,
  };
}

/** Apply damage; returns true when this hit killed the drone. */
export function damageEnemy(d: EnemyDrone, amount: number): boolean {
  if (!d.alive) return false;
  d.hp -= amount;
  if (d.hp <= 0) {
    d.hp = 0;
    d.alive = false;
    return true;
  }
  return false;
}

/** Move (x,y,z) of `d` toward a target point at `speed`, clamped by dt. */
function moveToward(d: EnemyDrone, tx: number, ty: number, tz: number, speed: number, dt: number): void {
  const dx = tx - d.x;
  const dy = ty - d.y;
  const dz = tz - d.z;
  const dist = Math.hypot(dx, dy, dz);
  if (dist < 1e-6) return;
  const step = Math.min(dist, speed * dt);
  d.x += (dx / dist) * step;
  d.y += (dy / dist) * step;
  d.z += (dz / dist) * step;
}

/**
 * Advance one fixed step of the escort state machine. Writes movement
 * onto d and raises d.fired when the drone shoots this step (the mode
 * spawns the actual projectile, aimed from d at the player).
 */
export function stepEnemy(
  d: EnemyDrone,
  px: number,
  py: number,
  pz: number,
  simTime: number,
  dt: number,
): void {
  d.fired = false;
  d.transitioned = null;
  if (!d.alive) return;

  const distToPlayer = Math.hypot(px - d.x, py - d.y, pz - d.z);

  // ---- transitions (real state, hysteresis on the range gates) ----
  if (d.state !== 'evade' && d.hp <= ENEMY.maxHp * ENEMY.evadeHpFrac) {
    d.state = 'evade';
    d.transitioned = 'evade';
  } else if (d.state === 'patrol' && distToPlayer <= ENEMY.engageRange) {
    d.state = 'engage';
    d.transitioned = 'engage';
  } else if (d.state === 'engage' && distToPlayer >= ENEMY.loseRange) {
    d.state = 'patrol';
    d.transitioned = 'patrol';
  }

  // ---- behavior --------------------------------------------------
  d.fireCooldown -= dt;

  if (d.state === 'patrol') {
    const a = d.phase + simTime * ENEMY.patrolAngular;
    moveToward(
      d,
      d.ax + Math.sin(a) * ENEMY.patrolRadius,
      d.ay + Math.sin(a * 0.7) * 2,
      d.az + Math.cos(a) * ENEMY.patrolRadius,
      ENEMY.speedPatrol,
      dt,
    );
    return;
  }

  if (d.state === 'engage') {
    // Hold a standoff ring around the player; slide sideways on it.
    const dx = d.x - px;
    const dy = d.y - py;
    const dz = d.z - pz;
    const dist = Math.max(1e-6, Math.hypot(dx, dy, dz));
    const slide = d.phase + simTime * 0.6;
    moveToward(
      d,
      px + (dx / dist) * ENEMY.standoff + Math.sin(slide) * 6,
      py + (dy / dist) * (ENEMY.standoff * 0.4) + 3,
      pz + (dz / dist) * ENEMY.standoff + Math.cos(slide) * 6,
      ENEMY.speedEngage,
      dt,
    );
    if (distToPlayer <= ENEMY.fireRange && d.fireCooldown <= 0) {
      d.fired = true;
      d.fireCooldown = ENEMY.fireInterval;
    }
    return;
  }

  // evade: flee straight away from the player, weaving, climbing.
  const dx = d.x - px;
  const dz = d.z - pz;
  const dist = Math.max(1e-6, Math.hypot(dx, dz));
  const weave = Math.sin(simTime * 3 + d.phase) * ENEMY.weaveAmp;
  // lateral (perpendicular) weave direction
  const lx = -dz / dist;
  const lz = dx / dist;
  moveToward(
    d,
    d.x + (dx / dist) * 20 + lx * weave,
    Math.min(110, d.y + 4),
    d.z + (dz / dist) * 20 + lz * weave,
    ENEMY.speedEvade,
    dt,
  );
}

// ---- Boss ----------------------------------------------------------------

export type BossPhase = 'shielded' | 'vulnerable' | 'enraged' | 'down';

export interface BossState {
  x: number;
  y: number;
  z: number;
  hp: number;
  phase: BossPhase;
  /** arena center the boss orbits/holds */
  cx: number;
  cy: number;
  cz: number;
  fireCooldown: number;
  /** outputs of the last step */
  fired: boolean;
  /** bolts to fire this step (1 aimed, or BOSS.spreadCount fan) */
  fireCount: number;
  transitioned: BossPhase | null;
}

export function createBoss(cx: number, cy: number, cz: number): BossState {
  return {
    x: cx + BOSS.orbitRadius,
    y: cy,
    z: cz,
    hp: BOSS.maxHp,
    phase: 'shielded',
    cx,
    cy,
    cz,
    fireCooldown: BOSS.fireIntervalShielded,
    fired: false,
    fireCount: 0,
    transitioned: null,
  };
}

/**
 * Damage the boss. Shield is REAL state: while any escort add lives the
 * boss is in 'shielded' phase and damage is rejected.
 */
export function damageBoss(b: BossState, amount: number): 'blocked' | 'hit' | 'killed' {
  if (b.phase === 'down') return 'blocked';
  if (b.phase === 'shielded') return 'blocked';
  b.hp -= amount;
  if (b.hp <= 0) {
    b.hp = 0;
    b.phase = 'down';
    return 'killed';
  }
  return 'hit';
}

/**
 * Advance one fixed step of the boss machine. `addsAlive` is the REAL
 * count of living escort adds (the mode counts them each step): the
 * shielded -> vulnerable transition derives from it, never a timer.
 */
export function stepBoss(
  b: BossState,
  addsAlive: number,
  px: number,
  py: number,
  pz: number,
  simTime: number,
  dt: number,
): void {
  b.fired = false;
  b.fireCount = 0;
  b.transitioned = null;
  if (b.phase === 'down') return;

  // ---- phase transitions from real state --------------------------
  if (b.phase === 'shielded' && addsAlive === 0) {
    b.phase = 'vulnerable';
    b.transitioned = 'vulnerable';
    b.fireCooldown = BOSS.fireIntervalVulnerable;
  }
  if (b.phase === 'vulnerable' && b.hp <= BOSS.maxHp * BOSS.enrageHpFrac) {
    b.phase = 'enraged';
    b.transitioned = 'enraged';
    b.fireCooldown = Math.min(b.fireCooldown, BOSS.fireIntervalEnraged);
  }

  // ---- movement ----------------------------------------------------
  if (b.phase === 'shielded' || b.phase === 'enraged') {
    const w = b.phase === 'shielded' ? BOSS.orbitAngularShielded : BOSS.orbitAngularEnraged;
    const a = simTime * w;
    const tx = b.cx + Math.sin(a) * BOSS.orbitRadius;
    const ty = b.cy + Math.sin(a * 0.6) * 5;
    const tz = b.cz + Math.cos(a) * BOSS.orbitRadius;
    const dx = tx - b.x;
    const dy = ty - b.y;
    const dz = tz - b.z;
    const dist = Math.hypot(dx, dy, dz);
    if (dist > 1e-6) {
      const step = Math.min(dist, BOSS.speed * dt * (b.phase === 'enraged' ? 1.6 : 1));
      b.x += (dx / dist) * step;
      b.y += (dy / dist) * step;
      b.z += (dz / dist) * step;
    }
  } else {
    // vulnerable: drift to the arena center and hold (the burst window).
    const dx = b.cx - b.x;
    const dy = b.cy - b.y;
    const dz = b.cz - b.z;
    const dist = Math.hypot(dx, dy, dz);
    if (dist > 0.5) {
      const step = Math.min(dist, BOSS.speed * 0.6 * dt);
      b.x += (dx / dist) * step;
      b.y += (dy / dist) * step;
      b.z += (dz / dist) * step;
    }
  }

  // ---- fire --------------------------------------------------------
  b.fireCooldown -= dt;
  if (b.fireCooldown > 0) return;
  const distToPlayer = Math.hypot(px - b.x, py - b.y, pz - b.z);
  if (distToPlayer > 130) return; // out of the fight entirely
  b.fired = true;
  if (b.phase === 'shielded') {
    b.fireCount = BOSS.spreadCount;
    b.fireCooldown = BOSS.fireIntervalShielded;
  } else if (b.phase === 'vulnerable') {
    b.fireCount = 1;
    b.fireCooldown = BOSS.fireIntervalVulnerable;
  } else {
    b.fireCount = BOSS.spreadCount;
    b.fireCooldown = BOSS.fireIntervalEnraged;
  }
}
