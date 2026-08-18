/**
 * ORBITAL SENTINEL - 3D Dashboard Application
 * =============================================
 * Three.js powered visualization of the satellite collision prevention system.
 */

// ============================================================================
// GLOBALS
// ============================================================================

let scene, camera, renderer, controls;
let earthMesh, atmosphereMesh, cloudsMesh;
let orbitLines = [], spacecraftMeshes = [], conjunctionLines = [];
let debrisParticles = null, shellMeshes = [];
let raycaster, mouse;
let simData = null;
let radarSweep = null;

// Real-time orbital motion for constellation spacecraft
const ORBIT_SPEED_MULTIPLIER = 60;
const simClockStart = Date.now();

// Visualization state
const vizState = {
    showOrbits: true,
    showSpacecraft: true,
    showConjunctions: true,
    showDebris: false,
    showShells: false,
    autoRotate: false,
    animationTime: 0,
    selectedObject: null,
    viewMode: 'geographic', // 'geographic' or 'orbital'
};

// Scale factor: Real Earth radius = 6378km, we use radius=1 in scene
const SCALE = 1.0 / 6378.137;
const EARTH_RADIUS = 1.0;

// Which metric is currently shown in the dynamic multi-tab charts
const chartState = {
    evoMetric: 'pc',       // pc | debris | kessler | fuel
    debrisMetric: 'size',  // size | altitude | lifetime
};

// Live telemetry chart (left sidebar) - fills in as a scenario plays back
const teleState = {
    scenario: null,
    history: [],      // [{ frame, t, dist, closingVel }]
    prevDist: undefined,
};

// Live B-plane (encounter plane) inset - tracks the current frame's
// projected miss vector, covariance ellipse, and hard-body-radius circle
// as a scenario plays back (see conjunction.py encounter-plane routines
// and _build_bplane_track in src/api.py for the underlying physics).
const bplaneState = {
    scenario: null,
    active: false,
};

// ============================================================================
// INITIALIZATION
// ============================================================================

async function init() {
    updateLoadStatus('Fetching simulation data...', 20);

    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 15000);
        const response = await fetch('/api/all', { signal: controller.signal });
        clearTimeout(timeoutId);
        if (!response.ok) {
            throw new Error(`Server returned ${response.status}`);
        }
        simData = await response.json();
        updateLoadStatus('Building 3D scene...', 50);
    } catch (err) {
        console.error('Failed to fetch simulation data:', err);
        const isTimeout = err.name === 'AbortError';
        updateLoadStatus(
            isTimeout
                ? 'Server busy (simulation running?). Retrying...'
                : 'Error connecting to server. Retrying...',
            20
        );
        setTimeout(init, 2000);
        return;
    }

    initThreeJS();
    updateLoadStatus('Creating Earth...', 60);

    createEarth();
    createRadarSweep();
    updateLoadStatus('Generating orbits...', 70);

    createOrbits();
    createSpacecraft();
    updateLoadStatus('Processing conjunctions...', 80);

    createConjunctions();
    createDebris();
    createAltitudeShells();
    updateLoadStatus('Populating dashboard...', 90);

    populateDashboard();
    setupControls();
    setupInteraction();
    initSimulationPanel();
    initChartTabs();
    initFullSimulationControl();
    initOrbits3dPanel();
    drawTelemetryChart();
    drawBplaneChart();

    setInterval(updateClock, 1000);

    updateLoadStatus('Ready', 100);
    setTimeout(showDashboard, 600);

    animate();
}

function updateLoadStatus(text, progress) {
    const statusEl = document.getElementById('load-status');
    const progressEl = document.getElementById('load-progress');
    if (statusEl) statusEl.textContent = text;
    if (progressEl) progressEl.style.width = progress + '%';
}

function showDashboard() {
    document.getElementById('loading-screen').classList.add('fade-out');
    document.getElementById('dashboard').classList.remove('hidden');
    setTimeout(() => {
        document.getElementById('loading-screen').style.display = 'none';
        onWindowResize();
    }, 600);
}

// ============================================================================
// THREE.JS SETUP
// ============================================================================

function initThreeJS() {
    const container = document.getElementById('three-viewport');

    // Scene
    scene = new THREE.Scene();

    // Camera
    camera = new THREE.PerspectiveCamera(
        45,
        container.clientWidth / container.clientHeight,
        0.01,
        100
    );
    camera.position.set(3, 2, 3);

    // Renderer
    renderer = new THREE.WebGLRenderer({
        antialias: true,
        alpha: true,
        powerPreference: 'high-performance'
    });
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.2;
    container.appendChild(renderer.domElement);

    // Controls
    controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.minDistance = 1.3;
    controls.maxDistance = 15;
    controls.rotateSpeed = 0.5;

    // Lighting
    const ambientLight = new THREE.AmbientLight(0x1a2240, 0.8);
    scene.add(ambientLight);

    const sunLight = new THREE.DirectionalLight(0xffffff, 1.8);
    sunLight.position.set(5, 3, 4);
    scene.add(sunLight);

    const rimLight = new THREE.DirectionalLight(0x4488ff, 0.3);
    rimLight.position.set(-3, -1, -2);
    scene.add(rimLight);

    // Starfield
    createStarfield();

    // Raycaster for interaction
    raycaster = new THREE.Raycaster();
    mouse = new THREE.Vector2();

    window.addEventListener('resize', onWindowResize);
}

