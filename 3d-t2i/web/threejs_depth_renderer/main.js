import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

class DepthRenderer {
    constructor() {
        this.scene = null;
        this.camera = null;
        this.renderer = null;
        this.depthRenderer = null;
        this.controls = null;
        this.objects = new Map();

        this.rgbCanvas = document.getElementById('rgb-canvas');
        this.depthCanvas = document.getElementById('depth-canvas');
        this.status = document.getElementById('status');

        this.init();
    }

    init() {
        // Create scene
        this.scene = new THREE.Scene();
        this.scene.background = new THREE.Color(0x1a1a2e);

        // Create camera
        this.camera = new THREE.PerspectiveCamera(50, 1, 0.1, 1000);
        this.camera.position.set(8, 3, 8);

        // Create RGB renderer
        this.renderer = new THREE.WebGLRenderer({
            canvas: this.rgbCanvas,
            antialias: true,
            preserveDrawingBuffer: true
        });
        this.renderer.setSize(1024, 1024);
        this.renderer.shadowMap.enabled = true;

        // Create depth renderer
        this.depthRenderer = new THREE.WebGLRenderer({
            canvas: this.depthCanvas,
            antialias: false
        });
        this.depthRenderer.setSize(1024, 1024);

        // Add orbit controls
        this.controls = new OrbitControls(this.camera, this.rgbCanvas);
        this.controls.enableDamping = true;
        this.controls.dampingFactor = 0.05;

        // Setup depth material
        this.setupDepthMaterial();

        // Add lights
        this.setupLights();

        // Start render loop
        this.animate();

        this.updateStatus('Initialized - Ready to load scene');
    }

    setupDepthMaterial() {
        // Custom shader for depth visualization
        this.depthMaterial = new THREE.ShaderMaterial({
            vertexShader: `
                varying vec2 vUv;
                varying float vDepth;
                void main() {
                    vUv = uv;
                    vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
                    vDepth = -mvPosition.z;
                    gl_Position = projectionMatrix * mvPosition;
                }
            `,
            fragmentShader: `
                varying vec2 vUv;
                varying float vDepth;
                void main() {
                    // Normalize depth to 0-1 range (adjust near/far as needed)
                    float near = 0.1;
                    float far = 50.0;
                    float normalizedDepth = (vDepth - near) / (far - near);
                    normalizedDepth = clamp(normalizedDepth, 0.0, 1.0);

                    // Invert so near is white (for ControlNet convention)
                    float depthValue = 1.0 - normalizedDepth;

                    gl_FragColor = vec4(vec3(depthValue), 1.0);
                }
            `,
            side: THREE.DoubleSide
        });
    }

    setupLights() {
        // Ambient light
        const ambientLight = new THREE.AmbientLight(0xffffff, 0.5);
        this.scene.add(ambientLight);

        // Directional light
        const dirLight = new THREE.DirectionalLight(0xffffff, 0.7);
        dirLight.position.set(5, 10, 5);
        dirLight.castShadow = true;
        this.scene.add(dirLight);
    }

    clearScene() {
        // Remove all objects except lights
        const objectsToRemove = [];
        this.scene.traverse((child) => {
            if (child.isMesh && !child.userData.isLight) {
                objectsToRemove.push(child);
            }
        });

        objectsToRemove.forEach(obj => {
            obj.geometry.dispose();
            if (obj.material) obj.material.dispose();
            this.scene.remove(obj);
        });

        this.objects.clear();
    }

    loadScene(sceneData) {
        this.clearScene();
        this.updateStatus('Loading scene...');

        try {
            // Set camera
            if (sceneData.camera) {
                const cam = sceneData.camera;
                this.camera.position.set(...cam.position);
                this.camera.fov = cam.fov || 50;
                this.camera.updateProjectionMatrix();

                // Set target for controls
                if (cam.target) {
                    this.controls.target.set(...cam.target);
                    this.controls.update();
                }
            }

            // Set lighting
            if (sceneData.lighting) {
                this.updateLighting(sceneData.lighting);
            }

            // Create objects
            if (sceneData.objects) {
                sceneData.objects.forEach(objData => {
                    this.createObject(objData);
                });
            }

            this.updateStatus(`Scene loaded - ${sceneData.objects?.length || 0} objects`);
        } catch (error) {
            this.updateStatus(`Error: ${error.message}`);
            console.error(error);
        }
    }

