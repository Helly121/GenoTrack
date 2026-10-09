# Build this site as a single HTML file: Helix and Harvest — An Immersive Gene Structure

You are an expert creative front-end developer. Produce a **single self-contained `index.html`**
that builds the concept below **exactly** — same layout, sections, visuals, motion, and
interaction. Pure HTML/CSS/JS in one file: no build step, no framework, no bundler. Use ES modules
with a CDN importmap for Three.js (r0.160 from unpkg, with the matching `GLTFLoader` addon, kept
available for an optional asset — see Assets). Hardcode every value given here as a fixed constant.
Rebuild each component described below as a section of the one file.

## What it is

A cinematic, scroll-driven landing page titled **"Helix and Harvest"** centered on a glowing,
semi-translucent **bioluminescent double-helix gene structure** rendered in WebGL on a deep-black
stage. The camera flies a full 360° orbit around the structure as you scroll through a very tall
page (900vh); drifting **pollen and chlorophyll motes** rise around it; a slow **living-soil wave
shader** breathes in the background, shifting its palette from warm germination amber at the top to
deep chlorophyll green at the bottom. Over the canvas sits an editorial overlay: a fixed header
(brand + nav + Contact button), four text "slides" that fade in at scroll milestones with per-letter
blur-up animation, a five-line vertical grid with drifting dots, a stories-style scroll progress bar,
and a custom double-ring cursor. Fonts are *Italiana* (display headings) and *Outfit* (body). The
whole thing is dark, slow, and precise — genetic data made sensory.

**Design intent for the hero structure:** the double helix is the *genotype* — the raw, inherited
sequence. Small glowing nodes strung along the rungs are individual *gene markers* (SNPs), each
tagged into one of three trait categories by color: gold = Yield, teal = Resilience, blue = Vigor.
Three larger rings orbit the helix at increasing radii, independent of the camera — these are the
*phenotype halos*, the expressed traits, and each ring's color matches its corresponding marker
category. The visual logic is deliberate: a genetic marker on the strand and the trait it expresses
share a color, so genotype and phenotype read as visibly, causally linked as the piece rotates.

## Page shell & libraries

- `<!DOCTYPE html>`, `lang="en"`, `<title>The Seed Genome</title>`, UTF-8, responsive viewport.
- Load fonts in CSS:
  `@import url('https://fonts.googleapis.com/css2?family=Italiana&family=Outfit:wght@300;400;600&family=Playfair+Display:ital,wght@1,500&display=swap');`
- Importmap + module script for Three.js:
  ```html
  <script type="importmap">
  {
    "imports": {
      "three": "https://unpkg.com/three@0.160.0/build/three.module.js",
      "three/examples/jsm/loaders/GLTFLoader.js": "https://unpkg.com/three@0.160.0/examples/jsm/loaders/GLTFLoader.js"
    }
  }
  </script>
  <script type="module"> /* all JS below */ </script>
  ```
- The page scroll model: `<body>` has `min-height: 900vh` so the page is very tall; the canvas and
  all overlay UI are `position: fixed`. Scroll position drives everything (camera orbit, shader,
  mote turbulence, slide reveals, grid dots, progress bar). No smooth-scroll library — smoothing is
  done in JS via lerp (see animation loop). All scrollbars are fully hidden (WebKit, Firefox, IE).
- The native cursor is hidden everywhere (`cursor: none` on body and `cursor: none !important` on
  `*`), replaced by a custom two-element cursor.

## Global CSS (reset + base)

```css
* { margin: 0; padding: 0; box-sizing: border-box; user-select: none; }

html, body {
    width: 100%;
    margin: 0;
    padding: 0;
    background-color: #000000;
    -ms-overflow-style: none;
    scrollbar-width: none;
}

body {
    min-height: 900vh;
    font-family: 'Outfit', sans-serif;
    color: #ffffff;
    overflow-x: hidden;
    cursor: none;
}

* { cursor: none !important; }

::-webkit-scrollbar { display: none; width: 0; }

#webgl {
    position: fixed;
    top: 0; left: 0;
    width: 100%; height: 100%;
    z-index: 1;
    outline: none;
}
```

## Layout & sections (in order)

The body markup, in order: two cursor divs, the `.cinematic-container` (header + slides), an image
mask, the grid-lines overlay, and the `<canvas id="webgl">`. Build them all.

### Custom cursor (two divs, top of `<body>`)
```html
<div class="cursor-inner"></div>
<div class="cursor-outer"></div>
```
```css
.cursor-inner {
    position: fixed; top: 0; left: 0;
    width: 6px; height: 6px;
    border: 2px solid rgba(255, 255, 255, 1);
    border-radius: 50%;
    transform: translate(-50%, -50%);
    pointer-events: none;
    z-index: 9999;
}
.cursor-outer {
    position: fixed; top: 0; left: 0;
    width: 40px; height: 40px;
    border: 1.5px solid rgba(255, 255, 255, 0.7);
    border-radius: 50%;
    transform: translate(-50%, -50%);
    pointer-events: none;
    z-index: 9998;
    transition: width 0.3s, height 0.3s, background 0.3s;
}
```
The inner ring snaps to the pointer instantly; the outer ring lerps toward it (see JS).

### `.cinematic-container` (the overlay layer)
```css
.cinematic-container {
    position: fixed;
    top: 0; left: 0;
    width: 100%; height: 100%;
    z-index: 10;
    pointer-events: none;          /* clicks pass through to canvas */
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    padding: 0 60px 40px 60px;
    box-sizing: border-box;
}
```