function createStarfield() {
    const starsGeometry = new THREE.BufferGeometry();
    const starCount = 4000;
    const positions = new Float32Array(starCount * 3);
    const colors = new Float32Array(starCount * 3);
    const sizes = new Float32Array(starCount);

    for (let i = 0; i < starCount; i++) {
        const theta = Math.random() * Math.PI * 2;
        const phi = Math.acos(2 * Math.random() - 1);
        const r = 40 + Math.random() * 20;

        positions[i * 3] = r * Math.sin(phi) * Math.cos(theta);
        positions[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
        positions[i * 3 + 2] = r * Math.cos(phi);

        // Slight color variation
        const temp = 0.8 + Math.random() * 0.2;
        colors[i * 3] = temp;
        colors[i * 3 + 1] = temp;
        colors[i * 3 + 2] = 0.9 + Math.random() * 0.1;

        sizes[i] = 0.5 + Math.random() * 1.5;
    }

    starsGeometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    starsGeometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    starsGeometry.setAttribute('size', new THREE.BufferAttribute(sizes, 1));

    const starsMaterial = new THREE.PointsMaterial({
        size: 0.05,
        vertexColors: true,
        transparent: true,
        opacity: 0.8,
        sizeAttenuation: true
    });

    const stars = new THREE.Points(starsGeometry, starsMaterial);
    scene.add(stars);
}

// ============================================================================
// EARTH
// ============================================================================

function createEarth() {
    // Earth sphere with procedural shader
    const earthGeometry = new THREE.SphereGeometry(EARTH_RADIUS, 64, 64);

    // Custom shader material for Earth
    const earthMaterial = new THREE.ShaderMaterial({
        uniforms: {
            sunDirection: { value: new THREE.Vector3(1, 0.5, 0.7).normalize() },
            earthColor1: { value: new THREE.Color(0x0a1628) },   // Dark ocean
            earthColor2: { value: new THREE.Color(0x0d2847) },   // Deep ocean
            landColor1: { value: new THREE.Color(0x1a3a2a) },    // Dark land
            landColor2: { value: new THREE.Color(0x2d5a3a) },    // Land highlight
            atmosphereColor: { value: new THREE.Color(0x4488ff) },
            time: { value: 0 }
        },
        vertexShader: `
            varying vec3 vNormal;
            varying vec3 vPosition;
            varying vec2 vUv;

            void main() {
                vNormal = normalize(normalMatrix * normal);
                vPosition = (modelViewMatrix * vec4(position, 1.0)).xyz;
                vUv = uv;
                gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
            }
        `,
        fragmentShader: `
            uniform vec3 sunDirection;
            uniform vec3 earthColor1;
            uniform vec3 earthColor2;
            uniform vec3 landColor1;
            uniform vec3 landColor2;
            uniform vec3 atmosphereColor;
            uniform float time;

            varying vec3 vNormal;
            varying vec3 vPosition;
            varying vec2 vUv;

            // Simplex noise approximation
            float hash(vec2 p) {
                return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
            }

            float noise(vec2 p) {
                vec2 i = floor(p);
                vec2 f = fract(p);
                f = f * f * (3.0 - 2.0 * f);
                float a = hash(i);
                float b = hash(i + vec2(1.0, 0.0));
                float c = hash(i + vec2(0.0, 1.0));
                float d = hash(i + vec2(1.0, 1.0));
                return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
            }

            float fbm(vec2 p) {
                float value = 0.0;
                float amplitude = 0.5;
                for (int i = 0; i < 5; i++) {
                    value += amplitude * noise(p);
                    p *= 2.0;
                    amplitude *= 0.5;
                }
                return value;
            }

            void main() {
                // Generate continent-like pattern
                vec2 uv = vUv * 8.0;
                float continents = fbm(uv + vec2(time * 0.001));
                float landMask = smoothstep(0.45, 0.55, continents);

                // Ocean colors
                vec3 ocean = mix(earthColor1, earthColor2, fbm(vUv * 12.0));

                // Land colors
                vec3 land = mix(landColor1, landColor2, fbm(vUv * 20.0));

                // Mix land and ocean
                vec3 surface = mix(ocean, land, landMask);

                // Lighting
                float diffuse = max(dot(vNormal, sunDirection), 0.0);
                float ambient = 0.08;
                float lighting = ambient + diffuse * 0.9;

                // Fresnel (atmosphere edge glow)
                vec3 viewDir = normalize(-vPosition);
                float fresnel = pow(1.0 - max(dot(viewDir, vNormal), 0.0), 3.0);
                vec3 atmosphereGlow = atmosphereColor * fresnel * 0.4;

                // City lights on dark side
                float nightMask = smoothstep(0.0, -0.15, diffuse);
                float cities = step(0.7, fbm(vUv * 40.0)) * landMask;
                vec3 cityLights = vec3(1.0, 0.85, 0.5) * cities * nightMask * 0.6;

                vec3 color = surface * lighting + atmosphereGlow + cityLights;
                gl_FragColor = vec4(color, 1.0);
            }
        `
    });

    earthMesh = new THREE.Mesh(earthGeometry, earthMaterial);
    scene.add(earthMesh);

    // Atmosphere glow
    const atmosphereGeometry = new THREE.SphereGeometry(EARTH_RADIUS * 1.015, 64, 64);
    const atmosphereMaterial = new THREE.ShaderMaterial({
        uniforms: {
            sunDirection: { value: new THREE.Vector3(1, 0.5, 0.7).normalize() }
        },
        vertexShader: `
            varying vec3 vNormal;
            varying vec3 vPosition;
            void main() {
                vNormal = normalize(normalMatrix * normal);
                vPosition = (modelViewMatrix * vec4(position, 1.0)).xyz;
                gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
            }
        `,
        fragmentShader: `
            uniform vec3 sunDirection;
            varying vec3 vNormal;
            varying vec3 vPosition;
            void main() {
                vec3 viewDir = normalize(-vPosition);
                float fresnel = pow(1.0 - max(dot(viewDir, vNormal), 0.0), 4.0);
                float sunFactor = max(dot(vNormal, sunDirection), 0.0) * 0.5 + 0.5;
                vec3 color = mix(
                    vec3(0.1, 0.3, 1.0),
                    vec3(0.3, 0.7, 1.0),
                    sunFactor
                );
                gl_FragColor = vec4(color, fresnel * 0.6);
            }
        `,
        transparent: true,
        side: THREE.FrontSide,
        depthWrite: false,
        blending: THREE.AdditiveBlending
    });

    atmosphereMesh = new THREE.Mesh(atmosphereGeometry, atmosphereMaterial);
    scene.add(atmosphereMesh);

    // Outer glow ring
    const outerGlowGeometry = new THREE.SphereGeometry(EARTH_RADIUS * 1.08, 48, 48);
    const outerGlowMaterial = new THREE.ShaderMaterial({
        vertexShader: `
            varying vec3 vNormal;
            varying vec3 vPosition;
            void main() {
                vNormal = normalize(normalMatrix * normal);
                vPosition = (modelViewMatrix * vec4(position, 1.0)).xyz;
                gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
            }
        `,
        fragmentShader: `
            varying vec3 vNormal;
            varying vec3 vPosition;
            void main() {
                vec3 viewDir = normalize(-vPosition);
                float fresnel = pow(1.0 - max(dot(viewDir, vNormal), 0.0), 6.0);
                vec3 color = vec3(0.2, 0.5, 1.0);
                gl_FragColor = vec4(color, fresnel * 0.25);
            }
        `,
        transparent: true,
        side: THREE.BackSide,
        depthWrite: false,
        blending: THREE.AdditiveBlending
    });

    const outerGlow = new THREE.Mesh(outerGlowGeometry, outerGlowMaterial);
    scene.add(outerGlow);
}

function createRadarSweep() {
    const sweepGeometry = new THREE.CircleGeometry(EARTH_RADIUS * 1.3, 64, 0, Math.PI / 6);
    const sweepMaterial = new THREE.MeshBasicMaterial({
        color: 0x00d4ff,
        transparent: true,
        opacity: 0.08,
        side: THREE.DoubleSide,
        blending: THREE.AdditiveBlending,
        depthWrite: false
    });

    radarSweep = new THREE.Mesh(sweepGeometry, sweepMaterial);
    radarSweep.rotation.x = Math.PI / 2;
    scene.add(radarSweep);
}

// ============================================================================
// ORBITS
// ============================================================================

function createOrbits() {
    if (!simData || !simData.spacecraft) return;

    const orbitGroup = new THREE.Group();
    orbitGroup.name = 'orbits';

    // Find the critical pair spacecraft for highlighting
    let criticalIds = new Set();
    simData.conjunctions.forEach((conj) => {
        const id1 = conj.obj1_id || '';
        const id2 = conj.obj2_id || '';
        if ((id1.includes('CUBE') && id1.includes('0002') && id2.includes('COMSAT') && id2.includes('0003')) ||
            (id2.includes('CUBE') && id2.includes('0002') && id1.includes('COMSAT') && id1.includes('0003'))) {
            criticalIds.add(id1);
            criticalIds.add(id2);
        }
    });

    simData.spacecraft.forEach((sc, idx) => {
        if (!sc.orbit_path || sc.orbit_path.length < 3) return;

        const points = sc.orbit_path.map(p =>
            new THREE.Vector3(p[0] * SCALE, p[2] * SCALE, p[1] * SCALE)
        );

        // Close the orbit loop
        points.push(points[0]);

        const curve = new THREE.CatmullRomCurve3(points, true);
        const geometry = new THREE.BufferGeometry().setFromPoints(curve.getPoints(150));

        const isCriticalPair = criticalIds.has(sc.id);

        // Color and opacity based on whether this is the critical pair
        let color, opacity, linewidth;
        if (isCriticalPair) {
            // Bright red for critical pair orbits
            color = new THREE.Color(0xff2d55);
            opacity = 0.9;
            linewidth = 2.5;
        } else {
            // Faded background orbits
            switch (sc.type) {
                case 'COMSAT': color = new THREE.Color(0x00d4ff); break;
                case 'EOS': color = new THREE.Color(0x7b2ff7); break;
                case 'CUBE': color = new THREE.Color(0x06ffd0); break;
                case 'DEBRIS': color = new THREE.Color(0x5a6b8a); break;
                default: color = new THREE.Color(0x3a5588);
            }
            opacity = sc.type === 'DEBRIS' ? 0.08 : 0.12;
            linewidth = 0.8;
        }

        const material = new THREE.LineBasicMaterial({
            color: color,
            transparent: true,
            opacity: opacity,
            linewidth: linewidth
        });

        const line = new THREE.Line(geometry, material);
        line.userData = { type: 'orbit', spacecraft: sc, index: idx, isCritical: isCriticalPair };
        orbitGroup.add(line);
        orbitLines.push(line);
    });

    scene.add(orbitGroup);
}

// ============================================================================
// SPACECRAFT
// ============================================================================

function createSpacecraft() {
    if (!simData || !simData.spacecraft) return;

    const scGroup = new THREE.Group();
    scGroup.name = 'spacecraft';

    simData.spacecraft.forEach((sc, idx) => {
        // Position in 3D scene (swap Y/Z for Three.js coordinate system)
        const pos = new THREE.Vector3(
            sc.position[0] * SCALE,
            sc.position[2] * SCALE,
            sc.position[1] * SCALE
        );

        // Spacecraft marker
        let color, size;
        switch (sc.type) {
            case 'COMSAT':
                color = 0x00d4ff;
                size = 0.015;
                break;
            case 'EOS':
                color = 0x7b2ff7;
                size = 0.018;
                break;
            case 'CUBE':
                color = 0x06ffd0;
                size = 0.01;
                break;
            case 'DEBRIS':
                color = 0x8b9cc0;
                size = 0.012;
                break;
            default:
                color = 0xffffff;
                size = 0.012;
        }

        // Create a glowing point sprite
        const spriteMaterial = new THREE.SpriteMaterial({
            color: color,
            transparent: true,
            opacity: 0.9,
            sizeAttenuation: true
        });

        const sprite = new THREE.Sprite(spriteMaterial);
        sprite.position.copy(pos);
        sprite.scale.set(size, size, size);
        sprite.userData = { type: 'spacecraft', data: sc, index: idx };

        // Precompute the orbit path in scene-space for real-time motion
        if (sc.orbit_path && sc.orbit_path.length > 1 && sc.period_min) {
            sprite.userData.orbitPoints = sc.orbit_path.map(p =>
                new THREE.Vector3(p[0] * SCALE, p[2] * SCALE, p[1] * SCALE)
            );
            sprite.userData.periodSec = sc.period_min * 60;
        }

        scGroup.add(sprite);
        spacecraftMeshes.push(sprite);

        // Add small glow sphere for maneuverable spacecraft
        if (sc.maneuverable && sc.type !== 'DEBRIS') {
            const glowGeom = new THREE.SphereGeometry(size * 1.5, 8, 8);
            const glowMat = new THREE.MeshBasicMaterial({
                color: color,
                transparent: true,
                opacity: 0.15,
                blending: THREE.AdditiveBlending
            });
            const glow = new THREE.Mesh(glowGeom, glowMat);
            glow.position.copy(pos);
            scGroup.add(glow);
            sprite.userData.glowMesh = glow;
        }
    });

    scene.add(scGroup);
}

/**
 * Advance each constellation spacecraft sprite along its precomputed
 * orbit path in real time, sped up by ORBIT_SPEED_MULTIPLIER. Static
 * reference orbit lines and conjunction snapshots are left untouched.
 */
function updateSpacecraftPositions() {
    const elapsed = (Date.now() - simClockStart) / 1000 * ORBIT_SPEED_MULTIPLIER;

    spacecraftMeshes.forEach(sprite => {
        const orbitPoints = sprite.userData.orbitPoints;
        const periodSec = sprite.userData.periodSec;
        if (!orbitPoints || !periodSec) return;

        const fraction = (elapsed % periodSec) / periodSec;
        const idx = fraction * (orbitPoints.length - 1);
        const idxFloor = Math.floor(idx);
        const idxCeil = Math.ceil(idx);
        const t = idx - idxFloor;

        const interpolated = orbitPoints[idxFloor].clone()
            .lerp(orbitPoints[idxCeil], t);

        sprite.position.copy(interpolated);
        if (sprite.userData.glowMesh) {
            sprite.userData.glowMesh.position.copy(interpolated);
        }
    });
}

// ============================================================================
// CONJUNCTIONS
// ============================================================================

function createConjunctions() {
    if (!simData || !simData.conjunctions) return;

    const conjGroup = new THREE.Group();
    conjGroup.name = 'conjunctions';

    // Find the highest-risk conjunction for dramatic highlighting (CRITICAL > HIGH > MEDIUM)
    let criticalPairIdx = -1;
    let maxRiskScore = -1;
    const riskPriority = { 'CRITICAL': 3, 'HIGH': 2, 'MEDIUM': 1, 'LOW': 0 };
    simData.conjunctions.forEach((conj, idx) => {
        const riskScore = riskPriority[conj.risk_level] || 0;
        if (riskScore > maxRiskScore) {
            maxRiskScore = riskScore;
            criticalPairIdx = idx;
        }
    });

    simData.conjunctions.forEach((conj, idx) => {
        const pos1 = new THREE.Vector3(
            conj.obj1_pos[0] * SCALE,
            conj.obj1_pos[2] * SCALE,
            conj.obj1_pos[1] * SCALE
        );
        const pos2 = new THREE.Vector3(
            conj.obj2_pos[0] * SCALE,
            conj.obj2_pos[2] * SCALE,
            conj.obj2_pos[1] * SCALE
        );

        // Conjunction line color based on risk
        let color;
        switch (conj.risk_level) {
            case 'CRITICAL': color = 0xff2d55; break;
            case 'HIGH': color = 0xff9500; break;
            case 'MEDIUM': color = 0xffcc00; break;
            default: color = 0x30d158;
        }

        const isCriticalPair = (idx === criticalPairIdx);

        if (isCriticalPair) {
            // DRAMATIC STYLING FOR THE COLLISION PAIR

            // 1. Bright solid connecting line between the two objects
            const brightLinePoints = [pos1, pos2];
            const brightLineGeo = new THREE.BufferGeometry().setFromPoints(brightLinePoints);
            const brightLineMat = new THREE.LineBasicMaterial({
                color: 0xff2d55,
                transparent: true,
                opacity: 1.0,
                linewidth: 4,
                blending: THREE.AdditiveBlending
            });
            const brightLine = new THREE.Line(brightLineGeo, brightLineMat);
            brightLine.userData = { type: 'conjunction_critical_line', data: conj, index: idx };
            conjGroup.add(brightLine);
            conjunctionLines.push(brightLine);

            // 2. Pulsing glow spheres around each collision object
            const pulseGlowSize = 0.045;
            const pulseGlowMat = new THREE.MeshBasicMaterial({
                color: 0xff2d55,
                transparent: true,
                opacity: 0.6,
                blending: THREE.AdditiveBlending
            });

            const glow1Geo = new THREE.SphereGeometry(pulseGlowSize, 16, 16);
            const glow1 = new THREE.Mesh(glow1Geo, pulseGlowMat.clone());
            glow1.position.copy(pos1);
            glow1.userData = { type: 'collision_glow', isPulsing: true, baseScale: 1 };
            conjGroup.add(glow1);

            const glow2Geo = new THREE.SphereGeometry(pulseGlowSize, 16, 16);
            const glow2 = new THREE.Mesh(glow2Geo, pulseGlowMat.clone());
            glow2.position.copy(pos2);
            glow2.userData = { type: 'collision_glow', isPulsing: true, baseScale: 1 };
            conjGroup.add(glow2);

            // 3. Large expanding pulse ring at midpoint
            const midpoint = pos1.clone().add(pos2).multiplyScalar(0.5);
            const pulseRingGeo = new THREE.RingGeometry(0.015, 0.035, 32);
            const pulseRingMat = new THREE.MeshBasicMaterial({
                color: 0xff2d55,
                transparent: true,
                opacity: 0.8,
                side: THREE.DoubleSide,
                blending: THREE.AdditiveBlending
            });
            const pulseRing = new THREE.Mesh(pulseRingGeo, pulseRingMat);
            pulseRing.position.copy(midpoint);
            pulseRing.lookAt(camera.position);
            pulseRing.userData = { type: 'collision_pulse_ring', isPulsing: true, baseScale: 1 };
            conjGroup.add(pulseRing);

            // 4. Bright marker at midpoint (rotating octahedron)
            const criticalMarkerGeo = new THREE.OctahedronGeometry(0.018, 1);
            const criticalMarkerMat = new THREE.MeshBasicMaterial({
                color: 0xff2d55,
                transparent: true,
                opacity: 1.0,
                blending: THREE.AdditiveBlending
            });
            const criticalMarker = new THREE.Mesh(criticalMarkerGeo, criticalMarkerMat);
            criticalMarker.position.copy(midpoint);
            criticalMarker.userData = { type: 'conjunction_critical_marker', isRotating: true };
            conjGroup.add(criticalMarker);

            // 5. TCA Zone: Semi-transparent sphere (0.05 radius) with red-to-yellow gradient
            const tcaZoneRadius = 0.05;
            const tcaZoneGeo = new THREE.SphereGeometry(tcaZoneRadius, 32, 32);
            
            // Create vertex colors for radial gradient (red center to yellow surface)
            const positionAttr = tcaZoneGeo.getAttribute('position');
            const colors = new Float32Array(positionAttr.count * 3);
            const redColor = new THREE.Color(0xff2d55);    // Red
            const yellowColor = new THREE.Color(0xffcc00); // Yellow
            
            for (let i = 0; i < positionAttr.count; i++) {
                const x = positionAttr.getX(i);
                const y = positionAttr.getY(i);
                const z = positionAttr.getZ(i);
                
                // Normalize position to get distance from center (0 to 1)
                const distFromCenter = Math.sqrt(x * x + y * y + z * z);
                
                // Blend from red (center, distFromCenter ≈ 0) to yellow (surface, distFromCenter ≈ 1)
                const blendFactor = Math.min(distFromCenter / tcaZoneRadius, 1.0);
                const color = new THREE.Color().lerpColors(redColor, yellowColor, blendFactor);
                
                colors[i * 3] = color.r;
                colors[i * 3 + 1] = color.g;
                colors[i * 3 + 2] = color.b;
            }
            tcaZoneGeo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
            
            const tcaZoneMat = new THREE.MeshBasicMaterial({
                vertexColors: true,
                transparent: true,
                opacity: 0.4,  // Base opacity will be animated
                blending: THREE.AdditiveBlending,
                side: THREE.FrontSide,
                wireframe: false
            });
            
            const tcaZoneMesh = new THREE.Mesh(tcaZoneGeo, tcaZoneMat);
            tcaZoneMesh.position.copy(midpoint);
            tcaZoneMesh.userData = { 
                type: 'tca_zone',
                isAnimating: true,
                baseOpacity: 0.4,
                opacityMin: 0.3,
                opacityMax: 0.5,
                frequency: 1.5  // Hz (1.5 cycles per second for smoother animation)
            };
            conjGroup.add(tcaZoneMesh);

        } else {
            // Standard styling for non-critical conjunctions (subtle background)

            // Dashed line between objects
            const points = [pos1, pos2];
            const geometry = new THREE.BufferGeometry().setFromPoints(points);
            const material = new THREE.LineDashedMaterial({
                color: color,
                dashSize: 0.02,
                gapSize: 0.01,
                transparent: true,
                opacity: 0.3,  // Reduced opacity for background
                linewidth: 1
            });

            const line = new THREE.Line(geometry, material);
            line.computeLineDistances();
            line.userData = { type: 'conjunction', data: conj, index: idx };
            conjGroup.add(line);
            conjunctionLines.push(line);

            // Subtle marker at midpoint
            const midpoint = pos1.clone().add(pos2).multiplyScalar(0.5);
            const markerGeom = new THREE.OctahedronGeometry(0.008, 0);
            const markerMat = new THREE.MeshBasicMaterial({
                color: color,
                transparent: true,
                opacity: 0.4,
            });
            const marker = new THREE.Mesh(markerGeom, markerMat);
            marker.position.copy(midpoint);
            marker.userData = { type: 'conjunction', data: conj, index: idx };
            conjGroup.add(marker);

            // Subtle glow around non-critical high-risk conjunctions
            if (conj.risk_level === 'HIGH') {
                const glowGeom = new THREE.SphereGeometry(0.02, 12, 12);
                const glowMat = new THREE.MeshBasicMaterial({
                    color: color,
                    transparent: true,
                    opacity: 0.08,
                    blending: THREE.AdditiveBlending
                });
                const glow = new THREE.Mesh(glowGeom, glowMat);
                glow.position.copy(midpoint);
                conjGroup.add(glow);
            }
        }
    });

    scene.add(conjGroup);
}

// ============================================================================
// DEBRIS
// ============================================================================

function createDebris() {
    if (!simData || !simData.debris) return;

    const particleCount = 2000;
    const positions = new Float32Array(particleCount * 3);
    const colors = new Float32Array(particleCount * 3);
    const sizes = new Float32Array(particleCount);

    let idx = 0;
    simData.debris.forEach(d => {
        const centerPos = new THREE.Vector3(
            d.position[0] * SCALE,
            d.position[2] * SCALE,
            d.position[1] * SCALE
        );

        const fragments = Math.min(d.fragment_count_10cm, 600);
        for (let i = 0; i < fragments && idx < particleCount; i++) {
            // Spread debris in a cloud around the collision point
            const spread = 0.08;
            positions[idx * 3] = centerPos.x + (Math.random() - 0.5) * spread;
            positions[idx * 3 + 1] = centerPos.y + (Math.random() - 0.5) * spread;
            positions[idx * 3 + 2] = centerPos.z + (Math.random() - 0.5) * spread;

            // Color: red-orange for dangerous, gray for small
            const danger = Math.random();
            if (danger > 0.7) {
                colors[idx * 3] = 1.0;
                colors[idx * 3 + 1] = 0.3 + Math.random() * 0.3;
                colors[idx * 3 + 2] = 0.1;
            } else {
                colors[idx * 3] = 0.5;
                colors[idx * 3 + 1] = 0.5;
                colors[idx * 3 + 2] = 0.6;
            }

            sizes[idx] = 0.5 + Math.random() * 2.0;
            idx++;
        }
    });

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    geometry.setAttribute('size', new THREE.BufferAttribute(sizes, 1));

    const material = new THREE.PointsMaterial({
        size: 0.008,
        vertexColors: true,
        transparent: true,
        opacity: 0.7,
        sizeAttenuation: true,
        blending: THREE.AdditiveBlending
    });

    debrisParticles = new THREE.Points(geometry, material);
    debrisParticles.visible = vizState.showDebris;
    scene.add(debrisParticles);
}

// ============================================================================
// ALTITUDE SHELLS
// ============================================================================

function createAltitudeShells() {
    if (!simData || !simData.shells) return;

    const shellGroup = new THREE.Group();
    shellGroup.name = 'shells';

    // Show a few key altitude shells
    const interestingShells = simData.shells.filter(s => s.object_count > 0 || s.is_unstable);

    interestingShells.forEach(shell => {
        const altMid = (shell.alt_min_km + shell.alt_max_km) / 2;
        const radius = (6378.137 + altMid) * SCALE;

        const geometry = new THREE.RingGeometry(radius - 0.002, radius + 0.002, 64);
        const color = shell.is_unstable ? 0xff2d55 : 0x2a3f66;
        const material = new THREE.MeshBasicMaterial({
            color: color,
            transparent: true,
            opacity: shell.is_unstable ? 0.3 : 0.1,
            side: THREE.DoubleSide,
            blending: THREE.AdditiveBlending
        });

        const ring = new THREE.Mesh(geometry, material);
        ring.rotation.x = Math.PI / 2;
        ring.userData = { type: 'shell', data: shell };
        shellGroup.add(ring);
        shellMeshes.push(ring);
    });

    shellGroup.visible = vizState.showShells;
    scene.add(shellGroup);
}

// ============================================================================
// DASHBOARD UI POPULATION
// ============================================================================

/**
 * Animate a numeric element's textContent from 0 up to targetValue using
 * an ease-out cubic curve (same easing style as animateCamera).
 */
function animateCountUp(element, targetValue, opts) {
    if (!element) return;
    opts = opts || {};
    const duration = opts.duration || 1200;
    const decimals = opts.decimals || 0;
    const prefix = opts.prefix || '';
    const suffix = opts.suffix || '';
    const startTime = Date.now();

    function step() {
        const elapsed = Date.now() - startTime;
        const t = Math.min(elapsed / duration, 1);
        const eased = 1 - Math.pow(1 - t, 3); // Ease out cubic
        const current = targetValue * eased;

        element.textContent = prefix + current.toFixed(decimals) + suffix;

        if (t < 1) requestAnimationFrame(step);
    }
    step();
}

function populateDashboard() {
    if (!simData) return;

    const risk = simData.risk_metrics;

    // Header stats (staggered count-up animation for visual cascade)
    setTimeout(() => animateCountUp(document.getElementById('h-objects'), risk.total_spacecraft), 0);
    setTimeout(() => animateCountUp(document.getElementById('h-conjunctions'), risk.total_conjunctions), 100);

    const threatLevel = risk.critical_conjunctions > 0 ? 'ELEVATED' :
                        risk.high_risk_conjunctions > 0 ? 'GUARDED' : 'NOMINAL';
    const threatEl = document.getElementById('h-threat');
    threatEl.textContent = threatLevel;
    threatEl.className = 'stat-value ' + (
        threatLevel === 'ELEVATED' ? 'warning' :
        threatLevel === 'GUARDED' ? '' : 'success'
    );

    // Risk metrics (staggered count-up)
    setTimeout(() => animateCountUp(document.getElementById('m-critical'), risk.critical_conjunctions), 200);
    setTimeout(() => animateCountUp(document.getElementById('m-high'), risk.high_risk_conjunctions), 300);
    setTimeout(() => animateCountUp(document.getElementById('m-maneuvers'), risk.maneuvers_planned), 400);
    setTimeout(() => animateCountUp(document.getElementById('m-fuel'), risk.total_fuel_cost_ms, { decimals: 1 }), 500);

    // Toggle the critical-card pulse glow only when there are active critical conjunctions
    const criticalCard = document.querySelector('.metric-card.critical');
    if (criticalCard) {
        criticalCard.classList.toggle('has-critical-risk', risk.critical_conjunctions > 0);
    }

    // Constellation breakdown
    const types = { COMSAT: 0, EOS: 0, CUBE: 0, DEBRIS: 0 };
    simData.spacecraft.forEach(sc => {
        if (types.hasOwnProperty(sc.type)) types[sc.type]++;
    });
    document.getElementById('c-comsat').textContent = types.COMSAT;
    document.getElementById('c-eos').textContent = types.EOS;
    document.getElementById('c-cube').textContent = types.CUBE;
    document.getElementById('c-debris').textContent = types.DEBRIS;

    // Conjunction list
    populateConjunctionList();

    // Charts
    drawRiskTimeline();
    drawRiskEvolutionChart();
    drawDebrisAnalysisChart();
    updateDebrisSummary();

    // Clock
    updateClock();
}

function populateConjunctionList() {
    const container = document.getElementById('conjunction-list');
    container.innerHTML = '';

    simData.conjunctions.forEach((conj, idx) => {
        const item = document.createElement('div');
        item.className = 'conjunction-item' +
            (conj.risk_level === 'CRITICAL' ? ' critical-glow' : '');
        item.innerHTML = `
            <div class="conj-header">
                <span class="conj-objects">${conj.obj1_id} ↔ ${conj.obj2_id}</span>
                <span class="conj-risk-badge ${conj.risk_level}">${conj.risk_level}</span>
            </div>
            <div class="conj-details">
                <span>Pc: ${conj.probability_of_collision.toExponential(1)}</span>
                <span>Miss: ${conj.miss_distance_km.toFixed(2)} km</span>
                <span>TCA: T+${conj.tca_hours.toFixed(1)}h</span>
            </div>
        `;
        item.addEventListener('click', () => focusOnConjunction(idx));
        container.appendChild(item);
    });
}

// ============================================================================
// CHARTS (Canvas 2D)
// ============================================================================

function drawRiskTimeline() {
    const canvas = document.getElementById('risk-chart');
    if (!canvas || !simData.risk_timeline) return;

    const ctx = canvas.getContext('2d');
    const w = canvas.width;
    const h = canvas.height;
    const padding = { top: 10, right: 10, bottom: 20, left: 35 };

    ctx.clearRect(0, 0, w, h);

    const data = simData.risk_timeline;
    const maxRisk = Math.max(...data.map(d => d.total_risk)) * 1.1;

    const plotW = w - padding.left - padding.right;
    const plotH = h - padding.top - padding.bottom;

    // Grid lines
    ctx.strokeStyle = '#1e2a42';
    ctx.lineWidth = 0.5;
    for (let i = 0; i <= 4; i++) {
        const y = padding.top + (plotH / 4) * i;
        ctx.beginPath();
        ctx.moveTo(padding.left, y);
        ctx.lineTo(w - padding.right, y);
        ctx.stroke();
    }

    // Risk line with gradient fill
    const gradient = ctx.createLinearGradient(0, padding.top, 0, h - padding.bottom);
    gradient.addColorStop(0, 'rgba(255, 45, 85, 0.3)');
    gradient.addColorStop(1, 'rgba(255, 45, 85, 0.0)');

    // Fill area
    ctx.beginPath();
    ctx.moveTo(padding.left, h - padding.bottom);
    data.forEach((d, i) => {
        const x = padding.left + (i / (data.length - 1)) * plotW;
        const y = padding.top + plotH - (d.total_risk / maxRisk) * plotH;
        ctx.lineTo(x, y);
    });
    ctx.lineTo(padding.left + plotW, h - padding.bottom);
    ctx.closePath();
    ctx.fillStyle = gradient;
    ctx.fill();

    // Line
    ctx.beginPath();
    data.forEach((d, i) => {
        const x = padding.left + (i / (data.length - 1)) * plotW;
        const y = padding.top + plotH - (d.total_risk / maxRisk) * plotH;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    });
    ctx.strokeStyle = '#ff2d55';
    ctx.lineWidth = 1.5;
    ctx.stroke();

    // Axes labels
    ctx.fillStyle = '#5a6b8a';
    ctx.font = '9px JetBrains Mono';
    ctx.textAlign = 'center';
    ctx.fillText('0h', padding.left, h - 4);
    ctx.fillText('12h', padding.left + plotW / 2, h - 4);
    ctx.fillText('24h', padding.left + plotW, h - 4);

    ctx.textAlign = 'right';
    ctx.fillText('0', padding.left - 4, h - padding.bottom);
    ctx.fillText(maxRisk.toExponential(0), padding.left - 4, padding.top + 8);
}

// ============================================================================
// DYNAMIC CHART: RISK EVOLUTION (multi-year projection, replaces risk_evolution.png)
// ============================================================================

const EVO_METRIC_CONFIG = {
    pc: {
        key: 'total_collision_probability',
        label: 'Collision Probability',
        color: '#ff2d55',
        log: true,
        fill: true,
    },
    debris: {
        key: 'total_expected_debris',
        label: 'Expected Debris Fragments',
        color: '#00d4ff',
        log: false,
        fill: true,
    },
    kessler: {
        key: 'kessler_risk_index',
        label: 'Kessler Syndrome Index',
        color: '#7b2ff7',
        log: false,
        fill: true,
        fixedMax: 1.0,
        threshold: 0.5,
    },
    fuel: {
        key: 'fuel_consumed_total_ms',
        label: 'Fuel Consumed [m/s]',
        color: '#30d158',
        log: false,
        fill: true,
    },
};

function drawRiskEvolutionChart() {
    const canvas = document.getElementById('risk-evolution-chart');
    const data = simData && simData.risk_evolution;
    if (!canvas || !data || data.length === 0) return;

    const cfg = EVO_METRIC_CONFIG[chartState.evoMetric] || EVO_METRIC_CONFIG.pc;
    const ctx = canvas.getContext('2d');
    const w = canvas.width;
    const h = canvas.height;
    const padding = { top: 10, right: 10, bottom: 20, left: 40 };

    ctx.clearRect(0, 0, w, h);

    const values = data.map(d => Math.max(d[cfg.key], cfg.log ? 1e-12 : 0));
    let maxVal = cfg.fixedMax !== undefined ? cfg.fixedMax : Math.max(...values) * 1.1;
    if (maxVal <= 0) maxVal = 1;
    const minVal = cfg.log ? Math.min(...values) : 0;

    const plotW = w - padding.left - padding.right;
    const plotH = h - padding.top - padding.bottom;

    const yFor = (v) => {
        if (cfg.log) {
            const logMax = Math.log10(maxVal);
            const logMin = Math.log10(Math.max(minVal, maxVal * 1e-8));
            const t = (Math.log10(Math.max(v, 1e-12)) - logMin) / Math.max(logMax - logMin, 1e-9);
            return padding.top + plotH - Math.max(0, Math.min(1, t)) * plotH;
        }
        return padding.top + plotH - (v / maxVal) * plotH;
    };

    // Grid lines
    ctx.strokeStyle = '#1e2a42';
    ctx.lineWidth = 0.5;
    for (let i = 0; i <= 4; i++) {
        const y = padding.top + (plotH / 4) * i;
        ctx.beginPath();
        ctx.moveTo(padding.left, y);
        ctx.lineTo(w - padding.right, y);
        ctx.stroke();
    }

    // Threshold line (e.g. Kessler critical)
    if (cfg.threshold !== undefined) {
        const ty = yFor(cfg.threshold);
        ctx.strokeStyle = 'rgba(255, 45, 85, 0.5)';
        ctx.setLineDash([4, 3]);
        ctx.beginPath();
        ctx.moveTo(padding.left, ty);
        ctx.lineTo(w - padding.right, ty);
        ctx.stroke();
        ctx.setLineDash([]);
    }

    // Fill area
    if (cfg.fill) {
        const gradient = ctx.createLinearGradient(0, padding.top, 0, h - padding.bottom);
        gradient.addColorStop(0, hexToRgba(cfg.color, 0.3));
        gradient.addColorStop(1, hexToRgba(cfg.color, 0.0));

        ctx.beginPath();
        ctx.moveTo(padding.left, h - padding.bottom);
        data.forEach((d, i) => {
            const x = padding.left + (i / (data.length - 1)) * plotW;
            const y = yFor(d[cfg.key]);
            ctx.lineTo(x, y);
        });
        ctx.lineTo(padding.left + plotW, h - padding.bottom);
        ctx.closePath();
        ctx.fillStyle = gradient;
        ctx.fill();
    }

    // Line
    ctx.beginPath();
    data.forEach((d, i) => {
        const x = padding.left + (i / (data.length - 1)) * plotW;
        const y = yFor(d[cfg.key]);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    });
    ctx.strokeStyle = cfg.color;
    ctx.lineWidth = 1.5;
    ctx.stroke();

    // Axis labels
    const years = data[data.length - 1].year;
    ctx.fillStyle = '#5a6b8a';
    ctx.font = '9px JetBrains Mono';
    ctx.textAlign = 'center';
    ctx.fillText('0y', padding.left, h - 4);
    ctx.fillText(`${(years / 2).toFixed(0)}y`, padding.left + plotW / 2, h - 4);
    ctx.fillText(`${years.toFixed(0)}y`, padding.left + plotW, h - 4);

    ctx.textAlign = 'right';
    ctx.fillText(cfg.log ? maxVal.toExponential(0) : maxVal.toFixed(cfg.fixedMax ? 1 : 0),
                 padding.left - 4, padding.top + 8);
    ctx.fillText('0', padding.left - 4, h - padding.bottom);

    ctx.textAlign = 'left';
    ctx.fillStyle = cfg.color;
    ctx.font = '9px Inter';
    ctx.fillText(cfg.label, padding.left, padding.top + 2);
}

function hexToRgba(hex, alpha) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

// ============================================================================
// DYNAMIC CHART: DEBRIS ANALYSIS (replaces debris_analysis.png)
// ============================================================================

function updateDebrisSummary() {
    const el = document.getElementById('debris-summary');
    const d = simData && simData.debris_analysis;
    if (!el) return;

    if (!d) {
        el.textContent = 'No high-risk conjunction available for debris analysis.';
        return;
    }

    const typeSpan = d.is_catastrophic
        ? '<span class="catastrophic">CATASTROPHIC</span>'
        : '<span class="non-catastrophic">Non-catastrophic</span>';

    el.innerHTML = `
        ${d.object1} &harr; ${d.object2}<br>
        Type: ${typeSpan}<br>
        Fragments &gt;10cm: ${d.total_fragments_gt_10cm} &middot; &gt;1cm: ${d.total_fragments_gt_1cm}<br>
        Debris mass: ${d.debris_mass_kg.toFixed(0)} kg &middot; Mean lifetime: ${d.mean_debris_lifetime_years.toFixed(1)}y<br>
        Cascade risk: ${d.risk_to_other_spacecraft.toExponential(2)}
    `;
}

function drawDebrisAnalysisChart() {
    const canvas = document.getElementById('debris-analysis-chart');
    const d = simData && simData.debris_analysis;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const w = canvas.width;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);

    if (!d) {
        ctx.fillStyle = '#5a6b8a';
        ctx.font = '10px Inter';
        ctx.textAlign = 'center';
        ctx.fillText('No debris data available', w / 2, h / 2);
        return;
    }

    const metric = chartState.debrisMetric;
    let values, color, xLabel;
    if (metric === 'size') {
        values = d.fragment_sizes;
        color = '#00d4ff';
        xLabel = 'Fragment Size [m]';
    } else if (metric === 'altitude') {
        values = d.perigees_km.concat(d.apogees_km);
        color = '#ff9500';
        xLabel = 'Altitude [km]';
    } else {
        values = d.lifetimes_years;
        color = '#ffcc00';
        xLabel = 'Lifetime [years]';
    }

    if (!values || values.length === 0) {
        ctx.fillStyle = '#5a6b8a';
        ctx.font = '10px Inter';
        ctx.textAlign = 'center';
        ctx.fillText('No fragment data for this metric', w / 2, h / 2);
        return;
    }

    const padding = { top: 14, right: 10, bottom: 20, left: 30 };
    const plotW = w - padding.left - padding.right;
    const plotH = h - padding.top - padding.bottom;

    const minV = Math.min(...values);
    const maxV = Math.max(...values);
    const bins = 16;
    const binWidth = Math.max(maxV - minV, 1e-9) / bins;
    const histogram = new Array(bins).fill(0);
    values.forEach(v => {
        const bin = Math.min(Math.floor((v - minV) / binWidth), bins - 1);
        histogram[Math.max(bin, 0)]++;
    });

    const maxCount = Math.max(...histogram);
    const barWidth = plotW / bins - 2;

    histogram.forEach((count, i) => {
        const x = padding.left + (i / bins) * plotW + 1;
        const barH = (count / maxCount) * plotH;
        const y = padding.top + plotH - barH;
        ctx.fillStyle = hexToRgba(color, 0.75);
        ctx.fillRect(x, y, barWidth, barH);
    });

    ctx.fillStyle = '#5a6b8a';
    ctx.font = '9px JetBrains Mono';
    ctx.textAlign = 'center';
    ctx.fillText(minV.toFixed(minV < 1 ? 2 : 0), padding.left, h - 4);
    ctx.fillText(maxV.toFixed(maxV < 1 ? 2 : 0), padding.left + plotW, h - 4);

    ctx.textAlign = 'left';
    ctx.fillStyle = color;
    ctx.font = '9px Inter';
    ctx.fillText(xLabel, padding.left, padding.top - 4);
}

