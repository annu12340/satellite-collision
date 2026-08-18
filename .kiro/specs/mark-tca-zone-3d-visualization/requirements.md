# Requirements Document: Mark TCA Zone in 3D Visualization

## Introduction

The TCA (Time of Closest Approach) Zone is a visual indicator in the 3D orbital visualization that highlights the spatial region where a critical pair of satellites approaches their closest point. This feature enhances operator awareness by showing not just the collision trajectory line, but also the geometric zone of highest risk around the predicted closest approach location.

The TCA Zone is displayed as an animated semi-transparent sphere positioned at the midpoint between the two critical spacecraft, with a red-to-yellow gradient appearance and subtle pulsing opacity to draw attention without dominating the scene.

## Glossary

- **System**: The Three.js-based 3D orbital visualization dashboard (Orbital Sentinel)
- **TCA (Time of Closest Approach)**: The calculated time when two satellites will reach their minimum distance during an encounter
- **TCA Zone**: A visual indicator sphere centered at the predicted closest approach midpoint
- **Critical Pair**: The highest-risk conjunction pair among all tracked conjunctions (selected by risk priority: CRITICAL > HIGH > MEDIUM > LOW)
- **Conjunction Group**: The Three.js scene group (`conjGroup`) containing all visual representations of conjunctions (lines, glows, markers)
- **Midpoint**: The geometric center point between obj1_pos and obj2_pos of a critical pair
- **Scene Units**: The Three.js coordinate system where Earth radius = 1.0 scene units (scaling factor: 1.0 / 6378.137 km)
- **Opacity Fade Animation**: A cyclical pulsing effect where base opacity modulates between low and high values at a fixed frequency
- **Additive Blending**: Three.js blending mode that combines colors by addition (brightens when overlapping with other emissive objects)

## Requirements

### Requirement 1: TCA Zone Visual Representation

**User Story:** As an operator, I want to see a distinct visual marker for the Time of Closest Approach zone so that I can immediately identify where the highest collision risk occurs in 3D space.

#### Acceptance Criteria

1. WHEN a critical pair is identified in the conjunction list, THE System SHALL render a semi-transparent sphere (the TCA Zone) at the midpoint between the two spacecraft positions.

2. THE TCA Zone sphere SHALL have a fixed radius of approximately 0.05 scene units (representing a visible but not oversized zone in the 3D view).

3. THE TCA Zone material SHALL use additive blending mode (THREE.AdditiveBlending) to maintain visibility when overlapping with other glowing elements.

4. THE TCA Zone material SHALL have a transparency setting enabled (transparent: true) to allow the gradient effect and pulsing to be visible through it.

---

### Requirement 2: TCA Zone Color Gradient

**User Story:** As an operator, I want the TCA Zone to have a visual gradient from red (danger) at the core to yellow (warning) at the edges so that the severity is communicated through color progression.

#### Acceptance Criteria