### Header `.main-header`
```html
<div class="main-header">
  <div class="brand">Genome</div>
  <nav class="header-nav">
    <a href="#slide-1" class="nav-link">Genotype</a>
    <span class="nav-dot"></span>
    <a href="#slide-2" class="nav-link">Phenotype</a>
    <span class="nav-dot"></span>
    <a href="#slide-3" class="nav-link">Expression</a>
    <span class="nav-dot"></span>
    <a href="#slide-4" class="nav-link">Harvest</a>
  </nav>
  <div class="header-actions">
    <a href="#" class="contact-btn">Contact <span class="btn-circle"></span></a>
  </div>
</div>
```
```css
.main-header {
    display: flex; justify-content: space-between; align-items: center;
    width: 100%; z-index: 20;
    pointer-events: auto;
    padding: 20px 0;
}
.brand { font-size: 14px; font-weight: 600; letter-spacing: 5px; text-transform: uppercase; }
.header-nav { display: flex; align-items: center; gap: 24px; }
.nav-link {
    color: #ffffff; text-decoration: none;
    font-size: 10px; text-transform: uppercase; letter-spacing: 2px;
    font-weight: 500; transition: color 0.3s;
}
.nav-link:hover { color: #ffffff; }
.nav-dot { width: 3px; height: 3px; background: rgba(255, 255, 255, 0.2); border-radius: 50%; }
.contact-btn {
    display: inline-flex; align-items: center; gap: 8px;
    padding: 10px 24px;
    background: #ffffff; color: #000000;
    text-decoration: none;
    font-size: 10px; text-transform: uppercase; letter-spacing: 1px; font-weight: 600;
    border-radius: 20px;
    transition: transform 0.3s, background 0.3s;
}
.btn-circle {
    display: inline-block; width: 6px; height: 6px;
    border: 1px solid #000000; border-radius: 50%; background: transparent;
}
.contact-btn:hover { transform: scale(1.05); background: #f0f0f0; }
```

### The four slides + the image mask
```html
<div class="slide" id="slide-1">
  <h2 class="slide-title">Helix <br>and Harvest</h2>
  <div class="desc-row">
    <p class="slide-desc col-1">A sequence of code holding centuries of survival and selection. Fluid in wild grasses, eternal in cultivated form. Each strand encodes a quiet, patient story.</p>
    <p class="slide-desc col-2">Born of ancient seed and patient breeding, it stands to bridge our agricultural memory and genomic vision. A living code fixed in dormant, waiting seed.</p>
  </div>
</div>
<div class="slide-image-mask" id="slide-2-img">
  <img src="ASSET_BASE_URL/field-macro.jpg" alt="Editorial Concept">
</div>
<div class="slide" id="slide-2">
  <h2 class="slide-title">Phenotype <br>Unfolding</h2>
  <p class="slide-desc">A kernel formed at the meeting point of inheritance and climate — genotype and environment, bound by quiet expression.</p>
</div>
<div class="slide" id="slide-3">
  <h2 class="slide-title">Living Code</h2>
  <p class="slide-desc">Biology that breathes. Mesmerizing currents of chlorophyll and signal flow through the structure, reflecting every switch and silence within the sequence.</p>
</div>
<div class="slide" id="slide-4">
  <h2 class="slide-title">Digital <br>Harvest</h2>
  <p class="slide-desc">Contemplating ancient grain through the lens of new dimensions. A field's wisdom reborn in the currents of radiant agricultural data.</p>
</div>
```
(Use the exact verbatim copy above. The `field-macro.jpg` image uses the asset bucket URL — see Assets.)

```css
.slide { position: absolute; bottom: 12%; pointer-events: none; }

#slide-1 { left: 0; width: 100%; }
#slide-1 .slide-title { margin-left: 60px; }
#slide-1 .desc-row { position: relative; display: flex; width: 100%; }
#slide-1 .col-1 {
    margin-left: 60px;
    width: calc(25vw - 60px);
    max-width: calc(25vw - 60px);
}
#slide-1 .col-2 {
    position: absolute;
    left: calc(25vw + 40px);
    width: calc(25vw - 60px);
    max-width: calc(25vw - 60px);
}

#slide-2 { left: 0; width: 100%; }
#slide-2-img {
    position: fixed;
    top: 90px;
    left: 60px;
    width: calc(25vw - 60px);
    aspect-ratio: 1 / 1;
    overflow: hidden;
    z-index: 2;
    pointer-events: none;
    clip-path: inset(0 0 100% 0);
    transition: clip-path 1.8s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.8s ease;
    opacity: 0;
}
#slide-2-img img {
    width: 100%; height: 100%;
    object-fit: cover;
    transform: scale(1.15);
    transition: transform 1.8s cubic-bezier(0.16, 1, 0.3, 1);
}
#slide-2-img.active { clip-path: inset(0 0 0 0); opacity: 1; }
#slide-2-img.active img { transform: scale(1); }

#slide-2 .slide-title { margin-left: calc(25vw + 40px); }
#slide-2 .slide-desc {
    margin-left: calc(50vw + 20px);
    width: calc(25vw - 60px);
    max-width: calc(25vw - 60px);
}

#slide-3 {
    left: calc(50vw + 20px);
    width: calc(25vw - 60px);
    max-width: calc(25vw - 60px);
}
#slide-3 .slide-title { white-space: nowrap; }

#slide-4 { left: calc(25% + 40px); max-width: 600px; }

.slide-title {
    font-family: 'Italiana', serif;
    font-size: 116px;
    line-height: 1.0;
    font-weight: 400;
    letter-spacing: 2px;
    margin-bottom: 20px;
    color: #f4ffe9;
}
.slide-desc {
    font-size: 16px; line-height: 1.7; font-weight: 300;
    color: #d1d5db; letter-spacing: 0.5px;
    opacity: 0;
    transform: translateY(30px);
    transition: opacity 0.8s cubic-bezier(0.25, 1, 0.5, 1),
                transform 0.8s cubic-bezier(0.25, 1, 0.5, 1);
    transition-delay: 0.4s;
}
.slide.active .slide-desc { opacity: 1; transform: translateY(0); }

.slide-title .char {
    display: inline-block;
    opacity: 0;
    transform: translateY(50px);
    filter: blur(12px);
    transition: opacity 0.8s cubic-bezier(0.25, 1, 0.5, 1),
                transform 0.8s cubic-bezier(0.25, 1, 0.5, 1),
                filter 0.8s cubic-bezier(0.25, 1, 0.5, 1);
}
.slide.active .slide-title .char { opacity: 1; transform: translateY(0); filter: blur(0); }
.slide.active { pointer-events: auto; }
```