// ============================================================================
// CHART TAB CONTROLS (risk evolution + debris analysis)
// ============================================================================

function initChartTabs() {
    document.querySelectorAll('.chart-tab[data-evo]').forEach(btn => {
        btn.addEventListener('click', (e) => {
            document.querySelectorAll('.chart-tab[data-evo]').forEach(b => b.classList.remove('active'));
            e.currentTarget.classList.add('active');
            chartState.evoMetric = e.currentTarget.dataset.evo;
            drawRiskEvolutionChart();
        });
    });

    document.querySelectorAll('.chart-tab[data-debris]').forEach(btn => {
        btn.addEventListener('click', (e) => {
            document.querySelectorAll('.chart-tab[data-debris]').forEach(b => b.classList.remove('active'));
            e.currentTarget.classList.add('active');
            chartState.debrisMetric = e.currentTarget.dataset.debris;
            drawDebrisAnalysisChart();
        });
    });
}

// ============================================================================
// FULL SIMULATION RUN (regenerates all data + charts + 3D scene)
// ============================================================================

function initFullSimulationControl() {
    const btn = document.getElementById('fullsim-run-btn');
    if (!btn) return;
    btn.addEventListener('click', runFullSimulation);
}

async function runFullSimulation() {
    const btn = document.getElementById('fullsim-run-btn');
    const status = document.getElementById('fullsim-status');
    if (!btn || !status) return;

    btn.disabled = true;
    status.textContent = 'RUNNING (~30-60s)...';
    status.className = 'sim-status-badge running';

    try {
        const res = await fetch('/api/run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ seed: Date.now() % 100000 }),
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.error || `Request failed (${res.status})`);
        }

        // Fetch the fresh dataset and rebuild everything
        const allRes = await fetch('/api/all');
        simData = await allRes.json();

        rebuildScene();
        populateDashboard();
        refreshOrbits3dPanel();

        status.textContent = 'COMPLETE';
        status.className = 'sim-status-badge complete';
    } catch (err) {
        console.error('Full simulation run failed:', err);
        status.textContent = 'ERROR';
        status.className = 'sim-status-badge error';
    } finally {
        btn.disabled = false;
        setTimeout(() => {
            if (status.textContent !== 'RUNNING...') {
                status.textContent = 'IDLE';
                status.className = 'sim-status-badge idle';
            }
        }, 2500);
    }
}

/**
 * Tear down and rebuild the parts of the 3D scene that depend on
 * simData (orbits, spacecraft, conjunctions, debris, altitude shells),
 * so a fresh simulation run is reflected in the viewport without a
 * full page reload.
 */
