/**
 * Jarvis Reactive Particle Orb — Master Engine + GIS Earth + Liquid Aura Charge Streams + Blurred Pedestal Lines
 * 
 * Features:
 * 1. High-Density AI Energy Core (26,400 Particles):
 *    - Strict 5:2:2:1 color ratio (Deep Blue, Electric Blue, Bright Blue, Cyan)
 *    - Uniform spherical surface coverage coating both continents and oceans with sparkling particles
 *    - Deep volumetric layering (dark transparent core, mid-field, dense surface contours)
 *    - Surface Radar: Localized 3D spherical ripple waves
 * 2. High-Precision GIS Holographic Earth Layer:
 *    - Natural Earth GeoJSON vector coastlines with 3-tier luminous cyan borders
 *    - Subtle dark blue continent landmass shading
 *    - Harmoniously integrated at R = 3.41
 * 3. 3 3D Orbital Liquid Aura Streams (Fluid Gradient Light & Glow Aura, -40% Wobble):
 *    - Exactly 3 tilted 3D orbital streams with continuous ethereal aura trails
 *    - Fluid gradient light flow, liquid blooming highlights, and 40% smoothed trajectory
 * 4. 3 Concentric Floor Pedestal Dashed Line Rings (Long Sleek Segments with Gaussian Blur & Opacity):
 *    - Exactly 3 concentric horizontal dashed LINE rings rotating below the sphere
 *    - Long, elegant, cybernetic dashed segments with soft Gaussian edge blur and high-tech opacity falloff
 * 5. Unified Coordinate Architecture:
 *    - Mathematical perspective point sizing (1:1 with Orb)
 *    - Dynamic auto-framing camera fits the full 6-ring composition on any window dimension
 */