### Grid overlay (horizontal divider + 5 vertical lines with dots + stories progress)
```html
<div class="grid-horizontal-line"></div>
<div class="grid-lines">
  <div class="grid-line"><div class="grid-dot top"></div><div class="grid-dot bottom"></div></div>
  <div class="grid-line"><div class="grid-dot top"></div><div class="grid-dot bottom"></div></div>
  <div class="grid-line"><div class="grid-dot top"></div><div class="grid-dot bottom"></div></div>
  <div class="grid-line"><div class="grid-dot top"></div><div class="grid-dot bottom"></div></div>
  <div class="grid-line story-progress-container">
    <div class="grid-dot top"></div>
    <div class="grid-dot bottom"></div>
    <div class="story-dashes">
      <div class="story-dash"><div class="story-dash-fill" id="dash-fill-1"></div></div>
      <div class="story-dash"><div class="story-dash-fill" id="dash-fill-2"></div></div>
      <div class="story-dash"><div class="story-dash-fill" id="dash-fill-3"></div></div>
      <div class="story-dash"><div class="story-dash-fill" id="dash-fill-4"></div></div>
    </div>
  </div>
</div>
```
```css
.story-dashes {
    position: absolute; top: 50%; left: 50%;
    transform: translate(-50%, -50%);
    display: flex; flex-direction: column; gap: 12px;
}
.story-dash { width: 2px; height: 40px; background: rgba(255, 255, 255, 0.15); border-radius: 2px; }
.story-dash-fill { width: 100%; height: 0%; background: #ffffff; border-radius: 2px; }

.grid-horizontal-line {
    position: fixed; top: 70px; left: 0; right: 0;
    width: 100%; height: 1px;
    background: rgba(255, 255, 255, 0.12);
    z-index: 5; pointer-events: none;
}
.grid-lines {
    position: fixed; top: 0; left: 40px; right: 40px;
    width: calc(100% - 80px); height: 100vh;
    display: flex; justify-content: space-between;
    z-index: 5; pointer-events: none;
}
.grid-line {
    position: relative; width: 1px; height: 100%;
    background: rgba(255, 255, 255, 0.12);
}
.grid-line:nth-child(3) { margin-top: 70px; height: calc(100vh - 70px); }
.grid-dot {
    position: absolute; left: 50%;
    transform: translate(-50%, -50%);
    width: 6px; height: 6px; border-radius: 50%;
    background: rgba(255, 255, 255, 0.35);
    box-shadow: 0 0 4px rgba(255, 255, 255, 0.15);
}
```

### Canvas (last element)
```html
<canvas id="webgl"></canvas>
```

## The WebGL scene

All of the following runs inside the module script. Globals to declare at top:

```js
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';

const canvas = document.querySelector('#webgl');
let scene, camera, renderer;
let geneGroup;      // the full gene-helix assembly (backbone strands + rungs + markers)
let helixPivot;      // pivot group for perfect center-rotation
let haloGroup;        // the three orbiting phenotype halo rings, independent spin
const clock = new THREE.Clock();
let currentScroll = 0;   // smoothed accumulated scroll for lerping

let mouseX = 0, mouseY = 0, targetMouseX = 0, targetMouseY = 0;

let cursorX = window.innerWidth / 2,  cursorY = window.innerHeight / 2;
let outerCursorX = window.innerWidth / 2, outerCursorY = window.innerHeight / 2;

let bgMaterial;
const shaderUniforms = {
    uTime: { value: 0 },
    uResolution: { value: new THREE.Vector2(window.innerWidth, window.innerHeight) },
    uMouse: { value: new THREE.Vector2(0, 0) },
    uScroll: { value: 0 }
};

let moteParticles;
const moteCount = 450;
const moteData = [];

const sizes = { width: window.innerWidth, height: window.innerHeight };
```

### Renderer, scene, camera (verbatim setup)
```js
scene = new THREE.Scene();
scene.background = new THREE.Color('#000000');
scene.fog = new THREE.FogExp2('#020402', 0.01);

camera = new THREE.PerspectiveCamera(50, sizes.width / sizes.height, 0.1, 100);
camera.position.set(0, 0.2, 3.0);
scene.add(camera);

createBackgroundShader();   // adds the wave plane as a child of the camera

renderer = new THREE.WebGLRenderer({
    canvas: canvas,
    antialias: true,
    alpha: false,
    powerPreference: "high-performance"
});
renderer.setSize(sizes.width, sizes.height);
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.9;
```

### Dramatic lighting (grow-light chiaroscuro) — verbatim
```js
const ambientLight = new THREE.AmbientLight('#ffffff', 0.12);
scene.add(ambientLight);

// Key light: warm daylight "grow-light" from upper-right, casts shadows
const keyLight = new THREE.SpotLight('#fff4d6', 16.0);
keyLight.position.set(4, 6, 3);
keyLight.angle = Math.PI / 4;
keyLight.penumbra = 0.9;
keyLight.castShadow = true;
keyLight.shadow.mapSize.width = 2048;
keyLight.shadow.mapSize.height = 2048;
keyLight.shadow.camera.near = 1.0;
keyLight.shadow.camera.far = 15;
keyLight.shadow.bias = -0.001;
scene.add(keyLight);

// Rim light: cool chlorophyll-green from behind-left, defines the silhouette
const rimLight = new THREE.DirectionalLight('#8fffc0', 9.0);
rimLight.position.set(-5, 3, -4);
scene.add(rimLight);

// Fill light: faint warm soil-amber from below-front
const fillLight = new THREE.DirectionalLight('#ffe9c4', 0.8);
fillLight.position.set(-2, -4, 2);
scene.add(fillLight);
```