function rebuildScene() {
    ['orbits', 'spacecraft', 'conjunctions', 'shells'].forEach(name => {
        const group = scene.getObjectByName(name);
        if (group) scene.remove(group);
    });
    if (debrisParticles) {
        scene.remove(debrisParticles);
        debrisParticles = null;
    }

    orbitLines = [];
    spacecraftMeshes = [];
    conjunctionLines = [];
    shellMeshes = [];

    createOrbits();
    createSpacecraft();
    createConjunctions();
    createDebris();
    createAltitudeShells();

    // Re-apply current visibility toggles
    const orbitsGroup = scene.getObjectByName('orbits');
    if (orbitsGroup) orbitsGroup.visible = vizState.showOrbits;
    const scGroup = scene.getObjectByName('spacecraft');
    if (scGroup) scGroup.visible = vizState.showSpacecraft;
    const conjGroup = scene.getObjectByName('conjunctions');
    if (conjGroup) conjGroup.visible = vizState.showConjunctions;
    const shellGroup = scene.getObjectByName('shells');
    if (shellGroup) shellGroup.visible = vizState.showShells;
    if (debrisParticles) debrisParticles.visible = vizState.showDebris;
}

// ============================================================================
// ORBITS 3D LIVE PLOT (Plotly.js) - dynamic, dark-themed, rotatable
// replacement for the old static matplotlib PNG preview. Shows only the
// red/danger elements: debris orbits and conjunctions.
// ============================================================================

let orbits3dAutoRotateTimer = null;

/** Build Plotly traces showing only the red (danger) elements: debris orbits/positions and conjunctions. */
function buildOrbits3dTraces() {
    if (!simData || !simData.spacecraft || simData.spacecraft.length === 0) return [];

    const traces = [];

    // Debris orbit path lines (single red trace, nulls break the line
    // between individual debris objects).
    const debrisPath = { x: [], y: [], z: [] };
    simData.spacecraft.forEach(sc => {
        const type = sc.type || (sc.id || '').split('_')[0];
        if (type !== 'DEBRIS') return;
        if (!sc.orbit_path || sc.orbit_path.length < 2) return;
        sc.orbit_path.forEach(p => {
            debrisPath.x.push(p[0]);
            debrisPath.y.push(p[1]);
            debrisPath.z.push(p[2]);
        });
        debrisPath.x.push(null);
        debrisPath.y.push(null);
        debrisPath.z.push(null);
    });

    if (debrisPath.x.length > 0) {
        traces.push({
            type: 'scatter3d',
            mode: 'lines',
            x: debrisPath.x, y: debrisPath.y, z: debrisPath.z,
            line: { color: '#ff6b6b', width: 1.5 },
            opacity: 0.5,
            name: 'Debris/Defunct',
            hoverinfo: 'skip',
        });
    }

    // Current debris positions
    const debrisPos = { x: [], y: [], z: [], text: [] };
    simData.spacecraft.forEach(sc => {
        const type = sc.type || (sc.id || '').split('_')[0];
        if (type !== 'DEBRIS') return;
        debrisPos.x.push(sc.position[0]);
        debrisPos.y.push(sc.position[1]);
        debrisPos.z.push(sc.position[2]);
        debrisPos.text.push(`${sc.name || sc.id}<br>Alt: ${sc.altitude_km.toFixed(0)} km`);
    });

    if (debrisPos.x.length > 0) {
        traces.push({
            type: 'scatter3d',
            mode: 'markers',
            x: debrisPos.x, y: debrisPos.y, z: debrisPos.z,
            text: debrisPos.text,
            hoverinfo: 'text',
            marker: { size: 3, color: '#ff6b6b' },
            name: 'Debris/Defunct',
            showlegend: false,
        });
    }

    // Conjunction highlight lines + midpoint markers
    if (simData.conjunctions && simData.conjunctions.length > 0) {
        const cx = [], cy = [], cz = [];
        const mx = [], my = [], mz = [];
        simData.conjunctions.forEach(conj => {
            cx.push(conj.obj1_pos[0], conj.obj2_pos[0], null);
            cy.push(conj.obj1_pos[1], conj.obj2_pos[1], null);
            cz.push(conj.obj1_pos[2], conj.obj2_pos[2], null);
            mx.push((conj.obj1_pos[0] + conj.obj2_pos[0]) / 2);
            my.push((conj.obj1_pos[1] + conj.obj2_pos[1]) / 2);
            mz.push((conj.obj1_pos[2] + conj.obj2_pos[2]) / 2);
        });
        traces.push({
            type: 'scatter3d', mode: 'lines',
            x: cx, y: cy, z: cz,
            line: { color: '#ff2d55', width: 3 },
            opacity: 0.85, name: 'Conjunction', hoverinfo: 'skip',
        });
        traces.push({
            type: 'scatter3d', mode: 'markers',
            x: mx, y: my, z: mz,
            marker: { size: 4, color: '#ff2d55', symbol: 'x' },
            name: 'Conjunction', showlegend: false, hoverinfo: 'skip',
        });
    }

    return traces;
}

/** Dark-themed Plotly layout matching the dashboard's color palette. */
function buildOrbits3dLayout() {
    const axisStyle = {
        title: '',
        showbackground: true,
        backgroundcolor: '#0f1520',
        gridcolor: '#1e2a42',
        zerolinecolor: '#1e2a42',
        color: '#5a6b8a',
        showspikes: false,
    };
    return {
        paper_bgcolor: '#0a0e17',
        plot_bgcolor: '#0a0e17',
        margin: { l: 0, r: 0, t: 0, b: 0 },
        showlegend: true,
        legend: {
            font: { color: '#8b9cc0', size: 10 },
            bgcolor: 'rgba(15,21,32,0.65)',
            bordercolor: '#1e2a42',
            borderwidth: 1,
            x: 0.01, y: 0.99,
        },
        scene: {
            xaxis: axisStyle, yaxis: axisStyle, zaxis: axisStyle,
            aspectmode: 'data',
            bgcolor: '#0a0e17',
            camera: { eye: { x: 1.6, y: 1.6, z: 1.0 } },
        },
        font: { color: '#8b9cc0' },
    };
}

/** (Re)render the live orbits plot into the given div from current simData. Returns false if no data yet. */
function renderOrbits3d(divId, options) {
    const el = document.getElementById(divId);
    if (!el || typeof Plotly === 'undefined') return false;

    const traces = buildOrbits3dTraces();
    if (traces.length === 0) return false;

    const layout = buildOrbits3dLayout();
    const config = {
        displayModeBar: !!(options && options.showToolbar),
        responsive: true,
        scrollZoom: true,
    };
    Plotly.react(divId, traces, layout, config);
    return true;
}

function stopOrbits3dAutoRotate() {
    if (orbits3dAutoRotateTimer) {
        clearInterval(orbits3dAutoRotateTimer);
        orbits3dAutoRotateTimer = null;
    }
}

/** Slowly orbit the camera around the plot so the preview reads as "live" at a glance. */
function startOrbits3dAutoRotate(divId) {
    stopOrbits3dAutoRotate();
    let angle = Math.atan2(1.6, 1.6);
    const radius = Math.sqrt(1.6 * 1.6 + 1.6 * 1.6);
    orbits3dAutoRotateTimer = setInterval(() => {
        angle += 0.006;
        const eye = { x: radius * Math.cos(angle), y: radius * Math.sin(angle), z: 1.0 };
        Plotly.relayout(divId, { 'scene.camera.eye': eye }).catch(() => {});
    }, 50);
}

function initOrbits3dPanel() {
    // Note: inline preview removed, only modal functionality remains
    const modal = document.getElementById('orbits3d-modal');
    const closeBtn = document.getElementById('orbits3d-close');

    const openModal = () => {
        if (!modal) return;
        modal.classList.remove('hidden');
        // Wait a frame so the modal is visible before Plotly measures its container size
        requestAnimationFrame(() => renderOrbits3d('orbits3d-plotly-modal', { showToolbar: true }));
    };
    const closeModal = () => modal && modal.classList.add('hidden');

    if (closeBtn) closeBtn.addEventListener('click', closeModal);
    if (modal) {
        modal.addEventListener('click', (e) => { if (e.target === modal) closeModal(); });
    }
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && modal && !modal.classList.contains('hidden')) closeModal();
    });
}

/** Re-render the inline preview (and modal, if open) from the latest simData. Call after any data refresh. */
function refreshOrbits3dPanel() {
    // Update main viewport if in orbital view
    if (vizState.viewMode === 'orbital') {
        renderOrbits3d('plotly-viewport', { showToolbar: true });
        stopOrbits3dAutoRotate();
        startOrbits3dAutoRotate('plotly-viewport');
    }

    // Update modal if open
    const modal = document.getElementById('orbits3d-modal');
    if (modal && !modal.classList.contains('hidden')) {
        renderOrbits3d('orbits3d-plotly-modal', { showToolbar: true });
    }
}

// ============================================================================
// CONTROLS
// ============================================================================

function setupControls() {
    // Toggle buttons
    document.getElementById('btn-orbits').addEventListener('click', (e) => {
        vizState.showOrbits = !vizState.showOrbits;
        e.currentTarget.classList.toggle('active');
        const orbitsGroup = scene.getObjectByName('orbits');
        if (orbitsGroup) orbitsGroup.visible = vizState.showOrbits;
    });

    document.getElementById('btn-spacecraft').addEventListener('click', (e) => {
        vizState.showSpacecraft = !vizState.showSpacecraft;
        e.currentTarget.classList.toggle('active');
        const scGroup = scene.getObjectByName('spacecraft');
        if (scGroup) scGroup.visible = vizState.showSpacecraft;
    });

    document.getElementById('btn-conjunctions').addEventListener('click', (e) => {
        vizState.showConjunctions = !vizState.showConjunctions;
        e.currentTarget.classList.toggle('active');
        const conjGroup = scene.getObjectByName('conjunctions');
        if (conjGroup) conjGroup.visible = vizState.showConjunctions;
    });

    document.getElementById('btn-debris').addEventListener('click', (e) => {
        vizState.showDebris = !vizState.showDebris;
        e.currentTarget.classList.toggle('active');
        if (debrisParticles) debrisParticles.visible = vizState.showDebris;
    });

    document.getElementById('btn-shells').addEventListener('click', (e) => {
        vizState.showShells = !vizState.showShells;
        e.currentTarget.classList.toggle('active');
        const shellGroup = scene.getObjectByName('shells');
        if (shellGroup) shellGroup.visible = vizState.showShells;
    });

    document.getElementById('btn-view-mode').addEventListener('click', toggleViewMode);
    
    // Also attach to the new inline toggle
    const viewModeToggle = document.getElementById('view-mode-toggle');
    if (viewModeToggle) {
        viewModeToggle.addEventListener('click', toggleViewMode);
    }

    document.getElementById('btn-autorotate').addEventListener('click', (e) => {
        vizState.autoRotate = !vizState.autoRotate;
        e.currentTarget.classList.toggle('active');
        controls.autoRotate = vizState.autoRotate;
        controls.autoRotateSpeed = 0.5;
    });

    document.getElementById('btn-reset').addEventListener('click', () => {
        camera.position.set(3, 2, 3);
        controls.target.set(0, 0, 0);
        controls.update();
    });
}

// ============================================================================
// VIEW MODE TOGGLE (Geographic ↔ Orbital Elements)
// ============================================================================

function toggleViewMode() {
    vizState.viewMode = vizState.viewMode === 'geographic' ? 'orbital' : 'geographic';
    
    const threeViewport = document.getElementById('three-viewport');
    const plotlyViewport = document.getElementById('plotly-viewport');
    const viewLabel = document.getElementById('view-mode-text');
    const viewToggle = document.getElementById('view-mode-toggle');
    
    if (vizState.viewMode === 'orbital') {
        // Switch to Plotly view
        threeViewport.classList.add('hidden');
        plotlyViewport.classList.remove('hidden');
        viewLabel.textContent = 'Orbital Elements';
        viewToggle.classList.add('orbital');
        
        // Render the Plotly plot
        if (simData) {
            renderOrbits3d('plotly-viewport', { showToolbar: true });
            startOrbits3dAutoRotate('plotly-viewport');
        }
    } else {
        // Switch to Three.js geographic view
        threeViewport.classList.remove('hidden');
        plotlyViewport.classList.add('hidden');
        viewLabel.textContent = 'Geographic View';
        viewToggle.classList.remove('orbital');
        stopOrbits3dAutoRotate();
        
        // Trigger a resize to ensure Three.js re-renders properly
        onWindowResize();
    }
}

// ============================================================================
// INTERACTION
// ============================================================================

function setupInteraction() {
    const container = document.getElementById('three-viewport');
    container.addEventListener('mousemove', onMouseMove);
    container.addEventListener('click', onMouseClick);
}

function onMouseMove(event) {
    const container = document.getElementById('three-viewport');
    const rect = container.getBoundingClientRect();
    mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

    raycaster.setFromCamera(mouse, camera);

    // Check intersections with spacecraft
    const intersects = raycaster.intersectObjects(spacecraftMeshes);
    const tooltip = document.getElementById('info-tooltip');

    if (intersects.length > 0) {
        const obj = intersects[0].object;
        const data = obj.userData.data;

        if (data) {
            tooltip.classList.remove('hidden');
            tooltip.style.left = (event.clientX - container.getBoundingClientRect().left + 15) + 'px';
            tooltip.style.top = (event.clientY - container.getBoundingClientRect().top - 10) + 'px';

            document.getElementById('tooltip-header').textContent = data.name || data.id;
            document.getElementById('tooltip-body').innerHTML = `
                Alt: ${data.altitude_km.toFixed(0)} km<br>
                Inc: ${data.inclination_deg.toFixed(1)}&deg;<br>
                Mass: ${data.mass.toFixed(0)} kg<br>
                ${data.maneuverable ? '&#9989; Maneuverable' : '&#10060; Non-maneuverable'}<br>
                Fuel: ${data.fuel_remaining_ms.toFixed(1)} m/s
            `;
        }
        container.style.cursor = 'pointer';
    } else {
        tooltip.classList.add('hidden');
        container.style.cursor = 'default';
    }
}

function onMouseClick(event) {
    const container = document.getElementById('three-viewport');
    const rect = container.getBoundingClientRect();
    mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

    raycaster.setFromCamera(mouse, camera);
    const intersects = raycaster.intersectObjects(spacecraftMeshes);

    if (intersects.length > 0) {
        const obj = intersects[0].object;
        const pos = obj.position.clone();

        // Smooth camera move toward object
        const targetPos = pos.clone().multiplyScalar(1.5);
        animateCamera(targetPos);
    }
}

function focusOnConjunction(idx) {
    if (!simData.conjunctions[idx]) return;

    const conj = simData.conjunctions[idx];
    const midPos = new THREE.Vector3(
        (conj.obj1_pos[0] + conj.obj2_pos[0]) / 2 * SCALE,
        (conj.obj1_pos[2] + conj.obj2_pos[2]) / 2 * SCALE,
        (conj.obj1_pos[1] + conj.obj2_pos[1]) / 2 * SCALE
    );

    const cameraTarget = midPos.clone().normalize().multiplyScalar(2.5);
    animateCamera(cameraTarget, midPos);
}

function animateCamera(targetPosition, lookAt, duration) {
    const startPos = camera.position.clone();
    const startLookAt = controls.target.clone();
    const endLookAt = lookAt || new THREE.Vector3(0, 0, 0);
    duration = duration || 1000;
    const startTime = Date.now();

    function step() {
        const elapsed = Date.now() - startTime;
        const t = Math.min(elapsed / duration, 1);
        const eased = 1 - Math.pow(1 - t, 3); // Ease out cubic

        camera.position.lerpVectors(startPos, targetPosition, eased);
        controls.target.lerpVectors(startLookAt, endLookAt, eased);
        controls.update();

        if (t < 1) requestAnimationFrame(step);
    }
    step();
}

// ============================================================================
// ANIMATION LOOP
// ============================================================================

