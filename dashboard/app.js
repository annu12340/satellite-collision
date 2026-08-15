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
};

// Scale factor: Real Earth radius = 6378km, we use radius=1 in scene
const SCALE = 1.0 / 6378.137;
const EARTH_RADIUS = 1.0;

// ============================================================================
// INITIALIZATION
// ============================================================================

async function init() {
    updateLoadStatus('Fetching simulation data...', 20);

    try {
        const response = await fetch('/api/all');
        simData = await response.json();
        updateLoadStatus('Building 3D scene...', 50);
    } catch (err) {
        console.error('Failed to fetch simulation data:', err);
        updateLoadStatus('Error connecting to server. Retrying...', 20);
        setTimeout(init, 2000);
        return;
    }

    initThreeJS();
    updateLoadStatus('Creating Earth...', 60);

    createEarth();
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

// ============================================================================
// ORBITS
// ============================================================================

function createOrbits() {
    if (!simData || !simData.spacecraft) return;

    const orbitGroup = new THREE.Group();
    orbitGroup.name = 'orbits';

    simData.spacecraft.forEach((sc, idx) => {
        if (!sc.orbit_path || sc.orbit_path.length < 3) return;

        const points = sc.orbit_path.map(p =>
            new THREE.Vector3(p[0] * SCALE, p[2] * SCALE, p[1] * SCALE)
        );

        // Close the orbit loop
        points.push(points[0]);

        const curve = new THREE.CatmullRomCurve3(points, true);
        const geometry = new THREE.BufferGeometry().setFromPoints(curve.getPoints(150));

        // Color based on spacecraft type
        let color;
        switch (sc.type) {
            case 'COMSAT': color = new THREE.Color(0x00d4ff); break;
            case 'EOS': color = new THREE.Color(0x7b2ff7); break;
            case 'CUBE': color = new THREE.Color(0x06ffd0); break;
            case 'DEBRIS': color = new THREE.Color(0x5a6b8a); break;
            default: color = new THREE.Color(0x3a5588);
        }

        const material = new THREE.LineBasicMaterial({
            color: color,
            transparent: true,
            opacity: sc.type === 'DEBRIS' ? 0.15 : 0.3,
            linewidth: 1
        });

        const line = new THREE.Line(geometry, material);
        line.userData = { type: 'orbit', spacecraft: sc, index: idx };
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
        }
    });

    scene.add(scGroup);
}

// ============================================================================
// CONJUNCTIONS
// ============================================================================