### Pollen & chlorophyll motes (450 additive point particles) — verbatim
Procedural radial-gradient texture (white core → transparent edge), identical mechanism to a
classic spark shader, just re-skinned in palette:
```js
function createMoteTexture() {
    const canvas = document.createElement('canvas');
    canvas.width = 16; canvas.height = 16;
    const ctx = canvas.getContext('2d');
    const gradient = ctx.createRadialGradient(8, 8, 0, 8, 8, 8);
    gradient.addColorStop(0, 'rgba(255, 255, 255, 1)');
    gradient.addColorStop(0.25, 'rgba(255, 255, 255, 0.85)');
    gradient.addColorStop(0.6, 'rgba(255, 255, 255, 0.3)');
    gradient.addColorStop(1, 'rgba(0, 0, 0, 0)');
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, 16, 16);
    return new THREE.CanvasTexture(canvas);
}
```
Build the particle cloud — random positions in a box around the structure, colors split 60% golden
pollen / 40% chlorophyll green, and per-particle physics stored in `moteData`:
```js
function createMotes() {
    const geometry = new THREE.BufferGeometry();
    const positions = new Float32Array(moteCount * 3);
    const colors = new Float32Array(moteCount * 3);

    for (let i = 0; i < moteCount; i++) {
        const x = (Math.random() - 0.5) * 6.5;
        const y = (Math.random() - 0.5) * 5.0 - 0.5;
        const z = (Math.random() - 0.5) * 6.5;
        positions[i * 3] = x;
        positions[i * 3 + 1] = y;
        positions[i * 3 + 2] = z;

        if (Math.random() < 0.6) {
            // saturated golden pollen
            colors[i * 3] = 1.0;
            colors[i * 3 + 1] = 0.78 + Math.random() * 0.15;
            colors[i * 3 + 2] = 0.25 + Math.random() * 0.15;
        } else {
            // luminous chlorophyll green
            colors[i * 3] = 0.35 + Math.random() * 0.15;
            colors[i * 3 + 1] = 0.95 + Math.random() * 0.05;
            colors[i * 3 + 2] = 0.55 + Math.random() * 0.15;
        }

        moteData.push({
            speedX: (Math.random() - 0.5) * 0.4,
            speedY: 0.15 + Math.random() * 0.3,
            speedZ: (Math.random() - 0.5) * 0.4,
            swaySpeed: 0.5 + Math.random() * 1.5,
            swayRadius: 0.05 + Math.random() * 0.15,
            phase: Math.random() * Math.PI * 2
        });
    }

    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

    const material = new THREE.PointsMaterial({
        size: 0.025,
        vertexColors: true,
        transparent: true,
        opacity: 0.85,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        map: createMoteTexture()
    });

    moteParticles = new THREE.Points(geometry, material);
    scene.add(moteParticles);
}
```

### Gene structure build — procedural, no external model required — verbatim
This is the hero object. It is built entirely from Three.js primitives, so the piece is fully
reproducible with **no bespoke 3D asset**. Three layers, matching the design intent above:

1. **Two backbone strands (the Genotype)** — two intertwined tubes following a parametric helix.
2. **Rungs + marker nodes (the Genes)** — 52 base-pair connectors, each with a glowing marker at its
   midpoint, cycling through three trait-category colors.
3. **Orbiting phenotype halos (the Phenotype)** — three tilted rings orbiting independently at
   increasing radii, color-matched to the marker categories.

```js
const HELIX_RADIUS = 0.85;
const HELIX_HALF_HEIGHT = 1.75;       // total structure height = 3.5, matching the orbit framing
const HELIX_TURNS = 6.5;
const STRAND_SEGMENTS = 480;          // resolution of each backbone curve
const STRAND_TUBE_RADIUS = 0.028;
const RUNG_COUNT = 52;                // base-pair "genes" connecting the two strands
const MARKER_RADIUS = 0.045;

function buildGeneStructure() {
    geneGroup = new THREE.Group();
    helixPivot = new THREE.Group();
    scene.add(helixPivot);
    helixPivot.add(geneGroup);

    // --- 1. Two backbone strands (the Genotype) ---
    const strandMaterialA = new THREE.MeshPhysicalMaterial({
        color: '#ffd98e',
        emissive: '#7a4b00',
        emissiveIntensity: 0.6,
        roughness: 0.3,
        metalness: 0.1,
        clearcoat: 1.0,
        clearcoatRoughness: 0.2,
        transmission: 0.15,
        transparent: true,
        opacity: 0.95
    });
    const strandMaterialB = strandMaterialA.clone();
    strandMaterialB.color = new THREE.Color('#8affc2');
    strandMaterialB.emissive = new THREE.Color('#0a5c33');

    const pointsA = [];
    const pointsB = [];
    for (let i = 0; i <= STRAND_SEGMENTS; i++) {
        const t = i / STRAND_SEGMENTS;
        const angle = t * Math.PI * 2 * HELIX_TURNS;
        const y = -HELIX_HALF_HEIGHT + t * HELIX_HALF_HEIGHT * 2;
        pointsA.push(new THREE.Vector3(Math.cos(angle) * HELIX_RADIUS, y, Math.sin(angle) * HELIX_RADIUS));
        pointsB.push(new THREE.Vector3(Math.cos(angle + Math.PI) * HELIX_RADIUS, y, Math.sin(angle + Math.PI) * HELIX_RADIUS));
    }
    const curveA = new THREE.CatmullRomCurve3(pointsA);
    const curveB = new THREE.CatmullRomCurve3(pointsB);
    const tubeA = new THREE.Mesh(new THREE.TubeGeometry(curveA, 400, STRAND_TUBE_RADIUS, 8, false), strandMaterialA);
    const tubeB = new THREE.Mesh(new THREE.TubeGeometry(curveB, 400, STRAND_TUBE_RADIUS, 8, false), strandMaterialB);
    tubeA.castShadow = tubeB.castShadow = true;
    tubeA.receiveShadow = tubeB.receiveShadow = true;
    geneGroup.add(tubeA, tubeB);

    // --- 2. Base-pair rungs + marker nodes (the Genes / SNP markers) ---
    const markerPalette = ['#ffd166', '#06d6a0', '#4cc9f0']; // trait categories: Yield / Resilience / Vigor
    const rungMaterial = new THREE.MeshStandardMaterial({ color: '#403a2e', roughness: 0.6, metalness: 0.2 });
    const markerGeometry = new THREE.IcosahedronGeometry(MARKER_RADIUS, 1);

    for (let i = 0; i < RUNG_COUNT; i++) {
        const t = i / (RUNG_COUNT - 1);
        const idx = Math.floor(t * STRAND_SEGMENTS);
        const pA = pointsA[idx];
        const pB = pointsB[idx];

        const rungCurve = new THREE.LineCurve3(pA, pB);
        const rungMesh = new THREE.Mesh(new THREE.TubeGeometry(rungCurve, 1, 0.012, 6, false), rungMaterial);
        geneGroup.add(rungMesh);

        const markerColor = markerPalette[i % markerPalette.length];
        const markerMat = new THREE.MeshPhysicalMaterial({
            color: markerColor, emissive: markerColor, emissiveIntensity: 1.4,
            roughness: 0.2, metalness: 0.0, clearcoat: 1.0
        });
        const midpoint = pA.clone().lerp(pB, 0.5);
        const marker = new THREE.Mesh(markerGeometry, markerMat);
        marker.position.copy(midpoint);
        marker.castShadow = true;
        geneGroup.add(marker);
    }

    // --- 3. Orbiting phenotype halos (the Phenotype), color-matched to the marker categories ---
    haloGroup = new THREE.Group();
    helixPivot.add(haloGroup);
    const haloDefs = [
        { radius: 1.55, tube: 0.006, color: '#ffd166', tilt: 0.35, speed: 0.06 },   // Yield
        { radius: 1.90, tube: 0.005, color: '#06d6a0', tilt: -0.50, speed: -0.04 }, // Resilience
        { radius: 2.25, tube: 0.004, color: '#4cc9f0', tilt: 0.15, speed: 0.03 }    // Vigor
    ];
    haloDefs.forEach((def) => {
        const torus = new THREE.Mesh(
            new THREE.TorusGeometry(def.radius, def.tube, 8, 128),
            new THREE.MeshBasicMaterial({ color: def.color, transparent: true, opacity: 0.35 })
        );
        torus.rotation.x = Math.PI / 2 + def.tilt;
        torus.userData.spinSpeed = def.speed;
        haloGroup.add(torus);
    });

    // --- 4. Drop the pivot for a grounded, centered orbit ---
    helixPivot.position.y = -0.15;

    // --- 5. Soft materialize-in (no async load delay, so fake a gentle reveal instead of a pop-in) ---
    geneGroup.scale.setScalar(0.001);
    haloGroup.scale.setScalar(0.001);
    const revealStart = clock.getElapsedTime();
    function revealTick() {
        const elapsed = clock.getElapsedTime() - revealStart;
        const p = Math.min(1, elapsed / 1.2);
        const eased = 1 - Math.pow(1 - p, 3);
        geneGroup.scale.setScalar(0.001 + eased * 0.999);
        haloGroup.scale.setScalar(0.001 + eased * 0.999);
        if (p < 1) requestAnimationFrame(revealTick);
    }
    revealTick();
}
```