    createObject(objData) {
        const { id, type, position, size, rotation, color } = objData;

        let geometry;

        // Create geometry based on type
        switch (type) {
            case 'box':
                geometry = new THREE.BoxGeometry(size[0], size[1], size[2]);
                break;
            case 'plane':
                geometry = new THREE.PlaneGeometry(size[0], size[2]);
                break;
            case 'sphere':
                geometry = new THREE.SphereGeometry(size[0] / 2, 32, 16);
                break;
            case 'cylinder':
                geometry = new THREE.CylinderGeometry(size[0], size[0], size[1], 32);
                break;
            default:
                // Default to box
                geometry = new THREE.BoxGeometry(size[0], size[1], size[2]);
        }

        // Create material
        const material = new THREE.MeshStandardMaterial({
            color: color || '#cccccc',
            roughness: 0.7,
            metalness: 0.1
        });

        // Create mesh
        const mesh = new THREE.Mesh(geometry, material);

        // Set position
        mesh.position.set(position[0], position[1], position[2]);

        // Set rotation
        if (rotation) {
            mesh.rotation.set(rotation[0], rotation[1], rotation[2]);
        }

        // Enable shadows
        mesh.castShadow = true;
        mesh.receiveShadow = true;

        // Store reference
        mesh.userData.id = id;
        this.objects.set(id, mesh);
        this.scene.add(mesh);
    }

    updateLighting(lighting) {
        // Update ambient light
        const ambient = this.scene.children.find(c => c.isAmbientLight);
        if (ambient && lighting.ambient) {
            ambient.color.set(lighting.ambient.color);
            ambient.intensity = lighting.ambient.intensity;
        }

        // Update directional light
        const dirLight = this.scene.children.find(c => c.isDirectionalLight);
        if (dirLight && lighting.directional) {
            dirLight.color.set(lighting.directional.color);
            dirLight.intensity = lighting.directional.intensity;
            if (lighting.directional.position) {
                dirLight.position.set(...lighting.directional.position);
            }
        }
    }

    render() {
        // Render RGB view
        this.renderer.render(this.scene, this.camera);

        // Render depth view
        const originalMaterials = new Map();

        // Swap to depth material
        this.scene.traverse((child) => {
            if (child.isMesh) {
                originalMaterials.set(child, child.material);
                child.material = this.depthMaterial;
            }
        });

        // Render depth
        this.depthRenderer.render(this.scene, this.camera);

        // Restore original materials
        originalMaterials.forEach((material, mesh) => {
            mesh.material = material;
        });
    }

    animate() {
        requestAnimationFrame(() => this.animate());
        this.controls.update();
        this.render();
    }

    exportDepthMap() {
        // Force a depth render
        const originalMaterials = new Map();

        this.scene.traverse((child) => {
            if (child.isMesh) {
                originalMaterials.set(child, child.material);
                child.material = this.depthMaterial;
            }
        });

        this.depthRenderer.render(this.scene, this.camera);

        // Export
        const link = document.createElement('a');
        link.download = 'depth_map.png';
        link.href = this.depthCanvas.toDataURL('image/png');
        link.click();

        // Restore
        originalMaterials.forEach((material, mesh) => {
            mesh.material = material;
        });

        this.updateStatus('Depth map exported!');
    }

    exportRGB() {
        const link = document.createElement('a');
        link.download = 'rgb_view.png';
        link.href = this.rgbCanvas.toDataURL('image/png');
        link.click();

        this.updateStatus('RGB view exported!');
    }

    updateStatus(message) {
        this.status.textContent = message;
        console.log(message);
    }
}

// Initialize
const renderer = new DepthRenderer();
const urlParams = new URLSearchParams(window.location.search);
const embeddedMode = urlParams.get('embedded') === '1';

if (embeddedMode) {
    const depthWrapper = document.querySelector('.canvas-wrapper:last-child');
    if (depthWrapper) {
        depthWrapper.style.display = 'none';
    }
    const exportDepthBtn = document.getElementById('export-depth');
    if (exportDepthBtn) {
        exportDepthBtn.style.display = 'none';
    }
    const toggleBtn = document.getElementById('toggle-view');
    if (toggleBtn) {
        toggleBtn.style.display = 'none';
    }

    const header = document.querySelector('.header');
    if (header) {
        header.style.display = 'none';
    }
    const controls = document.querySelector('.controls');
    if (controls) {
        controls.style.display = 'none';
    }
    const info = document.querySelector('.info');
    if (info) {
        info.style.display = 'none';
    }
    const status = document.querySelector('.status');
    if (status) {
        status.style.display = 'none';
    }

    document.body.style.background = 'transparent';
    document.body.style.minHeight = 'auto';
    document.body.style.overflow = 'hidden';

    const canvasContainer = document.querySelector('.canvas-container');
    if (canvasContainer) {
        canvasContainer.style.padding = '0';
        canvasContainer.style.gap = '0';
        canvasContainer.style.justifyContent = 'flex-start';
    }

    const rgbWrapper = document.querySelector('.canvas-wrapper:first-child');
    if (rgbWrapper) {
        rgbWrapper.style.width = '100%';
    }

    const rgbTitle = document.querySelector('.canvas-wrapper:first-child h3');
    if (rgbTitle) {
        rgbTitle.style.display = 'none';
    }

    const rgbCanvas = document.getElementById('rgb-canvas');
    if (rgbCanvas) {
        rgbCanvas.style.border = 'none';
        rgbCanvas.style.width = '100%';
        rgbCanvas.style.height = 'auto';
        rgbCanvas.style.maxHeight = '500px';
        rgbCanvas.style.display = 'block';
    }
}


