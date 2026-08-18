# Demo Testing Guide - 3D Visualization

## Quick Start

1. **Launch Dashboard**
   ```bash
   cd /Users/annu/Desktop/satellite-collision
   python -m src.simulation
   # Opens at http://localhost:5000
   ```

2. **Navigate to Visualizations**
   - Main dashboard loads with 3D globe visible
   - Click **Conjunctions** button in viewport controls to toggle visibility

## What to Look For

### Critical Collision Pair (CUBE_0002 ↔ COMSAT_0003)

#### Visual Elements
✅ **Bright Red Connecting Line**
- Solid line between the two objects
- Glows brightly (additive blending)
- Clearly distinguishable from background

✅ **Pulsing Glow Spheres**
- Each object surrounded by expanding/contracting red sphere
- Pulses at ~4 Hz (fast, eye-catching)
- Visible from all camera angles

✅ **Expanding Pulse Ring**
- Large ring centered between the two objects
- Expands and fades rhythmically
- Draws attention to the collision point

✅ **Rotating Central Marker**
- Bright octahedron at midpoint
- Rotates continuously
- Scales pulse in sync with other elements

✅ **Red Orbit Paths**
- Both objects' orbits rendered in bright red (#ff2d55)
- Much more prominent than background orbits
- Nearly opaque (0.9 opacity)

### Background Elements (Faded)

✅ **Dimmed Background Orbits**
- Standard orbit colors (cyan, purple, etc.) but very dim
- Opacity reduced to 0.08-0.12 (85-95% darker)
- Creates clear visual hierarchy

✅ **Subtle Background Conjunctions**
- Dashed lines with low opacity
- Small, faint markers
- Don't distract from critical pair

## Interactive Testing

### Camera Controls
- **Rotate**: Click and drag
- **Zoom**: Scroll wheel
- **Pan**: Right-click and drag (or Ctrl+click on Mac)

### Viewport Controls
Click buttons in top-left of viewport:
- ⭕ **Orbits**: Toggle all orbit paths
- 🔵 **Spacecraft**: Toggle satellite markers
- ⚠️ **Conjunctions**: Toggle conjunction lines/markers (keep ON to see critical pair)
- ✦ **Debris**: Toggle debris particles
- ◯ **Shells**: Toggle altitude shell rings
- ↻ **Auto-rotate**: Enable smooth camera rotation
- 🏠 **Reset**: Return to default camera position

### Demo Sequence

1. **Initial View** (30 seconds)
   - Start with auto-rotate OFF
   - Default camera shows constellation
   - Clearly see red orbit pair stands out
   - Red connecting line obvious

2. **Dramatic Zoom** (20 seconds)
   - Click on the critical conjunction in left panel ("CUBE_0002 ↔ COMSAT_0003")
   - Camera smoothly animates toward collision pair
   - Pulsing glows become dominant visual elements
   - Rotating marker becomes clear

3. **Full Rotation** (30 seconds)
   - Enable auto-rotate
   - Watch as scene rotates around collision pair
   - Notice visibility is maintained from all angles
   - Background dims appropriately

4. **Context View** (20 seconds)
   - Click Reset button
   - Auto-rotate still enabled
   - Shows full constellation with critical pair highlighted
   - Emphasizes needle-in-haystack problem

## Visual Quality Checklist

### Critical Pair Should Have:
- [ ] Bright solid red connecting line
- [ ] Two pulsing glow spheres (one per object)
- [ ] Large expanding pulse ring at midpoint
- [ ] Rotating octahedron marker
- [ ] Bright red orbit paths
- [ ] Glows visible from all angles

### Background Should Have:
- [ ] Dimmed, subtle conjunction lines
- [ ] Small, faint markers for other conjunctions
- [ ] Faded orbit paths (visible but recessive)
- [ ] Clear visual hierarchy

### Performance Should Be:
- [ ] Smooth 60 FPS
- [ ] No stuttering during animations
- [ ] No flickering
- [ ] Camera controls responsive

## Troubleshooting

### Collision Pair Not Visible
**Cause**: Conjunctions button toggled off
**Fix**: Click ⚠️ Conjunctions button to enable

### Red Orbits Not Showing
**Cause**: Orbits button toggled off
**Fix**: Click ⭕ Orbits button to enable

### Glows Look Too Faint
**Cause**: Screen brightness low
**Fix**: Increase monitor brightness; glows use additive blending

### Performance Stuttering
**Cause**: Too many elements rendered
**Fix**: Disable debris (✦ button) or debris shells to reduce draw calls

## Judge Feedback Points

When demonstrating to judges, emphasize:

1. **Immediate Clarity**
   - "See this bright red pair? That's the collision threat"
   - No need to explain; visually obvious

2. **Pulsing Animation**
   - "The animations draw attention without being distracting"
   - Shows the threat is active/urgent

3. **Visual Hierarchy**
   - "Notice how everything else fades away"
   - Demonstrates intelligent focus

4. **Real-time Responsiveness**
   - Show camera controls working smoothly
   - Demonstrates reactive system

5. **Context**
   - "One critical pair among 1000+ objects"
   - Shows the AI's filtering/prioritization capability

## Technical Details for Developers

### Animation Loops
- All animations use `vizState.animationTime` (incremented each frame)
- No setTimeout/setInterval loops (keeps timing synchronized)
- Frequencies: 4 Hz (glows), 3.5 Hz (rings), 3 Hz (markers)

### Rendering
- Uses Three.js LineBasicMaterial and MeshBasicMaterial
- Additive blending for glows (THREE.AdditiveBlending)
- No post-processing shaders
- Geometry is static; only animations are material properties

### Color Values
- Critical pair red: `0xff2d55` (#ff2d55)
- Background cyan: `0x00d4ff` (#00d4ff)
- Background purple: `0x7b2ff7` (#7b2ff7)
- All use 8-bit sRGB color space

## Debug Mode

To enable console logging (if needed):
```javascript
// Add to app.js animate() function
if (vizState.animationTime % 100 < 1) {
    console.log('Critical pair glows:', simPlayer.obj1Mesh?.position);
}
```

## Video Recording Tips

If recording the demo:
1. Use 1440p resolution for clarity
2. 60 FPS capture
3. Start with slow camera rotation (auto-rotate)
4. Zoom in to show details
5. The red highlights should be clearly visible even when compressed to H.264