function animate() {
    requestAnimationFrame(animate);

    vizState.animationTime += 0.01;

    // Slowly rotate Earth
    if (earthMesh) {
        earthMesh.rotation.y += 0.0003;
        earthMesh.material.uniforms.time.value = vizState.animationTime;
    }

    // Pulse collision pair glows and rotating critical marker
    const conjGroup = scene.getObjectByName('conjunctions');
    if (conjGroup) {
        conjGroup.children.forEach(child => {
            // Pulsing collision glows
            if (child.userData?.isPulsing && child.userData?.type === 'collision_glow') {
                const pulse = 1.0 + Math.sin(vizState.animationTime * 4) * 0.3;
                child.scale.set(pulse, pulse, pulse);
                child.material.opacity = 0.4 + Math.sin(vizState.animationTime * 4) * 0.3;
            }
            // Pulsing collision pulse ring
            else if (child.userData?.isPulsing && child.userData?.type === 'collision_pulse_ring') {
                const pulse = 1.0 + Math.sin(vizState.animationTime * 3.5) * 0.4;
                child.scale.set(pulse, pulse, pulse);
                child.material.opacity = Math.max(0.2, Math.sin(vizState.animationTime * 3.5) * 0.8);
            }
            // Rotating critical marker
            else if (child.userData?.isRotating && child.userData?.type === 'conjunction_critical_marker') {
                child.rotation.y += 0.04;
                child.rotation.x += 0.02;
                const scale = 1.0 + Math.sin(vizState.animationTime * 3) * 0.25;
                child.scale.set(scale, scale, scale);
            }
            // TCA Zone: Sinusoidal opacity animation (1-2 Hz range specified as 1.5 Hz base)
            else if (child.userData?.type === 'tca_zone' && child.userData?.isAnimating) {
                const userData = child.userData;
                // Sinusoidal wave: oscillate between opacityMin and opacityMax
                const frequency = userData.frequency || 1.5;
                const phase = vizState.animationTime * frequency * 2 * Math.PI;
                const opacityRange = userData.opacityMax - userData.opacityMin;
                const newOpacity = userData.opacityMin + opacityRange * (Math.sin(phase) + 1) / 2;
                child.material.opacity = newOpacity;
            }
            // Original conjunction marker rotation (non-critical)
            else if (child.type === 'Mesh' && child.geometry.type === 'OctahedronGeometry' && !child.userData?.isRotating) {
                child.rotation.y += 0.02;
                child.rotation.x += 0.01;
                const scale = 1.0 + Math.sin(vizState.animationTime * 3) * 0.15;
                child.scale.set(scale, scale, scale);
            }
        });
    }

    // Move constellation spacecraft along their real orbit paths
    if (spacecraftMeshes.length > 0) updateSpacecraftPositions();

    // Rotate the radar sweep wedge
    if (radarSweep) radarSweep.rotation.y += 0.008;

    // Animate debris particles
    if (debrisParticles && debrisParticles.visible) {
        const positions = debrisParticles.geometry.attributes.position.array;
        for (let i = 0; i < positions.length; i += 3) {
            if (positions[i] !== 0) {
                // Orbital drift
                const r = Math.sqrt(positions[i] ** 2 + positions[i + 1] ** 2 + positions[i + 2] ** 2);
                const speed = 0.0005 / Math.max(r, 0.1);
                const angle = speed;
                const x = positions[i];
                const z = positions[i + 2];
                positions[i] = x * Math.cos(angle) - z * Math.sin(angle);
                positions[i + 2] = x * Math.sin(angle) + z * Math.cos(angle);
            }
        }
        debrisParticles.geometry.attributes.position.needsUpdate = true;
    }

    controls.update();
    renderer.render(scene, camera);
}

// ============================================================================
// UTILITIES
// ============================================================================

function onWindowResize() {
    const container = document.getElementById('three-viewport');
    if (!container || !camera || !renderer) return;

    camera.aspect = container.clientWidth / container.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(container.clientWidth, container.clientHeight);
}

function updateClock() {
    const now = new Date();
    const utc = now.toISOString().slice(11, 19);
    const el = document.getElementById('utc-time');
    if (el) el.textContent = utc;
}

// ============================================================================
// START
// ============================================================================

window.addEventListener('DOMContentLoaded', init);


// ============================================================================
// COLLISION SIMULATION PLAYER (SSE-powered)
// ============================================================================

const simPlayer = {
    active: false,
    eventSource: null,
    playInterval: null,
    scenario: null,
    speed: 1.0,
    paused: false,

    // Three.js objects for the simulation
    obj1Mesh: null,
    obj2Mesh: null,
    obj1Trail: null,
    obj2Trail: null,
    obj1CorrectedTrail: null,
    burnEffect: null,
    collisionExplosion: null,
    debrisCloud: null,
    distanceLine: null,
    simGroup: null,
    pathPreviewGroup: null,
    label1: null,
    label2: null,
    velocityArrow1: null,
    velocityArrow2: null,
    tcaMarker: null,
    tcaPulseInterval: null,
    ambientDebris: [],

    // State
    currentFrame: 0,
    totalFrames: 0,
    obj1Positions: [],
    obj2Positions: [],
    trailPoints1: [],
    trailPoints2: [],
    prevPos1: null,
    prevPos2: null,
    _prevHudDist: undefined,
};

function initSimulationPanel() {
    // Fetch available scenarios and populate the selector
    fetch('/api/scenarios')
        .then(r => r.json())
        .then(scenarios => {
            const select = document.getElementById('scenario-select');
            if (!select) return;
            select.innerHTML = '';
            scenarios.forEach(s => {
                const opt = document.createElement('option');
                opt.value = s.id;
                opt.textContent = s.name;
                select.appendChild(opt);
            });
        })
        .catch(err => console.warn('Could not load scenarios:', err));

    // Button handlers
    const playBtn = document.getElementById('sim-play-btn');
    const stopBtn = document.getElementById('sim-stop-btn');
    const speedSlider = document.getElementById('sim-speed');

    if (playBtn) playBtn.addEventListener('click', startSimulation);
    if (stopBtn) stopBtn.addEventListener('click', stopSimulation);
    if (speedSlider) {
        speedSlider.addEventListener('input', (e) => {
            simPlayer.speed = parseFloat(e.target.value);
            document.getElementById('sim-speed-val').textContent = simPlayer.speed.toFixed(1) + 'x';
        });
    }
}

function startSimulation() {
    const scenarioId = document.getElementById('scenario-select')?.value;
    if (!scenarioId) return;

    // Stop any existing simulation
    stopSimulation();

    simPlayer.active = true;
    document.getElementById('sim-status').textContent = 'LOADING...';
    document.getElementById('sim-status').className = 'sim-status-badge connecting';
    document.getElementById('sim-play-btn').disabled = true;
    document.getElementById('sim-stop-btn').disabled = false;
    document.getElementById('sim-event-log').innerHTML = '';
    document.getElementById('sim-progress-fill').style.width = '0%';

    // Reset the left-sidebar live telemetry chart for the new run
    resetTelemetryPanel();

    // Clear previous sim objects
    clearSimObjects();
    createSimObjects();

    // Fetch full scenario data (not SSE — more reliable)
    fetch(`/api/scenario/${scenarioId}`)
        .then(r => r.json())
        .then(scenario => {
            simPlayer.scenario = scenario;
            simPlayer.totalFrames = scenario.n_frames;
            simPlayer.currentFrame = 0;
            simPlayer.trailPoints1 = [];
            simPlayer.trailPoints2 = [];

            document.getElementById('sim-status').textContent = 'LIVE';
            document.getElementById('sim-status').className = 'sim-status-badge live';
            document.getElementById('sim-scenario-name').textContent = scenario.name;

            teleState.scenario = scenario;
            setTelemetryBadge('live', 'LIVE');

            bplaneState.scenario = scenario;
            bplaneState.active = true;
            setBplaneBadge('live', 'LIVE');

            addEventLogEntry('info', `Scenario: ${scenario.name}`);
            addEventLogEntry('info', `Alt: ${scenario.metadata.altitude_km} km | V_rel: ${scenario.metadata.relative_velocity_kms} km/s`);

            // Refresh object labels now that scenario metadata is known
            updateLabelText(simPlayer.label1, `${scenario.metadata.object1_type}-1`, '#00d4ff');
            updateLabelText(simPlayer.label2, `${scenario.metadata.object2_type}-2`, '#ff4444');

            // Draw the full precomputed trajectories immediately
            drawPathPreview(scenario);

            // Show the telemetry HUD
            const hud = document.getElementById('sim-hud');
            if (hud) hud.classList.remove('hidden');

            // Move camera to wide view
            const camPos = new THREE.Vector3(2.5, 1.5, 3.5);
            animateCamera(camPos, new THREE.Vector3(0, 0, 0));

            // Start client-side animation loop
            playScenarioFrames(scenario);
        })
        .catch(err => {
            console.error('Failed to load scenario:', err);
            document.getElementById('sim-status').textContent = 'ERROR';
            document.getElementById('sim-status').className = 'sim-status-badge error';
            document.getElementById('sim-play-btn').disabled = false;
        });
}

function playScenarioFrames(scenario) {
    const frameInterval = 50 / simPlayer.speed; // ms per frame
    let eventIdx = 0;

    simPlayer.playInterval = setInterval(() => {
        if (!simPlayer.active) {
            clearInterval(simPlayer.playInterval);
            return;
        }

        const frame = simPlayer.currentFrame;
        if (frame >= scenario.n_frames) {
            // Simulation complete
            clearInterval(simPlayer.playInterval);
            document.getElementById('sim-status').textContent = 'COMPLETE';
            document.getElementById('sim-status').className = 'sim-status-badge complete';
            document.getElementById('sim-play-btn').disabled = false;
            simPlayer.active = false;
            setTelemetryBadge('complete', 'COMPLETE');
            return;
        }

        // Get positions for this frame
        const hasCorrection = scenario.has_correction;
        const useCorrection = hasCorrection && frame >= scenario.maneuver_frame;
        const pos1Raw = useCorrection ? scenario.path_object1_corrected[frame] : scenario.path_object1[frame];
        const pos2Raw = scenario.path_object2[frame];
        const dist = useCorrection ? scenario.distances_corrected[frame] : scenario.distances[frame];

        const energySeries = scenario.specific_energy_j_per_kg;
        const frameData = {
            frame: frame,
            progress: frame / scenario.n_frames,
            object1_pos: pos1Raw,
            object2_pos: pos2Raw,
            distance_km: dist,
            is_corrected: useCorrection,
            specific_energy_j_per_kg: (energySeries && frame < energySeries.length) ? energySeries[frame] : null,
        };

        updateSimFrame(frameData);

        // Update progress
        const pct = (frameData.progress * 100).toFixed(1);
        document.getElementById('sim-progress-fill').style.width = pct + '%';
        document.getElementById('sim-distance').textContent = dist.toFixed(1) + ' km';

        // Update the in-viewport telemetry HUD
        updateSimHud(scenario, frame, dist);

        // Feed the left-sidebar live telemetry chart
        recordTelemetrySample(scenario, frame, dist);

        // Update the catastrophic-threshold energy gauge (E_MR vs 40 J/g line)
        updateCatastrophicGauge(frameData.specific_energy_j_per_kg, scenario);

        // Update the live B-plane encounter-geometry inset
        updateBplaneFrame(scenario, frame);

        // Fire events at their scheduled frames
        while (eventIdx < scenario.events.length && scenario.events[eventIdx].frame <= frame) {
            const evt = scenario.events[eventIdx];
            handleSimEvent(evt);

            // Spawn debris on collision
            if (evt.type === 'collision' && scenario.debris_fragments.length > 0) {
                spawnDebrisExplosion(scenario.debris_fragments);
            }

            eventIdx++;
        }

        simPlayer.currentFrame++;
    }, frameInterval);
}

function stopSimulation() {
    if (simPlayer.playInterval) {
        clearInterval(simPlayer.playInterval);
        simPlayer.playInterval = null;
    }
    if (simPlayer.eventSource) {
        simPlayer.eventSource.close();
        simPlayer.eventSource = null;
    }
    simPlayer.active = false;
    document.getElementById('sim-status').textContent = 'IDLE';
    document.getElementById('sim-status').className = 'sim-status-badge idle';
    document.getElementById('sim-play-btn').disabled = false;
    document.getElementById('sim-stop-btn').disabled = true;

    setTelemetryBadge('idle', 'IDLE');
    bplaneState.active = false;
    setBplaneBadge('idle', 'IDLE');

    // Hide the telemetry HUD
    const hud = document.getElementById('sim-hud');
    if (hud) hud.classList.add('hidden');

    clearSimObjects();
}

// ============================================================================
// LIVE TELEMETRY CHART (left sidebar) - populates dynamically as a
// collision scenario plays back, plotting range-to-target over time
// with event markers overlaid.
// ============================================================================

function setTelemetryBadge(cls, text) {
    const badge = document.getElementById('telemetry-badge');
    if (!badge) return;
    badge.className = 'sim-status-badge ' + cls;
    badge.textContent = text;
}

function resetTelemetryPanel() {
    teleState.scenario = null;
    teleState.history = [];
    teleState.prevDist = undefined;
    setTelemetryBadge('idle', 'IDLE');
    const hint = document.getElementById('telemetry-hint');
    if (hint) hint.classList.remove('hidden');
    ['tel-range', 'tel-miss-distance', 'tel-vel', 'tel-proximity'].forEach(id => {
        const el = document.getElementById(id);
        if (el) { el.textContent = '--'; el.className = 'telemetry-value'; }
    });
    const eqDistEl = document.getElementById('physics-eq-dist');
    const eqVelEl = document.getElementById('physics-eq-vel');
    if (eqDistEl) eqDistEl.textContent = '= -- km';
    if (eqVelEl) eqVelEl.textContent = '= -- km/s';
    drawTelemetryChart();
    resetCatastrophicGauge();
    resetBplanePanel();
}

// ============================================================================
// LIVE B-PLANE (ENCOUNTER PLANE) INSET
// ----------------------------------------------------------------------------
// Physics: the B-plane is the 2D plane through the secondary object,
// perpendicular to the relative velocity vector at closest approach. All
// conjunction-assessment probability-of-collision calculations happen in
// this plane (see compute_encounter_plane() / probability_of_collision_2d()
// in src/conjunction.py, and docs/physics.md). This inset renders exactly
// that geometry, live:
//   - the hard-body-radius disk (physical collision cross-section)
//   - the n-sigma covariance confidence ellipse (tracking uncertainty)
//   - the miss-distance vector (xi, zeta) from tracking data
// as the avoidance burn executes and both the vector and the ellipse move.
// ============================================================================

function setBplaneBadge(cls, text) {
    const badge = document.getElementById('bplane-badge');
    if (!badge) return;
    badge.className = 'sim-status-badge ' + cls;
    badge.textContent = text;
}

function resetBplanePanel() {
    bplaneState.scenario = null;
    bplaneState.active = false;
    setBplaneBadge('idle', 'IDLE');
    const missEl = document.getElementById('bplane-miss');
    const ellipseEl = document.getElementById('bplane-ellipse');
    const hbrEl = document.getElementById('bplane-hbr');
    const pcEl = document.getElementById('bplane-pc');
    if (missEl) missEl.textContent = '-- , -- km';
    if (ellipseEl) ellipseEl.textContent = '-- \u00d7 -- km';
    if (hbrEl) hbrEl.textContent = '-- m';
    if (pcEl) { pcEl.textContent = '--'; pcEl.className = 'bplane-value'; }
    drawBplaneChart();
}

function updateBplaneFrame(scenario, frame) {
    const bp = scenario && scenario.bplane;
    if (!bp) return;

    const idx = Math.min(frame, bp.miss_xi_km.length - 1);
    const xi = bp.miss_xi_km[idx];
    const zeta = bp.miss_zeta_km[idx];
    const semiMajor = bp.cov_semi_major_km[idx];
    const semiMinor = bp.cov_semi_minor_km[idx];
    const pc = bp.pc_estimate[idx];
    const combinedRadiusM = bp.combined_radius_km * 1000;

    const missEl = document.getElementById('bplane-miss');
    const ellipseEl = document.getElementById('bplane-ellipse');
    const hbrEl = document.getElementById('bplane-hbr');
    const pcEl = document.getElementById('bplane-pc');

    if (missEl) missEl.textContent = `${xi.toFixed(2)}, ${zeta.toFixed(2)} km`;
    if (ellipseEl) ellipseEl.textContent = `${semiMajor.toFixed(2)} \u00d7 ${semiMinor.toFixed(2)} km`;
    if (hbrEl) hbrEl.textContent = `${combinedRadiusM.toFixed(1)} m`;
    if (pcEl) {
        pcEl.textContent = pc.toExponential(2);
        pcEl.className = 'bplane-value' + (pc > 1e-4 ? ' critical-text' : '');
    }

    drawBplaneChart(bp, idx);
}

/**
 * Draw the B-plane inset: hard-body-radius circle, covariance confidence
 * ellipse, and miss-distance vector, auto-scaled to fit whichever is
 * currently larger (ellipse or miss distance) so the geometry stays
 * readable as the burn shrinks the miss vector toward (or away from) the
 * origin.
 */