(function () {
  'use strict';

  // ==========================================
  // 1. UNIFIED ORB CONFIGURATION & PALETTE
  // ==========================================
  const PALETTE = {
    deepBlue: new THREE.Color(0x063E95),     // 50% Deep blue base
    electricBlue: new THREE.Color(0x0B63DE), // 20% Electric blue
    brightBlue: new THREE.Color(0x2898E4),   // 20% Bright tech blue
    cyan: new THREE.Color(0x49D9F1),         // 10% Cyan highlight
    peakCyan: new THREE.Color(0x86DEF2)      // Rare peak energy
  };

  const ORB_CONFIG = {
    // Central Coordinate Space
    radius: 3.4,
    earthRadiusRatio: 1.004,       // R * 1.004 = 3.413 (harmoniously integrated with surface particles)
    totalParticles: 26400,         // High-density spherical coating
    maxSurfaceWaves: 6,
    
    // Normalized Point Sizing
    particleWorldSizeBase: 0.034,  // Balanced pinpoint particle diameter
    maxPointSizeClamp: 4.5,        // Upper clamp preventing giant whiteout clusters
    minPointSizeClamp: 1.0,        // Lower clamp preserving particle visibility
    
    // Camera & Framing (Frames Orb + 3 Liquid Aura Streams + 3 Floor Pedestal Rings)
    cameraFov: 45.0,
    defaultCameraZ: 9,          // User-set initial camera distance
    minZoomZ: 8.0,
    maxZoomZ: 20,
    
    // Physics & Bridge
    springK: 140.0,
    springDamping: 14.0,
    wsPort: 8765
  };

  // Crisp pinpoint circular dot texture with smooth Gaussian falloff
  function createCrispDotTexture() {
    const canvas = document.createElement('canvas');
    canvas.width = 64;
    canvas.height = 64;
    const ctx = canvas.getContext('2d');

    const grad = ctx.createRadialGradient(32, 32, 0, 32, 32, 32);
    grad.addColorStop(0.0, 'rgba(255, 255, 255, 1.0)');
    grad.addColorStop(0.20, 'rgba(73, 217, 241, 0.95)');
    grad.addColorStop(0.50, 'rgba(40, 152, 228, 0.65)');
    grad.addColorStop(0.75, 'rgba(11, 99, 222, 0.25)');
    grad.addColorStop(1.0, 'rgba(0, 0, 0, 0)');

    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(32, 32, 31, 0, Math.PI * 2);
    ctx.fill();

    const texture = new THREE.CanvasTexture(canvas);
    texture.generateMipmaps = false;
    texture.minFilter = THREE.LinearFilter;
    return texture;
  }

  // ==========================================
  // 2. HIGH-PRECISION GIS EARTH TEXTURE GENERATOR
  // ==========================================
  function createGISEarthTexture() {
    const width = 4096;
    const height = 2048;
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext('2d');

    // Pure transparent background
    ctx.clearRect(0, 0, width, height);

    // Exact Equirectangular Projection: [lon, lat] -> [x, y]
    const toXY = (lon, lat) => {
      const x = ((lon + 180.0) / 360.0) * width;
      const y = ((90.0 - lat) / 180.0) * height;
      return [x, y];
    };

    // A. Subtle Dotted Lat/Long Geographic Graticule Grid
    ctx.strokeStyle = 'rgba(11, 99, 222, 0.18)';
    ctx.lineWidth = 1.2;
    ctx.setLineDash([3, 8]);

    // Parallels (every 30 deg)
    for (let lat = -60; lat <= 60; lat += 30) {
      const [, y] = toXY(0, lat);
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
      ctx.stroke();
    }

    // Meridians (every 30 deg)
    for (let lon = -180; lon < 180; lon += 30) {
      const [x] = toXY(lon, 0);
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, height);
      ctx.stroke();
    }
    ctx.setLineDash([]); // Reset dash

    // B. Draw Official GeoJSON World Coastlines & Country Boundaries
    const geoData = window.WORLD_GEOJSON;

    const drawRing = (ring) => {
      if (!ring || ring.length === 0) return;
      const [startX, startY] = toXY(ring[0][0], ring[0][1]);
      ctx.moveTo(startX, startY);
      for (let i = 1; i < ring.length; i++) {
        const [x, y] = toXY(ring[i][0], ring[i][1]);
        ctx.lineTo(x, y);
      }
    };

    const drawAllFeatures = () => {
      if (!geoData || !geoData.features) return;
      ctx.beginPath();
      for (const feat of geoData.features) {
        const geom = feat.geometry;
        if (!geom) continue;
        if (geom.type === 'Polygon') {
          for (const ring of geom.coordinates) {
            drawRing(ring);
          }
        } else if (geom.type === 'MultiPolygon') {
          for (const poly of geom.coordinates) {
            for (const ring of poly) {
              drawRing(ring);
            }
          }
        }
      }
    };

    if (geoData) {
      // 1. Subtle Holographic Continent Land Tint
      ctx.fillStyle = 'rgba(6, 62, 149, 0.16)';
      drawAllFeatures();
      ctx.fill();

      // 2. Layer 1: Outer Soft Blue Glow Stroke
      ctx.strokeStyle = 'rgba(11, 99, 222, 0.55)';
      ctx.lineWidth = 4.5;
      drawAllFeatures();
      ctx.stroke();

      // 3. Layer 2: Main Crisp Technology Blue Line
      ctx.strokeStyle = 'rgba(40, 152, 228, 0.90)';
      ctx.lineWidth = 2.2;
      drawAllFeatures();
      ctx.stroke();

      // 4. Layer 3: Ultra-Sharp Luminous Cyan Coastline Core
      ctx.strokeStyle = 'rgba(73, 217, 241, 1.0)';
      ctx.lineWidth = 1.0;
      drawAllFeatures();
      ctx.stroke();
    }

    // C. Major Global Holographic Tech Nodes (Data Points)
    const techNodes = [
      [-74.006, 40.7128],   // New York
      [-122.4194, 37.7749], // San Francisco
      [-0.1278, 51.5074],   // London
      [2.3522, 48.8566],    // Paris
      [13.4050, 52.5200],   // Berlin
      [37.6173, 55.7558],   // Moscow
      [139.6917, 35.6895],  // Tokyo
      [116.4074, 39.9042],  // Beijing
      [103.8198, 1.3521],   // Singapore
      [151.2093, -33.8688], // Sydney
      [31.2357, 30.0444],   // Cairo
      [-46.6333, -23.5505], // Sao Paulo
      [77.2090, 28.6139],   // New Delhi
      [106.6601, 10.7626],  // Ho Chi Minh City
      [105.8342, 21.0278]   // Hanoi
    ];

    techNodes.forEach(([lon, lat]) => {
      const [x, y] = toXY(lon, lat);

      // Outer data pulse ring
      ctx.strokeStyle = 'rgba(73, 217, 241, 0.75)';
      ctx.lineWidth = 1.4;
      ctx.beginPath();
      ctx.arc(x, y, 6.5, 0, Math.PI * 2);
      ctx.stroke();

      // Solid central data node
      ctx.fillStyle = 'rgba(134, 222, 242, 0.95)';
      ctx.beginPath();
      ctx.arc(x, y, 2.2, 0, Math.PI * 2);
      ctx.fill();
    });

    const texture = new THREE.CanvasTexture(canvas);
    texture.generateMipmaps = false;
    texture.minFilter = THREE.LinearFilter;
    return texture;
  }

  // ==========================================
  // 3. SURFACE WAVE MANAGER (Surface Radar)
  // ==========================================
  class SurfaceWaveManager {
    constructor(maxWaves = 6) {
      this.maxWaves = maxWaves;
      this.waves = [];
      for (let i = 0; i < maxWaves; i++) {
        this.waves.push({
          active: false,
          center: new THREE.Vector3(0, 1, 0),
          progress: 0,
          speed: 0.8,
          maxRadius: 1.5,
          intensity: 1.0,
          noiseSeed: Math.random() * 100.0
        });
      }
      this.spawnTimer = 0;
      this.nextSpawnInterval = 0.5;
    }

    spawn(forcedIntensity = 1.0, forcedSpeed = null) {
      const freeWave = this.waves.find(w => !w.active);
      if (!freeWave) return;

      const phi = Math.acos(2 * Math.random() - 1);
      const theta = Math.random() * Math.PI * 2;
      freeWave.center.set(
        Math.sin(phi) * Math.cos(theta),
        Math.sin(phi) * Math.sin(theta),
        Math.cos(phi)
      ).normalize();

      freeWave.active = true;
      freeWave.progress = 0.0;
      freeWave.speed = forcedSpeed || (0.65 + Math.random() * 0.7);
      freeWave.maxRadius = 1.1 + Math.random() * 0.8;
      freeWave.intensity = forcedIntensity;
      freeWave.noiseSeed = Math.random() * 100.0;
    }

    update(dt, state, amplitude) {
      if (state === 'hidden' || state === 'closing') return;

      this.spawnTimer += dt;
      let interval = 0.65;
      if (state === 'listening') interval = 0.35 / (1.0 + amplitude * 1.5);
      else if (state === 'processing') interval = 0.20;
      else if (state === 'speaking') interval = 0.25 / (1.0 + amplitude * 2.0);
      else if (state === 'wake') interval = 0.15;

      if (this.spawnTimer > this.nextSpawnInterval) {
        this.spawnTimer = 0;
        this.nextSpawnInterval = interval * (0.6 + Math.random() * 0.8);
        this.spawn(state === 'speaking' ? 1.4 : 1.0);
      }

      for (const w of this.waves) {
        if (!w.active) continue;
        w.progress += dt * w.speed;
        if (w.progress >= 1.0) {
          w.active = false;
          w.progress = 0;
        }
      }
    }

    fillUniforms(waveCenters, waveData, waveParams) {
      for (let i = 0; i < this.maxWaves; i++) {
        const w = this.waves[i];
        if (w && w.active) {
          waveCenters[i].copy(w.center);
          waveData[i].set(w.progress, w.maxRadius, w.intensity, 1.0);
          waveParams[i].set(w.noiseSeed, 0, 0, 0);
        } else {
          waveData[i].set(0, 0, 0, 0.0);
        }
      }
    }
  }

  // ==========================================
  // 4. HYBRID AUDIO ENGINE
  // ==========================================
  class HybridAudioEngine {
    constructor() {
      this.amplitude = 0.05;
      this.targetAmplitude = 0.05;
      this.hasRealAudio = false;
      this.lastRealAudioTime = 0;
      this.speechTimer = 0;
      this.speechSyllable = 0;
    }

    setRealAmplitude(val) {
      this.targetAmplitude = Math.max(0.0, Math.min(1.0, val));
      this.hasRealAudio = true;
      this.lastRealAudioTime = performance.now();
    }

    update(dt, state) {
      const now = performance.now();
      const realAudioActive = this.hasRealAudio && (now - this.lastRealAudioTime < 250);

      if (!realAudioActive) {
        if (state === 'hidden' || state === 'closing') {
          this.targetAmplitude = 0.0;
        } else if (state === 'listening') {
          const time = now * 0.005;
          const micNoise = Math.sin(time * 3.8) * 0.08 + Math.cos(time * 7.5) * 0.05;
          this.targetAmplitude = 0.08 + Math.abs(micNoise);
        } else if (state === 'processing') {
          const time = now * 0.008;
          this.targetAmplitude = 0.28 + 0.14 * Math.sin(time * 6.5) * Math.cos(time * 3.2);
        } else if (state === 'speaking') {
          this.speechTimer += dt;
          if (this.speechTimer > 0.11) {
            this.speechTimer = 0;
            const r = Math.random();
            if (r < 0.2) this.speechSyllable = 0.12;
            else if (r < 0.72) this.speechSyllable = 0.45 + Math.random() * 0.35;
            else this.speechSyllable = 0.85 + Math.random() * 0.15;
          }
          this.targetAmplitude = this.speechSyllable;
        } else if (state === 'wake') {
          this.targetAmplitude = 0.95;
        }
      }

      const lerpSpeed = realAudioActive ? 22.0 : 14.0;
      this.amplitude += (this.targetAmplitude - this.amplitude) * Math.min(1.0, dt * lerpSpeed);
      return this.amplitude;
    }
  }

  // ==========================================
  // 5. SPRING PHYSICS (Damped Harmonic Oscillator)
  // ==========================================
  class SpringPhysics2D {
    constructor(k = 140.0, damping = 14.0) {
      this.k = k;
      this.damping = damping;
      this.pos = { x: 0, y: 0 };
      this.vel = { x: 0, y: 0 };
      this.target = { x: 0, y: 0 };
      this.isDragging = false;
      this.dragOffset = { x: 0, y: 0 };
      this.dragVelocity = { x: 0, y: 0 };
      this.lastPos = { x: 0, y: 0 };
    }

    startDrag(pointerX, pointerY) {
      this.isDragging = true;
      this.dragOffset.x = this.pos.x - pointerX;
      this.dragOffset.y = this.pos.y - pointerY;
      this.vel.x = 0;
      this.vel.y = 0;
    }

    updateDrag(pointerX, pointerY) {
      if (!this.isDragging) return;
      const rawX = pointerX + this.dragOffset.x;
      const rawY = pointerY + this.dragOffset.y;
      const dist = Math.sqrt(rawX * rawX + rawY * rawY);
      const maxDist = 4.2;
      const dampedDist = maxDist * Math.tanh(dist / maxDist);
      const factor = dist > 0.001 ? dampedDist / dist : 1.0;
      this.target.x = rawX * factor;
      this.target.y = rawY * factor;
    }

    endDrag() {
      this.isDragging = false;
      this.target.x = 0;
      this.target.y = 0;
    }

    step(dt) {
      const clampedDt = Math.min(dt, 0.033);
      if (this.isDragging) {
        this.pos.x += (this.target.x - this.pos.x) * Math.min(1.0, clampedDt * 24.0);
        this.pos.y += (this.target.y - this.pos.y) * Math.min(1.0, clampedDt * 24.0);
        this.vel.x = (this.pos.x - this.lastPos.x) / (clampedDt || 0.016);
        this.vel.y = (this.pos.y - this.lastPos.y) / (clampedDt || 0.016);
      } else {
        const fx = -this.k * (this.pos.x - this.target.x) - this.damping * this.vel.x;
        const fy = -this.k * (this.pos.y - this.target.y) - this.damping * this.vel.y;
        this.vel.x += fx * clampedDt;
        this.vel.y += fy * clampedDt;
        this.pos.x += this.vel.x * clampedDt;
        this.pos.y += this.vel.y * clampedDt;
        this.dragVelocity.x = this.vel.x;
        this.dragVelocity.y = this.vel.y;
      }
      this.lastPos.x = this.pos.x;
      this.lastPos.y = this.pos.y;
    }
  }

  // ==========================================
  // 6. MAIN JARVIS ORB CONTROLLER
  // ==========================================
  class JarvisOrbApp {
    constructor() {
      this.state = 'hidden';
      this.stateEnum = { hidden: 0, listening: 1, processing: 2, speaking: 3, wake: 4, closing: 5 };
      this.displayScale = 0.0;
      this.targetScale = 0.0;
      this.wakePhase = 0;

      // 3D Orbit Interaction
      this.isInteracting = false;
      this.previousPointerPos = { x: 0, y: 0 };
      this.rotationVelocity = { x: 0, y: 0.0022 };

      this.dotTexture = createCrispDotTexture();
      this.earthTexture = createGISEarthTexture();
      this.waveManager = new SurfaceWaveManager(ORB_CONFIG.maxSurfaceWaves);

      // Uniform buffers for surface waves
      this.waveCenters = [];
      this.waveData = [];
      this.waveParams = [];
      for (let i = 0; i < ORB_CONFIG.maxSurfaceWaves; i++) {
        this.waveCenters.push(new THREE.Vector3(0, 1, 0));
        this.waveData.push(new THREE.Vector4(0, 0, 0, 0));
        this.waveParams.push(new THREE.Vector4(0, 0, 0, 0));
      }

      this.initThree();
      this.initComponents();
      this.initInteractions();
      this.initKeyboardControls();
      this.initWebSocket();
      this.animate = this.animate.bind(this);

      this.clock = new THREE.Clock();
      requestAnimationFrame(this.animate);
    }

    // Mathematical projection scale: converts world-space diameter to physical screen pixels
    getProjectionScale() {
      const halfFovRad = THREE.MathUtils.degToRad(ORB_CONFIG.cameraFov / 2.0);
      return (this.height / 2.0) / Math.tan(halfFovRad);
    }

    initThree() {
      this.container = document.getElementById('canvas-container');
      this.width = window.innerWidth || 480;
      this.height = window.innerHeight || 480;

      this.scene = new THREE.Scene();
      this.camera = new THREE.PerspectiveCamera(ORB_CONFIG.cameraFov, this.width / this.height, 0.1, 1000);
      
      this.updateCameraPlacement();

      this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: 'high-performance' });
      this.renderer.setSize(this.width, this.height);
      this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1.0, 2.0));
      // Pure deep black clear color ensures 100% faithful additive blending contrast
      this.renderer.setClearColor(0x000000, 1.0);
      this.container.appendChild(this.renderer.domElement);

      this.rootGroup = new THREE.Group();
      this.scene.add(this.rootGroup);

      this.orbGroup = new THREE.Group();
      this.rootGroup.add(this.orbGroup);

      // Start hidden with zero scale
      this.rootGroup.scale.set(0.001, 0.001, 0.001);

      window.addEventListener('resize', () => this.onWindowResize());
    }

    updateCameraPlacement() {
      const aspect = this.width / this.height;
      this.camera.aspect = aspect;

      // Dynamic framing: preserves comfortable margin for globe, 3 orbital streams, and 3 floor pedestal rings
      if (aspect < 1.0) {
        this.camera.position.set(0, 0, ORB_CONFIG.defaultCameraZ / aspect);
      } else {
        this.camera.position.set(0, 0, ORB_CONFIG.defaultCameraZ);
      }
      this.camera.updateProjectionMatrix();
    }

    initComponents() {
      this.physics = new SpringPhysics2D(ORB_CONFIG.springK, ORB_CONFIG.springDamping);
      this.audio = new HybridAudioEngine();

      // 1. Primary AI Energy Core (26,400 Particles with 5:2:2:1 Strict Palette)
      this.initUnifiedParticleSystem();

      // 2. Secondary GIS Holographic Earth Layer (Accurate Vector GIS Projection)
      this.initGISEarthLayer();

      // 3. Exactly 3 3D Orbital Liquid Aura Streams (Fluid Gradient Light & Glow Aura, -40% Wobble)
      this.initOrbitalSatelliteRings();

      // 4. Subtle Magnetic Aura Wind (Long, thin particle streams)
      this.initMagneticAura();

      // 5. Exactly 3 Concentric Floor Pedestal Dashed Line Rings (Gaussian Blur & High-Tech Opacity)
      this.initPedestalRings();
    }

    // 1. Primary Unified 3D Particle System (26,400 Particles — Even Spherical Coverage)
    initUnifiedParticleSystem() {
      const count = ORB_CONFIG.totalParticles;
      const positions = new Float32Array(count * 3);
      const baseNormals = new Float32Array(count * 3);
      const colors = new Float32Array(count * 3);
      const sizes = new Float32Array(count);
      const phases = new Float32Array(count);
      const layers = new Float32Array(count);

      const R = ORB_CONFIG.radius;

      // STRICT 5:2:2:1 GLOBAL COLOR RATIO
      const countDeep = Math.floor(count * 0.50);
      const countElectric = Math.floor(count * 0.20);
      const countBright = Math.floor(count * 0.20);
      const countCyan = count - (countDeep + countElectric + countBright);

      const colorPool = [];
      for (let i = 0; i < countDeep; i++) colorPool.push(PALETTE.deepBlue);
      for (let i = 0; i < countElectric; i++) colorPool.push(PALETTE.electricBlue);
      for (let i = 0; i < countBright; i++) colorPool.push(PALETTE.brightBlue);
      for (let i = 0; i < countCyan; i++) colorPool.push(PALETTE.cyan);

      // REFINED SIZE RATIO: 85% Fine (1.0-1.4), 12% Medium (1.6-2.0), 3% Highlight (2.2-2.6)
      const sizePool = [];
      const countFine = Math.floor(count * 0.85);
      const countMedium = Math.floor(count * 0.12);
      const countHighlight = count - (countFine + countMedium);

      for (let i = 0; i < countFine; i++) sizePool.push(1.0 + Math.random() * 0.4);
      for (let i = 0; i < countMedium; i++) sizePool.push(1.6 + Math.random() * 0.4);
      for (let i = 0; i < countHighlight; i++) sizePool.push(2.2 + Math.random() * 0.4);

      const countCore = Math.floor(count * 0.10);
      const countMid = Math.floor(count * 0.20);
      const countSurface = count - (countCore + countMid);

      let idx = 0;

      // A. Deep Core Particles (Mostly #063E95)
      for (let i = 0; i < countCore; i++) {
        const u = Math.random();
        const r = R * 0.65 * Math.cbrt(u);
        const phi = Math.acos(2 * Math.random() - 1);
        const theta = Math.random() * Math.PI * 2;

        const nx = Math.sin(phi) * Math.cos(theta);
        const ny = Math.sin(phi) * Math.sin(theta);
        const nz = Math.cos(phi);

        positions[idx * 3] = r * nx;
        positions[idx * 3 + 1] = r * ny;
        positions[idx * 3 + 2] = r * nz;

        baseNormals[idx * 3] = nx;
        baseNormals[idx * 3 + 1] = ny;
        baseNormals[idx * 3 + 2] = nz;

        const col = PALETTE.deepBlue;
        colors[idx * 3] = col.r;
        colors[idx * 3 + 1] = col.g;
        colors[idx * 3 + 2] = col.b;

        sizes[idx] = sizePool[idx] || 1.0;
        phases[idx] = Math.random() * Math.PI * 2;
        layers[idx] = 0.0;
        idx++;
      }

      // B. Mid-Field Particles (#063E95 + #0B63DE)
      for (let i = 0; i < countMid; i++) {
        const r = R * (0.65 + 0.30 * Math.random());
        const phi = Math.acos(2 * Math.random() - 1);
        const theta = Math.random() * Math.PI * 2;

        const nx = Math.sin(phi) * Math.cos(theta);
        const ny = Math.sin(phi) * Math.sin(theta);
        const nz = Math.cos(phi);

        positions[idx * 3] = r * nx;
        positions[idx * 3 + 1] = r * ny;
        positions[idx * 3 + 2] = r * nz;

        baseNormals[idx * 3] = nx;
        baseNormals[idx * 3 + 1] = ny;
        baseNormals[idx * 3 + 2] = nz;

        const col = (i % 2 === 0) ? PALETTE.deepBlue : PALETTE.electricBlue;
        colors[idx * 3] = col.r;
        colors[idx * 3 + 1] = col.g;
        colors[idx * 3 + 2] = col.b;

        sizes[idx] = sizePool[idx] || 1.1;
        phases[idx] = Math.random() * Math.PI * 2;
        layers[idx] = 1.0;
        idx++;
      }

      // C. Surface & Border Shell Particles (Uniform Spherical Sampling for Full Coverage)
      let colorPoolIdx = countCore + countMid;
      for (let i = 0; i < countSurface; i++) {
        // Uniform spherical coordinates (prevents clustering at poles or blank spots in oceans)
        const phi = Math.acos(2 * Math.random() - 1);
        const theta = Math.random() * Math.PI * 2;

        const nx = Math.sin(phi) * Math.cos(theta);
        const ny = Math.sin(phi) * Math.sin(theta);
        const nz = Math.cos(phi);

        const contourNoise = Math.sin(nx * 3.6 + ny * 2.8) * Math.cos(ny * 3.2 + nz * 2.6);
        const onContour = Math.abs(contourNoise) < 0.28;

        const r = R + (Math.random() - 0.5) * (onContour ? 0.08 : 0.12);

        positions[idx * 3] = r * nx;
        positions[idx * 3 + 1] = r * ny;
        positions[idx * 3 + 2] = r * nz;

        baseNormals[idx * 3] = nx;
        baseNormals[idx * 3 + 1] = ny;
        baseNormals[idx * 3 + 2] = nz;

        let col = colorPool[colorPoolIdx % colorPool.length];
        if (onContour && Math.random() < 0.35) {
          col = PALETTE.cyan;
        }
        colorPoolIdx++;

        colors[idx * 3] = col.r;
        colors[idx * 3 + 1] = col.g;
        colors[idx * 3 + 2] = col.b;

        sizes[idx] = sizePool[idx] || (onContour ? 1.6 : 1.1);
        phases[idx] = Math.random() * Math.PI * 2;
        layers[idx] = onContour ? 3.0 : 2.0;
        idx++;
      }

      const geom = new THREE.BufferGeometry();
      geom.setAttribute('position', new THREE.BufferAttribute(positions, 3));
      geom.setAttribute('aNormal', new THREE.BufferAttribute(baseNormals, 3));
      geom.setAttribute('aColor', new THREE.BufferAttribute(colors, 3));
      geom.setAttribute('aSize', new THREE.BufferAttribute(sizes, 1));
      geom.setAttribute('aPhase', new THREE.BufferAttribute(phases, 1));
      geom.setAttribute('aLayer', new THREE.BufferAttribute(layers, 1));

      this.particleMaterial = new THREE.ShaderMaterial({
        vertexShader: `
          uniform float uTime;
          uniform float uRadius;
          uniform float uState;
          uniform float uAmplitude;
          uniform float uProjectionScale;
          uniform vec3 uWaveCenters[6];
          uniform vec4 uWaveData[6];
          uniform vec4 uWaveParams[6];

          attribute vec3 aNormal;
          attribute vec3 aColor;
          attribute float aSize;
          attribute float aPhase;
          attribute float aLayer;

          varying vec3 vColor;
          varying float vAlpha;
          varying float vLayer;

          vec3 mod289(vec3 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
          vec4 mod289(vec4 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
          vec4 permute(vec4 x) { return mod289(((x*34.0)+1.0)*x); }
          vec4 taylorInvSqrt(vec4 r) { return 1.79284291400159 - 0.85373472095314 * r; }

          float snoise(vec3 v) {
            const vec2 C = vec2(1.0/6.0, 1.0/3.0);
            const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);
            vec3 i  = floor(v + dot(v, C.yyy));
            vec3 x0 = v - i + dot(i, C.xxx);
            vec3 g = step(x0.yzx, x0.xyz);
            vec3 l = 1.0 - g;
            vec3 i1 = min(g.xyz, l.zxy);
            vec3 i2 = max(g.xyz, l.zxy);
            vec3 x1 = x0 - i1 + C.xxx;
            vec3 x2 = x0 - i2 + C.yyy;
            vec3 x3 = x0 - D.yyy;
            i = mod289(i);
            vec4 p = permute(permute(permute(
                      i.z + vec4(0.0, i1.z, i2.z, 1.0))
                    + i.y + vec4(0.0, i1.y, i2.y, 1.0))
                    + i.x + vec4(0.0, i1.x, i2.x, 1.0));
            float n_ = 0.142857142857;
            vec3 ns = n_ * D.wyz - D.xzx;
            vec4 j = p - 49.0 * floor(p * ns.z * ns.z);
            vec4 x_ = floor(j * ns.z);
            vec4 y_ = floor(j - 7.0 * x_);
            vec4 x = x_ *ns.x + ns.yyyy;
            vec4 y = y_ *ns.x + ns.yyyy;
            vec4 h = 1.0 - abs(x) - abs(y);
            vec4 b0 = vec4(x.xy, y.xy);
            vec4 b1 = vec4(x.zw, y.zw);
            vec4 s0 = floor(b0)*2.0 + 1.0;
            vec4 s1 = floor(b1)*2.0 + 1.0;
            vec4 sh = -step(h, vec4(0.0));
            vec4 a0 = b0.xzyw + s0.xzyw*sh.xxyy;
            vec4 a1 = b1.xzyw + s1.xzyw*sh.zzww;
            vec3 p0 = vec3(a0.xy, h.x);
            vec3 p1 = vec3(a0.zw, h.y);
            vec3 p2 = vec3(a1.xy, h.z);
            vec3 p3 = vec3(a1.zw, h.w);
            vec4 norm = taylorInvSqrt(vec4(dot(p0,p0), dot(p1,p1), dot(p2, p2), dot(p3,p3)));
            p0 *= norm.x; p1 *= norm.y; p2 *= norm.z; p3 *= norm.w;
            vec4 m = max(0.6 - vec4(dot(x0,x0), dot(x1,x1), dot(x2,x2), dot(x3,x3)), 0.0);
            m = m * m;
            return 42.0 * dot(m*m, vec4(dot(p0,x0), dot(p1,x1), dot(p2,x2), dot(p3,x3)));
          }

          void main() {
            vLayer = aLayer;
            vec3 norm = normalize(aNormal);
            vec3 pos = position;

            float slowNoise = snoise(norm * 1.6 + vec3(uTime * 0.2, 0.0, 0.0)) * 0.03;
            float breath = sin(uTime * 1.5 + aPhase) * 0.012;

            float audioDisplace = 0.0;
            if (uState == 1.0) {
              audioDisplace = sin(length(pos) * 5.0 - uTime * 6.0) * uAmplitude * 0.16;
            } else if (uState == 3.0) {
              float voiceTurbulence = snoise(norm * 3.0 + vec3(0.0, uTime * 4.0, 0.0));
              audioDisplace = (voiceTurbulence * 0.28 + sin(uTime * 8.0 + aPhase) * 0.12) * uAmplitude;
            } else if (uState == 4.0) {
              audioDisplace = sin(uTime * 10.0 + aPhase) * 0.22;
            } else if (uState == 5.0) {
              audioDisplace = -0.15 * (1.0 - aLayer * 0.3);
            }

            // Surface Waves
            float totalWaveDisp = 0.0;
            float totalWaveBoost = 0.0;

            if (aLayer >= 1.5) {
              for (int i = 0; i < 6; i++) {
                if (uWaveData[i].w > 0.5) {
                  vec3 waveCenter = normalize(uWaveCenters[i]);
                  float waveProgress = uWaveData[i].x;
                  float maxRadius = uWaveData[i].y;
                  float intensity = uWaveData[i].z;
                  float noiseSeed = uWaveParams[i].x;

                  float cosAngle = clamp(dot(norm, waveCenter), -1.0, 1.0);
                  float angle = acos(cosAngle);

                  float waveNoise = snoise(norm * 4.0 + vec3(noiseSeed, 0.0, 0.0)) * 0.14;
                  float currentWaveRadius = (waveProgress * maxRadius) + waveNoise;

                  float distToFront = abs(angle - currentWaveRadius);
                  float waveThickness = 0.20 * (1.0 + waveProgress * 0.5);

                  if (distToFront < waveThickness) {
                    float waveFactor = smoothstep(waveThickness, 0.0, distToFront);
                    float lifeFade = (1.0 - waveProgress) * smoothstep(0.0, 0.12, waveProgress);
                    float impulse = waveFactor * lifeFade * intensity;

                    totalWaveDisp += impulse * 0.16;
                    totalWaveBoost += impulse * 1.4;
                  }
                }
              }
            }

            vec3 displaced = pos + norm * (slowNoise + breath + audioDisplace + totalWaveDisp);

            vec4 mvPos = modelViewMatrix * vec4(displaced, 1.0);
            vec3 viewNorm = normalize((modelViewMatrix * vec4(norm, 0.0)).xyz);
            vec3 viewDir = normalize(-mvPos.xyz);
            
            float fresnel = 1.0 - abs(dot(viewNorm, viewDir));
            fresnel = pow(fresnel, 1.6);

            float distFromCam = -mvPos.z;
            float depthFactor = clamp((mvPos.z + 18.0) / 9.0, 0.35, 1.0);

            vec3 baseCol = aColor;

            if (totalWaveBoost > 0.01) {
              baseCol = mix(baseCol, vec3(0.286, 0.851, 0.945), clamp(totalWaveBoost * 0.8, 0.0, 1.0));
            }

            if (uState == 3.0 && uAmplitude > 0.35) {
              baseCol = mix(baseCol, vec3(0.286, 0.851, 0.945), uAmplitude * 0.35);
            }

            if (uState == 4.0) {
              baseCol = mix(baseCol, vec3(0.525, 0.871, 0.949), 0.5);
            }

            vColor = baseCol;

            // Vibrant, rich particle surface alpha covering the entire sphere
            float baseAlpha = (aLayer < 0.5) ? 0.12 : ((aLayer < 1.5) ? 0.32 : 0.75);
            float alpha = (baseAlpha * (0.40 + 0.60 * fresnel) + totalWaveBoost * 0.35) * depthFactor;
            vAlpha = clamp(alpha, 0.0, 0.90);

            // Normalized point sizing: scales 1:1 with Orb
            float worldSize = aSize * 0.034 * (1.0 + fresnel * 0.25 + totalWaveBoost * 0.35) * depthFactor;
            float projectedSize = worldSize * (uProjectionScale / distFromCam);
            gl_PointSize = clamp(projectedSize, 1.0, 4.5);
            gl_Position = projectionMatrix * mvPos;
          }
        `,
        fragmentShader: `
          uniform sampler2D uTexture;
          varying vec3 vColor;
          varying float vAlpha;
          varying float vLayer;

          void main() {
            vec2 coord = gl_PointCoord - vec2(0.5);
            float r = length(coord);
            if (r > 0.5) discard;

            float softEdge = smoothstep(0.5, 0.06, r);
            float coreHotspot = smoothstep(0.18, 0.0, r);

            // Luminous sparkling core
            vec3 finalColor = vColor + vec3(coreHotspot * 0.22);
            float finalAlpha = vAlpha * softEdge;

            gl_FragColor = vec4(finalColor, finalAlpha);
          }
        `,
        uniforms: {
          uTime: { value: 0 },
          uRadius: { value: R },
          uState: { value: 0 },
          uAmplitude: { value: 0 },
          uProjectionScale: { value: this.getProjectionScale() },
          uWaveCenters: { value: this.waveCenters },
          uWaveData: { value: this.waveData },
          uWaveParams: { value: this.waveParams },
          uTexture: { value: this.dotTexture }
        },
        transparent: true,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });

      this.particleMesh = new THREE.Points(geom, this.particleMaterial);
      this.orbGroup.add(this.particleMesh);
    }

    // 2. Secondary GIS Holographic Earth Layer (Accurate Vector GIS Projection)
    initGISEarthLayer() {
      // Placed right on the particle shell (R * 1.004) for harmonious integration
      const R = ORB_CONFIG.radius * ORB_CONFIG.earthRadiusRatio;
      const geom = new THREE.SphereGeometry(R, 96, 96);

      this.earthMaterial = new THREE.ShaderMaterial({
        vertexShader: `
          uniform float uTime;
          uniform float uState;
          uniform float uAmplitude;
          uniform vec3 uWaveCenters[6];
          uniform vec4 uWaveData[6];
          uniform vec4 uWaveParams[6];

          varying vec2 vUv;
          varying vec3 vNormal;
          varying vec3 vViewPosition;

          void main() {
            vUv = uv;
            vec3 norm = normalize(normal);
            vec3 pos = position;

            float breath = sin(uTime * 1.5) * 0.01;
            float audioDisp = 0.0;
            if (uState == 1.0) {
              audioDisp = sin(length(pos) * 5.0 - uTime * 6.0) * uAmplitude * 0.12;
            } else if (uState == 3.0) {
              audioDisp = sin(uTime * 8.0) * uAmplitude * 0.18;
            }

            float waveDisp = 0.0;
            for (int i = 0; i < 6; i++) {
              if (uWaveData[i].w > 0.5) {
                vec3 waveCenter = normalize(uWaveCenters[i]);
                float waveProgress = uWaveData[i].x;
                float maxRadius = uWaveData[i].y;
                float cosAngle = clamp(dot(norm, waveCenter), -1.0, 1.0);
                float angle = acos(cosAngle);
                float distToFront = abs(angle - (waveProgress * maxRadius));
                if (distToFront < 0.20) {
                  float factor = smoothstep(0.20, 0.0, distToFront);
                  waveDisp += factor * (1.0 - waveProgress) * 0.12 * uWaveData[i].z;
                }
              }
            }

            vec3 displaced = pos + norm * (breath + audioDisp + waveDisp);
            vec4 mvPos = modelViewMatrix * vec4(displaced, 1.0);
            vNormal = normalize((modelViewMatrix * vec4(norm, 0.0)).xyz);
            vViewPosition = -mvPos.xyz;
            gl_Position = projectionMatrix * mvPos;
          }
        `,
        fragmentShader: `
          uniform sampler2D uEarthTexture;
          uniform float uTime;
          uniform float uState;
          uniform float uAmplitude;

          varying vec2 vUv;
          varying vec3 vNormal;
          varying vec3 vViewPosition;

          void main() {
            vec4 tex = texture2D(uEarthTexture, vUv);
            if (tex.a < 0.012) discard;

            vec3 viewDir = normalize(vViewPosition);
            float fresnel = 1.0 - abs(dot(vNormal, viewDir));
            fresnel = pow(fresnel, 1.3);

            // Rich neon cyan / electric blue contrast
            vec3 lineCol = tex.rgb * 1.5;
            lineCol = mix(lineCol, vec3(0.286, 0.851, 0.945), fresnel * 0.55);

            if (uState == 3.0 && uAmplitude > 0.3) {
              lineCol = mix(lineCol, vec3(0.525, 0.871, 0.949), uAmplitude * 0.35);
            }

            float alpha = tex.a * (0.80 + 0.30 * fresnel);
            gl_FragColor = vec4(lineCol, clamp(alpha, 0.0, 1.0));
          }
        `,
        uniforms: {
          uEarthTexture: { value: this.earthTexture },
          uTime: { value: 0 },
          uState: { value: 0 },
          uAmplitude: { value: 0 },
          uWaveCenters: { value: this.waveCenters },
          uWaveData: { value: this.waveData },
          uWaveParams: { value: this.waveParams }
        },
        transparent: true,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        side: THREE.DoubleSide
      });

      this.earthMesh = new THREE.Mesh(geom, this.earthMaterial);
      // Align initial view to show Africa / Europe / Asia / Americas
      this.earthMesh.rotation.y = -Math.PI * 0.45;
      this.orbGroup.add(this.earthMesh);
    }

    // 3. Exactly 3 3D Orbital Liquid Aura Streams (Fluid Gradient Light & Glow Aura, -40% Wobble)
    initOrbitalSatelliteRings() {
      this.orbitGroup = new THREE.Group();
      this.orbGroup.add(this.orbitGroup);

      const R = ORB_CONFIG.radius;
      // Exactly 3 Orbital Rings
      const orbitalConfigs = [
        { radiusX: R * 1.40, radiusY: R * 1.25, rotX: 0.78, rotY: 0.30, rotZ: 0.15, count: 280, speed: 0.42, color: 0x49D9F1 },
        { radiusX: R * 1.62, radiusY: R * 1.38, rotX: -0.58, rotY: -0.72, rotZ: 0.38, count: 300, speed: -0.35, color: 0x2898E4 },
        { radiusX: R * 1.82, radiusY: R * 1.52, rotX: 0.24, rotY: 1.02, rotZ: -0.42, count: 320, speed: 0.28, color: 0x0B63DE }
      ];

      this.orbitRings = [];

      orbitalConfigs.forEach((cfg) => {
        const ringObj = new THREE.Group();
        ringObj.rotation.set(cfg.rotX, cfg.rotY, cfg.rotZ);

        // A. Subtle Liquid Aura Trail Spline
        const curvePoints = [];
        const splineSegments = 96;
        for (let i = 0; i <= splineSegments; i++) {
          const theta = (i / splineSegments) * Math.PI * 2;
          curvePoints.push(new THREE.Vector3(cfg.radiusX * Math.cos(theta), 0, cfg.radiusY * Math.sin(theta)));
        }
        const trailGeom = new THREE.BufferGeometry().setFromPoints(curvePoints);
        const trailMat = new THREE.LineBasicMaterial({
          color: cfg.color,
          transparent: true,
          opacity: 0.20,
          blending: THREE.AdditiveBlending
        });
        const trailMesh = new THREE.Line(trailGeom, trailMat);
        ringObj.add(trailMesh);

        // B. Liquid Aura Particles with Fluid Gradient Light
        const satCount = cfg.count;
        const satPositions = new Float32Array(satCount * 3);
        const satAngles = new Float32Array(satCount);
        const satSizes = new Float32Array(satCount);

        for (let i = 0; i < satCount; i++) {
          satPositions[i * 3] = 0;
          satPositions[i * 3 + 1] = 0;
          satPositions[i * 3 + 2] = 0;
          satAngles[i] = (i / satCount) * Math.PI * 2;
          satSizes[i] = (i % 6 === 0) ? 2.0 : ((i % 2 === 0) ? 1.4 : 1.0);
        }

        const satGeom = new THREE.BufferGeometry();
        satGeom.setAttribute('position', new THREE.BufferAttribute(satPositions, 3));
        satGeom.setAttribute('aAngle', new THREE.BufferAttribute(satAngles, 1));
        satGeom.setAttribute('aSize', new THREE.BufferAttribute(satSizes, 1));

        const satMat = new THREE.ShaderMaterial({
          vertexShader: `
            uniform float uTime;
            uniform float uRadiusX;
            uniform float uRadiusY;
            uniform float uSpeed;
            uniform float uProjectionScale;
            attribute float aAngle;
            attribute float aSize;
            varying vec3 vColor;
            varying float vAlpha;

            void main() {
              float curAngle = aAngle + uTime * uSpeed;
              // 40% Reduced Wobble for smooth, elegant liquid flow
              float wobble = sin(curAngle * 3.0 + uTime * 2.0) * 0.06;
              vec3 pos = vec3(uRadiusX * cos(curAngle), wobble, uRadiusY * sin(curAngle));

              vec4 mvPos = modelViewMatrix * vec4(pos, 1.0);
              float distFromCam = -mvPos.z;

              // Fluid Gradient Wave flowing along the liquid stream
              float wave1 = sin(curAngle * 4.0 - uTime * 3.5);
              float wave2 = sin(curAngle * 2.0 + uTime * 1.8);
              float fluidFlow = pow(0.5 + 0.5 * wave1, 2.0) * 0.65 + (0.5 + 0.5 * wave2) * 0.35;

              float worldSize = (aSize * 0.042) * (1.0 + fluidFlow * 0.55);
              gl_PointSize = clamp(worldSize * (uProjectionScale / distFromCam), 2.0, 7.0);
              gl_Position = projectionMatrix * mvPos;

              vAlpha = clamp(0.35 + fluidFlow * 0.60, 0.0, 1.0);

              // Liquid Aura Color Gradient (Deep Blue -> Tech Blue -> Radiant Cyan Core)
              vec3 baseCol = (uSpeed > 0.0) ? vec3(0.157, 0.596, 0.894) : vec3(0.043, 0.450, 0.920);
              vec3 liquidCol = mix(baseCol, vec3(0.286, 0.851, 0.945), fluidFlow);
              if (fluidFlow > 0.55) {
                liquidCol = mix(liquidCol, vec3(0.70, 0.95, 1.0), (fluidFlow - 0.55) * 1.6);
              }
              vColor = liquidCol;
            }
          `,
          fragmentShader: `
            uniform sampler2D uTexture;
            varying vec3 vColor;
            varying float vAlpha;
            void main() {
              vec4 tex = texture2D(uTexture, gl_PointCoord);
              gl_FragColor = vec4(vColor, vAlpha * tex.a);
            }
          `,
          uniforms: {
            uTime: { value: 0 },
            uRadiusX: { value: cfg.radiusX },
            uRadiusY: { value: cfg.radiusY },
            uSpeed: { value: cfg.speed },
            uProjectionScale: { value: this.getProjectionScale() },
            uTexture: { value: this.dotTexture }
          },
          transparent: true,
          blending: THREE.AdditiveBlending,
          depthWrite: false
        });

        const satMesh = new THREE.Points(satGeom, satMat);
        ringObj.add(satMesh);

        this.orbitGroup.add(ringObj);
        this.orbitRings.push({ group: ringObj, satMat: satMat });
      });
    }

    // 4. Subtle Magnetic Aura Wind
    initMagneticAura() {
      this.auraGroup = new THREE.Group();
      this.orbGroup.add(this.auraGroup);

      const streamCount = 14;
      const R = ORB_CONFIG.radius;

      for (let s = 0; s < streamCount; s++) {
        const points = [];
        const segmentCount = 50;
        const baseAngle = (s / streamCount) * Math.PI * 2;
        const tilt = Math.sin(s * 1.8) * 0.7;

        for (let p = 0; p <= segmentCount; p++) {
          const t = p / segmentCount;
          const angle = baseAngle + t * 2.2 * (s % 2 === 0 ? 1 : -1);
          const r = R * (1.02 + Math.pow(t, 1.5) * 0.7);
          const z = Math.sin(t * Math.PI) * (1.4 * Math.cos(s)) + (t - 0.5) * tilt * 1.8;

          points.push(new THREE.Vector3(r * Math.cos(angle), r * Math.sin(angle), z));
        }

        const curve = new THREE.CatmullRomCurve3(points);
        const tubeGeom = new THREE.BufferGeometry().setFromPoints(curve.getPoints(40));

        const lineMat = new THREE.LineBasicMaterial({
          color: (s % 2 === 0) ? 0x2898E4 : 0x0B63DE,
          transparent: true,
          opacity: 0.12 + Math.random() * 0.08,
          blending: THREE.AdditiveBlending
        });

        const line = new THREE.Line(tubeGeom, lineMat);
        this.auraGroup.add(line);
      }

      const auraParticleCount = 400;
      const auraPositions = new Float32Array(auraParticleCount * 3);
      const auraProgress = new Float32Array(auraParticleCount);
      const auraStreamIds = new Float32Array(auraParticleCount);

      for (let i = 0; i < auraParticleCount; i++) {
        auraPositions[i * 3] = 0;
        auraPositions[i * 3 + 1] = 0;
        auraPositions[i * 3 + 2] = 0;
        auraProgress[i] = Math.random();
        auraStreamIds[i] = i % streamCount;
      }

      const auraGeom = new THREE.BufferGeometry();
      auraGeom.setAttribute('position', new THREE.BufferAttribute(auraPositions, 3));
      auraGeom.setAttribute('aProgress', new THREE.BufferAttribute(auraProgress, 1));
      auraGeom.setAttribute('aStreamId', new THREE.BufferAttribute(auraStreamIds, 1));

      this.auraParticleMat = new THREE.ShaderMaterial({
        vertexShader: `
          uniform float uTime;
          uniform float uRadius;
          uniform float uSpeed;
          uniform float uProjectionScale;
          attribute float aProgress;
          attribute float aStreamId;
          varying vec3 vColor;
          varying float vAlpha;

          void main() {
            float t = fract(aProgress + uTime * uSpeed * (0.07 + 0.02 * sin(aStreamId)));
            float baseAngle = aStreamId * 0.448799;
            float spiralDir = mod(aStreamId, 2.0) == 0.0 ? 1.0 : -1.0;
            float angle = baseAngle + t * 2.2 * spiralDir;
            float r = uRadius * (1.02 + pow(t, 1.5) * 0.7);
            float z = sin(t * 3.14159) * (1.4 * cos(aStreamId));

            vec3 pos = vec3(r * cos(angle), r * sin(angle), z);

            vec4 mvPos = modelViewMatrix * vec4(pos, 1.0);
            float distFromCam = -mvPos.z;
            float worldSize = 0.024;
            gl_PointSize = clamp(worldSize * (uProjectionScale / distFromCam), 0.8, 3.5);
            gl_Position = projectionMatrix * mvPos;

            float fade = sin(t * 3.14159265);
            vColor = mix(vec3(0.043, 0.388, 0.871), vec3(0.157, 0.596, 0.894), fade);
            vAlpha = fade * 0.45;
          }
        `,
        fragmentShader: `
          uniform sampler2D uTexture;
          varying vec3 vColor;
          varying float vAlpha;
          void main() {
            vec4 tex = texture2D(uTexture, gl_PointCoord);
            gl_FragColor = vec4(vColor, vAlpha * tex.a);
          }
        `,
        uniforms: {
          uTime: { value: 0 },
          uRadius: { value: ORB_CONFIG.radius },
          uSpeed: { value: 0.7 },
          uProjectionScale: { value: this.getProjectionScale() },
          uTexture: { value: this.dotTexture }
        },
        transparent: true,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });

      this.auraParticles = new THREE.Points(auraGeom, this.auraParticleMat);
      this.auraGroup.add(this.auraParticles);
    }

    // 5. Exactly 3 Concentric Floor Pedestal Dashed Line Rings (Sleek Segments, Gaussian Blur & Opacity)
    initPedestalRings() {
      this.pedestalGroup = new THREE.Group();
      this.rootGroup.add(this.pedestalGroup);

      const R = ORB_CONFIG.radius;
      const lineThickness = 0.08;
      const baseY = -R * 1.05;

      // Sleek long dash segments (4, 5, 6 dashes per ring instead of choppy ones)
      const ringConfigs = [
        { radius: R * 0.90, dashes: 4.0, speed: 0.22, color: new THREE.Color(0x0B63DE) }, // Electric Blue
        { radius: R * 1.30, dashes: 5.0, speed: -0.16, color: new THREE.Color(0x49D9F1) }, // Luminous Cyan
        { radius: R * 1.70, dashes: 6.0, speed: 0.28, color: new THREE.Color(0x2898E4) }  // Bright Tech Blue
      ];

      this.pedestalMaterials = [];

      ringConfigs.forEach((cfg) => {
        const segments = 256;
        const innerR = cfg.radius - lineThickness * 0.5;
        const outerR = cfg.radius + lineThickness * 0.5;

        // Construct 2D flat ribbon ring geometry (lying in XZ plane)
        const geom = new THREE.RingGeometry(innerR, outerR, segments, 1);
        geom.rotateX(-Math.PI * 0.5); // Lay flat horizontally

        // Custom ShaderMaterial rendering sleek Gaussian blurred glowing dashed lines
        const mat = new THREE.ShaderMaterial({
          vertexShader: `
            varying vec2 vUv;
            varying float vAngle;
            void main() {
              vUv = uv;
              vAngle = atan(position.z, position.x);
              if (vAngle < 0.0) vAngle += 6.28318530718;
              gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
            }
          `,
          fragmentShader: `
            uniform float uTime;
            uniform float uSpeed;
            uniform float uDashes;
            uniform vec3 uColor;
            varying vec2 vUv;
            varying float vAngle;

            void main() {
              // Sleek, long continuous dash segment easing
              float dash = sin(vAngle * uDashes + uTime * uSpeed * 2.8);
              float dashMask = smoothstep(0.05, 0.70, dash);
              if (dashMask < 0.01) discard;

              // Double Gaussian radial blur across the line stroke:
              // Core sharp line (center 30%) + wide soft glowing blurred halo (outer 70%)
              float distFromCenter = abs(vUv.y - 0.5) * 2.0;
              float coreLine = exp(-distFromCenter * distFromCenter * 8.0);
              float glowHalo = exp(-distFromCenter * distFromCenter * 2.5);
              float blurProfile = coreLine * 0.55 + glowHalo * 0.45;

              float pulse = 0.85 + 0.15 * sin(uTime * 2.5);
              float alpha = dashMask * blurProfile * pulse * 0.78;

              // High-tech cybernetic color blending: core bright cyan / outer colored halo
              vec3 finalCol = mix(uColor, vec3(0.525, 0.871, 0.949), coreLine * 0.5);
              gl_FragColor = vec4(finalCol, alpha);
            }
          `,
          uniforms: {
            uTime: { value: 0 },
            uSpeed: { value: cfg.speed },
            uDashes: { value: cfg.dashes },
            uColor: { value: cfg.color }
          },
          transparent: true,
          blending: THREE.AdditiveBlending,
          depthWrite: false,
          side: THREE.DoubleSide
        });

        const mesh = new THREE.Mesh(geom, mat);
        mesh.position.y = baseY;
        this.pedestalGroup.add(mesh);
        this.pedestalMaterials.push(mat);
      });

      this.pedestalGroup.rotation.x = 0.28;
    }

    // ==========================================
    // 7. WEBSOCKET REAL-TIME BRIDGE CLIENT
    // ==========================================
    initWebSocket() {
      const port = ORB_CONFIG.wsPort;
      const host = window.location.hostname || '127.0.0.1';
      const wsUrl = `ws://${host}:${port}`;
      this.ws = null;

      const connect = () => {
        try {
          this.ws = new WebSocket(wsUrl);

          this.ws.onopen = () => {
            console.log('[JARVIS ORB] Connected to Python Runtime Bridge at ' + wsUrl);
            this.ws.send(JSON.stringify({ type: 'get_state' }));
          };

          this.ws.onmessage = (evt) => {
            try {
              const data = JSON.parse(evt.data);
              this.handleBackendEvent(data);
            } catch (err) {
              console.warn('[JARVIS ORB] Invalid WS payload:', err);
            }
          };

          this.ws.onclose = () => {
            setTimeout(connect, 1500);
          };

          this.ws.onerror = () => {
            if (this.ws) this.ws.close();
          };
        } catch (e) {
          setTimeout(connect, 1500);
        }
      };

      connect();
    }

    handleBackendEvent(data) {
      const type = data.type;

      if (type === 'wake_detected') {
        this.triggerWakeSequence();
      } else if (type === 'state_changed') {
        if (data.state === 'wake') {
          this.triggerWakeSequence();
        } else if (data.state === 'closing') {
          this.triggerClosingSequence();
        } else {
          this.setState(data.state);
        }
      } else if (type === 'state_sync') {
        if (data.state === 'wake') {
          this.triggerWakeSequence();
        } else if (data.state === 'closing') {
          this.triggerClosingSequence();
        } else {
          this.setState(data.state);
        }
      } else if (type === 'audio_level') {
        if (this.state === 'listening') {
          this.audio.setRealAmplitude(data.value);
        }
      } else if (type === 'tts_audio_level') {
        if (this.state === 'speaking') {
          this.audio.setRealAmplitude(data.value);
        }
      } else if (type === 'session_ended') {
        this.setState('hidden');
      }
    }

    sendWs(msg) {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify(msg));
      }
    }

    // ==========================================
    // 8. INTERACTION: 3D ORBIT ROTATION + SPRING DRAG
    // ==========================================
    initInteractions() {
      const getPointerPos = (e) => {
        const clientX = e.touches ? e.touches[0].clientX : e.clientX;
        const clientY = e.touches ? e.touches[0].clientY : e.clientY;
        return { x: clientX, y: clientY };
      };

      const pointerToWorld = (screenX, screenY) => {
        const normX = (screenX / window.innerWidth) * 2 - 1;
        const normY = -(screenY / window.innerHeight) * 2 + 1;
        const vec = new THREE.Vector3(normX, normY, 0.5);
        vec.unproject(this.camera);
        vec.sub(this.camera.position).normalize();
        const distance = -this.camera.position.z / vec.z;
        return this.camera.position.clone().add(vec.multiplyScalar(distance));
      };

      const onPointerDown = (e) => {
        if (this.state === 'hidden' || this.state === 'closing') return;
        if (e.target && e.target.classList && e.target.classList.contains('resize-handle')) {
          return;
        }
        this.isInteracting = true;
        const pos = getPointerPos(e);
        this.previousPointerPos = pos;

        const world = pointerToWorld(pos.x, pos.y);
        this.physics.startDrag(world.x, world.y);
        this.waveManager.spawn(1.5, 1.4);
      };

      const onPointerMove = (e) => {
        if (this.state === 'hidden' || this.state === 'closing') return;
        const pos = getPointerPos(e);

        if (this.isInteracting) {
          const deltaX = pos.x - this.previousPointerPos.x;
          const deltaY = pos.y - this.previousPointerPos.y;

          this.rotationVelocity.y = deltaX * 0.003;
          this.rotationVelocity.x = deltaY * 0.003;

          const world = pointerToWorld(pos.x, pos.y);
          this.physics.updateDrag(world.x, world.y);

          this.previousPointerPos = pos;
        }
      };

      const onPointerUp = () => {
        if (this.isInteracting) {
          this.isInteracting = false;
          this.physics.endDrag();
          this.waveManager.spawn(1.2, 1.0);
        }
      };

      const onWheel = (e) => {
        if (this.state === 'hidden' || this.state === 'closing') return;
        e.preventDefault();
        this.camera.position.z += e.deltaY * 0.006;
        this.camera.position.z = Math.max(ORB_CONFIG.minZoomZ, Math.min(ORB_CONFIG.maxZoomZ, this.camera.position.z));
      };

      window.addEventListener('mousedown', onPointerDown);
      window.addEventListener('mousemove', onPointerMove, { passive: true });
      window.addEventListener('mouseup', onPointerUp);

      window.addEventListener('touchstart', onPointerDown, { passive: true });
      window.addEventListener('touchmove', onPointerMove, { passive: true });
      window.addEventListener('touchend', onPointerUp, { passive: true });

      window.addEventListener('wheel', onWheel, { passive: false });
    }

    initKeyboardControls() {
      window.addEventListener('keydown', (e) => {
        if (e.key === '1') {
          this.setState('hidden');
          this.sendWs({ type: 'dev_set_state', state: 'hidden' });
        } else if (e.key === '2') {
          this.triggerWakeSequence();
          this.sendWs({ type: 'dev_set_state', state: 'wake' });
        } else if (e.key === '3') {
          this.setState('listening');
          this.sendWs({ type: 'dev_set_state', state: 'listening' });
        } else if (e.key === '4') {
          this.setState('processing');
          this.sendWs({ type: 'dev_set_state', state: 'processing' });
        } else if (e.key === '5') {
          this.setState('speaking');
          this.sendWs({ type: 'dev_set_state', state: 'speaking' });
        } else if (e.key === '6') {
          this.triggerClosingSequence();
          this.sendWs({ type: 'dev_set_state', state: 'closing' });
        } else if (e.key === ' ' || e.code === 'Space') {
          e.preventDefault();
          this.waveManager.spawn(1.8, 1.5);
        } else if (e.key === 'h' || e.key === 'H') {
          const hud = document.getElementById('dev-hud');
          if (hud) hud.classList.toggle('hidden');
        }
      });

      document.querySelectorAll('.dev-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          const targetState = btn.getAttribute('data-state');
          if (targetState === 'wake') {
            this.triggerWakeSequence();
            this.sendWs({ type: 'dev_set_state', state: 'wake' });
          } else if (targetState === 'closing') {
            this.triggerClosingSequence();
            this.sendWs({ type: 'dev_set_state', state: 'closing' });
          } else {
            this.setState(targetState);
            this.sendWs({ type: 'dev_set_state', state: targetState });
          }
        });
      });
    }

    setState(newState) {
      if (!this.stateEnum.hasOwnProperty(newState)) return;
      this.state = newState;

      const badge = document.getElementById('dev-state-badge');
      if (badge) badge.innerText = newState.toUpperCase();

      document.querySelectorAll('.dev-btn').forEach(btn => {
        btn.classList.toggle('active', btn.getAttribute('data-state') === newState);
      });

      if (newState === 'hidden') {
        this.targetScale = 0.001;
      } else if (newState === 'closing') {
        this.targetScale = 0.001;
      } else {
        this.targetScale = 1.0;
      }
    }

    triggerWakeSequence() {
      this.setState('wake');
      this.displayScale = 0.001;
      this.targetScale = 1.0;
      this.wakePhase = 1;

      const flash = document.getElementById('flash-overlay');
      if (flash) {
        flash.classList.add('active');
        setTimeout(() => flash.classList.remove('active'), 180);
      }

      this.waveManager.spawn(2.0, 1.6);
      setTimeout(() => this.waveManager.spawn(1.4, 1.2), 220);

      setTimeout(() => {
        if (this.state === 'wake') {
          this.wakePhase = 0;
          this.setState('listening');
        }
      }, 1200);
    }

    triggerClosingSequence() {
      if (this.state === 'hidden' || this.state === 'closing') return;
      this.setState('closing');
      this.targetScale = 0.001;

      setTimeout(() => {
        if (this.state === 'closing') {
          this.setState('hidden');
        }
      }, 700);
    }

    onWindowResize() {
      this.width = window.innerWidth || 480;
      this.height = window.innerHeight || 480;
      
      this.updateCameraPlacement();

      this.renderer.setSize(this.width, this.height);
      this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1.0, 2.0));

      // Update projection scale across all particle materials
      const projScale = this.getProjectionScale();
      if (this.particleMaterial) {
        this.particleMaterial.uniforms.uProjectionScale.value = projScale;
      }
      if (this.auraParticleMat) {
        this.auraParticleMat.uniforms.uProjectionScale.value = projScale;
      }
      if (this.orbitRings) {
        this.orbitRings.forEach(r => {
          if (r.satMat) r.satMat.uniforms.uProjectionScale.value = projScale;
        });
      }
    }

    animate() {
      requestAnimationFrame(this.animate);

      const dt = this.clock.getDelta();
      const time = this.clock.getElapsedTime();

      // If hidden and scale collapsed, skip heavy rendering to save 100% GPU
      if (this.state === 'hidden' && this.displayScale <= 0.002) {
        return;
      }

      // Smooth Scale Interpolation (Materialize on wake / Contract on closing)
      if (Math.abs(this.displayScale - this.targetScale) > 0.001) {
        const speed = (this.state === 'closing') ? 8.0 : 5.5;
        this.displayScale += (this.targetScale - this.displayScale) * Math.min(1.0, dt * speed);
        const s = Math.max(0.001, this.displayScale);
        this.rootGroup.scale.set(s, s, s);
      }

      // 1. Spring Physics Step
      this.physics.step(dt);
      this.rootGroup.position.x = this.physics.pos.x;
      this.rootGroup.position.y = this.physics.pos.y;

      // 2. 3D Orbit Rotation with Smooth Inertia Damping
      if (!this.isInteracting) {
        this.orbGroup.rotation.y += this.rotationVelocity.y;
        this.orbGroup.rotation.x += this.rotationVelocity.x;

        const baseOrbitSpeed = (this.state === 'processing') ? 0.0075 : (this.state === 'speaking' ? 0.0040 : 0.0022);
        this.rotationVelocity.y += (baseOrbitSpeed - this.rotationVelocity.y) * 0.04;
        this.rotationVelocity.x += (0.0 - this.rotationVelocity.x) * 0.04;
      }

      // 3. Audio Simulation / Live Stream Processing
      const amplitude = this.audio.update(dt, this.state);

      // 4. Update Surface Waves (Surface Radar)
      this.waveManager.update(dt, this.state, amplitude);
      this.waveManager.fillUniforms(this.waveCenters, this.waveData, this.waveParams);

      // 5. Update Shader Uniforms
      const stateNum = this.stateEnum[this.state] !== undefined ? this.stateEnum[this.state] : 0;

      if (this.particleMaterial) {
        this.particleMaterial.uniforms.uTime.value = time;
        this.particleMaterial.uniforms.uState.value = stateNum;
        this.particleMaterial.uniforms.uAmplitude.value = amplitude;
      }

      if (this.earthMaterial) {
        this.earthMaterial.uniforms.uTime.value = time;
        this.earthMaterial.uniforms.uState.value = stateNum;
        this.earthMaterial.uniforms.uAmplitude.value = amplitude;
      }

      if (this.auraParticleMat) {
        this.auraParticleMat.uniforms.uTime.value = time;
      }

      if (this.orbitRings) {
        this.orbitRings.forEach(r => {
          if (r.satMat) r.satMat.uniforms.uTime.value = time;
        });
      }

      if (this.pedestalMaterials) {
        this.pedestalMaterials.forEach(m => {
          m.uniforms.uTime.value = time;
        });
      }

      if (this.auraGroup) {
        this.auraGroup.rotation.y += 0.0035;
      }

      if (this.orbitGroup) {
        this.orbitGroup.rotation.y -= 0.0025;
      }

      // Render Scene
      this.renderer.render(this.scene, this.camera);
    }
  }

  window.addEventListener('DOMContentLoaded', () => {
    window.jarvisOrb = new JarvisOrbApp();
  });
})();