// Event listeners
document.getElementById('file-input').addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (event) => {
        try {
            const sceneData = JSON.parse(event.target.result);
            renderer.loadScene(sceneData);
        } catch (error) {
            renderer.updateStatus(`Error parsing JSON: ${error.message}`);
        }
    };
    reader.readAsText(file);
});

document.getElementById('export-depth').addEventListener('click', () => {
    renderer.exportDepthMap();
});

document.getElementById('export-rgb').addEventListener('click', () => {
    renderer.exportRGB();
});

document.getElementById('toggle-view').addEventListener('click', () => {
    // Toggle between RGB-only, Depth-only, and Both views
    const rgbWrapper = document.querySelector('.canvas-wrapper:first-child');
    const depthWrapper = document.querySelector('.canvas-wrapper:last-child');

    // Get current state
    const rgbVisible = rgbWrapper.style.display !== 'none';
    const depthVisible = depthWrapper.style.display !== 'none';

    if (rgbVisible && depthVisible) {
        // Both visible -> show only RGB
        rgbWrapper.style.display = 'block';
        depthWrapper.style.display = 'none';
        renderer.updateStatus('View: RGB only');
    } else if (rgbVisible && !depthVisible) {
        // RGB only -> show only Depth
        rgbWrapper.style.display = 'none';
        depthWrapper.style.display = 'block';
        renderer.updateStatus('View: Depth only');
    } else {
        // Depth only or any other state -> show both
        rgbWrapper.style.display = 'block';
        depthWrapper.style.display = 'block';
        renderer.updateStatus('View: RGB + Depth');
    }
});

function emitRGBSnapshot() {
    if (window.parent === window) {
        return;
    }
    try {
        renderer.render();
        const dataUrl = renderer.rgbCanvas.toDataURL('image/png');
        window.parent.postMessage({ type: 'rgb_snapshot', dataUrl }, window.location.origin);
    } catch (error) {
        renderer.updateStatus(`Failed to export snapshot: ${error.message}`);
    }
}

window.addEventListener('message', (event) => {
    if (event.origin !== window.location.origin) {
        return;
    }

    const payload = event.data;
    if (!payload) {
        return;
    }

    if (payload.type === 'load_scene_data' && payload.scene_data) {
        try {
            renderer.loadScene(payload.scene_data);
            renderer.updateStatus('Scene loaded from parent page');
            if (embeddedMode) {
                setTimeout(emitRGBSnapshot, 350);
            }
        } catch (error) {
            renderer.updateStatus(`Failed to load parent scene: ${error.message}`);
        }
        return;
    }

    if (payload.type === 'export_rgb_snapshot') {
        setTimeout(emitRGBSnapshot, 120);
    }
});

// ========== 自动加载 scene.json ==========

// 1. 从 URL 参数加载
const sceneUrl = urlParams.get('scene');
if (sceneUrl) {
    renderer.updateStatus('Loading scene from URL...');
    fetch(sceneUrl)
        .then(r => r.json())
        .then(data => renderer.loadScene(data))
        .catch(e => renderer.updateStatus(`Failed to load scene: ${e.message}`));
}

// 2. 尝试自动加载本地 scene.json
async function tryAutoLoadScene() {
    // 尝试多个可能的路径
    const possiblePaths = [
        './scene.json',                          // 同目录
        '../../data/outputs/scene.json',         // 相对项目根目录
        '../data/outputs/scene.json',            // 另一种相对路径
        '/data/outputs/scene.json',              // 绝对路径
    ];

    // 如果 URL 已经指定了 scene，跳过自动加载
    if (sceneUrl) return;

    renderer.updateStatus('Looking for scene.json...');

    for (const path of possiblePaths) {
        try {
            const response = await fetch(path, { method: 'HEAD' });
            if (response.ok) {
                renderer.updateStatus(`Found scene.json at ${path}, loading...`);
                const dataResponse = await fetch(path);
                const sceneData = await dataResponse.json();
                renderer.loadScene(sceneData);
                return;
            }
        } catch (e) {
            // 继续尝试下一个路径
        }
    }

    renderer.updateStatus('No scene.json found. Please load manually or generate one.');
}

// 页面加载完成后尝试自动加载
window.addEventListener('load', () => {
    // 延迟一点执行，确保其他初始化完成
    setTimeout(tryAutoLoadScene, 500);
});