function drawBplaneChart(bp, idx) {
    const canvas = document.getElementById('bplane-chart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const w = canvas.width;
    const h = canvas.height;
    const cx = w / 2;
    const cy = h / 2;

    ctx.clearRect(0, 0, w, h);

    if (!bp) {
        // Empty state: faint crosshair only
        ctx.strokeStyle = '#1e2a42';
        ctx.lineWidth = 0.5;
        ctx.beginPath();
        ctx.moveTo(cx, 8); ctx.lineTo(cx, h - 8);
        ctx.moveTo(8, cy); ctx.lineTo(w - 8, cy);
        ctx.stroke();
        return;
    }

    const xi = bp.miss_xi_km[idx];
    const zeta = bp.miss_zeta_km[idx];
    const semiMajor = bp.cov_semi_major_km[idx];
    const combinedRadiusKm = bp.combined_radius_km;

    // Auto-scale: fit the larger of (miss distance + ellipse) or a
    // reasonable minimum, with margin, into the canvas half-width.
    const missDist = Math.sqrt(xi * xi + zeta * zeta);
    const extent = Math.max(missDist + semiMajor, semiMajor * 1.3, combinedRadiusKm * 4, 0.05);
    const margin = 28; // px reserved for axis labels
    const plotRadiusPx = Math.min(w, h) / 2 - margin;
    const scale = plotRadiusPx / extent; // px per km

    const toPx = (xKm, yKm) => [cx + xKm * scale, cy - yKm * scale];

    // Grid: faint concentric range rings + crosshair axes
    ctx.strokeStyle = '#1e2a42';
    ctx.lineWidth = 0.5;
    [0.33, 0.66, 1.0].forEach(f => {
        ctx.beginPath();
        ctx.arc(cx, cy, plotRadiusPx * f, 0, Math.PI * 2);
        ctx.stroke();
    });
    ctx.beginPath();
    ctx.moveTo(cx, margin * 0.3); ctx.lineTo(cx, h - margin * 0.3);
    ctx.moveTo(margin * 0.3, cy); ctx.lineTo(w - margin * 0.3, cy);
    ctx.stroke();

    // Axis labels (xi = along-track-ish, zeta = out-of-plane-ish)
    ctx.fillStyle = '#5a6b8a';
    ctx.font = '9px JetBrains Mono';
    ctx.textAlign = 'center';
    ctx.fillText('\u03be (km)', w - margin + 4, cy - 6);
    ctx.fillText('\u03b6 (km)', cx + 18, margin * 0.3 + 8);

    // 3-sigma covariance confidence ellipse
    const [ex, ey] = toPx(xi, zeta);
    ctx.save();
    ctx.translate(ex, ey);
    ctx.rotate(-bp.cov_angle_rad);
    ctx.beginPath();
    ctx.ellipse(0, 0, bp.cov_semi_major_km[idx] * scale, bp.cov_semi_minor_km[idx] * scale, 0, 0, Math.PI * 2);
    ctx.strokeStyle = '#7b2ff7';
    ctx.lineWidth = 1.5;
    ctx.setLineDash([4, 3]);
    ctx.stroke();
    ctx.fillStyle = 'rgba(123, 47, 247, 0.08)';
    ctx.fill();
    ctx.setLineDash([]);
    ctx.restore();

    // Miss-distance vector: origin (secondary object) -> miss point
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(ex, ey);
    ctx.strokeStyle = '#ffcc00';
    ctx.lineWidth = 1.5;
    ctx.stroke();

    // Hard-body-radius disk, centered at the miss point (relative
    // geometry: the secondary object's hard body sits at the origin,
    // the combined radius disk is drawn around the primary's position)
    const hbrPx = Math.max(combinedRadiusKm * scale, 2);
    ctx.beginPath();
    ctx.arc(ex, ey, hbrPx, 0, Math.PI * 2);
    ctx.fillStyle = 'rgba(255, 45, 85, 0.35)';
    ctx.fill();
    ctx.strokeStyle = '#ff2d55';
    ctx.lineWidth = 1;
    ctx.stroke();

    // Secondary object marker at the origin (reference body of the B-plane)
    ctx.beginPath();
    ctx.arc(cx, cy, 3, 0, Math.PI * 2);
    ctx.fillStyle = '#00d4ff';
    ctx.fill();

    // Primary object marker at the miss point
    ctx.beginPath();
    ctx.arc(ex, ey, 3, 0, Math.PI * 2);
    ctx.fillStyle = '#ffcc00';
    ctx.fill();

    // View extent readout (bottom-left) - clarifies the auto-scaled zoom level
    ctx.fillStyle = '#5a6b8a';
    ctx.font = '8px JetBrains Mono';
    ctx.textAlign = 'left';
    ctx.fillText(`view: \u00b1${extent.toFixed(2)} km`, 6, h - 6);
}

// ============================================================================
// CATASTROPHIC THRESHOLD GAUGE
// ----------------------------------------------------------------------------
// Physics: NASA Standard Breakup Model classifies a collision as
// "catastrophic" (complete fragmentation of both bodies, vs. cratering /
// partial damage) when the specific mass-normalized kinetic energy of the
// encounter exceeds ~40 J/g:
//
//     E_MR = (m_p * v_rel^2) / (2 * m_t)   >   40 J/g  (= 40,000 J/kg)
//
// where m_p is the smaller ("projectile") mass, m_t the larger ("target")
// mass, and v_rel the relative velocity at closest approach. This gauge
// renders the live E_MR value against that catastrophic-fragmentation line
// so a successful avoidance burn reads as "encounter energy kept under the
// breakup threshold", not just "objects didn't touch".
// See docs/physics.md and src/damage_minimization.collision_specific_energy().
// ============================================================================

function resetCatastrophicGauge() {
    const fill = document.getElementById('catastrophic-fill');
    const marker = document.getElementById('catastrophic-marker');
    const valueEl = document.getElementById('catastrophic-value');
    const statusEl = document.getElementById('catastrophic-status');
    const eqEl = document.getElementById('physics-eq-emr');
    if (fill) { fill.style.width = '0%'; fill.className = 'catastrophic-fill'; }
    if (marker) marker.style.left = '0%';
    if (valueEl) valueEl.textContent = '-- J/g';
    if (statusEl) { statusEl.textContent = 'STANDBY'; statusEl.className = 'catastrophic-status-badge'; }
    if (eqEl) eqEl.textContent = '= -- J/g';
}

/**
 * Update the catastrophic-threshold horizontal bar gauge from the current
 * frame's specific energy (J/kg, converted to J/g for display to match the
 * 40 J/g convention used in the breakup-model literature).
 */
function updateCatastrophicGauge(specificEnergyJPerKg, scenario) {
    const fill = document.getElementById('catastrophic-fill');
    const valueEl = document.getElementById('catastrophic-value');
    const statusEl = document.getElementById('catastrophic-status');
    const eqEl = document.getElementById('physics-eq-emr');
    if (!fill || specificEnergyJPerKg === null || specificEnergyJPerKg === undefined) return;

    const thresholdJPerKg = (scenario && scenario.catastrophic_energy_threshold_j_per_kg) || 40000;
    const eJPerG = specificEnergyJPerKg / 1000.0;
    const thresholdJPerG = thresholdJPerKg / 1000.0;

    // Scale the bar so the 40 J/g line sits at 60% of the track width,
    // leaving room to visualize energies well above threshold too.
    const scaleMax = thresholdJPerG / 0.6;
    const pct = Math.max(0, Math.min(100, (eJPerG / scaleMax) * 100));

    fill.style.width = pct.toFixed(1) + '%';

    const isCatastrophic = specificEnergyJPerKg >= thresholdJPerKg;
    fill.className = 'catastrophic-fill' + (isCatastrophic ? ' over-threshold' : '');

    if (valueEl) valueEl.textContent = `${eJPerG.toFixed(1)} J/g`;
    if (eqEl) eqEl.textContent = `= ${eJPerG.toFixed(1)} J/g`;

    if (statusEl) {
        if (isCatastrophic) {
            statusEl.textContent = 'CATASTROPHIC';
            statusEl.className = 'catastrophic-status-badge critical';
        } else if (eJPerG > thresholdJPerG * 0.75) {
            statusEl.textContent = 'APPROACHING';
            statusEl.className = 'catastrophic-status-badge warning';
        } else {
            statusEl.textContent = 'BELOW THRESHOLD';
            statusEl.className = 'catastrophic-status-badge success';
        }
    }
}

function recordTelemetrySample(scenario, frame, dist) {
    const hint = document.getElementById('telemetry-hint');
    if (hint) hint.classList.add('hidden');

    const t = frame * 0.05 / Math.max(simPlayer.speed, 0.001);
    // Use scenario's relative velocity (constant for the encounter).
    // Do NOT recompute from Δdist/Δt, as that gives spurious values from
    // the synthetic trajectory paths. The relative velocity is a physical
    // property of the encounter and comes from the scenario metadata.
    const closingKms = scenario.metadata?.relative_velocity_kms || 0;
    teleState.prevDist = dist;

    teleState.history.push({ frame, t, dist, closingVel: closingKms });
    // Cap history so the chart stays responsive on long runs
    if (teleState.history.length > scenario.n_frames + 5) teleState.history.shift();

    // Live readouts
    const rangeEl = document.getElementById('tel-range');
    const missEl = document.getElementById('tel-miss-distance');
    const velEl = document.getElementById('tel-vel');
    const proxEl = document.getElementById('tel-proximity');

    // Current separation: live instantaneous distance
    if (rangeEl) rangeEl.textContent = dist.toFixed(1) + ' km';

    // Predicted miss distance at TCA: minimum distance from precomputed trajectory
    if (missEl) {
        const missDistKm = scenario.min_distance_km;
        if (missDistKm !== undefined && missDistKm !== null) {
            missEl.textContent = missDistKm.toFixed(2) + ' km';
        } else {
            missEl.textContent = '-- km';
        }
    }

    if (velEl) velEl.textContent = closingKms.toFixed(2) + ' km/s (closing)';

    // Live-evaluated physics equations: d(t) = |r1(t) - r2(t)|, v_rel from scenario
    const eqDistEl = document.getElementById('physics-eq-dist');
    const eqVelEl = document.getElementById('physics-eq-vel');
    if (eqDistEl) eqDistEl.textContent = `= ${dist.toFixed(2)} km`;
    if (eqVelEl) eqVelEl.textContent = `= ${closingKms.toFixed(2)} km/s`;

    let proxLabel, proxClass;
    if (dist > 500) { proxLabel = 'SAFE'; proxClass = 'success'; }
    else if (dist > 100) { proxLabel = 'GUARDED'; proxClass = ''; }
    else if (dist > 10) { proxLabel = 'ELEVATED'; proxClass = 'warning'; }
    else { proxLabel = 'CRITICAL'; proxClass = 'warning critical-text'; }
    if (proxEl) proxEl.textContent = proxLabel;
    if (proxEl) proxEl.className = 'telemetry-value ' + proxClass;

    // Update telemetry hint
    const hintEl = document.getElementById('telemetry-hint');
    if (hintEl) {
        hintEl.textContent = 'Current Separation = live distance. Predicted Miss Distance = closest approach forecast.';
        hintEl.classList.remove('hidden');
    }

    drawTelemetryChart();
}

function drawTelemetryChart() {
    const canvas = document.getElementById('telemetry-chart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const w = canvas.width;
    const h = canvas.height;
    const padding = { top: 10, right: 8, bottom: 18, left: 38 };

    ctx.clearRect(0, 0, w, h);

    const scenario = teleState.scenario;
    const history = teleState.history;

    if (!scenario || history.length < 2) {
        // Empty state: draw a faint baseline grid so the panel doesn't look broken
        ctx.strokeStyle = '#1e2a42';
        ctx.lineWidth = 0.5;
        for (let i = 0; i <= 3; i++) {
            const y = padding.top + ((h - padding.top - padding.bottom) / 3) * i;
            ctx.beginPath();
            ctx.moveTo(padding.left, y);
            ctx.lineTo(w - padding.right, y);
            ctx.stroke();
        }
        return;
    }

    const plotW = w - padding.left - padding.right;
    const plotH = h - padding.top - padding.bottom;

    // X domain spans the full scenario duration so the line grows left-to-right
    // as playback progresses, rather than rescaling every frame.
    const tMax = Math.max(scenario.n_frames * 0.05 / Math.max(simPlayer.speed, 0.001), history[history.length - 1].t);
    const distMax = Math.max(...history.map(d => d.dist), scenario.min_distance_km || 0) * 1.15 || 1;

    const xFor = (t) => padding.left + (t / tMax) * plotW;
    const yFor = (d) => padding.top + plotH - (d / distMax) * plotH;

    // Grid lines
    ctx.strokeStyle = '#1e2a42';
    ctx.lineWidth = 0.5;
    for (let i = 0; i <= 3; i++) {
        const y = padding.top + (plotH / 3) * i;
        ctx.beginPath();
        ctx.moveTo(padding.left, y);
        ctx.lineTo(w - padding.right, y);
        ctx.stroke();
    }

    // Danger threshold band (< 10km considered critical proximity)
    const dangerY = yFor(Math.min(10, distMax));
    ctx.fillStyle = 'rgba(255, 45, 85, 0.08)';
    ctx.fillRect(padding.left, dangerY, plotW, padding.top + plotH - dangerY);

    // Gradient fill under the range curve
    const gradient = ctx.createLinearGradient(0, padding.top, 0, h - padding.bottom);
    gradient.addColorStop(0, 'rgba(0, 212, 255, 0.25)');
    gradient.addColorStop(1, 'rgba(0, 212, 255, 0.0)');

    ctx.beginPath();
    ctx.moveTo(xFor(history[0].t), h - padding.bottom);
    history.forEach(d => ctx.lineTo(xFor(d.t), yFor(d.dist)));
    ctx.lineTo(xFor(history[history.length - 1].t), h - padding.bottom);
    ctx.closePath();
    ctx.fillStyle = gradient;
    ctx.fill();

    // Range line, colored by current proximity risk
    ctx.beginPath();
    history.forEach((d, i) => {
        const x = xFor(d.t);
        const y = yFor(d.dist);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    });
    const lastDist = history[history.length - 1].dist;
    const lineColor = lastDist > 500 ? '#30d158' : lastDist > 100 ? '#ffcc00' : lastDist > 10 ? '#ff9500' : '#ff2d55';
    ctx.strokeStyle = lineColor;
    ctx.lineWidth = 1.5;
    ctx.stroke();

    // Current position marker (pulsing dot at the leading edge)
    const lastPt = history[history.length - 1];
    ctx.beginPath();
    ctx.arc(xFor(lastPt.t), yFor(lastPt.dist), 3, 0, Math.PI * 2);
    ctx.fillStyle = lineColor;
    ctx.fill();

    // Event markers (vertical ticks) for any events already fired
    if (scenario.events) {
        scenario.events.forEach(evt => {
            const evtT = evt.frame * 0.05 / Math.max(simPlayer.speed, 0.001);
            if (evtT > lastPt.t) return; // hasn't happened yet
            const x = xFor(evtT);
            ctx.strokeStyle = 'rgba(255, 255, 255, 0.25)';
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(x, padding.top);
            ctx.lineTo(x, padding.top + plotH);
            ctx.stroke();
        });
    }

    // Axis labels
    ctx.fillStyle = '#5a6b8a';
    ctx.font = '9px JetBrains Mono';
    ctx.textAlign = 'center';
    ctx.fillText('0s', padding.left, h - 4);
    ctx.fillText(`${tMax.toFixed(1)}s`, padding.left + plotW, h - 4);

    ctx.textAlign = 'right';
    ctx.fillText(distMax.toFixed(0), padding.left - 4, padding.top + 8);
    ctx.fillText('0', padding.left - 4, h - padding.bottom);

    ctx.textAlign = 'left';
    ctx.fillStyle = '#8b9cc0';
    ctx.font = '9px Inter';
    ctx.fillText('Separation (km)', padding.left, padding.top + 2);
}

// ============================================================================
// PROCEDURAL SATELLITE / DEBRIS MODELS
// ============================================================================

function createSatelliteModel(color) {
    const group = new THREE.Group();

    // Central bus (body)
    const busGeo = new THREE.BoxGeometry(0.018, 0.018, 0.032);
    const busMat = new THREE.MeshStandardMaterial({
        color: 0xcccccc,
        metalness: 0.6,
        roughness: 0.4,
        emissive: color,
        emissiveIntensity: 0.15
    });
    const bus = new THREE.Mesh(busGeo, busMat);
    group.add(bus);

    // Solar panel wings (two, extending from either side of the bus)
    const panelGeo = new THREE.BoxGeometry(0.05, 0.002, 0.022);
    const panelMatL = new THREE.MeshStandardMaterial({
        color: 0x0a1a3a,
        metalness: 0.3,
        roughness: 0.6,
        emissive: color,
        emissiveIntensity: 0.08
    });
    const panelLeft = new THREE.Mesh(panelGeo, panelMatL);
    panelLeft.position.x = -0.043;
    group.add(panelLeft);

    const panelMatR = panelMatL.clone();
    const panelRight = new THREE.Mesh(panelGeo, panelMatR);
    panelRight.position.x = 0.043;
    group.add(panelRight);

    // Antenna dish
    const dishGeo = new THREE.ConeGeometry(0.008, 0.016, 8);
    const dishMat = new THREE.MeshStandardMaterial({
        color: 0xeeeeee,
        metalness: 0.7,
        roughness: 0.3
    });
    const dish = new THREE.Mesh(dishGeo, dishMat);
    dish.position.z = 0.02;
    dish.rotation.x = Math.PI / 2;
    group.add(dish);

    // Blinking anti-collision beacon
    const beaconGeo = new THREE.SphereGeometry(0.004, 8, 8);
    const beaconMat = new THREE.MeshBasicMaterial({
        color: 0xff2d55,
        transparent: true,
        opacity: 1
    });
    const beacon = new THREE.Mesh(beaconGeo, beaconMat);
    beacon.position.set(0, 0.011, -0.014);
    group.add(beacon);
    group.userData.beacon = beacon;

    // Glow sphere (kept for burn-effect color swap compatibility)
    const glowGeo = new THREE.SphereGeometry(0.06, 12, 12);
    const glowMat = new THREE.MeshBasicMaterial({
        color: color,
        transparent: true,
        opacity: 0.35,
        blending: THREE.AdditiveBlending
    });
    const glow = new THREE.Mesh(glowGeo, glowMat);
    group.add(glow);
    group.userData.glow = glow;

    return group;
}

function createDebrisModel(color) {
    const group = new THREE.Group();

    // Irregular rock shape via jittered icosahedron vertices
    const geo = new THREE.IcosahedronGeometry(0.028, 1);
    const posAttr = geo.attributes.position;
    for (let i = 0; i < posAttr.count; i++) {
        const jitter = 0.35;
        posAttr.setXYZ(
            i,
            posAttr.getX(i) * (1 + (Math.random() - 0.5) * jitter),
            posAttr.getY(i) * (1 + (Math.random() - 0.5) * jitter),
            posAttr.getZ(i) * (1 + (Math.random() - 0.5) * jitter)
        );
    }
    geo.computeVertexNormals();

    const mat = new THREE.MeshStandardMaterial({
        color: 0x8b8378,
        metalness: 0.5,
        roughness: 0.8,
        emissive: color,
        emissiveIntensity: 0.12
    });
    const rock = new THREE.Mesh(geo, mat);
    group.add(rock);

    // Jagged wireframe overlay for a damaged-metal look
    const wireGeo = new THREE.EdgesGeometry(geo);
    const wireMat = new THREE.LineBasicMaterial({
        color: color,
        transparent: true,
        opacity: 0.3
    });
    const wire = new THREE.LineSegments(wireGeo, wireMat);
    group.add(wire);

    // Glow (kept for consistency with satellite model's glow reference pattern)
    const glowGeo = new THREE.SphereGeometry(0.045, 12, 12);
    const glowMat = new THREE.MeshBasicMaterial({
        color: color,
        transparent: true,
        opacity: 0.25,
        blending: THREE.AdditiveBlending
    });
    const glow = new THREE.Mesh(glowGeo, glowMat);
    group.add(glow);
    group.userData.glow = glow;

    return group;
}

function createSimObjects() {
    simPlayer.simGroup = new THREE.Group();
    simPlayer.simGroup.name = 'simulation';

    // Object 1 (maneuverable spacecraft) - detailed satellite model
    simPlayer.obj1Mesh = createSatelliteModel(0x00d4ff);
    simPlayer.simGroup.add(simPlayer.obj1Mesh);

    // Object 2 (debris/target) - tumbling irregular rock chunk
    simPlayer.obj2Mesh = createDebrisModel(0xff4444);
    simPlayer.simGroup.add(simPlayer.obj2Mesh);

    // Distance line between objects (pre-allocate buffer for in-place updates)
    const lineGeo = new THREE.BufferGeometry();
    const linePositions = new Float32Array(6); // 2 points x 3 components
    lineGeo.setAttribute('position', new THREE.BufferAttribute(linePositions, 3));
    const lineMat = new THREE.LineBasicMaterial({
        color: 0xffcc00,
        transparent: true,
        opacity: 0.6
    });
    simPlayer.distanceLine = new THREE.Line(lineGeo, lineMat);
    simPlayer.simGroup.add(simPlayer.distanceLine);

    // Burn effect (particle burst) - initially invisible
    const burnGeo = new THREE.ConeGeometry(0.01, 0.04, 8);
    const burnMat = new THREE.MeshBasicMaterial({
        color: 0xff8800,
        transparent: true,
        opacity: 0,
        blending: THREE.AdditiveBlending
    });
    simPlayer.burnEffect = new THREE.Mesh(burnGeo, burnMat);
    simPlayer.simGroup.add(simPlayer.burnEffect);

    // Floating labels above each object
    const label1Text = simPlayer.scenario?.metadata?.object1_type
        ? `${simPlayer.scenario.metadata.object1_type}-1` : 'OBJECT-1';
    const label2Text = simPlayer.scenario?.metadata?.object2_type
        ? `${simPlayer.scenario.metadata.object2_type}-2` : 'OBJECT-2';
    simPlayer.label1 = createTextSprite(label1Text, '#00d4ff');
    simPlayer.label2 = createTextSprite(label2Text, '#ff4444');
    simPlayer.simGroup.add(simPlayer.label1);
    simPlayer.simGroup.add(simPlayer.label2);

    // Velocity direction arrows
    simPlayer.velocityArrow1 = new THREE.ArrowHelper(
        new THREE.Vector3(0, 1, 0), new THREE.Vector3(), 0.08, 0x00d4ff
    );
    simPlayer.velocityArrow2 = new THREE.ArrowHelper(
        new THREE.Vector3(0, 1, 0), new THREE.Vector3(), 0.08, 0xff4444
    );
    simPlayer.simGroup.add(simPlayer.velocityArrow1);
    simPlayer.simGroup.add(simPlayer.velocityArrow2);

    // A handful of extra ambient debris tumbling in the background,
    // giving the scene a cluttered, realistic orbital-environment feel
    simPlayer.ambientDebris = [];
    const ambientColors = [0xff4444, 0x8b8378, 0xffaa00, 0x8b8378, 0xff6644];
    for (let i = 0; i < 5; i++) {
        const debrisMesh = createDebrisModel(ambientColors[i % ambientColors.length]);
        debrisMesh.scale.setScalar(0.3 + Math.random() * 0.4); // smaller than the main debris object
        simPlayer.simGroup.add(debrisMesh);

        simPlayer.ambientDebris.push({
            mesh: debrisMesh,
            orbitRadius: 0.12 + Math.random() * 0.18,
            orbitSpeed: (0.3 + Math.random() * 0.5) * (Math.random() < 0.5 ? 1 : -1),
            orbitPhase: Math.random() * Math.PI * 2,
            orbitAxis: new THREE.Vector3(
                Math.random() - 0.5, Math.random() - 0.5, Math.random() - 0.5
            ).normalize(),
            spinSpeed: {
                x: (Math.random() - 0.5) * 0.03,
                y: (Math.random() - 0.5) * 0.03,
                z: (Math.random() - 0.5) * 0.03,
            },
        });
    }

    scene.add(simPlayer.simGroup);
}

// ============================================================================
// TEXT SPRITES (floating HTML-free labels rendered via canvas texture)
// ============================================================================

function createTextSprite(text, color) {
    const canvas = document.createElement('canvas');
    canvas.width = 256;
    canvas.height = 64;
    const ctx = canvas.getContext('2d');
    ctx.font = '600 32px "JetBrains Mono", monospace';
    ctx.fillStyle = color;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.shadowColor = color;
    ctx.shadowBlur = 8;
    ctx.fillText(text, canvas.width / 2, canvas.height / 2);

    const texture = new THREE.CanvasTexture(canvas);
    const material = new THREE.SpriteMaterial({
        map: texture,
        transparent: true,
        depthWrite: false
    });
    const sprite = new THREE.Sprite(material);
    sprite.scale.set(0.16, 0.04, 1);
    return sprite;
}

function updateLabelText(sprite, text, color) {
    if (!sprite || !sprite.material || !sprite.material.map) return;
    const canvas = sprite.material.map.image;
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.font = '600 32px "JetBrains Mono", monospace';
    ctx.fillStyle = color;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.shadowColor = color;
    ctx.shadowBlur = 8;
    ctx.fillText(text, canvas.width / 2, canvas.height / 2);
    sprite.material.map.needsUpdate = true;
}

function clearSimObjects() {
    if (simPlayer.simGroup) {
        scene.remove(simPlayer.simGroup);
        simPlayer.simGroup = null;
    }
    if (simPlayer.obj1Trail) {
        scene.remove(simPlayer.obj1Trail);
        simPlayer.obj1Trail = null;
    }
    if (simPlayer.obj2Trail) {
        scene.remove(simPlayer.obj2Trail);
        simPlayer.obj2Trail = null;
    }
    if (simPlayer.obj1CorrectedTrail) {
        scene.remove(simPlayer.obj1CorrectedTrail);
        simPlayer.obj1CorrectedTrail = null;
    }
    if (simPlayer.collisionExplosion) {
        scene.remove(simPlayer.collisionExplosion);
        simPlayer.collisionExplosion = null;
    }
    if (simPlayer.debrisCloud) {
        scene.remove(simPlayer.debrisCloud);
        simPlayer.debrisCloud = null;
    }
    if (simPlayer.pathPreviewGroup) {
        scene.remove(simPlayer.pathPreviewGroup);
        simPlayer.pathPreviewGroup = null;
    }
    if (simPlayer.tcaPulseInterval) {
        clearInterval(simPlayer.tcaPulseInterval);
        simPlayer.tcaPulseInterval = null;
    }
    // Labels and velocity arrows are children of simGroup and are removed
    // along with it above; just clear the references here.
    simPlayer.label1 = null;
    simPlayer.label2 = null;
    simPlayer.velocityArrow1 = null;
    simPlayer.velocityArrow2 = null;
    simPlayer.tcaMarker = null;
    simPlayer.ambientDebris = [];
    simPlayer.trailPoints1 = [];
    simPlayer.trailPoints2 = [];
    simPlayer.prevPos1 = null;
    simPlayer.prevPos2 = null;
    simPlayer._prevHudDist = undefined;
}

// ============================================================================
// PATH PREVIEW (full precomputed trajectory rendered up-front)
// ============================================================================

function drawPathPreview(scenario) {
    simPlayer.pathPreviewGroup = new THREE.Group();
    simPlayer.pathPreviewGroup.name = 'pathPreview';

    const toVec3 = (p) => new THREE.Vector3(p[0] * SCALE, p[2] * SCALE, p[1] * SCALE);

    const fadeMaterials = [];

    // Object 1 original/danger path - dashed amber
    const points1 = scenario.path_object1.map(toVec3);
    const geo1 = new THREE.BufferGeometry().setFromPoints(points1);
    const mat1 = new THREE.LineDashedMaterial({
        color: 0xffaa00,
        dashSize: 0.03,
        gapSize: 0.015,
        transparent: true,
        opacity: 0,
    });
    const line1 = new THREE.Line(geo1, mat1);
    line1.computeLineDistances();
    simPlayer.pathPreviewGroup.add(line1);
    fadeMaterials.push({ material: mat1, target: 0.5 });

    // Object 2 path - dashed red
    const points2 = scenario.path_object2.map(toVec3);
    const geo2 = new THREE.BufferGeometry().setFromPoints(points2);
    const mat2 = new THREE.LineDashedMaterial({
        color: 0xff4444,
        dashSize: 0.03,
        gapSize: 0.015,
        transparent: true,
        opacity: 0,
    });
    const line2 = new THREE.Line(geo2, mat2);
    line2.computeLineDistances();
    simPlayer.pathPreviewGroup.add(line2);
    fadeMaterials.push({ material: mat2, target: 0.4 });

    // Object 1 corrected/safe path - solid glowing cyan (only if a correction exists)
    if (scenario.has_correction) {
        const pointsCorrected = scenario.path_object1_corrected.map(toVec3);
        const geoCorrected = new THREE.BufferGeometry().setFromPoints(pointsCorrected);
        const matCorrected = new THREE.LineBasicMaterial({
            color: 0x06ffd0,
            transparent: true,
            opacity: 0,
        });
        const lineCorrected = new THREE.Line(geoCorrected, matCorrected);
        simPlayer.pathPreviewGroup.add(lineCorrected);
        fadeMaterials.push({ material: matCorrected, target: 0.8 });

        // Burn point marker on the original path (cyan cone)
        const burnPos = toVec3(scenario.path_object1[scenario.maneuver_frame]);
        const burnMarkerGeo = new THREE.ConeGeometry(0.015, 0.04, 8);
        const burnMarkerMat = new THREE.MeshBasicMaterial({
            color: 0x06ffd0,
            transparent: true,
            opacity: 0,
        });
        const burnMarker = new THREE.Mesh(burnMarkerGeo, burnMarkerMat);
        burnMarker.position.copy(burnPos);
        simPlayer.pathPreviewGroup.add(burnMarker);
        fadeMaterials.push({ material: burnMarkerMat, target: 0.9 });
    }

    // TCA ring marker (pulsing)
    const tcaPos = toVec3(scenario.path_object1[scenario.tca_frame]);

    // Scatter the ambient debris pieces around the TCA point so they
    // read as background clutter near the danger zone
    if (simPlayer.ambientDebris && simPlayer.ambientDebris.length > 0) {
        simPlayer.ambientDebris.forEach(d => {
            d.orbitCenter = tcaPos.clone();
        });
    }

    const tcaGeo = new THREE.RingGeometry(0.022, 0.03, 32);
    const tcaMat = new THREE.MeshBasicMaterial({
        color: 0xff9500,
        transparent: true,
        opacity: 0,
        side: THREE.DoubleSide,
    });
    simPlayer.tcaMarker = new THREE.Mesh(tcaGeo, tcaMat);
    simPlayer.tcaMarker.position.copy(tcaPos);
    simPlayer.tcaMarker.lookAt(camera.position);
    simPlayer.pathPreviewGroup.add(simPlayer.tcaMarker);
    fadeMaterials.push({ material: tcaMat, target: 0.85 });

    scene.add(simPlayer.pathPreviewGroup);

    // Fade in all preview materials over ~800ms
    const fadeStart = Date.now();
    const fadeDuration = 800;
    function fadeStep() {
        if (!simPlayer.pathPreviewGroup) return; // cleared already
        const elapsed = Date.now() - fadeStart;
        const t = Math.min(elapsed / fadeDuration, 1);
        fadeMaterials.forEach(({ material, target }) => {
            material.opacity = target * t;
        });
        if (t < 1) requestAnimationFrame(fadeStep);
    }
    fadeStep();

    // Subtle pulsing animation for the TCA ring marker
    simPlayer.tcaPulseInterval = setInterval(() => {
        if (!simPlayer.tcaMarker) {
            clearInterval(simPlayer.tcaPulseInterval);
            simPlayer.tcaPulseInterval = null;
            return;
        }
        const scale = 1.0 + Math.sin(Date.now() * 0.004) * 0.25;
        simPlayer.tcaMarker.scale.set(scale, scale, scale);
    }, 40);
}

function updateSimFrame(data) {
    if (!simPlayer.simGroup) return;

    const pos1 = new THREE.Vector3(
        data.object1_pos[0] * SCALE,
        data.object1_pos[2] * SCALE,
        data.object1_pos[1] * SCALE
    );
    const pos2 = new THREE.Vector3(
        data.object2_pos[0] * SCALE,
        data.object2_pos[2] * SCALE,
        data.object2_pos[1] * SCALE
    );

    // Update spacecraft positions
    simPlayer.obj1Mesh.position.copy(pos1);
    simPlayer.obj2Mesh.position.copy(pos2);

    // Slow self-rotation for the satellite model (character animation)
    simPlayer.obj1Mesh.rotation.y += 0.01;

    // Chaotic tumbling for the debris model
    simPlayer.obj2Mesh.rotation.x += 0.018;
    simPlayer.obj2Mesh.rotation.y += 0.011;
    simPlayer.obj2Mesh.rotation.z += 0.006;

    // Animate the ambient background debris: each orbits around the TCA
    // point (or origin as a fallback) on its own tilted circular path,
    // plus continuous chaotic tumbling
    if (simPlayer.ambientDebris && simPlayer.ambientDebris.length > 0) {
        const nowSec = Date.now() / 1000;
        simPlayer.ambientDebris.forEach(d => {
            const center = d.orbitCenter || new THREE.Vector3(0, 0, 0);
            const angle = d.orbitPhase + nowSec * d.orbitSpeed;

            // Circular path in a plane perpendicular to orbitAxis, via
            // two vectors spanning that plane
            const arbitrary = Math.abs(d.orbitAxis.x) < 0.9
                ? new THREE.Vector3(1, 0, 0)
                : new THREE.Vector3(0, 1, 0);
            const u = new THREE.Vector3().crossVectors(d.orbitAxis, arbitrary).normalize();
            const v = new THREE.Vector3().crossVectors(d.orbitAxis, u).normalize();

            const offset = u.clone().multiplyScalar(Math.cos(angle) * d.orbitRadius)
                .add(v.clone().multiplyScalar(Math.sin(angle) * d.orbitRadius));

            d.mesh.position.copy(center).add(offset);
            d.mesh.rotation.x += d.spinSpeed.x;
            d.mesh.rotation.y += d.spinSpeed.y;
            d.mesh.rotation.z += d.spinSpeed.z;
        });
    }

    // Blink the satellite's anti-collision beacon
    if (simPlayer.obj1Mesh.userData.beacon) {
        const blinkOn = Math.sin(vizState.animationTime * 8) > 0.6;
        simPlayer.obj1Mesh.userData.beacon.material.opacity = blinkOn ? 1 : 0.15;
    }

    // Update floating labels (positioned slightly above each mesh)
    if (simPlayer.label1) {
        simPlayer.label1.position.set(pos1.x, pos1.y + 0.08, pos1.z);
    }
    if (simPlayer.label2) {
        simPlayer.label2.position.set(pos2.x, pos2.y + 0.08, pos2.z);
    }

    // Update velocity direction arrows from previous frame's position
    if (simPlayer.velocityArrow1) {
        simPlayer.velocityArrow1.position.copy(pos1);
        if (simPlayer.prevPos1) {
            const dir1 = pos1.clone().sub(simPlayer.prevPos1);
            if (dir1.lengthSq() > 1e-10) {
                simPlayer.velocityArrow1.setDirection(dir1.normalize());
            }
        }
    }
    if (simPlayer.velocityArrow2) {
        simPlayer.velocityArrow2.position.copy(pos2);
        if (simPlayer.prevPos2) {
            const dir2 = pos2.clone().sub(simPlayer.prevPos2);
            if (dir2.lengthSq() > 1e-10) {
                simPlayer.velocityArrow2.setDirection(dir2.normalize());
            }
        }
    }
    simPlayer.prevPos1 = pos1.clone();
    simPlayer.prevPos2 = pos2.clone();

    // Update distance line (reuse geometry, just update positions)
    const posAttr = simPlayer.distanceLine.geometry.getAttribute('position');
    if (posAttr) {
        posAttr.array[0] = pos1.x;
        posAttr.array[1] = pos1.y;
        posAttr.array[2] = pos1.z;
        posAttr.array[3] = pos2.x;
        posAttr.array[4] = pos2.y;
        posAttr.array[5] = pos2.z;
        posAttr.needsUpdate = true;
    }

    // Color distance line by proximity (green -> yellow -> red)
    const dist = data.distance_km;
    let lineColor;
    if (dist > 500) lineColor = 0x30d158;
    else if (dist > 100) lineColor = 0xffcc00;
    else if (dist > 10) lineColor = 0xff9500;
    else lineColor = 0xff2d55;
    simPlayer.distanceLine.material.color.setHex(lineColor);
    simPlayer.distanceLine.material.opacity = Math.min(0.8, 500 / Math.max(dist, 1));

    // Update trails every 3rd frame to avoid performance issues
    if (data.frame % 3 === 0) {
        simPlayer.trailPoints1.push(pos1.clone());
        simPlayer.trailPoints2.push(pos2.clone());

        // Limit trail length
        const maxTrail = 80;
        if (simPlayer.trailPoints1.length > maxTrail) simPlayer.trailPoints1.shift();
        if (simPlayer.trailPoints2.length > maxTrail) simPlayer.trailPoints2.shift();

        // Update trail 1 geometry in-place
        if (simPlayer.trailPoints1.length > 2) {
            if (!simPlayer.obj1Trail) {
                const trailGeo = new THREE.BufferGeometry();
                const trailMat = new THREE.LineBasicMaterial({
                    color: 0x00d4ff, transparent: true, opacity: 0.6
                });
                simPlayer.obj1Trail = new THREE.Line(trailGeo, trailMat);
                scene.add(simPlayer.obj1Trail);
            }
            simPlayer.obj1Trail.geometry.setFromPoints(simPlayer.trailPoints1);
            simPlayer.obj1Trail.material.color.setHex(data.is_corrected ? 0x06ffd0 : 0x00d4ff);
        }

        // Update trail 2 geometry in-place
        if (simPlayer.trailPoints2.length > 2) {
            if (!simPlayer.obj2Trail) {
                const trailGeo = new THREE.BufferGeometry();
                const trailMat = new THREE.LineBasicMaterial({
                    color: 0xff4444, transparent: true, opacity: 0.5
                });
                simPlayer.obj2Trail = new THREE.Line(trailGeo, trailMat);
                scene.add(simPlayer.obj2Trail);
            }
            simPlayer.obj2Trail.geometry.setFromPoints(simPlayer.trailPoints2);
        }
    }

    // Animate burn effect
    if (simPlayer.burnEffect) {
        simPlayer.burnEffect.position.copy(pos1);
        // Orient burn cone away from velocity direction
        if (simPlayer.trailPoints1.length > 3) {
            const prev = simPlayer.trailPoints1[simPlayer.trailPoints1.length - 3];
            const dir = pos1.clone().sub(prev).normalize();
            simPlayer.burnEffect.lookAt(pos1.clone().sub(dir));
        }
    }
}

function handleSimEvent(evt) {
    const type = evt.type;
    const message = evt.message;

    // Visual effects based on event type
    switch (type) {
        case 'radar_contact':
            addEventLogEntry('info', message);
            break;

        case 'detection':
            addEventLogEntry('warning', message);
            break;

        case 'orbit_refinement':
            addEventLogEntry('info', message);
            break;

        case 'covariance_update':
            addEventLogEntry('info', message);
            break;

        case 'risk_assessment':
            addEventLogEntry('critical', message);
            // Pulse the danger indicator
            flashDangerIndicator();
            // Cinematic zoom toward a point between both objects
            if (simPlayer.obj1Mesh && simPlayer.obj2Mesh) {
                const mid = simPlayer.obj1Mesh.position.clone()
                    .add(simPlayer.obj2Mesh.position).multiplyScalar(0.5);
                const camTarget = mid.clone().add(new THREE.Vector3(1.2, 1.2, 1.2).normalize().multiplyScalar(1.2));
                animateCamera(camTarget, mid, 1300);
            }
            break;

        case 'ground_alert':
            addEventLogEntry('warning', message);
            break;

        case 'fuel_check':
            addEventLogEntry('info', message);
            break;

        case 'maneuver_planning':
            addEventLogEntry('info', message);
            break;

        case 'attitude_control':
            addEventLogEntry('info', message);
            break;

        case 'maneuver_execute':
            addEventLogEntry('burn', message);
            activateBurnEffect();
            break;

        case 'maneuver_complete':
            addEventLogEntry('success', message);
            deactivateBurnEffect();
            break;

        case 'post_burn_tracking':
            addEventLogEntry('success', message);
            break;

        case 'final_approach':
            addEventLogEntry('warning', message);
            break;

        case 'no_maneuver':
            addEventLogEntry('critical', message);
            break;

        case 'operator_response':
            addEventLogEntry('info', message);
            break;

        case 'impact_imminent':
            addEventLogEntry('critical', message);
            flashDangerIndicator();
            break;

        case 'collision':
            addEventLogEntry('explosion', message);
            triggerCollisionFlash();
            // Cinematic tight zoom to the TCA point
            zoomToTcaPoint();
            break;

        case 'debris_field_analysis':
            addEventLogEntry('critical', message);
            break;

        case 'closest_approach':
            addEventLogEntry('success', message);
            // Cinematic tight zoom to the TCA point
            zoomToTcaPoint();
            break;

        case 'secondary_screening':
            addEventLogEntry('info', message);
            break;

        case 'scenario_end':
            addEventLogEntry('info', message);
            // Pull back to the wide establishing shot
            animateCamera(new THREE.Vector3(2.5, 1.5, 3.5), new THREE.Vector3(0, 0, 0), 1500);
            break;

        case 'archival':
            addEventLogEntry('info', message);
            break;

        default:
            addEventLogEntry('info', message);
    }
}

function addEventLogEntry(type, message) {
    const log = document.getElementById('sim-event-log');
    if (!log) return;

    const entry = document.createElement('div');
    entry.className = `event-entry event-${type}`;

    const timestamp = (simPlayer.currentFrame * 0.05 / simPlayer.speed).toFixed(1);
    entry.innerHTML = `
        <span class="event-time">T+${timestamp}s</span>
        <span class="event-icon">${getEventIcon(type)}</span>
        <span class="event-msg">${message}</span>
    `;
    log.appendChild(entry);
    log.scrollTop = log.scrollHeight;
}

function getEventIcon(type) {
    switch (type) {
        case 'critical': return '&#9888;';
        case 'warning': return '&#9679;';
        case 'burn': return '&#128293;';
        case 'success': return '&#9989;';
        case 'explosion': return '&#128165;';
        case 'info': return '&#8226;';
        default: return '&#8226;';
    }
}

function activateBurnEffect() {
    if (!simPlayer.burnEffect) return;
    simPlayer.burnEffect.material.opacity = 0.9;
    simPlayer.burnEffect.scale.set(1.5, 2, 1.5);

    // Change object 1 glow to orange during burn
    if (simPlayer.obj1Mesh && simPlayer.obj1Mesh.userData.glow) {
        simPlayer.obj1Mesh.userData.glow.material.color.setHex(0xff8800);
        simPlayer.obj1Mesh.userData.glow.material.opacity = 0.6;
    }
}

function deactivateBurnEffect() {
    if (!simPlayer.burnEffect) return;
    // Fade out burn over time
    let opacity = 0.9;
    const fadeInterval = setInterval(() => {
        opacity -= 0.05;
        if (opacity <= 0) {
            simPlayer.burnEffect.material.opacity = 0;
            simPlayer.burnEffect.scale.set(1, 1, 1);
            clearInterval(fadeInterval);
            // Restore glow color
            if (simPlayer.obj1Mesh && simPlayer.obj1Mesh.userData.glow) {
                simPlayer.obj1Mesh.userData.glow.material.color.setHex(0x06ffd0);
                simPlayer.obj1Mesh.userData.glow.material.opacity = 0.4;
            }
        } else {
            simPlayer.burnEffect.material.opacity = opacity;
        }
    }, 50);
}

function triggerCollisionFlash() {
    if (!simPlayer.obj1Mesh) return;

    // Big flash at collision point
    const pos = simPlayer.obj1Mesh.position.clone();
    const flashGeo = new THREE.SphereGeometry(0.08, 16, 16);
    const flashMat = new THREE.MeshBasicMaterial({
        color: 0xffffff,
        transparent: true,
        opacity: 1.0,
        blending: THREE.AdditiveBlending
    });
    const flash = new THREE.Mesh(flashGeo, flashMat);
    flash.position.copy(pos);
    scene.add(flash);

    // Expand and fade
    let scale = 1;
    const expandInterval = setInterval(() => {
        scale += 0.3;
        flash.scale.set(scale, scale, scale);
        flash.material.opacity -= 0.04;
        if (flash.material.opacity <= 0) {
            scene.remove(flash);
            clearInterval(expandInterval);
        }
    }, 30);

    // Hide the spacecraft (they've been destroyed)
    simPlayer.obj1Mesh.visible = false;
    simPlayer.obj2Mesh.visible = false;
    simPlayer.distanceLine.visible = false;
}

function spawnDebrisExplosion(fragments) {
    if (!fragments || fragments.length === 0) return;

    const count = fragments.length;
    const positions = new Float32Array(count * 3);
    const velocities = new Float32Array(count * 3);
    const colors = new Float32Array(count * 3);

    for (let i = 0; i < count; i++) {
        positions[i * 3] = fragments[i][0] * SCALE;
        positions[i * 3 + 1] = fragments[i][2] * SCALE;
        positions[i * 3 + 2] = fragments[i][1] * SCALE;

        // Random velocities for expansion
        velocities[i * 3] = (Math.random() - 0.5) * 0.002;
        velocities[i * 3 + 1] = (Math.random() - 0.5) * 0.002;
        velocities[i * 3 + 2] = (Math.random() - 0.5) * 0.002;

        // Orange-red colors
        colors[i * 3] = 0.8 + Math.random() * 0.2;
        colors[i * 3 + 1] = 0.2 + Math.random() * 0.4;
        colors[i * 3 + 2] = 0.0 + Math.random() * 0.1;
    }

    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    geo.userData = { velocities: velocities };

    const mat = new THREE.PointsMaterial({
        size: 0.012,
        vertexColors: true,
        transparent: true,
        opacity: 0.9,
        blending: THREE.AdditiveBlending,
        sizeAttenuation: true
    });

    simPlayer.debrisCloud = new THREE.Points(geo, mat);
    scene.add(simPlayer.debrisCloud);

    // Animate debris expansion
    let debrisFrame = 0;
    const debrisInterval = setInterval(() => {
        if (!simPlayer.debrisCloud) { clearInterval(debrisInterval); return; }
        const pos = simPlayer.debrisCloud.geometry.attributes.position.array;
        const vel = simPlayer.debrisCloud.geometry.userData.velocities;
        for (let i = 0; i < pos.length; i++) {
            pos[i] += vel[i];
        }
        simPlayer.debrisCloud.geometry.attributes.position.needsUpdate = true;
        simPlayer.debrisCloud.material.opacity -= 0.003;
        debrisFrame++;
        if (debrisFrame > 200 || simPlayer.debrisCloud.material.opacity <= 0) {
            clearInterval(debrisInterval);
        }
    }, 30);
}

function zoomToTcaPoint() {
    if (!simPlayer.scenario) return;
    const tcaPos = simPlayer.scenario.path_object1[simPlayer.scenario.tca_frame];
    const tcaVec = new THREE.Vector3(
        tcaPos[0] * SCALE, tcaPos[2] * SCALE, tcaPos[1] * SCALE
    );
    // Distance ~1.0 along a diagonal offset for a tight, cinematic framing
    const camTarget = tcaVec.clone().add(new THREE.Vector3(0.6, 0.6, 0.6).normalize().multiplyScalar(1.0));
    animateCamera(camTarget, tcaVec, 1400);
}

function updateSimHud(scenario, frame, dist) {
    const hud = document.getElementById('sim-hud');
    if (!hud || hud.classList.contains('hidden')) return;

    const distEl = document.getElementById('hud-distance');
    const missEl = document.getElementById('hud-miss-distance');
    const velEl = document.getElementById('hud-velocity');
    const tcaEl = document.getElementById('hud-tca');

    // Current separation: live distance between both objects right now
    if (distEl) distEl.textContent = dist.toFixed(1) + ' km';

    // Predicted miss distance at TCA: the minimum separation the trajectory
    // predicts at closest approach (from scenario precomputation)
    if (missEl) {
        const missDistKm = scenario.min_distance_km;
        if (missDistKm !== undefined && missDistKm !== null) {
            missEl.textContent = missDistKm.toFixed(2) + ' km';
        } else {
            missEl.textContent = '-- km';
        }
    }

    // Relative velocity: use scenario metadata (fixed physical property of the encounter)
    // Do NOT recompute from Δdist/Δt, as the synthetic paths don't correspond to
    // the real physical time steps of the encounter.
    if (velEl) {
        const relVel = scenario.metadata?.relative_velocity_kms || 0;
        velEl.textContent = relVel.toFixed(2) + ' km/s (closing)';
    }
    simPlayer._prevHudDist = dist;

    // Estimated time to TCA
    if (tcaEl) {
        const framesRemaining = scenario.tca_frame - frame;
        if (framesRemaining <= 0) {
            tcaEl.textContent = 'PASSED';
        } else {
            const secondsRemaining = framesRemaining * 0.05 / simPlayer.speed;
            tcaEl.textContent = secondsRemaining.toFixed(1) + ' s';
        }
    }
}

function flashDangerIndicator() {
    const status = document.getElementById('sim-status');
    if (!status) return;
    status.classList.add('flash-danger');
    setTimeout(() => status.classList.remove('flash-danger'), 1000);
}


// ============================================================================
// START
// ============================================================================

window.addEventListener('DOMContentLoaded', init);