1. WHEN the TCA Zone is rendered, THE System SHALL apply a red-to-yellow radial gradient appearing as a core of red (#ff2d55 or similar) fading to yellow (#ffcc00 or similar) at the outer edge.

2. THE gradient appearance SHALL be achieved using a Three.js ShaderMaterial or by vertex coloring on a custom mesh that provides smooth color interpolation from center to radius.

3. WHERE vertex coloring is used, THE inner vertices (near center) SHALL be assigned the red color and the outer vertices SHALL be assigned the yellow color to create the gradient effect.

4. THE gradient transition SHALL be smooth and continuous, not stepped or discrete.

---

### Requirement 3: TCA Zone Opacity Animation

**User Story:** As an operator, I want the TCA Zone to subtly pulse with varying opacity so that it draws attention to the critical encounter point without becoming visually overwhelming.

#### Acceptance Criteria

1. WHEN the animation loop updates (each frame), THE System SHALL modulate the TCA Zone's opacity using a sinusoidal function with a frequency of 1-2 Hz (period of 0.5 to 1.0 seconds).

2. THE base opacity range for the pulsing animation SHALL be between 0.3 (minimum) and 0.5 (maximum), creating a noticeable but non-intrusive fade effect.

3. WHILE the TCA Zone is visible, THE System SHALL apply the opacity modulation continuously throughout the animation frame to maintain the pulse effect.

4. IF the critical pair is replaced or cleared, THEN THE opacity animation SHALL cease and the zone's opacity SHALL be set to a neutral value (0.3) before the mesh is removed.

---

### Requirement 4: TCA Zone Positioning and Lifecycle

**User Story:** As an operator, I want the TCA Zone to be positioned at the exact encounter midpoint and to appear or disappear based on conjunction status so that spatial representation remains accurate.

#### Acceptance Criteria

1. WHEN a critical pair is identified, THE System SHALL calculate the midpoint as (obj1_pos + obj2_pos) / 2.0 in ECI coordinates.

2. THE TCA Zone sphere position SHALL be set to this midpoint, scaled by the Scene Units scale factor (SCALE constant).

3. THE TCA Zone mesh SHALL be added to the Conjunction Group (conjGroup) during critical pair creation in the createConjunctions() function.

4. WHEN the critical pair is replaced by a new higher-risk conjunction, THE previous TCA Zone mesh SHALL be removed from conjGroup and the new one SHALL be created at the new midpoint location.

5. IF no critical pair exists (all conjunction risk levels fall below CRITICAL), THEN no TCA Zone SHALL be rendered.

---

### Requirement 5: Visual Prominence and Balance

**User Story:** As an operator, I want the TCA Zone to be balanced visually so that it complements rather than dominates the existing critical pair styling (glows, line, rotating marker).

#### Acceptance Criteria

1. WHERE the TCA Zone is rendered alongside existing critical pair elements (bright connecting line, pulsing glows at each spacecraft, pulse ring, rotating marker), THE TCA Zone's base opacity SHALL be set such that it is visible but secondary in visual hierarchy to the connecting line and spacecraft glows.

2. THE TCA Zone opacity range (0.3-0.5) SHALL remain lower than the brightness of the connecting line (opacity: 1.0) and spacecraft glows (opacity: 0.6), ensuring visual balance.

3. THE TCA Zone radius (0.05 scene units) SHALL be proportionally sized between the pulse ring (0.015-0.035) and the bright connecting line width, creating coherent visual grammar.

4. WHEN the viewport updates or camera moves, THE TCA Zone position SHALL remain correctly positioned at the midpoint and SHALL not shift or drift relative to the spacecraft positions.

---

### Requirement 6: Integration with Existing Animation Loop

**User Story:** As a developer, I want the TCA Zone animation to integrate cleanly with the existing animate() loop so that the implementation is maintainable and consistent with current code patterns.

#### Acceptance Criteria

1. WHEN the animate() function executes each frame, THE System SHALL identify all meshes with userData.type === 'tca_zone' in the scene.

2. FOR each TCA Zone mesh, THE System SHALL apply the opacity pulsing calculation using the elapsed time (vizState.animationTime) to determine the current sinusoidal value.

3. THE TCA Zone mesh userData object SHALL store metadata (type: 'tca_zone', isPulsing: true, baseScale: 1, baseOpacity: [min, max]) to support the animation loop logic.

4. WHILE processing collision_glow meshes (userData.type === 'collision_glow') in the animate loop, IF a TCA Zone exists, THE opacity update logic SHALL be applied in the same pattern as existing glow animations.

---

### Requirement 7: Technical Implementation Details

**User Story:** As a developer, I want clear specifications for the mesh construction and shader approach so that the implementation is unambiguous and performant.

#### Acceptance Criteria

1. THE TCA Zone mesh geometry SHALL be created using THREE.SphereGeometry with parameters: radius=0.05, widthSegments=16, heightSegments=16 (sufficient for smooth appearance without excessive polygon count).

2. WHERE vertex coloring is applied (alternative to ShaderMaterial), THE vertices SHALL be colored using THREE.BufferGeometry with a BufferAttribute for color, applying red (#ff2d55) at inner positions and yellow (#ffcc00) at outer radii.

3. IF a ShaderMaterial is used for the gradient, THE shader SHALL accept uniform variables for: baseOpacity (float), pulseOpacity (float), time (float), and the fragment shader SHALL compute the radial gradient based on fragment distance from sphere center.

4. THE TCA Zone material blending mode SHALL be THREE.AdditiveBlending to ensure compatibility with the existing scene lighting and other emissive objects.

5. THE TCA Zone mesh SHALL be created once during createConjunctions() at the time the critical pair is identified, rather than recreated each frame, to minimize performance overhead.

---

### Requirement 8: Data Dependencies and API Contract

**User Story:** As a developer, I want to know what data fields are required from the API to render the TCA Zone so that the implementation is robust to API changes.

#### Acceptance Criteria

1. THE TCA Zone positioning requires the following data fields from each conjunction object in simData.conjunctions: obj1_pos (array [x, y, z]), obj2_pos (array [x, y, z]), and risk_level (string) to identify the critical pair.

2. WHERE simData.conjunctions is not available or contains fewer than one element with risk_level === 'CRITICAL', THE System SHALL not attempt to render a TCA Zone.

3. WHEN simData is updated or refreshed, THE System SHALL recalculate which conjunction is critical and update the TCA Zone position and visibility accordingly.

---

### Requirement 9: Browser Compatibility and Performance

**User Story:** As a developer, I want to ensure the TCA Zone renders efficiently across target browsers so that dashboard performance is maintained.

#### Acceptance Criteria

1. THE TCA Zone implementation SHALL use only standard Three.js geometry and material types (SphereGeometry, MeshBasicMaterial, ShaderMaterial) that are supported in modern WebGL 2.0-capable browsers.

2. WHERE the browser does not support vertex coloring or custom shaders, THE System SHALL fall back to a simpler approach using MeshBasicMaterial with a single color and gradient approximated via opacity layering.

3. THE memory footprint for a single TCA Zone mesh (geometry + material) SHALL not exceed 500 KB to maintain overall scene performance.

4. WHEN rendering the TCA Zone alongside 100+ other scene objects, THE frame rate impact SHALL be less than 5% on a machine capable of 60 FPS (measured before and after zone addition).