function createConjunctions() {
    if (!simData || !simData.conjunctions) return;

    const conjGroup = new THREE.Group();
    conjGroup.name = 'conjunctions';

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

        // Dashed line between objects
        const points = [pos1, pos2];
        const geometry = new THREE.BufferGeometry().setFromPoints(points);
        const material = new THREE.LineDashedMaterial({
            color: color,
            dashSize: 0.02,
            gapSize: 0.01,
            transparent: true,
            opacity: 0.8,
            linewidth: 2
        });

        const line = new THREE.Line(geometry, material);
        line.computeLineDistances();
        line.userData = { type: 'conjunction', data: conj, index: idx };
        conjGroup.add(line);
        conjunctionLines.push(line);

        // Warning marker at midpoint
        const midpoint = pos1.clone().add(pos2).multiplyScalar(0.5);
        const markerGeom = new THREE.OctahedronGeometry(0.012, 0);
        const markerMat = new THREE.MeshBasicMaterial({
            color: color,
            transparent: true,
            opacity: 0.9,
        });
        const marker = new THREE.Mesh(markerGeom, markerMat);
        marker.position.copy(midpoint);
        marker.userData = { type: 'conjunction', data: conj, index: idx };
        conjGroup.add(marker);

        // Glow around critical conjunctions
        if (conj.risk_level === 'CRITICAL' || conj.risk_level === 'HIGH') {
            const glowGeom = new THREE.SphereGeometry(0.025, 12, 12);
            const glowMat = new THREE.MeshBasicMaterial({
                color: color,
                transparent: true,
                opacity: 0.15,
                blending: THREE.AdditiveBlending
            });
            const glow = new THREE.Mesh(glowGeom, glowMat);
            glow.position.copy(midpoint);
            conjGroup.add(glow);
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

function populateDashboard() {
    if (!simData) return;

    const risk = simData.risk_metrics;

    // Header stats
    document.getElementById('h-objects').textContent = risk.total_spacecraft;
    document.getElementById('h-conjunctions').textContent = risk.total_conjunctions;

    const threatLevel = risk.critical_conjunctions > 0 ? 'ELEVATED' :
                        risk.high_risk_conjunctions > 0 ? 'GUARDED' : 'NOMINAL';
    const threatEl = document.getElementById('h-threat');
    threatEl.textContent = threatLevel;
    threatEl.className = 'stat-value ' + (
        threatLevel === 'ELEVATED' ? 'warning' :
        threatLevel === 'GUARDED' ? '' : 'success'
    );

    // Risk metrics
    document.getElementById('m-critical').textContent = risk.critical_conjunctions;
    document.getElementById('m-high').textContent = risk.high_risk_conjunctions;
    document.getElementById('m-maneuvers').textContent = risk.maneuvers_planned;
    document.getElementById('m-fuel').textContent = risk.total_fuel_cost_ms.toFixed(1);

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

    // Maneuver list
    populateManeuverList();

    // Kessler gauge
    const kesslerValue = risk.critical_conjunctions * 0.15 +
                         risk.high_risk_conjunctions * 0.05;
    const kesslerClamped = Math.min(kesslerValue, 1.0);
    document.getElementById('kessler-fill').style.width = (kesslerClamped * 100) + '%';
    document.getElementById('kessler-value').textContent = kesslerClamped.toFixed(3);

    if (kesslerClamped > 0.7) {
        document.getElementById('kessler-fill').style.background = 'var(--gradient-danger)';
    } else if (kesslerClamped > 0.4) {
        document.getElementById('kessler-fill').style.background =
            'linear-gradient(90deg, #06ffd0, #ffcc00)';
    }

    // Charts
    drawRiskTimeline();
    drawAltitudeChart();

    // Clock
    updateClock();
    setInterval(updateClock, 1000);
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

function populateManeuverList() {
    const container = document.getElementById('maneuver-list');
    container.innerHTML = '';

    if (!simData.maneuvers || simData.maneuvers.length === 0) {
        container.innerHTML = '<div style="color:var(--text-muted);font-size:0.7rem;padding:8px;">No maneuvers scheduled</div>';
        return;
    }

    simData.maneuvers.slice(0, 8).forEach(man => {
        const item = document.createElement('div');
        item.className = 'maneuver-item';
        const dvMag = Math.sqrt(
            man.delta_v_rtn_ms[0] ** 2 +
            man.delta_v_rtn_ms[1] ** 2 +
            man.delta_v_rtn_ms[2] ** 2
        ).toFixed(2);
        item.innerHTML = `
            <div class="man-header">
                <span class="man-sc">${man.spacecraft_id}</span>
                <span class="man-time">T+${man.time_hours.toFixed(1)}h</span>
            </div>
            <div class="man-details">
                |&Delta;v| = ${dvMag} m/s &middot; RTN [${man.delta_v_rtn_ms[0].toFixed(1)}, ${man.delta_v_rtn_ms[1].toFixed(1)}, ${man.delta_v_rtn_ms[2].toFixed(1)}]
            </div>
        `;
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

function drawAltitudeChart() {
    const canvas = document.getElementById('altitude-chart');
    if (!canvas || !simData.spacecraft) return;

    const ctx = canvas.getContext('2d');
    const w = canvas.width;
    const h = canvas.height;
    const padding = { top: 10, right: 10, bottom: 20, left: 35 };

    ctx.clearRect(0, 0, w, h);

    // Create altitude histogram
    const altitudes = simData.spacecraft.map(sc => sc.altitude_km);
    const minAlt = Math.min(...altitudes);
    const maxAlt = Math.max(...altitudes);
    const bins = 15;
    const binWidth = (maxAlt - minAlt) / bins;
    const histogram = new Array(bins).fill(0);

    altitudes.forEach(alt => {
        const bin = Math.min(Math.floor((alt - minAlt) / binWidth), bins - 1);
        histogram[bin]++;
    });

    const maxCount = Math.max(...histogram);
    const plotW = w - padding.left - padding.right;
    const plotH = h - padding.top - padding.bottom;
    const barWidth = plotW / bins - 2;

    // Draw bars
    histogram.forEach((count, i) => {
        const x = padding.left + (i / bins) * plotW + 1;
        const barH = (count / maxCount) * plotH;
        const y = padding.top + plotH - barH;

        // Gradient color based on position
        const t = i / bins;
        const r = Math.floor(6 + t * 245);
        const g = Math.floor(255 - t * 192);
        const b = Math.floor(208 - t * 67);
        ctx.fillStyle = `rgba(${r}, ${g}, ${b}, 0.7)`;
        ctx.fillRect(x, y, barWidth, barH);
    });

    // Labels
    ctx.fillStyle = '#5a6b8a';
    ctx.font = '9px JetBrains Mono';
    ctx.textAlign = 'center';
    ctx.fillText(`${minAlt.toFixed(0)}`, padding.left, h - 4);
    ctx.fillText(`${((minAlt + maxAlt) / 2).toFixed(0)}`, padding.left + plotW / 2, h - 4);
    ctx.fillText(`${maxAlt.toFixed(0)}`, padding.left + plotW, h - 4);
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

    // Pulse conjunction markers
    const conjGroup = scene.getObjectByName('conjunctions');
    if (conjGroup) {
        conjGroup.children.forEach(child => {
            if (child.type === 'Mesh' && child.geometry.type === 'OctahedronGeometry') {
                child.rotation.y += 0.02;
                child.rotation.x += 0.01;
                const scale = 1.0 + Math.sin(vizState.animationTime * 3) * 0.2;
                child.scale.set(scale, scale, scale);
            }
        });
    }

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
            return;
        }

        // Get positions for this frame
        const hasCorrection = scenario.has_correction;
        const useCorrection = hasCorrection && frame >= scenario.maneuver_frame;
        const pos1Raw = useCorrection ? scenario.path_object1_corrected[frame] : scenario.path_object1[frame];
        const pos2Raw = scenario.path_object2[frame];
        const dist = useCorrection ? scenario.distances_corrected[frame] : scenario.distances[frame];

        const frameData = {
            frame: frame,
            progress: frame / scenario.n_frames,
            object1_pos: pos1Raw,
            object2_pos: pos2Raw,
            distance_km: dist,
            is_corrected: useCorrection
        };

        updateSimFrame(frameData);

        // Update progress
        const pct = (frameData.progress * 100).toFixed(1);
        document.getElementById('sim-progress-fill').style.width = pct + '%';
        document.getElementById('sim-distance').textContent = dist.toFixed(1) + ' km';

        // Update the in-viewport telemetry HUD
        updateSimHud(scenario, frame, dist);

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

    // Hide the telemetry HUD
    const hud = document.getElementById('sim-hud');
    if (hud) hud.classList.add('hidden');

    clearSimObjects();
}

function createSimObjects() {
    simPlayer.simGroup = new THREE.Group();
    simPlayer.simGroup.name = 'simulation';

    // Object 1 (maneuverable spacecraft) - bright cyan sphere
    const geo1 = new THREE.SphereGeometry(0.035, 16, 16);
    const mat1 = new THREE.MeshBasicMaterial({
        color: 0x00d4ff,
        transparent: true,
        opacity: 1.0
    });
    simPlayer.obj1Mesh = new THREE.Mesh(geo1, mat1);
    simPlayer.simGroup.add(simPlayer.obj1Mesh);

    // Object 1 glow
    const glow1Geo = new THREE.SphereGeometry(0.06, 12, 12);
    const glow1Mat = new THREE.MeshBasicMaterial({
        color: 0x00d4ff,
        transparent: true,
        opacity: 0.35,
        blending: THREE.AdditiveBlending
    });
    const glow1 = new THREE.Mesh(glow1Geo, glow1Mat);
    simPlayer.obj1Mesh.add(glow1);

    // Object 2 (debris/target) - red-orange sphere
    const geo2 = new THREE.SphereGeometry(0.03, 16, 16);
    const mat2 = new THREE.MeshBasicMaterial({
        color: 0xff4444,
        transparent: true,
        opacity: 1.0
    });
    simPlayer.obj2Mesh = new THREE.Mesh(geo2, mat2);
    simPlayer.simGroup.add(simPlayer.obj2Mesh);

    // Object 2 glow
    const glow2Geo = new THREE.SphereGeometry(0.05, 12, 12);
    const glow2Mat = new THREE.MeshBasicMaterial({
        color: 0xff4444,
        transparent: true,
        opacity: 0.3,
        blending: THREE.AdditiveBlending
    });
    const glow2 = new THREE.Mesh(glow2Geo, glow2Mat);
    simPlayer.obj2Mesh.add(glow2);

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
        case 'detection':
            addEventLogEntry('warning', message);
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

        case 'maneuver_planning':
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

        case 'no_maneuver':
            addEventLogEntry('critical', message);
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

        case 'closest_approach':
            addEventLogEntry('success', message);
            // Cinematic tight zoom to the TCA point
            zoomToTcaPoint();
            break;

        case 'scenario_end':
            addEventLogEntry('info', message);
            // Pull back to the wide establishing shot
            animateCamera(new THREE.Vector3(2.5, 1.5, 3.5), new THREE.Vector3(0, 0, 0), 1500);
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
    if (simPlayer.obj1Mesh && simPlayer.obj1Mesh.children[0]) {
        simPlayer.obj1Mesh.children[0].material.color.setHex(0xff8800);
        simPlayer.obj1Mesh.children[0].material.opacity = 0.6;
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
            if (simPlayer.obj1Mesh && simPlayer.obj1Mesh.children[0]) {
                simPlayer.obj1Mesh.children[0].material.color.setHex(0x06ffd0);
                simPlayer.obj1Mesh.children[0].material.opacity = 0.4;
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
    const velEl = document.getElementById('hud-velocity');
    const tcaEl = document.getElementById('hud-tca');

    if (distEl) distEl.textContent = dist.toFixed(1) + ' km';

    // Closing/relative velocity: derived from the change in distance over one frame
    if (velEl) {
        const prevDist = simPlayer._prevHudDist;
        if (prevDist !== undefined) {
            const closingKms = (prevDist - dist) / 0.05;
            velEl.textContent = Math.abs(closingKms).toFixed(2) + ' km/s ' + (closingKms >= 0 ? '(closing)' : '(opening)');
        } else {
            velEl.textContent = '-- km/s';
        }
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