### Background living-soil wave shader (full-screen plane, child of camera) — VERBATIM
Identical wave/noise mechanics to a liquid-metal shader, re-paletted from germination amber to
chlorophyll green:
```js
function createBackgroundShader() {
    const vertexShader = `
        varying vec2 vUv;
        void main() {
            vUv = uv;
            gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
    `;

    const fragmentShader = `
        varying vec2 vUv;
        uniform float uTime;
        uniform vec2 uResolution;
        uniform vec2 uMouse;
        uniform float uScroll;

        // 3D Noise function for organic warping (high performance hash-based noise)
        float hash(float n) { return fract(sin(n) * 43758.5453123); }
        float noise(in vec3 x) {
            vec3 p = floor(x);
            vec3 f = fract(x);
            f = f*f*(3.0-2.0*f);
            float n = p.x + p.y*57.0 + 113.0*p.z;
            return mix(mix(mix(hash(n+  0.0), hash(n+  1.0), f.x),
                           mix(hash(n+ 57.0), hash(n+ 58.0), f.x), f.y),
                       mix(mix(hash(n+113.0), hash(n+114.0), f.x),
                           mix(hash(n+170.0), hash(n+171.0), f.x), f.y), f.z);
        }

        void main() {
            // Normalize UV coordinates
            vec2 uv = (gl_FragCoord.xy - 0.5 * uResolution.xy) / uResolution.y;
            float aspect = uResolution.x / uResolution.y;
            
            float time = uTime * 0.08; // Extremely slow, calm breathing speed
            float scroll = uScroll;
            
            // --- 1. Constant Wave Parameters (Perfect Scroll Stability) ---
            float angle1 = 0.6;
            float angle2 = -0.7;
            float angle3 = 1.2;
            
            float freq1 = 2.4;
            float freq2 = 3.2;
            float freq3 = 4.0;
            
            // --- 2. Coordinates Distortion (Smooth Rounded Arcs & Scroll Deformation) ---
            vec2 warpedUv = uv;
            
            float scrollDeform = scroll * 5.0;
            
            warpedUv.x += sin(uv.y * 2.5 + time * 0.2 + scrollDeform) * 0.35;
            warpedUv.y += cos(uv.x * 2.5 - time * 0.15 - scrollDeform * 0.8) * 0.35;
            
            warpedUv.x += sin(uv.y * 1.2 - time * 0.1 - scrollDeform * 1.5) * 0.25;
            warpedUv.y += cos(uv.x * 1.2 + time * 0.18 + scrollDeform * 1.2) * 0.25;
            
            vec2 scrollDrift = vec2(scroll * 0.04, -scroll * 0.02);
            vec2 mouseShift = vec2(uMouse.x * aspect * 0.05, uMouse.y * 0.05);
            warpedUv += scrollDrift + mouseShift;
            
            // --- 3. Layered Wave Computations ---
            vec2 dir1 = vec2(cos(angle1), sin(angle1));
            vec2 dir2 = vec2(cos(angle2), sin(angle2));
            vec2 dir3 = vec2(cos(angle3), sin(angle3));
            
            float w1 = sin(dot(warpedUv, dir1) * freq1 + time * 1.0);
            float w2 = cos(dot(warpedUv, dir2) * freq2 - time * 1.4 + w1 * 0.4);
            float w3 = sin(dot(warpedUv, dir3) * freq3 + time * 1.8 + w2 * 0.5);
            
            float waveField = w1 * 0.50 + w2 * 0.35 + w3 * 0.15;
            
            // --- 4. Crisp Organic Lustre ---
            float wideSheen = pow(max(0.0, 1.0 - abs(waveField - 0.1)), 2.5);
            float crispSpecular = pow(max(0.0, 1.0 - abs(waveField - 0.15)), 8.0);
            float crest = wideSheen * 0.5 + crispSpecular * 0.9;
            
            // --- 5. Scroll-Driven Color Palettes: Germination Amber to Chlorophyll Green ---
            // Top Palette (Scroll = 0.0): Warm Germination Amber
            vec3 c0_shadow = vec3(0.0008, 0.0005, 0.0002);
            vec3 c0_wave1  = vec3(0.075, 0.045, 0.012);
            vec3 c0_wave2  = vec3(0.045, 0.026, 0.006);
            vec3 c0_crest  = vec3(0.55, 0.38, 0.14);
            
            // Bottom Palette (Scroll = 1.0): Deep Chlorophyll Green
            vec3 c1_shadow = vec3(0.0003, 0.0008, 0.0004);
            vec3 c1_wave1  = vec3(0.012, 0.055, 0.028);
            vec3 c1_wave2  = vec3(0.006, 0.032, 0.016);
            vec3 c1_crest  = vec3(0.16, 0.55, 0.30);
            
            float t = smoothstep(0.0, 1.0, scroll);
            vec3 colShadow = mix(c0_shadow, c1_shadow, t);
            vec3 colWave1  = mix(c0_wave1, c1_wave1, t);
            vec3 colWave2  = mix(c0_wave2, c1_wave2, t);
            vec3 colCrest  = mix(c0_crest, c1_crest, t);
            
            // --- 6. Final Composition ---
            vec3 color = colShadow;
            color = mix(color, colWave2, smoothstep(-0.6, 0.2, waveField));
            color = mix(color, colWave1, smoothstep(0.0, 0.8, waveField));
            
            color += colCrest * crest * 1.4;
            
            float vignette = 1.0 - dot(uv, uv) * 0.12;
            color *= vignette;
            
            gl_FragColor = vec4(color, 1.0);
        }
    `;

    bgMaterial = new THREE.ShaderMaterial({
        vertexShader: vertexShader,
        fragmentShader: fragmentShader,
        uniforms: shaderUniforms,
        depthWrite: false,
        depthTest: false
    });

    const bgGeometry = new THREE.PlaneGeometry(30, 30);
    const bgMesh = new THREE.Mesh(bgGeometry, bgMaterial);
    bgMesh.position.set(0.0, 0.0, -8.0);   // local camera space, far behind
    bgMesh.renderOrder = -10;
    camera.add(bgMesh);                    // attach to camera so it always fills view
}
```

### Resize handler — verbatim
```js
function onWindowResize() {
    sizes.width = window.innerWidth;
    sizes.height = window.innerHeight;
    camera.aspect = sizes.width / sizes.height;
    camera.updateProjectionMatrix();
    renderer.setSize(sizes.width, sizes.height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    if (shaderUniforms) shaderUniforms.uResolution.value.set(sizes.width, sizes.height);
}
```

## Interaction & animation loop

### Pointer handling
On `mousemove`: snap the inner cursor to `event.clientX/Y` (set its `left`/`top`); store normalized
mouse target `targetMouseX = clientX/innerWidth*2-1`, `targetMouseY = clientY/innerHeight*2-1`.
```js
window.addEventListener('mousemove', (event) => {
    cursorX = event.clientX;
    cursorY = event.clientY;
    const cursorInner = document.querySelector('.cursor-inner');
    if (cursorInner) { cursorInner.style.left = `${cursorX}px`; cursorInner.style.top = `${cursorY}px`; }
    targetMouseX = (event.clientX / window.innerWidth) * 2 - 1;
    targetMouseY = (event.clientY / window.innerHeight) * 2 - 1;
});
window.addEventListener('resize', onWindowResize);
```

### Per-letter title split (call before first frame)
Split each `.slide-title` into per-character `<span class="char">` with a staggered
`transition-delay` of `index * 0.035s`, preserving `<br>` tags and spaces:
```js
function splitTitlesIntoChars() {
    const titles = document.querySelectorAll('.slide-title');
    titles.forEach(title => {
        const text = title.innerHTML;
        let newHTML = '';
        let delayCounter = 0;
        const parts = text.split(/(<br\s*\/?>)/i);
        parts.forEach(part => {
            if (part.toLowerCase().startsWith('<br')) {
                newHTML += part;
            } else {
                for (let i = 0; i < part.length; i++) {
                    if (part[i] === ' ') {
                        newHTML += ' ';
                    } else {
                        newHTML += `<span class="char" style="transition-delay: ${delayCounter * 0.035}s">${part[i]}</span>`;
                        delayCounter++;
                    }
                }
            }
        });
        title.innerHTML = newHTML;
    });
}
```

### The `animate()` loop (verbatim logic)
```js
function animate() {
    requestAnimationFrame(animate);
    const deltaTime = clock.getDelta();

    // 1. target scroll [0..1], cross-browser
    const maxScroll = document.documentElement.scrollHeight - window.innerHeight;
    const scrollTop = window.scrollY !== undefined ? window.scrollY
        : (window.pageYOffset !== undefined ? window.pageYOffset : document.documentElement.scrollTop);
    const targetScroll = maxScroll > 0 ? scrollTop / maxScroll : 0;

    // smooth physical lerp (inertia)
    currentScroll += (targetScroll - currentScroll) * 0.025;

    // smooth structure rotation lerp
    mouseX += (targetMouseX - mouseX) * 0.05;
    mouseY += (targetMouseY - mouseY) * 0.05;

    // outer cursor ring lerps toward inner
    outerCursorX += (cursorX - outerCursorX) * 0.2;
    outerCursorY += (cursorY - outerCursorY) * 0.2;
    const cursorOuter = document.querySelector('.cursor-outer');
    if (cursorOuter) { cursorOuter.style.left = `${outerCursorX}px`; cursorOuter.style.top = `${outerCursorY}px`; }

    // gentle autonomous spin (the sequence continuously "unwinding") + subtle interactive nudge from mouse
    if (helixPivot) {
        helixPivot.rotation.y += deltaTime * 0.05;
        helixPivot.rotation.y += mouseX * 0.001;
        helixPivot.rotation.x = mouseY * 0.08;
    }
    // phenotype halos spin independently of the helix itself
    if (haloGroup) {
        haloGroup.children.forEach((torus) => {
            torus.rotation.z += deltaTime * torus.userData.spinSpeed;
        });
    }

    // 2. mote physics, accelerated/turbulent on fast scroll
    if (moteParticles) {
        const positions = moteParticles.geometry.attributes.position.array;
        const time = clock.getElapsedTime();
        const scrollVelocity = Math.abs(targetScroll - currentScroll);
        const speedMultiplier = 1.0 + scrollVelocity * 9.0;
        const turbulence = scrollVelocity * 0.8;

        for (let i = 0; i < moteCount; i++) {
            const idx = i * 3;
            const data = moteData[i];
            positions[idx]     += data.speedX * deltaTime * speedMultiplier;
            positions[idx + 1] += data.speedY * deltaTime * speedMultiplier;
            positions[idx + 2] += data.speedZ * deltaTime * speedMultiplier;

            const currentSway = data.swayRadius * (1.0 + turbulence * 4.0);
            positions[idx]     += Math.sin(time * data.swaySpeed + data.phase) * currentSway * deltaTime;
            positions[idx + 2] += Math.cos(time * data.swaySpeed + data.phase) * currentSway * deltaTime;

            // recycle when out of bounds
            if (positions[idx + 1] > 3.0 || Math.abs(positions[idx]) > 3.5 || Math.abs(positions[idx + 2]) > 3.5) {
                positions[idx + 1] = -2.5;
                positions[idx]     = (Math.random() - 0.5) * 3.0;
                positions[idx + 2] = (Math.random() - 0.5) * 3.0;
            }
        }
        moteParticles.geometry.attributes.position.needsUpdate = true;
    }

    // 3. camera orbits the structure 360° driven by scroll
    const phi = currentScroll * Math.PI * 2.0;
    const y = 0.35 + Math.sin(currentScroll * Math.PI) * 0.8;
    const radius = 4.2 - Math.sin(currentScroll * Math.PI) * 0.6;
    const x = radius * Math.sin(phi);
    const z = radius * Math.cos(phi);

    // shift the framing left on the first screen to clear room for the text columns
    let transitionProgress = Math.min(1.0, currentScroll / 0.28);
    let easeFactor = (Math.cos(transitionProgress * Math.PI) + 1.0) * 0.5; // 1.0 → 0.0
    const lookAtXOffset = -0.9 * easeFactor;
    const targetLookAt = new THREE.Vector3(lookAtXOffset, -0.15, 0);
    const targetPos = new THREE.Vector3(x, y, z);
    camera.position.lerp(targetPos, 0.025);
    camera.lookAt(targetLookAt);

    // background shader uniforms
    if (shaderUniforms) {
        shaderUniforms.uTime.value = clock.getElapsedTime();
        shaderUniforms.uMouse.value.set(mouseX, -mouseY);
        shaderUniforms.uScroll.value = currentScroll;
    }

    updateSlides(currentScroll);
    updateGridDots(currentScroll);
    renderer.render(scene, camera);
}
```

### Grid dots drift — verbatim
```js
function updateGridDots(scroll) {
    const dots = document.querySelectorAll('.grid-dot');
    dots.forEach((dot, i) => {
        const startY = (i * 17) % 80 + 10;
        let speed = 90 + (i * 55) % 180;
        if (i % 2 === 0) speed = -speed;
        let y = startY + scroll * speed;
        y = ((y % 100) + 100) % 100;
        dot.style.top = `${y}%`;
    });
}
```

### Slides + stories progress — verbatim
```js
function updateSlides(scroll) {
    const slide1 = document.getElementById('slide-1');
    const slide2 = document.getElementById('slide-2');
    const slide3 = document.getElementById('slide-3');
    const slide4 = document.getElementById('slide-4');

    for (let i = 1; i <= 4; i++) {
        const fill = document.getElementById(`dash-fill-${i}`);
        if (fill) {
            const start = (i - 1) * 0.25;
            const end = i * 0.25;
            let progress = (scroll - start) / (end - start);
            progress = Math.max(0, Math.min(1, progress));
            fill.style.height = `${progress * 100}%`;
        }
    }

    function isActive(val, start, end) { return val >= start && val <= end; }

    if (slide1) slide1.classList.toggle('active', isActive(scroll, -0.10, 0.12));
    if (slide2) {
        const active2 = isActive(scroll, 0.28, 0.40);
        slide2.classList.toggle('active', active2);
        const slide2Img = document.getElementById('slide-2-img');
        if (slide2Img) slide2Img.classList.toggle('active', active2);
    }
    if (slide3) slide3.classList.toggle('active', isActive(scroll, 0.56, 0.68));
    if (slide4) slide4.classList.toggle('active', isActive(scroll, 0.84, 1.05));
}
```

### Nav click → smooth scroll-to — verbatim
```js
function setupNavigation() {
    const navLinks = document.querySelectorAll('.nav-link');
    const targetScrolls = [0.0, 0.34, 0.62, 0.94];
    navLinks.forEach((link, index) => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            const maxScroll = document.documentElement.scrollHeight - window.innerHeight;
            const targetY = maxScroll * targetScrolls[index];
            window.scrollTo({ top: targetY, behavior: 'smooth' });
        });
    });
}
```

### Bootstrap
```js
window.addEventListener('DOMContentLoaded', () => {
    splitTitlesIntoChars();   // (or call inside init before animate)
    // ... build scene: createScene/camera/shader, renderer, lighting, motes, buildGeneStructure ...
    onWindowResize();         // optional initial sync
    animate();
    setupNavigation();
});
```
Order matters: split titles, create scene + camera, `createBackgroundShader()`, renderer + tone
mapping, lighting, `createMotes()`, then `buildGeneStructure()`, then start `animate()` and wire
navigation. Because the gene structure is procedural rather than an async model fetch, it can be
built synchronously in this same sequence — no loading-state branching is required.

## The reveal

There is no separate loading screen. The reveal is the natural sequence: the black stage + breathing
amber-to-green wave shader render immediately; the gene structure materializes from a near-zero scale
into full presence over ~1.2s (see the `revealTick` easing in the build function) rather than
popping in; slide-1 ("Helix and Harvest") is active at the top — its title animates in per-letter
from below with a 12px→0 blur and 50px→0 rise (0.035s stagger per char), and its two description
columns float up (translateY 30px→0, 0.4s delay). As you scroll, each subsequent slide repeats the
blur-up reveal at its milestone, the editorial image (slide-2) wipes open top-to-bottom via
`clip-path` with a 1.15→1 parallax zoom, motes swirl faster, and the shader palette migrates
amber→chlorophyll-green while the phenotype halos keep gently, independently turning.

## Fixed parameters (bake these in)

- Background: pure black `#000000`; `FogExp2('#020402', 0.01)`.
- Camera: `PerspectiveCamera(50, aspect, 0.1, 100)`, start `(0, 0.2, 3.0)`.
- Renderer: antialias on, pixelRatio `min(dpr, 2)`, `PCFSoftShadowMap`, `ACESFilmicToneMapping`,
  exposure `1.9`.
- Lights: ambient `#ffffff @ 0.12`; key SpotLight `#fff4d6 @ 16.0` at `(4,6,3)`, angle `PI/4`,
  penumbra `0.9`, shadow map 2048², near 1.0 far 15, bias -0.001; rim DirectionalLight
  `#8fffc0 @ 9.0` at `(-5,3,-4)`; fill DirectionalLight `#ffe9c4 @ 0.8` at `(-2,-4,2)`.
- Gene structure: `HELIX_RADIUS 0.85`, `HELIX_HALF_HEIGHT 1.75` (total height 3.5),
  `HELIX_TURNS 6.5`, `STRAND_SEGMENTS 480`, `STRAND_TUBE_RADIUS 0.028`, `RUNG_COUNT 52`,
  `MARKER_RADIUS 0.045`; strand A `#ffd98e` / emissive `#7a4b00`, strand B `#8affc2` / emissive
  `#0a5c33`; marker palette cycling `#ffd166` (Yield) / `#06d6a0` (Resilience) / `#4cc9f0` (Vigor);
  halo radii `1.55 / 1.90 / 2.25` at tilts `0.35 / -0.50 / 0.15`, spin speeds
  `0.06 / -0.04 / 0.03` rad/s, matched to the same three colors; `helixPivot.position.y = -0.15`;
  reveal tween `0.001 → 1.0` scale over `1.2s`, cubic ease-out.
- Motes: `moteCount = 450`, `PointsMaterial` size `0.025`, opacity `0.85`, additive,
  `depthWrite:false`, vertexColors; 60% golden-pollen / 40% chlorophyll-green; recycle bounds
  `y>3.0` or `|x|>3.5`/`|z|>3.5` → respawn at `y=-2.5`, `x,z = ±1.5`.
- Camera orbit: `phi = scroll * 2π`; `y = 0.35 + sin(scroll·π)*0.8`;
  `radius = 4.2 - sin(scroll·π)*0.6`; lookAt `(lookAtXOffset, -0.15, 0)`,
  `lookAtXOffset = -0.9 * easeFactor`, ease over `scroll/0.28`; `camera.position.lerp(target, 0.025)`.
- Smoothing lerps: scroll `0.025`, mouse `0.05`, outer cursor `0.2`.
- Structure spin from mouse/time: `rotation.y += deltaTime*0.05 + mouseX*0.001`,
  `rotation.x = mouseY*0.08`. Halo spin: per-ring speeds above.
- Slide active ranges: s1 `[-0.10, 0.12]`, s2 `[0.28, 0.40]`, s3 `[0.56, 0.68]`, s4 `[0.84, 1.05]`.
- Nav target scrolls: `[0.0, 0.34, 0.62, 0.94]`.
- Title font 116px Italiana; body 16px Outfit weight 300; title color `#f4ffe9`; desc `#d1d5db`.
- Page height `min-height: 900vh`. Layout padding `0 60px 40px 60px`; columns based on `25vw` grid.
- Shader: time scale `0.08`; freqs `2.4 / 3.2 / 4.0`; angles `0.6 / -0.7 / 1.2`; wave weights
  `0.50 / 0.35 / 0.15`; `scrollDeform = scroll*5.0`; palette germination-amber→chlorophyll-green
  (values in shader); vignette `1.0 - dot(uv,uv)*0.12`; crest multiplier `1.4`;
  plane `PlaneGeometry(30,30)` at camera-local `z = -8.0`, `renderOrder -10`,
  `depthWrite/depthTest false`.

## Assets

Define once near the top of the script:
```js
const ASSET_BASE_URL = "https://YOUR_ASSET_BUCKET_URL/helix-and-harvest";
```

| Asset | Usage | Notes |
|-------|-------|-------|
| `field-macro.jpg` | Editorial image inside slide-2 mask (`#slide-2-img img` src) | Supply your own macro photography — a single kernel, a furrow of soil, a close crop of grain heads. High-contrast, one dominant subject reads best against the black stage. |
| *(optional)* `seed_pod.glb` | Optional decorative kernel mesh anchored at the base of `helixPivot`, loaded via `GLTFLoader` if supplied | Entirely optional. The hero visual — helix, markers, and halos — is 100% procedural and needs no external 3D asset to reproduce. Only add this if you want a literal seed sitting beneath the structure. |

The double helix, base-pair markers, phenotype halos, and pollen/chlorophyll motes are all generated
in code — the `GLTFLoader` import is kept available only for the optional kernel mesh above and can
be omitted entirely if you skip it. The mote texture is generated procedurally in code (no file).
Fonts come from Google Fonts (Italiana, Outfit) via the CSS `@import`.
